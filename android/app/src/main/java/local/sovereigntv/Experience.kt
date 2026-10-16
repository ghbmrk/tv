package local.sovereigntv

import org.json.JSONObject
import org.json.JSONArray
import java.util.UUID

data class Tile(val id: String, val title: String, val kind: String, val target: String, val visible: Boolean, val poster: String? = null, val playback: MovieLink? = null)
data class Section(val id: String, val title: String, val layout: String, val items: List<Tile>)
data class Collection(val id: String, val title: String, val items: List<Tile>)
data class Experience(val title: String, val theme: String, val textScale: Float, val sections: List<Section>,
    val collections: List<Collection> = emptyList(), val artworkIntervalSeconds: Int = 300) {
    val artworkRefs get() = (collections.flatMap { it.items }.filter { it.kind == "artwork" }.map { it.target } + sections.flatMap { it.items }.filter { it.kind == "movie" }.mapNotNull { it.poster?.takeIf { poster -> Regex("[a-f0-9]{64}").matches(poster) } }).toSet()
    companion object {
        private fun exact(o: JSONObject, keys: Set<String>) { require(o.keys().asSequence().toSet() == keys) }
        private fun label(value: Any): String { require(value is String && value.codePointCount(0, value.length) in 1..120 && value.none { it.code < 32 } && Charsets.UTF_8.newEncoder().canEncode(value)); return value }
        private fun id(value: Any): String { require(value is String && Regex("[a-z][a-z0-9_-]{0,63}").matches(value)); return value }
        fun parse(text: String): Experience {
            require(Charsets.UTF_8.newEncoder().canEncode(text)) { "Well-formed Unicode required" }
            require(text.toByteArray(Charsets.UTF_8).size <= 65536)
            val root = JSONObject(text)
            require(root.get("schema_version") is Int && root.getInt("schema_version") in 1..3)
            val version = root.getInt("schema_version")
            exact(root, setOf("schema_version", "title", "theme", "sections", "settings") + if (version >= 2) setOf("collections") else emptySet())
            val title = label(root.get("title"))
            val theme = root.getString("theme"); require(theme in setOf("night", "warm", "light", "storybook"))
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
                val items = section.getJSONArray("items"); require(items.length() in (if (version == 3) 0..24 else 1..24))
                Section(section.getString("id"), label(section.get("title")), layout, (0 until items.length()).map { j ->
                    val item = items.getJSONObject(j)
                    exact(item, setOf("id", "title", "kind", "target", "visible") + if (version == 3 && item.optString("kind") == "movie") setOf("poster", "playback") else emptySet())
                    val itemId = id(item.get("id")); require(ids.add(itemId))
                    val kind = item.getString("kind"); require(kind in (if (version == 3) setOf("app", "collection", "movie") else setOf("app", "collection")))
                    require(item.get("visible") is Boolean)
                    val poster = if (kind == "movie") item.getString("poster").also { require(item.get("poster") is String) }.also { require(it == "blank" || it in MovieLink.POSTERS || Regex("[a-f0-9]{64}").matches(it)) } else null
                    val playback = if (kind == "movie" && !item.isNull("playback")) MovieLink.parse(item.getJSONObject("playback")) else null
                    Tile(itemId, label(item.get("title")), kind, id(item.get("target")), item.getBoolean("visible"), poster, playback)
                })
            }
            require(sections.any { section -> section.items.any { it.visible } })
            val collectionIds = mutableSetOf<String>()
            var total = 0
            val collections = if (version == 1) emptyList() else {
                val array = root.getJSONArray("collections"); require(array.length() <= 12)
                (0 until array.length()).map { i ->
                    val collection = array.getJSONObject(i)
                    exact(collection, setOf("id", "title", "items"))
                    val cid = id(collection.get("id")); require(collectionIds.add(cid))
                    val entries = collection.getJSONArray("items"); require(entries.length() <= 48)
                    val entryIds = mutableSetOf<String>()
                    Collection(cid, label(collection.get("title")), (0 until entries.length()).map { j ->
                        val entry = entries.getJSONObject(j)
                        exact(entry, setOf("id", "title", "kind", "target", "visible"))
                        val eid = id(entry.get("id")); require(entryIds.add(eid))
                        val kind = entry.getString("kind"); require(kind in setOf("app", "artwork"))
                        val target = entry.getString("target")
                        if (kind == "app") id(target) else require(Regex("[a-f0-9]{64}").matches(target))
                        require(entry.get("visible") is Boolean)
                        total++
                        Tile(eid, label(entry.get("title")), kind, target, entry.getBoolean("visible"))
                    })
                }
            }
            require(total <= 256)
            if (version >= 2) require(sections.flatMap { it.items }.filter { it.kind == "collection" }.all { it.target in collectionIds })
            return Experience(title, theme, scale.toFloat(), sections, collections, settings.getInt("artwork_interval_seconds"))
        }

        /** Stage a local image in a collection. Original v1 bytes remain available through undo. */
        fun withArtwork(document: String, digest: String): String {
            val parsed = parse(document)
            require(Regex("[a-f0-9]{64}").matches(digest))
            val root = JSONObject(document)
            val collections = if (root.getInt("schema_version") >= 2) root.getJSONArray("collections") else JSONArray().also { array ->
                parsed.sections.flatMap { it.items }.filter { it.kind == "collection" }.distinctBy { it.target }.forEach {
                    array.put(JSONObject().put("id", it.target).put("title", it.title).put("items", JSONArray()))
                }
                root.put("schema_version", 2).put("collections", array)
            }
            val target = parsed.sections.flatMap { it.items }.firstOrNull { it.kind == "collection" }?.target ?: "artwork"
            var collection = (0 until collections.length()).map { collections.getJSONObject(it) }.firstOrNull { it.getString("id") == target }
            if (collection == null) {
                collection = JSONObject().put("id", target).put("title", "Local artwork").put("items", JSONArray())
                collections.put(collection)
            }
            if (parsed.sections.flatMap { it.items }.none { it.kind == "collection" }) {
                val used = parsed.sections.flatMap { listOf(it.id) + it.items.map(Tile::id) }.toSet()
                var tileId = "local_artwork"
                while (tileId in used) tileId += "_"
                val tile = JSONObject().put("id", tileId).put("title", "Local artwork").put("kind", "collection").put("target", target).put("visible", true)
                val sections = root.getJSONArray("sections")
                val section = (0 until sections.length()).map { sections.getJSONObject(it) }.firstOrNull { it.getJSONArray("items").length() < 24 }
                    ?: error("No room for artwork tile; edit a section first")
                section.getJSONArray("items").put(tile)
            }
            val entries = collection.getJSONArray("items")
            if ((0 until entries.length()).none { entries.getJSONObject(it).let { entry -> entry.getString("kind") == "artwork" && entry.getString("target") == digest } }) {
                entries.put(JSONObject().put("id", "art_" + UUID.randomUUID().toString().replace("-", ""))
                    .put("title", "Local artwork ${entries.length() + 1}").put("kind", "artwork").put("target", digest).put("visible", true))
            }
            return root.toString().also { parse(it) }
        }
    }
}
