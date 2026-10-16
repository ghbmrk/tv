package local.sovereigntv

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intended
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasComponent
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.*
import org.junit.runner.RunWith

@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class HouseholdControlEntryTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private fun activate(text: String) {
        compose.onNodeWithText(text).performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        compose.onNodeWithText(text).performKeyInput { pressKey(Key.DirectionCenter) }
    }
    @Test fun settingsOpensTheDiscoveredOwnerSignedController() {
        useLegacyHome(compose)
        Intents.init()
        try {
            lateinit var model: ExperienceViewModel
            compose.runOnIdle { model = ViewModelProvider(compose.activity)[ExperienceViewModel::class.java] }
            compose.waitUntil(10000) { model.appAvailability("local_control") == "INSTALLED" }
            val component = hasComponent("local.sovereigntv.control.ControlActivity")
            intending(component).respondWith(ActivityResult(Activity.RESULT_CANCELED, null))
            activate("Settings"); activate("Household control")
            intended(component)
        } finally { Intents.release() }
    }
}
