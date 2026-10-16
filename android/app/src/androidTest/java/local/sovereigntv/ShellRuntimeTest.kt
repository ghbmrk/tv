package local.sovereigntv

import android.app.Activity
import android.app.Instrumentation.ActivityResult
import android.content.Intent
import android.net.Uri
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.Intents.intending
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.Assert.*
import java.io.ByteArrayInputStream

@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class ShellRuntimeTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    private fun waitForText(text: String) = compose.waitUntil(10000) {
        compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
    }

    private fun activate(text: String) {
        if (text in setOf("Import experience", "Import artwork", "Restore default", "Undo last change") && compose.onAllNodesWithText(text).fetchSemanticsNodes().isEmpty()) {
            compose.onNodeWithText("Settings").performSemanticsAction(SemanticsActions.RequestFocus) { it() }
            compose.onNodeWithText("Settings").performKeyInput { pressKey(Key.DirectionCenter) }
            waitForText(text)
        }
        compose.onNodeWithText(text).performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        compose.onNodeWithText(text).performKeyInput { pressKey(Key.DirectionCenter) }
    }

    @Before fun reset() {
        Intents.init()
        useLegacyHome(compose)
    }
    @After fun release() { Intents.release() }

    @Test fun dpadFocusSurvivesRecreation() {
        compose.onNodeWithText("Netflix").performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        compose.onNodeWithText("Netflix").performKeyInput { pressKey(Key.DirectionRight) }
        compose.onNodeWithText("Prime Video").assertIsFocused()
        compose.activityRule.scenario.recreate()
        waitForText("Household TV")
        compose.onNodeWithText("Prime Video").assertIsFocused()
    }

    @Test fun importsThroughDocumentResultAndRejectsInvalidContent() {
        intending(hasAction(Intent.ACTION_OPEN_DOCUMENT)).respondWith(ActivityResult(Activity.RESULT_OK,
            Intent().setData(Uri.parse("content://local.sovereigntv.test.fixture/valid"))))
        activate("Import experience")
        waitForText("Runtime household")
        waitForText("Unsaved preview • apply or cancel")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        assertEquals("Household TV", ExperienceRepository(context).load().experience.title)
        activate("Apply preview")
        waitForText("Imported local experience")
        activate("Netflix")
        waitForText("No installed TV activity found for Netflix")
        assertEquals("Runtime household", ExperienceRepository(context).load().experience.title)
        compose.activityRule.scenario.recreate()
        waitForText("Runtime household")
        // Test the same repository used by the import callback, including its read budget.
        for (content in listOf("{\"invalid\":true}", "x".repeat(65537))) {
            assertThrows(Exception::class.java) { ExperienceRepository(context).import(ByteArrayInputStream(content.toByteArray())) }
            assertEquals("Runtime household", ExperienceRepository(context).load().experience.title)
        }
        activate("Restore default")
        waitForText("Household TV")
        assertEquals("Household TV", ExperienceRepository(context).load().experience.title)
    }

    @Test fun cancelsPreviewAndUndoesAppliedChange() {
        intending(hasAction(Intent.ACTION_OPEN_DOCUMENT)).respondWith(ActivityResult(Activity.RESULT_OK,
            Intent().setData(Uri.parse("content://local.sovereigntv.test.fixture/valid"))))
        activate("Import experience")
        waitForText("Runtime household")
        compose.activityRule.scenario.recreate()
        waitForText("Runtime household")
        activate("Cancel preview")
        waitForText("Household TV")
        activate("Import experience")
        waitForText("Runtime household")
        activate("Apply preview")
        waitForText("Imported local experience")
        compose.activityRule.scenario.recreate()
        waitForText("Runtime household")
        activate("Undo last change")
        waitForText("Last change undone")
        waitForText("Household TV")
    }

    @Test fun invalidPickerResultPreservesExistingExperience() {
        intending(hasAction(Intent.ACTION_OPEN_DOCUMENT)).respondWith(ActivityResult(Activity.RESULT_OK,
            Intent().setData(Uri.parse("content://local.sovereigntv.test.fixture/invalid"))))
        activate("Import experience")
        waitForText("Change refused; previous experience preserved")
        compose.onNodeWithText("Household TV").assertExists()
    }

    @Test fun legacyConfigurationMigratesAndCorruptDiskFallsBack() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val saved = java.io.File(context.filesDir, "experience.json")
        val old = context.assets.open("experience.json").bufferedReader().use { it.readText().replace("Household TV", "Legacy household") }
        context.deleteDatabase("experience-journal.sqlite3")
        saved.delete()
        assertTrue(context.getSharedPreferences("experience", 0).edit().putString("document", old).commit())
        val repository = ExperienceRepository(context)
        assertEquals("Legacy household", repository.load().experience.title)
        assertEquals("Legacy household", repository.load().experience.title)
        // Once migrated, legacy stores cannot override the authoritative revision journal.
        saved.writeText("not valid JSON")
        assertEquals("Legacy household", repository.load().experience.title)
        context.deleteDatabase("experience-journal.sqlite3")
        val recovered = repository.load()
        assertTrue(recovered.restoredDefault)
        assertEquals("Household TV", recovered.experience.title)
        assertEquals("not valid JSON", saved.readText()) // Keep evidence until explicit restore.
        repository.reset()
    }
}
