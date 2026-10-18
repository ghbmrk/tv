package local.sovereigntv

import android.graphics.Bitmap
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.espresso.Espresso
import androidx.test.espresso.intent.Intents
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.File

@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class StorybookRuntimeTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private fun node(id: String) = compose.onNodeWithTag("storybook-tile:$id")
    private fun seed(document: String) {
        ExperienceRepository(context).import(document)
        compose.activityRule.scenario.recreate()
        compose.waitUntil(10000) { compose.onAllNodesWithTag("storybook-home").fetchSemanticsNodes().isNotEmpty() }
        val expected = Experience.parse(document)
        compose.waitUntil(10000) { ViewModelProvider(compose.activity)[ExperienceViewModel::class.java].experience == expected }
        node("film_balto").performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        compose.waitForIdle()
    }
    @Before fun setup() {
        Intents.init()
        // An unexpected launch must be recorded for assertions, never open a real client.
        Intents.intending(androidx.test.espresso.intent.matcher.IntentMatchers.anyIntent())
            .respondWith(android.app.Instrumentation.ActivityResult(android.app.Activity.RESULT_CANCELED, null))
        seed(context.assets.open("storybook.json").bufferedReader().use { it.readText() })
    }
    @After fun releaseIntents() { Intents.release() }

    @Test fun textFreeHomeHasManualMoviesSixAppsDpadAndRestoredFocus() {
        compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.Text)).assertCountEquals(0)
        node("film_balto").assertIsFocused()
        node("film_balto").performKeyInput { pressKey(Key.DirectionRight) }
        node("film_little_mermaid").assertIsFocused()
        node("film_little_mermaid").performKeyInput { pressKey(Key.DirectionDown) }
        node("app_prime_video").assertIsFocused()
        val document = ExperienceRepository(context).load().document
        compose.mainClock.advanceTimeBy(360000)
        node("app_prime_video").assertIsFocused()
        assertEquals(document, ExperienceRepository(context).load().document)
        repeat(6) { round ->
            if (round == 0) compose.onNodeWithTag("storybook-settings").performTouchInput { click(center) }
            else {
                compose.onNodeWithContentDescription("Settings").performSemanticsAction(SemanticsActions.RequestFocus) { it() }
                compose.onNodeWithContentDescription("Settings").performKeyInput { pressKey(Key.DirectionCenter) }
            }
            compose.waitUntil(10000) { compose.onAllNodesWithText("Your TV, your rules.").fetchSemanticsNodes().isNotEmpty() }
            Espresso.pressBack()
            compose.waitUntil(10000) { compose.onAllNodesWithText("Your TV, your rules.").fetchSemanticsNodes().isEmpty() }
            try { compose.waitUntil(3000) { compose.onAllNodes(hasTestTag("storybook-tile:app_prime_video") and isFocused()).fetchSemanticsNodes().isNotEmpty() } }
            catch (failure: Throwable) { throw AssertionError("Focused nodes after settings return: " + compose.onAllNodes(isFocused(), useUnmergedTree = true).fetchSemanticsNodes().map { it.config.toString() }, failure) }
            node("app_prime_video").assertIsFocused()
        }
        compose.activityRule.scenario.recreate()
        compose.waitUntil(10000) { compose.onAllNodesWithTag("storybook-home").fetchSemanticsNodes().isNotEmpty() }
        node("app_prime_video").assertIsFocused()
        compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.Text)).assertCountEquals(0)
        node("app_prime_video").performKeyInput { pressKey(Key.DirectionUp) }
        node("film_little_mermaid").performKeyInput { pressKey(Key.DirectionLeft) }
        node("film_balto").assertIsFocused()
        compose.onRoot().captureToImage().asAndroidBitmap().let { bitmap ->
            val colors = mutableSetOf<Int>()
            for (y in 1..8) for (x in 1..12) colors.add(bitmap.getPixel(bitmap.width * x / 13, bitmap.height * y / 9))
            assertTrue("Rendered Home must contain actual illustrations, not an opaque hidden surface", colors.size > 32)
            val bounds = node("film_balto").fetchSemanticsNode().boundsInRoot
            assertEquals("Focused movie must have a visible paper edge", 0xffffebad.toInt(), bitmap.getPixel((bounds.left - 2).toInt(), bounds.center.y.toInt()))
            File(context.filesDir, "storybook-home-proof.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
    }

    @Test fun unconfiguredMovieNeverLaunchesProviderOrRecommendations() {
        node("film_balto").performKeyInput { pressKey(Key.DirectionCenter) }
        compose.waitUntil(10000) { compose.onAllNodesWithTag("storybook-notice").fetchSemanticsNodes().isNotEmpty() }
        assertTrue(Intents.getIntents().isEmpty())
        node("film_balto").assertIsFocused()
        compose.onAllNodes(SemanticsMatcher.keyIsDefined(SemanticsProperties.Text)).assertCountEquals(0)
    }

    @Test fun evenAnExplicitMovieBindingCannotBypassStopAtEndQualification() {
        val doc = JSONObject(context.assets.open("storybook.json").bufferedReader().use { it.readText() })
        doc.getJSONArray("sections").getJSONObject(0).getJSONArray("items").getJSONObject(2)
            .put("playback", JSONObject().put("provider","youtube").put("content_id","abcdefghijk"))
        seed(doc.toString())
        node("film_balto").performKeyInput { pressKey(Key.DirectionCenter) }
        compose.waitUntil(10000) { compose.onAllNodesWithTag("storybook-notice").fetchSemanticsNodes().isNotEmpty() }
        assertTrue(Intents.getIntents().isEmpty())
        compose.runOnIdle { assertTrue(ViewModelProvider(compose.activity)[ExperienceViewModel::class.java].message.contains("stop-at-end")) }
    }

    @Test fun householdEditsReorderAndRemoveMoviesWithoutRepopulatingThem() {
        val repository = ExperienceRepository(context)
        val initial = repository.load()
        val doc = JSONObject(initial.document)
        val movies = doc.getJSONArray("sections").getJSONObject(0).getJSONArray("items")
        movies.remove(2) // Owner removes Balto. No algorithm may put it back.
        val first = movies.getJSONObject(0); movies.put(0,movies.getJSONObject(1)); movies.put(1,first)
        repository.import(doc.toString())
        compose.runOnIdle { ViewModelProvider(compose.activity)[ExperienceViewModel::class.java].refreshSaved() }
        compose.waitUntil(10000) { compose.onAllNodesWithTag("storybook-tile:film_balto").fetchSemanticsNodes().isEmpty() }
        compose.activityRule.scenario.recreate()
        compose.waitUntil(10000) { compose.onAllNodesWithTag("storybook-home").fetchSemanticsNodes().isNotEmpty() }
        node("film_balto").assertDoesNotExist()
        val left = node("film_kung_fu_panda").fetchSemanticsNode().boundsInRoot.left
        assertTrue(left < node("film_princess_frog").fetchSemanticsNode().boundsInRoot.left)
        val current = repository.load()
        repository.undo(java.util.UUID.randomUUID().toString(), current.revision, initial.revision)
        compose.runOnIdle { ViewModelProvider(compose.activity)[ExperienceViewModel::class.java].refreshSaved() }
        compose.waitUntil(10000) { compose.onAllNodesWithTag("storybook-tile:film_balto").fetchSemanticsNodes().isNotEmpty() }
    }

    @Test fun liveReorderRestoresSelectedMovieBeyondTheComposedViewport() {
        val doc = JSONObject(context.assets.open("storybook.json").bufferedReader().use { it.readText() })
        val movies = doc.getJSONArray("sections").getJSONObject(0).getJSONArray("items")
        repeat(18) { index -> movies.put(JSONObject(movies.getJSONObject(0).toString()).put("id", "extra_$index")) }
        seed(doc.toString())
        node("film_balto").assertIsFocused()
        val selected = movies.remove(2)
        movies.put(selected)
        ExperienceRepository(context).import(doc.toString())
        compose.runOnIdle { ViewModelProvider(compose.activity)[ExperienceViewModel::class.java].refreshSaved() }
        compose.waitUntil(10000) {
            compose.onAllNodes(hasTestTag("storybook-tile:film_balto") and isFocused()).fetchSemanticsNodes().isNotEmpty() &&
                compose.onAllNodesWithTag("storybook-tile:extra_17").fetchSemanticsNodes().isNotEmpty()
        }
        node("film_balto").assertIsDisplayed().assertIsFocused()
        compose.activityRule.scenario.recreate()
        compose.waitUntil(10000) { compose.onAllNodes(hasTestTag("storybook-tile:film_balto") and isFocused()).fetchSemanticsNodes().isNotEmpty() }
        node("film_balto").performKeyInput { pressKey(Key.DirectionLeft) }
        node("extra_17").assertIsFocused()
        // Removing the selected tail must recover to a visible, navigable card rather
        // than leave focus parked on the detached item or the Settings button.
        movies.getJSONObject(movies.length() - 2).put("visible", false)
        ExperienceRepository(context).import(doc.toString())
        compose.runOnIdle { ViewModelProvider(compose.activity)[ExperienceViewModel::class.java].refreshSaved() }
        compose.waitUntil(10000) { compose.onAllNodes(hasTestTag("storybook-tile:film_little_mermaid") and isFocused()).fetchSemanticsNodes().isNotEmpty() }
        node("film_little_mermaid").assertIsDisplayed().performKeyInput { pressKey(Key.DirectionRight) }
        node("film_hunchback").assertIsFocused()
    }

    @Test fun liveSectionMoveRetainsRemoteSelectionAcrossVerticalVirtualization() {
        val doc = JSONObject(context.assets.open("storybook.json").bufferedReader().use { it.readText() })
        val sections = doc.getJSONArray("sections")
        repeat(10) { index ->
            val section = JSONObject(sections.getJSONObject(0).toString()).put("id", "shelf_$index")
            val entries = section.getJSONArray("items")
            repeat(entries.length()) { item -> entries.getJSONObject(item).put("id", "shelf_${index}_$item") }
            sections.put(section)
        }
        seed(doc.toString())
        node("film_balto").assertIsFocused()
        sections.put(sections.remove(0))
        ExperienceRepository(context).import(doc.toString())
        compose.runOnIdle { ViewModelProvider(compose.activity)[ExperienceViewModel::class.java].refreshSaved() }
        compose.waitUntil(10000) { ViewModelProvider(compose.activity)[ExperienceViewModel::class.java].experience?.sections?.firstOrNull()?.id == "apps" }
        compose.waitUntil(10000) { compose.onAllNodes(hasTestTag("storybook-tile:film_balto") and isFocused()).fetchSemanticsNodes().isNotEmpty() }
        node("film_balto").assertIsDisplayed()
        compose.activityRule.scenario.recreate()
        compose.waitUntil(10000) { compose.onAllNodes(hasTestTag("storybook-tile:film_balto") and isFocused()).fetchSemanticsNodes().isNotEmpty() }
        node("film_balto").assertIsDisplayed().performKeyInput { pressKey(Key.DirectionRight) }
        node("film_little_mermaid").assertIsFocused()
    }
}
