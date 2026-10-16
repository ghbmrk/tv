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
    @Test fun malformedUnicodeCannotAliasAnExactDocumentFingerprint() {
        val first = sample.replace("Household TV", "Bad " + 0xD800.toChar())
        val second = sample.replace("Household TV", "Bad " + 0xD801.toChar())
        assertArrayEquals(first.toByteArray(Charsets.UTF_8), second.toByteArray(Charsets.UTF_8))
        assertThrows(IllegalArgumentException::class.java) { Experience.parse(first) }
        assertThrows(IllegalArgumentException::class.java) { Experience.parse(second) }
        assertThrows(IllegalArgumentException::class.java) { Experience.parse(sample.replace("Household TV", "Bad " + "\\ud800")) }
        assertThrows(IllegalArgumentException::class.java) { Experience.parse(sample.replace("Household TV", "Bad " + 0xDC00.toChar())) }
        val valid = "Film " + String(Character.toChars(0x1F3AC))
        assertEquals(valid, Experience.parse(sample.replace("Household TV", valid)).title)
        val emoji = String(Character.toChars(0x1F3AC))
        assertEquals(emoji.repeat(120), Experience.parse(sample.replace("Household TV", emoji.repeat(120))).title)
        assertThrows(IllegalArgumentException::class.java) { Experience.parse(sample.replace("Household TV", emoji.repeat(121))) }
    }

    @Test fun fileImportsRejectMalformedUtf8InsteadOfReplacingBytes() {
        val invalid = sample.replace("Household TV", "Malformed ").toByteArray(Charsets.UTF_8)
        val index = invalid.indexOf('M'.code.toByte())
        invalid[index] = 0xC0.toByte() // Invalid UTF-8 lead byte, formerly silently replaced.
        assertThrows(java.nio.charset.CharacterCodingException::class.java) {
            ExperienceRepository.readBounded(invalid.inputStream())
        }
        val valid = sample.replace("Household TV", "Film " + String(Character.toChars(0x1F3AC)))
        assertEquals(valid, ExperienceRepository.readBounded(valid.toByteArray(Charsets.UTF_8).inputStream()))
    }

    @Test fun curatedMoviesAreVersionedDataAndNeverImplicitProviderLaunches() {
        val text = java.io.File("src/main/assets/storybook.json").readText()
        val experience = Experience.parse(text)
        assertEquals("storybook", experience.theme)
        assertEquals(6, experience.sections[0].items.size)
        assertEquals(6, experience.sections[1].items.size)
        assertTrue(experience.sections[0].items.all { it.kind == "movie" && it.playback == null })
        val root = org.json.JSONObject(text)
        root.getJSONArray("sections").getJSONObject(0).put("items", org.json.JSONArray())
        assertTrue(Experience.parse(root.toString()).sections[0].items.isEmpty())
        root.put("autoplay", true)
        assertThrows(IllegalArgumentException::class.java) { Experience.parse(root.toString()) }
        for (value in listOf("https://example.com", "1234/../../private")) {
            assertThrows(IllegalArgumentException::class.java) { MovieLink.parse(org.json.JSONObject().put("provider","netflix").put("content_id",value)) }
        }
        assertThrows(IllegalArgumentException::class.java) { MovieLink.parse(org.json.JSONObject().put("provider","netflix").put("content_id",12345678)) }
    }

}
