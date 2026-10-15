package local.sovereigntv

import org.json.JSONObject

data class Tile(val id: String, val title: String, val kind: String, val target: String, val visible: Boolean)
data class Section(val id: String, val title: String, val layout: String, val items: List<Tile>)
data class Experience(val title: String, val theme: String, val textScale: Float, val sections: List<Section>) {
    companion object {
        private fun exact(o: JSONObject, keys: Set<String>) { require(o.keys().asSequence().toSet() == keys) }
        private fun label(value: Any): String { require(value is String && value.length in 1..120 && value.none { it.code < 32 }); return value }
        private fun id(value: Any): String { require(value is String && Regex("[a-z][a-z0-9_-]{0,63}").matches(value)); return value }
        fun parse(text: String): Experience {
            require(text.toByteArray(Charsets.UTF_8).size <= 65536)
            val root = JSONObject(text)
            exact(root, setOf("schema_version", "title", "theme", "sections", "settings"))
            require(root.get("schema_version") is Int && root.getInt("schema_version") == 1)
            val title = label(root.get("title"))
            val theme = root.getString("theme"); require(theme in setOf("night", "warm", "light"))
            val settings = root.getJSONObject("settings")
            exact(settings, setOf("text_scale", "artwork_interval_seconds"))
            require(settings.get("text_scale") is Number)
            val scale = settings.getDouble("text_scale"); require(scale in 0.8..1.6)
            require(settings.get("artwork_interval_seconds") is Int && settings.getInt("artwork_interval_seconds") in 30..86400)
            val ids = mutableSetOf<String>()
            val source = root.getJSONArray("sections"); require(source.length() in 1..12)
            val sections = (0 until source.length()).map { index ->
                val section = source.getJSONObject(index)
                exact(section, setOf("id", "title", "layout", "items"))
                require(ids.add(id(section.get("id"))))
                val layout = section.getString("layout"); require(layout in setOf("row", "grid"))
                val items = section.getJSONArray("items"); require(items.length() in 1..24)
                Section(section.getString("id"), label(section.get("title")), layout, (0 until items.length()).map { j ->
                    val item = items.getJSONObject(j)
                    exact(item, setOf("id", "title", "kind", "target", "visible"))
                    val itemId = id(item.get("id")); require(ids.add(itemId))
                    val kind = item.getString("kind"); require(kind in setOf("app", "collection"))
                    require(item.get("visible") is Boolean)
                    Tile(itemId, label(item.get("title")), kind, id(item.get("target")), item.getBoolean("visible"))
                })
            }
            require(sections.any { section -> section.items.any { it.visible } })
            return Experience(title, theme, scale.toFloat(), sections)
        }
    }
}
