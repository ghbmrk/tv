package local.sovereigntv

import org.junit.Assert.*
import org.junit.Test

class ExperienceTest {
    private val sample = java.io.File("src/main/assets/experience.json").readText()
    @Test fun importsSharedHostFormat() {
        val parsed = Experience.parse(sample)
        assertEquals("Household TV", parsed.title)
        assertEquals(4, parsed.sections.first().items.size)
    }
    @Test fun rejectsInvalidImportBeforeReplacingState() {
        for (text in listOf(sample.replace("\"night\"", "\"unknown\""), sample.replace("\"target\": \"netflix\"", "\"target\": \"https://example.com\""), sample.replace("\"schema_version\": 1", "\"schema_version\": 2"))) {
            assertThrows(Exception::class.java) { Experience.parse(text) }
        }
    }
}
