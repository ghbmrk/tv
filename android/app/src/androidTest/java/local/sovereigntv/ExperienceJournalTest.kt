package local.sovereigntv

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

@RunWith(AndroidJUnit4::class)
class ExperienceJournalTest {
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun repository() = ExperienceRepository(context)
    private fun id() = UUID.randomUUID().toString()

    @Test fun previewReceiptRestartConflictAndUndo() {
        val repository = repository()
        val before = repository.load()
        val document = before.document.replace(before.experience.title, "Journal household")
        assertEquals("Journal household", repository.preview(before.revision, document).experience.title)
        assertEquals(before, repository().load())
        val request = id()
        val receipt = repository.apply(request, before.revision, document)
        assertEquals(receipt, repository().receipt(request))
        assertEquals(receipt, repository().apply(request, before.revision, document))
        assertEquals(receipt.revision, repository().load().revision)
        assertThrows(ExperienceJournal.Conflict::class.java) { repository.apply(request, before.revision, before.document) }
        assertThrows(ExperienceJournal.Conflict::class.java) { repository.apply(id(), before.revision, before.document) }
        val undoId = id()
        val undone = repository.undo(undoId, receipt.revision, receipt.previousRevision)
        assertEquals(before.document, repository().load().document)
        assertEquals(undone, repository().undo(undoId, receipt.revision, receipt.previousRevision))
        assertThrows(ExperienceJournal.Conflict::class.java) { repository.undo(id(), receipt.revision, receipt.previousRevision) }
    }

    @Test fun concurrentEditorsCannotLoseEachOthersChanges() {
        val before = repository().load()
        val start = CountDownLatch(1)
        val pool = Executors.newFixedThreadPool(2)
        try {
            val results = (1..2).map { index -> pool.submit<Boolean> {
                start.await()
                try {
                    repository().apply(id(), before.revision, before.document.replace(before.experience.title, "Concurrent $index"))
                    true
                } catch (_: ExperienceJournal.Conflict) { false }
            } }
            start.countDown()
            assertEquals(1, results.count { it.get(15, TimeUnit.SECONDS) })
            assertEquals(before.revision + 1, repository().load().revision)
        } finally { pool.shutdownNow() }
    }

    @Test fun invalidDataCannotMutateJournal() {
        val before = repository().load()
        val invalidTheme = org.json.JSONObject(before.document).put("theme", "unsupported").toString()
        for (document in listOf("not JSON", "x".repeat(65537), invalidTheme)) {
            assertThrows(Exception::class.java) { repository().apply(id(), before.revision, document) }
        }
        assertEquals(before, repository().load())
    }

    @Test fun unreadableDocumentCannotBeSilentlyOverwritten() {
        val before = repository().load()
        val database = android.database.sqlite.SQLiteDatabase.openDatabase(context.getDatabasePath("experience-journal.sqlite3").path, null, 0)
        try {
            database.execSQL("UPDATE revisions SET document=? WHERE revision=?", arrayOf<Any>("not JSON", before.revision))
            assertTrue(repository().load().journalUnavailable)
            assertThrows(Exception::class.java) { repository().apply(id(), before.revision, before.document) }
            database.rawQuery("SELECT document FROM revisions WHERE revision=?", arrayOf(before.revision.toString())).use {
                assertTrue(it.moveToFirst()); assertEquals("not JSON", it.getString(0))
            }
        } finally {
            database.execSQL("UPDATE revisions SET document=? WHERE revision=?", arrayOf<Any>(before.document, before.revision))
            database.close()
        }
    }

    @Test fun receiptCapacityRefusesNewEffectsWithoutLosingExistingReceipts() {
        val before = repository().load()
        val requestId = id()
        val receipt = repository().apply(requestId, before.revision, before.document)
        val current = repository().load()
        val database = android.database.sqlite.SQLiteDatabase.openDatabase(context.getDatabasePath("experience-journal.sqlite3").path, null, 0)
        try {
            val count = database.rawQuery("SELECT COUNT(*) FROM receipts", null).use { it.moveToFirst(); it.getInt(0) }
            database.execSQL("WITH RECURSIVE sequence(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM sequence WHERE n < ?) INSERT INTO receipts SELECT 'capacity-fixture-' || n,'synthetic',0,0,'synthetic' FROM sequence", arrayOf(10000 - count))
            assertThrows(ExperienceJournal.Capacity::class.java) { repository().apply(id(), current.revision, current.document) }
            assertEquals(current, repository().load())
            assertEquals(receipt, repository().apply(requestId, before.revision, before.document))
        } finally {
            database.execSQL("DELETE FROM receipts WHERE request_id LIKE 'capacity-fixture-%'")
            database.close()
        }
    }

    @Test fun boundsHistoryWithoutDiscardingReceipts() {
        var state = repository().load()
        val originalRequest = id()
        val originalBase = state.revision
        val originalDocument = state.document
        val originalReceipt = repository().apply(originalRequest, state.revision, state.document)
        repeat(128) {
            state = repository().load()
            repository().apply(id(), state.revision, state.document)
        }
        state = repository().load()
        assertEquals(originalReceipt, repository().apply(originalRequest, originalBase, originalDocument))
        assertThrows(IllegalArgumentException::class.java) { repository().undo(id(), state.revision, originalBase) }
        repository().undo(id(), state.revision, state.revision - 1)
    }

    @Test fun corruptJournalIsPreservedAndEditingFailsClosed() {
        repository().load()
        val database = context.getDatabasePath("experience-journal.sqlite3")
        val backup = database.readBytes()
        try {
            database.writeText("synthetic corrupt journal")
            val fallback = repository().load()
            assertTrue(fallback.journalUnavailable)
            assertEquals(0L, fallback.revision)
            assertEquals("synthetic corrupt journal", database.readText())
            assertThrows(Exception::class.java) { repository().apply(id(), 1, fallback.document) }
            assertEquals("synthetic corrupt journal", database.readText())
        } finally { database.writeBytes(backup) }
    }
}
