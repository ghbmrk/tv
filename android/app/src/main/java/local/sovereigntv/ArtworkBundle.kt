package local.sovereigntv

import android.content.Context
import java.io.File
import java.io.InputStream
import java.util.zip.ZipFile

/** A portable experience and its immutable assets. Archive paths are never extracted. */
object ArtworkBundle {
    fun read(context: Context, artwork: ArtworkStore, input: InputStream): String {
        val temporary = File.createTempFile("experience-", ".zip", context.cacheDir)
        try {
            temporary.outputStream().use { output ->
                val buffer = ByteArray(65536)
                var bytes = 0L
                while (true) {
                    val n = input.read(buffer)
                    if (n < 0) break
                    require(n > 0)
                    bytes += n; require(bytes <= 40L * 1024 * 1024) { "Experience bundle exceeds 40 MiB" }
                    output.write(buffer, 0, n)
                }
            }
            return ZipFile(temporary).use { zip ->
                val names = mutableSetOf<String>()
                val images = linkedMapOf<String, java.util.zip.ZipEntry>()
                var document: String? = null
                var total = 0L
                val entries = zip.entries()
                while (entries.hasMoreElements()) {
                    val entry = entries.nextElement()
                    require(names.add(entry.name) && names.size <= 257 && !entry.isDirectory)
                    if (entry.name == "experience.json") {
                        require(entry.size in 1..65536)
                        document = zip.getInputStream(entry).use(ExperienceRepository::readBounded)
                    } else {
                        val match = Regex("artwork/([a-f0-9]{64})\\.png").matchEntire(entry.name) ?: error("Unsupported bundle member")
                        require(entry.size in 1..ArtworkStore.MAX_BYTES.toLong())
                        total += entry.size; require(total <= 32L * 1024 * 1024)
                        val id = match.groupValues[1]
                        val bytes = zip.getInputStream(entry).use(ArtworkStore::readBounded)
                        require(ExperienceJournal.sha256Bytes(bytes) == id)
                        ArtworkStore.inspect(bytes)
                        images[id] = entry
                    }
                }
                val text = requireNotNull(document) { "Experience document missing" }
                require(Experience.parse(text).artworkRefs == images.keys) { "Bundle artwork references differ" }
                // Configuration remains untouched until the user explicitly applies its preview.
                images.forEach { (id, entry) -> require(artwork.import(zip.getInputStream(entry)) == id) }
                text
            }
        } finally { temporary.delete() }
    }
}
