package local.sovereigntv

import org.json.JSONObject

/** Owner-declared title routes only. A syntactically valid link is not playback qualification. */
data class MovieLink(val provider: String, val contentId: String) {
    companion object {
        val POSTERS = listOf("princess_frog", "kung_fu_panda", "balto", "little_mermaid", "hunchback", "land_before_time")
        private val IDS = mapOf("netflix" to "[0-9]{6,12}", "youtube" to "[A-Za-z0-9_-]{11}",
            "prime_video" to "[A-Z0-9]{10}", "disney_plus" to "[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}")
        fun parse(json: JSONObject): MovieLink {
            require(json.keys().asSequence().toSet() == setOf("provider", "content_id"))
            require(json.get("provider") is String && json.get("content_id") is String)
            val provider = json.getString("provider"); val content = json.getString("content_id")
            require(IDS[provider]?.let { Regex(it).matches(content) } == true)
            return MovieLink(provider, content)
        }
    }
}
