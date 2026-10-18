package local.sovereigntv

import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test

/** Changes the Home role only on the dedicated emulator, restoring it in finally. */
@OptIn(ExperimentalTestApi::class)
class LabHomeRuntimeTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    private fun shell(command: String): String = android.os.ParcelFileDescriptor.AutoCloseInputStream(
        instrumentation.uiAutomation.executeShellCommand(command)).bufferedReader().use { it.readText() }

    @Test fun systemHomeReturnsFromAnotherAppWithoutReplacingTheHomeTask() {
        assumeTrue("Home-role mutation is emulator-only", Build.HARDWARE in setOf("ranchu", "goldfish"))
        val context = instrumentation.targetContext
        val pm = context.packageManager
        val homeIntent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
        val previous = requireNotNull(pm.resolveActivity(homeIntent, PackageManager.MATCH_DEFAULT_ONLY)?.activityInfo)
        val previousHome = ComponentName(previous.packageName, previous.name).flattenToString()
        require(Regex("[A-Za-z0-9_.$]+/[A-Za-z0-9_.$]+").matches(previousHome))
        require(previous.packageName != "android" && previous.packageName != context.packageName)
        val alias = ComponentName(context, "local.sovereigntv.LabHome")
        val priorEnabled = pm.getComponentEnabledSetting(alias)
        val originalActivity = compose.activity
        fun originalResumed(): Boolean {
            var resumed = false
            instrumentation.runOnMainSync {
                resumed = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).contains(originalActivity)
            }
            return resumed
        }
        val document = context.assets.open("storybook.json").bufferedReader().use { it.readText() }
        ExperienceRepository(context).import(document)
        compose.runOnIdle { androidx.lifecycle.ViewModelProvider(originalActivity)[ExperienceViewModel::class.java].refreshSaved() }
        val expected = Experience.parse(document)
        compose.waitUntil(10000) { androidx.lifecycle.ViewModelProvider(originalActivity)[ExperienceViewModel::class.java].experience == expected }
        compose.waitUntil(10000) { compose.onAllNodesWithTag("storybook-tile:film_balto").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("storybook-tile:film_balto").performSemanticsAction(androidx.compose.ui.semantics.SemanticsActions.RequestFocus) { it() }
        compose.onNodeWithTag("storybook-tile:film_balto").performKeyInput { pressKey(Key.DirectionRight) }
        compose.onNodeWithTag("storybook-tile:film_little_mermaid").assertIsFocused()
        try {
            pm.setComponentEnabledSetting(alias, PackageManager.COMPONENT_ENABLED_STATE_ENABLED, PackageManager.DONT_KILL_APP)
            shell("cmd package set-home-activity --user 0 ${alias.flattenToString()}")
            assertEquals(context.packageName, pm.resolveActivity(homeIntent, PackageManager.MATCH_DEFAULT_ONLY)?.activityInfo?.packageName)
            repeat(3) {
                // The separate-UID synthetic app has no provider account or media session.
                assertTrue(shell("am start -W -n local.sovereigntv.controlprobe/.TvFixtureActivity").contains("Status: ok"))
                assertFalse("Synthetic app must actually leave Home", originalResumed())
                shell("input keyevent KEYCODE_HOME")
                compose.waitUntil(10000) { originalResumed() }
                compose.onNodeWithTag("storybook-tile:film_little_mermaid").assertIsFocused().assertIsDisplayed()
            }
        } finally {
            shell("cmd package set-home-activity --user 0 $previousHome")
            pm.setComponentEnabledSetting(alias, priorEnabled, PackageManager.DONT_KILL_APP)
            assertEquals(previousHome, pm.resolveActivity(homeIntent, PackageManager.MATCH_DEFAULT_ONLY)?.activityInfo?.let {
                ComponentName(it.packageName, it.name).flattenToString()
            })
        }
    }
}
