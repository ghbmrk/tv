package local.sovereigntv.control

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.ComponentName
import android.content.Intent
import android.net.Uri
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class OwnerControlTest {
    @get:Rule val compose = createAndroidComposeRule<ControlActivity>()
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun waitFor(text: String) = compose.waitUntil(10000) { compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty() }
    private fun activate(text: String) {
        compose.onNodeWithText(text).performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        compose.onNodeWithText(text).performKeyInput { pressKey(Key.DirectionCenter) }
    }
    @Before fun setup() {
        Intents.init(); PairedStore(context).revoke()
        waitFor("Refresh local status"); activate("Refresh local status"); waitFor("No agent trusted")
    }
    @After fun close() {
        context.stopService(Intent(context, LocalControlService::class.java)); PairedStore(context).revoke()
        Identity.keyStore().deleteEntry("fixture-owner-client"); Intents.release()
    }
    @Test fun remoteReviewCancelApproveEnableAndRevoke() {
        val certificate = Identity.ensure("fixture-owner-client")
        val uri = Uri.parse("content://local.sovereigntv.control.fixture/certificate")
        context.contentResolver.openOutputStream(uri, "w")!!.use { it.write(certificate.encoded) }
        intending(hasAction(Intent.ACTION_OPEN_DOCUMENT)).respondWith(ActivityResult(Activity.RESULT_OK, Intent().setData(uri)))
        activate("Import agent certificate"); waitFor("Trust this agent")
        assertNull(PairedStore(context).paired())
        compose.onNodeWithText("Cancel").assertIsFocused()
        compose.onRoot().captureToImage().asAndroidBitmap().let { image ->
            val bounds = compose.onNodeWithTag("control-action:Cancel").fetchSemanticsNode().boundsInRoot
            assertEquals(0xffd5e6b4.toInt(), image.getPixel((bounds.left + bounds.width * .12f).toInt(), bounds.center.y.toInt()))
            java.io.File(context.filesDir, "control-owner-proof.png").outputStream().use { image.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }
        }
        activate("Cancel"); waitFor("Certificate not approved"); assertNull(PairedStore(context).paired())
        activate("Import agent certificate"); waitFor("Trust this agent")
        compose.onNodeWithText("Cancel").performKeyInput { pressKey(Key.DirectionLeft) }
        compose.onNodeWithText("Trust this agent").assertIsFocused()
        compose.onNodeWithText("Trust this agent").performKeyInput { pressKey(Key.DirectionCenter) }
        waitFor("Agent trusted • local control remains off")
        assertEquals(Identity.pin(certificate), Identity.pin(PairedStore(context).paired()!!))
        compose.runOnIdle { assertFalse(ControlStatus.active) }
        val address = LocalAddresses.current().first().hostAddress!!
        activate("Enable on $address")
        compose.waitUntil(10000) { ControlStatus.active }
        compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.CREATED)
        assertTrue(ControlStatus.active) // Separate foreground service remains available outside its UI.
        compose.activityRule.scenario.moveToState(androidx.lifecycle.Lifecycle.State.RESUMED)
        activate("Remove agent"); waitFor("Agent removed • existing connections closed")
        assertNull(PairedStore(context).paired())
        compose.waitUntil(10000) { !ControlStatus.active }
        @Suppress("DEPRECATION") val service = context.packageManager.getServiceInfo(ComponentName(context, LocalControlService::class.java), 0)
        assertFalse(service.exported)
    }
}
