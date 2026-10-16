package local.sovereigntv

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.AndroidComposeTestRule
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.platform.app.InstrumentationRegistry

fun useLegacyHome(compose: AndroidComposeTestRule<ActivityScenarioRule<MainActivity>, MainActivity>) {
    val context = InstrumentationRegistry.getInstrumentation().targetContext
    val doc = context.assets.open("experience.json").bufferedReader().use { it.readText() }
    ExperienceRepository(context).import(doc)
    compose.activityRule.scenario.recreate()
    compose.waitUntil(10000) { compose.onAllNodes(androidx.compose.ui.test.hasText("Settings")).fetchSemanticsNodes().isNotEmpty() }
}
