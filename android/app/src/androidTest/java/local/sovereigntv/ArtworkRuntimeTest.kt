package local.sovereigntv

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.RandomAccessFile
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class ArtworkRuntimeTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun waitFor(text: String) = compose.waitUntil(10000) { compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty() }
    private fun revealArtwork() {
        if (compose.onAllNodesWithTag("artwork-surface").fetchSemanticsNodes().isNotEmpty() && compose.onAllNodesWithText("Back to collection").fetchSemanticsNodes().isEmpty()) {
            compose.onNodeWithTag("artwork-surface").performKeyInput { pressKey(Key.DirectionCenter) }
            waitFor("Back to collection")
            compose.onNodeWithTag("artwork-image").assertExists()
        }
    }
    private fun activate(text: String) {
        revealArtwork()
        if (text in setOf("Import experience", "Import artwork", "Restore default", "Undo last change") && compose.onAllNodesWithText(text).fetchSemanticsNodes().isEmpty()) {
            compose.onNodeWithText("Settings").performSemanticsAction(SemanticsActions.RequestFocus) { it() }
            compose.onNodeWithText("Settings").performKeyInput { pressKey(Key.DirectionCenter) }
            waitFor(text)
        }
        compose.onNodeWithText(text).performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        compose.onNodeWithText(text).performKeyInput { pressKey(Key.DirectionCenter) }
    }
    @Before fun reset() {
        Intents.init(); useLegacyHome(compose)
    }
    @After fun finish() { Intents.release() }

    @Test fun portablePreviewGalleryNavigationPersistenceAndUndo() {
        intending(hasAction(Intent.ACTION_OPEN_DOCUMENT)).respondWith(ActivityResult(Activity.RESULT_OK,
            Intent().setData(Uri.parse("content://local.sovereigntv.test.fixture/bundle"))))
        activate("Import experience"); waitFor("Runtime gallery")
        assertEquals("Household TV", ExperienceRepository(context).load().experience.title)
        activate("Local artwork"); waitFor("First artwork")
        compose.onNodeWithText("Hidden artwork").assertDoesNotExist()
        activate("First artwork")
        compose.waitUntil(10000) { compose.onAllNodesWithTag("artwork-image").fetchSemanticsNodes().isNotEmpty() }
        activate("Start slideshow"); waitFor("Pause slideshow")
        compose.mainClock.advanceTimeBy(301000)
        revealArtwork()
        waitFor("Second artwork • 2/2 • Unsaved preview")
        compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.STARTED)
        compose.waitForIdle()
        compose.mainClock.advanceTimeBy(301000)
        compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.RESUMED)
        revealArtwork()
        waitFor("Second artwork • 2/2 • Unsaved preview")
        activate("Pause slideshow")
        compose.mainClock.advanceTimeBy(301000)
        compose.onNodeWithText("Back to collection").assertDoesNotExist()
        compose.onNodeWithTag("artwork-image").assertExists()
        revealArtwork()
        compose.onNodeWithText("Second artwork • 2/2 • Unsaved preview").assertExists()
        activate("Previous artwork"); waitFor("First artwork • 1/2 • Unsaved preview")
        activate("Next artwork"); waitFor("Second artwork • 2/2 • Unsaved preview")
        activate("Back to collection"); waitFor("First artwork")
        compose.onNodeWithText("Second artwork").assertIsFocused()
        activate("Apply preview"); waitFor("Imported local experience")
        compose.activityRule.scenario.recreate(); waitFor("First artwork")
        assertEquals("Runtime gallery", ExperienceRepository(context).load().experience.title)
        activate("Back to Home"); waitFor("Runtime gallery")
        activate("Undo last change"); waitFor("Last change undone"); waitFor("Household TV")
    }

    @Test fun manyAssetsAndShortReadsRoundTripWithoutApplying() {
        val repository = ExperienceRepository(context)
        val before = repository.load()
        val root = org.json.JSONObject(before.document).put("schema_version", 2)
        val collections = org.json.JSONArray()
        val output = ByteArrayOutputStream()
        ZipOutputStream(output).use { zip ->
            repeat(3) { group ->
                val items = org.json.JSONArray()
                repeat(43) { index ->
                    val bytes = FixtureProvider.png(group * 43 + index, 80, 160)
                    val id = ExperienceJournal.sha256Bytes(bytes)
                    zip.putNextEntry(ZipEntry("artwork/$id.png")); zip.write(bytes); zip.closeEntry()
                    items.put(org.json.JSONObject().put("id", "image_$index").put("title", "Image $index")
                        .put("kind", "artwork").put("target", id).put("visible", true))
                }
                collections.put(org.json.JSONObject().put("id", if (group == 0) "artwork" else "gallery_$group")
                    .put("title", "Gallery $group").put("items", items))
            }
            root.put("collections", collections)
            zip.putNextEntry(ZipEntry("experience.json")); zip.write(root.toString().toByteArray()); zip.closeEntry()
        }
        val shortReads = object : ByteArrayInputStream(output.toByteArray()) {
            override fun read(bytes: ByteArray, offset: Int, length: Int): Int = super.read(bytes, offset, minOf(length, 1))
        }
        val preview = repository.previewImport(before.revision, shortReads)
        assertEquals(129, preview.experience.artworkRefs.size)
        assertEquals(before.document, repository.load().document)
    }

    @Test fun pngIntegrityPixelsCapacityAndRestart() {
        val bytes = FixtureProvider.png(50,120,180)
        val art = ArtworkStore(context)
        val id = art.import(ByteArrayInputStream(bytes))
        assertEquals(id, art.import(ByteArrayInputStream(bytes)))
        val bitmap = ArtworkStore(context).bitmap(id, 1920, 1080)
        assertEquals(Color.rgb(50,120,180), bitmap.getPixel(0,0)); bitmap.recycle()
        val damaged = bytes.clone().also { it[it.lastIndex - 4] = (it[it.lastIndex - 4].toInt() xor 1).toByte() }
        for (invalid in listOf(damaged, bytes + byteArrayOf(1), "<svg/>".toByteArray()))
            assertThrows(Exception::class.java) { art.import(ByteArrayInputStream(invalid)) }
        val marker = File(context.filesDir, "artwork/" + "0".repeat(64) + ".png")
        try {
            RandomAccessFile(marker, "rw").use { it.setLength(ArtworkStore.MAX_STORE_BYTES + 1) }
            assertEquals(id, art.import(ByteArrayInputStream(bytes)))
            val fresh = FixtureProvider.png(51,121,181)
            assertThrows(Exception::class.java) { art.import(ByteArrayInputStream(fresh)) }
        } finally { marker.delete() }
    }

    @Test fun malformedBundlesAndMissingAssetsPreserveRevision() {
        val repository = ExperienceRepository(context)
        val before = repository.load()
        for (name in listOf("../experience.json", "artwork/../../bad.png", "experience.json")) {
            val output = ByteArrayOutputStream()
            ZipOutputStream(output).use { zip -> zip.putNextEntry(ZipEntry(name)); zip.write("{}".toByteArray()); zip.closeEntry() }
            assertThrows(Exception::class.java) { repository.previewImport(before.revision, ByteArrayInputStream(output.toByteArray())) }
            assertEquals(before.revision, repository.load().revision)
        }
        val missing = Experience.withArtwork(before.document, "a".repeat(64))
        assertThrows(Exception::class.java) { repository.preview(before.revision, missing) }
        assertThrows(Exception::class.java) { repository.apply("missing-artwork", before.revision, missing) }
        assertEquals(before.revision, repository.load().revision)
    }
}
