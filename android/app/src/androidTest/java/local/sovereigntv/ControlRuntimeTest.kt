package local.sovereigntv

import android.app.Activity
import android.app.ActivityManager
import android.app.Instrumentation.ActivityResult
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PermissionInfo
import android.database.sqlite.SQLiteDatabase
import android.net.Uri
import android.os.Bundle
import android.os.IBinder
import android.os.Parcel
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.File
import java.io.RandomAccessFile
import java.util.UUID
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class ControlRuntimeTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private val connected = LinkedBlockingQueue<IExperienceControl>()
    private lateinit var control: IExperienceControl
    private var bound = false
    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, binder: IBinder) { connected.offer(IExperienceControl.Stub.asInterface(binder)) }
        override fun onServiceDisconnected(name: ComponentName) { }
    }
    private fun expiry() = System.currentTimeMillis() + 10000
    private fun id() = UUID.randomUUID().toString()
    private fun json(bundle: Bundle): JSONObject { assertEquals("ok", bundle.getString("status")); return JSONObject(bundle.getString("json")!!) }
    private fun state() = json(control.state(expiry()))
    private fun waitFor(text: String) = compose.waitUntil(10000) { compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty() }
    private fun activate(text: String) {
        compose.onNodeWithText(text).performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        compose.onNodeWithText(text).performKeyInput { pressKey(Key.DirectionCenter) }
    }
    @Before fun bindAndReset() {
        Intents.init(); waitFor("Settings")
        bound = context.bindService(Intent(context, ExperienceControlService::class.java), connection, Context.BIND_AUTO_CREATE)
        assertTrue(bound)
        control = requireNotNull(connected.poll(10, TimeUnit.SECONDS))
        assertNull(control.asBinder().queryLocalInterface("local.sovereigntv.IExperienceControl")) // Real IPC, not a local Stub shortcut.
        val current = state()
        val doc = context.assets.open("experience.json").bufferedReader().use { it.readText() }
        json(control.apply(id(), current.getLong("revision"), doc, expiry()))
        waitFor("Household TV")
    }
    @After fun release() { if (bound) context.unbindService(connection); Intents.release() }

    @Test fun discoverOwnerChosenAppApplyAndLaunchThroughPhysicalNavigation() {
        val before = state()
        val catalog = json(control.applications(expiry()))
        assertEquals(catalog.toString(), json(control.applications(expiry())).toString())
        assertEquals(before.toString(), state().toString())
        val applications = catalog.getJSONArray("applications")
        assertTrue(applications.length() <= TvApplications.MAX_APPLICATIONS)
        assertEquals(ExperienceJournal.sha256(applications.toString()), catalog.getString("catalog_sha256"))
        assertFalse(catalog.getBoolean("launch_is_playback_qualification"))
        val entries = (0 until applications.length()).map { applications.getJSONObject(it) }
        val chosen = entries.single { it.getString("title") == "Synthetic TV app" }
        val component = ComponentName("local.sovereigntv.controlprobe", "local.sovereigntv.controlprobe.TvFixtureActivity")
        val target = chosen.getString("target")
        assertEquals(TvApplications.target(component), target)
        assertTrue(Regex("app_[a-f0-9]{60}").matches(target))
        for (name in listOf("PrivateTv", "DisabledTv", "ProtectedTv")) {
            val denied = TvApplications.target(ComponentName(component.packageName, component.packageName + "." + name))
            assertTrue(entries.none { it.getString("target") == denied })
        }
        assertTrue(entries.none { it.getString("target") == TvApplications.target(ComponentName(context, MainActivity::class.java)) })
        assertEquals("expired", control.applications(System.currentTimeMillis() - 1).getString("status"))
        val document = JSONObject(before.getString("document"))
        document.getJSONArray("sections").getJSONObject(0).getJSONArray("items").getJSONObject(0)
            .put("target", target).put("title", "Owner selected app")
        json(control.apply(id(), before.getLong("revision"), document.toString(), expiry()))
        waitFor("Owner selected app")
        intending(androidx.test.espresso.intent.matcher.IntentMatchers.hasComponent(component)).respondWith(ActivityResult(Activity.RESULT_OK, null))
        activate("Owner selected app")
        compose.waitUntil(10000) { Intents.getIntents().any { it.component == component } }
        androidx.test.espresso.intent.Intents.intended(androidx.test.espresso.intent.matcher.IntentMatchers.hasComponent(component))
        assertEquals(before.getLong("revision") + 1, state().getLong("revision"))
        val probe = Uri.parse("content://local.sovereigntv.controlprobe")
        try {
            context.contentResolver.call(probe, "disable-tv-fixture", null, null)
            compose.waitUntil(10000) { compose.onAllNodes(hasText("Owner selected app") and hasText("NOT INSTALLED")).fetchSemanticsNodes().isNotEmpty() }
            val changed = json(control.applications(expiry())).getJSONArray("applications")
            assertTrue((0 until changed.length()).none { changed.getJSONObject(it).getString("target") == target })
            activate("Owner selected app")
            waitFor("No installed TV activity found for Owner selected app")
        } finally { context.contentResolver.call(probe, "enable-tv-fixture", null, null) }
        compose.waitUntil(10000) { compose.onAllNodes(hasText("Owner selected app") and hasText("INSTALLED")).fetchSemanticsNodes().isNotEmpty() }
        document.getJSONArray("sections").getJSONObject(0).getJSONArray("items").getJSONObject(0)
            .put("target", "app_" + "f".repeat(60)).put("title", "Unavailable app")
        json(control.apply(id(), before.getLong("revision") + 1, document.toString(), expiry()))
        waitFor("Unavailable app")
        activate("Unavailable app")
        waitFor("No installed TV activity found for Unavailable app")
    }

    @Test fun crossProcessEditReceiptRestartAndUndoUpdateVisibleHome() {
        val initial = state(); val before = initial.getLong("revision")
        val document = initial.getString("document").replace("Household TV", "Agent evening")
        val capabilities = json(control.capabilities(expiry()))
        assertTrue(capabilities.getBoolean("receipt_operation_sha256"))
        assertFalse(capabilities.getBoolean("network_endpoint")); assertFalse(capabilities.getBoolean("agentos_qualified"))
        assertFalse(json(control.preview(before, document, expiry())).getBoolean("saved"))
        assertEquals(before, state().getLong("revision"))
        compose.onNodeWithText("Agent evening").assertDoesNotExist()
        val request = id()
        val receipt = json(control.apply(request, before, document, expiry())).getJSONObject("receipt")
        waitFor("Agent evening")
        assertEquals(before + 1, receipt.getLong("revision"))
        assertEquals(ExperienceJournal.sha256("apply:$before:${ExperienceJournal.sha256(document)}"), receipt.getString("operation_sha256"))
        assertEquals(receipt.toString(), json(control.apply(request, before, document, expiry())).getJSONObject("receipt").toString())
        assertEquals("conflict", control.apply(request, before, document + " ", expiry()).getString("status"))
        val process = context.getSystemService(ActivityManager::class.java).runningAppProcesses.single { it.processName == context.packageName + ":domain" }
        assertNotEquals(android.os.Process.myPid(), process.pid)
        android.os.Process.killProcess(process.pid) // Dedicated test app's domain process only.
        control = requireNotNull(connected.poll(15, TimeUnit.SECONDS))
        assertEquals(receipt.toString(), json(control.receipt(request, expiry())).toString())
        assertEquals(document, state().getString("document"))
        val undoReceipt = json(control.undo(id(), before + 1, before, expiry())).getJSONObject("receipt")
        assertEquals(ExperienceJournal.sha256("undo:${before + 1}:$before"), undoReceipt.getString("operation_sha256"))
        waitFor("Household TV")
    }

    @Test fun unpermittedProcessCannotBindOrUseForwardedHandle() {
        @Suppress("DEPRECATION") val permission = context.packageManager.getPermissionInfo(ExperienceControlService.PERMISSION, 0)
        assertEquals(PermissionInfo.PROTECTION_SIGNATURE, permission.protectionLevel and PermissionInfo.PROTECTION_MASK_BASE)
        val result = context.contentResolver.call(Uri.parse("content://local.sovereigntv.test.fixture"), "bridge-denials", null,
            Bundle().apply { putBinder("forwarded", control.asBinder()) })!!
        assertTrue(result.getBoolean("different_uid"))
        assertTrue(result.getBoolean("bind_denied"))
        assertTrue(result.getBoolean("forwarded_handle_denied"))
        assertTrue(result.getBoolean("probe_denied"))
    }

    @Test fun invalidAndExpiredRequestsNeverChangeStateIncludingWriterWait() {
        val initial = state(); val before = initial.getLong("revision"); val document = initial.getString("document")
        assertEquals("expired", control.apply(id(), before, document, System.currentTimeMillis() - 1).getString("status"))
        assertEquals("invalid", control.state(System.currentTimeMillis() + 60000).getString("status"))
        assertEquals("invalid", control.state(Long.MIN_VALUE).getString("status"))
        assertEquals("invalid", control.apply(id(), before, "{", expiry()).getString("status"))
        assertEquals("invalid", control.apply(id(), before, "x".repeat(65537), expiry()).getString("status"))
        assertEquals("invalid", control.apply(null, before, document, expiry()).getString("status"))
        assertEquals("invalid", control.preview(before, null, expiry()).getString("status"))
        for (suffix in listOf(0xD800.toChar().toString(), 0xD801.toChar().toString(), "\\ud800")) {
            val badId = id()
            assertEquals("invalid", control.apply(badId, before, document.replace("Household TV", "Bad " + suffix), expiry()).getString("status"))
            assertEquals("not_found", control.receipt(badId, expiry()).getString("status"))
        }
        assertEquals("not_found", control.receipt(id(), expiry()).getString("status"))
        val request = id()
        val pool = Executors.newSingleThreadExecutor()
        val db = SQLiteDatabase.openDatabase(context.getDatabasePath("experience-journal.sqlite3").absolutePath, null, SQLiteDatabase.OPEN_READWRITE)
        try {
            db.beginTransaction()
            val future = pool.submit<Bundle> { control.apply(request, before, document.replace("Household TV", "Too late"), System.currentTimeMillis() + 1000) }
            SystemClock.sleep(200); assertFalse(future.isDone)
            SystemClock.sleep(1100)
            db.endTransaction()
            assertEquals("expired", future.get(10, TimeUnit.SECONDS).getString("status"))
        } finally {
            if (db.inTransaction()) db.endTransaction()
            db.close(); pool.shutdownNow()
        }
        assertEquals(before, state().getLong("revision"))
        assertEquals("not_found", control.receipt(request, expiry()).getString("status"))
        val calls = java.util.concurrent.atomic.AtomicInteger()
        assertThrows(IllegalStateException::class.java) {
            ExperienceRepository(context).apply(id(), before, document) { if (calls.incrementAndGet() == 2) error("Synthetic pre-write deadline") }
        }
        assertEquals(2, calls.get()); assertEquals(before, state().getLong("revision"))
    }

    @Test fun boundedArtworkDescriptorsAndHashIntegrityRoundTrip() {
        val bytes = FixtureProvider.png(77,133,201); val digest = ExperienceJournal.sha256Bytes(bytes)
        val file = File(context.cacheDir, "control-fixture.png").apply { writeBytes(bytes) }
        fun upload(hash: String): Bundle = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { control.putArtwork(hash, it, expiry()) }
        assertEquals("invalid", upload("0".repeat(64)).getString("status"))
        json(upload(digest)); json(upload(digest))
        val opened = control.openArtwork(digest, expiry()); json(opened)
        @Suppress("DEPRECATION") val descriptor = opened.getParcelable<ParcelFileDescriptor>("file")!!
        ParcelFileDescriptor.AutoCloseInputStream(descriptor).use { assertArrayEquals(bytes, it.readBytes()) }
        val malformed = bytes.copyOf()
        val compressedSize = java.nio.ByteBuffer.wrap(malformed, 33, 4).int
        malformed[41] = 0 // Invalid zlib header with a correct PNG chunk CRC.
        val crc = java.util.zip.CRC32().apply { update(malformed, 37, compressedSize + 4) }
        java.nio.ByteBuffer.wrap(malformed, 41 + compressedSize, 4).putInt(crc.value.toInt())
        file.writeBytes(malformed)
        assertEquals("invalid", upload(ExperienceJournal.sha256Bytes(malformed)).getString("status"))
        file.writeBytes(bytes)
        val pipe = ParcelFileDescriptor.createPipe()
        try { assertEquals("invalid", control.putArtwork(digest, pipe[0], expiry()).getString("status")) }
        finally { pipe.forEach { it.close() } }
        RandomAccessFile(file, "rw").use { it.setLength(ArtworkStore.MAX_BYTES + 1L) }
        assertEquals("invalid", upload(digest).getString("status"))
        file.delete()
        val current = state()
        val document = Experience.withArtwork(current.getString("document"), digest)
        json(control.apply(id(), current.getLong("revision"), document, expiry()))
        activate("Local artwork"); waitFor("Local artwork 1")
        activate("Local artwork 1")
        compose.waitUntil(10000) { compose.onAllNodesWithTag("artwork-image").fetchSemanticsNodes().isNotEmpty() }
    }

    @Test fun externalEditPreservesManualPreviewThenRefusesStaleApply() {
        intending(hasAction(Intent.ACTION_OPEN_DOCUMENT)).respondWith(ActivityResult(Activity.RESULT_OK,
            Intent().setData(Uri.parse("content://local.sovereigntv.test.fixture/valid"))))
        activate("Settings"); activate("Import experience"); waitFor("Runtime household")
        val current = state()
        val document = current.getString("document").replace("Household TV", "Agent saved")
        val revision = json(control.apply(id(), current.getLong("revision"), document, expiry())).getJSONObject("receipt").getLong("revision")
        waitFor("Experience changed; reload saved before editing")
        compose.onNodeWithText("Runtime household").assertExists()
        activate("Apply preview")
        waitFor("Agent saved")
        assertEquals(revision, state().getLong("revision"))
        assertEquals(document, state().getString("document"))
    }
    @Test fun concurrentWritersHaveOneWinnerAndDefaultRestoreIsIdempotent() {
        val initial = state(); val before = initial.getLong("revision")
        val requests = listOf(id(), id())
        val pool = Executors.newFixedThreadPool(2)
        val start = java.util.concurrent.CountDownLatch(1)
        try {
            val writes = requests.mapIndexed { index, request -> pool.submit<Bundle> {
                start.await()
                control.apply(request, before, initial.getString("document").replace("Household TV", "Writer $index"), expiry())
            } }
            start.countDown()
            val responses = writes.map { it.get(10, TimeUnit.SECONDS) }
            assertEquals(listOf("conflict", "ok"), responses.map { it.getString("status")!! }.sorted())
            val winner = responses.indexOfFirst { it.getString("status") == "ok" }
            waitFor("Writer $winner")
            assertEquals(before + 1, state().getLong("revision"))
            assertEquals("not_found", control.receipt(requests[1 - winner], expiry()).getString("status"))
            val reset = id()
            val receipt = json(control.restoreDefault(reset, before + 1, expiry())).getJSONObject("receipt")
            waitFor("Household TV")
            assertEquals(before + 2, receipt.getLong("revision"))
            assertEquals(receipt.toString(), json(control.restoreDefault(reset, before + 1, expiry())).getJSONObject("receipt").toString())
            assertEquals(before + 2, state().getLong("revision"))
        } finally { pool.shutdownNow() }
    }

    @Test fun oneWayTransactionCannotApplyAnUnobservableEffect() {
        val initial = state(); val request = id()
        val data = Parcel.obtain()
        try {
            data.writeInterfaceToken("local.sovereigntv.IExperienceControl")
            data.writeString(request); data.writeLong(initial.getLong("revision"))
            data.writeString(initial.getString("document").replace("Household TV", "Unobservable")); data.writeLong(expiry())
            // Generated AIDL ordinal, without a generated Proxy that would force synchronous transport.
            control.asBinder().transact(IExperienceControl.Stub.TRANSACTION_apply, data, null, IBinder.FLAG_ONEWAY)
        } finally { data.recycle() }
        SystemClock.sleep(300)
        assertEquals(initial.getLong("revision"), state().getLong("revision"))
        assertEquals("not_found", control.receipt(request, expiry()).getString("status"))
    }

    @Test fun ownerSignedSeparateApplicationCanEditReadBackAndRetry() {
        val initial = state()
        val result = context.contentResolver.call(Uri.parse("content://local.sovereigntv.controlprobe"), "roundtrip", null, null)!!
        assertNotEquals(android.os.Process.myUid(), result.getInt("caller_uid"))
        assertTrue(result.getBoolean("remote_domain")); assertTrue(result.getBoolean("read_back"))
        assertTrue(result.getBoolean("durable_retry")); assertTrue(result.getBoolean("restored"))
        assertEquals(initial.getLong("revision") + 2, state().getLong("revision"))
        assertEquals(initial.getString("document"), state().getString("document"))
        waitFor("Household TV")
    }

    @Test fun cancellingManualPreviewReconcilesLatestExternalCommit() {
        intending(hasAction(Intent.ACTION_OPEN_DOCUMENT)).respondWith(ActivityResult(Activity.RESULT_OK,
            Intent().setData(Uri.parse("content://local.sovereigntv.test.fixture/valid"))))
        activate("Settings"); activate("Import experience"); waitFor("Runtime household")
        val current = state()
        val document = current.getString("document").replace("Household TV", "Latest saved home")
        json(control.apply(id(), current.getLong("revision"), document, expiry()))
        waitFor("Experience changed; reload saved before editing")
        activate("Cancel preview")
        waitFor("Latest saved home")
        compose.onNodeWithText("Runtime household").assertDoesNotExist()
        assertEquals(current.getLong("revision") + 1, state().getLong("revision"))
    }

}
