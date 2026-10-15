package local.sovereigntv

import android.content.Context
import android.util.AtomicFile
import java.io.File
import java.io.InputStream
import java.io.FileNotFoundException
import java.util.UUID

/** Validated persistence shared by local UI and the future paired service. Call off the UI thread. */
class ExperienceRepository(private val context: Context) {
    private val artwork by lazy { ArtworkStore(context) }
    private val file = AtomicFile(File(context.filesDir, "experience.json"))
    private val legacy = context.getSharedPreferences("experience", Context.MODE_PRIVATE)

    data class Loaded(val experience: Experience, val restoredDefault: Boolean = false, val document: String, val revision: Long = 1, val journalUnavailable: Boolean = false)

    private fun <T> journal(operation: (ExperienceJournal) -> T): T = ExperienceJournal(context, ::legacyLoad).use(operation)

    fun load(): Loaded = try { journal { it.load() } } catch (_: Exception) {
        loaded(defaultDocument(), true).copy(revision = 0, journalUnavailable = true)
    }
    fun preview(baseRevision: Long, document: String): Loaded = journal { it.preview(baseRevision, document) }
    fun previewImport(baseRevision: Long, stream: InputStream): Loaded = stream.buffered().use { input ->
        input.mark(4)
        val prefix = ByteArray(4)
        var count = 0
        while (count < prefix.size) {
            val read = input.read(prefix, count, prefix.size - count)
            if (read < 0) break
            check(read > 0) { "Input made no progress" }
            count += read
        }
        input.reset()
        val document = if (count == 4 && prefix[0] == 80.toByte() && prefix[1] == 75.toByte())
            ArtworkBundle.read(context, artwork, input) else readBounded(input)
        preview(baseRevision, document)
    }
    fun previewArtwork(baseRevision: Long, stream: InputStream): Loaded {
        val current = load()
        if (current.revision != baseRevision) throw ExperienceJournal.Conflict("Experience changed; read and rebase")
        val digest = artwork.import(stream)
        return preview(baseRevision, Experience.withArtwork(current.document, digest))
    }
    fun apply(requestId: String, baseRevision: Long, document: String): ExperienceJournal.Receipt = journal { it.apply(requestId, baseRevision, document) }
    fun undo(requestId: String, baseRevision: Long, restoreRevision: Long): ExperienceJournal.Receipt = journal { it.undo(requestId, baseRevision, restoreRevision) }
    fun receipt(requestId: String): ExperienceJournal.Receipt? = journal { it.receipt(requestId) }
    fun applyDefault(requestId: String, baseRevision: Long): ExperienceJournal.Receipt = apply(requestId, baseRevision, defaultDocument())

    private fun loaded(document: String, recovered: Boolean = false): Loaded = Loaded(Experience.parse(document), recovered, document)

    private fun legacyLoad(): Loaded {
        try {
            return loaded(file.openRead().use(::readBounded))
        } catch (_: FileNotFoundException) {
            // openRead also restores any legacy AtomicFile backup before deciding absence.
        } catch (_: Exception) {
            return loaded(defaultDocument(), true)
        }
        val previous = legacy.getString("document", null)
        if (previous != null) {
            return runCatching { loaded(previous) }.getOrElse { loaded(defaultDocument(), true) }
        }
        return loaded(defaultDocument())
    }

    fun import(stream: InputStream): Loaded = import(stream.use(::readBounded))

    fun import(document: String): Loaded {
        apply(UUID.randomUUID().toString(), load().revision, document)
        return load()
    }

    fun reset(baseRevision: Long = load().revision): Loaded {
        applyDefault(UUID.randomUUID().toString(), baseRevision)
        return load()
    }

    private fun defaultDocument(): String = context.assets.open("experience.json").use(::readBounded)

    companion object {
        fun readBounded(stream: InputStream): String {
            val buffer = ByteArray(65537)
            var count = 0
            while (count < buffer.size) {
                val n = stream.read(buffer, count, buffer.size - count)
                if (n < 0) break
                check(n > 0) { "Input made no progress" }
                count += n
            }
            require(count <= 65536) { "Experience exceeds 64 KiB" }
            return buffer.copyOf(count).toString(Charsets.UTF_8)
        }
    }
}
