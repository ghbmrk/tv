package local.sovereigntv

import android.content.Context
import android.util.AtomicFile
import java.io.File
import java.io.InputStream
import java.io.FileNotFoundException

/** Validated persistence shared by local UI and the future paired service. Call off the UI thread. */
class ExperienceRepository(private val context: Context) {
    private val file = AtomicFile(File(context.filesDir, "experience.json"))
    private val legacy = context.getSharedPreferences("experience", Context.MODE_PRIVATE)

    data class Loaded(val experience: Experience, val restoredDefault: Boolean = false)

    fun load(): Loaded {
        try {
            return Loaded(Experience.parse(file.openRead().use(::readBounded)))
        } catch (_: FileNotFoundException) {
            // openRead also restores any legacy AtomicFile backup before deciding absence.
        } catch (_: Exception) {
            return Loaded(Experience.parse(defaultDocument()), restoredDefault = true)
        }
        val previous = legacy.getString("document", null)
        if (previous != null) {
            return runCatching { import(previous) }.getOrElse { Loaded(Experience.parse(defaultDocument()), restoredDefault = true) }
        }
        return Loaded(Experience.parse(defaultDocument()))
    }

    fun import(stream: InputStream): Loaded = import(stream.use(::readBounded))

    fun import(document: String): Loaded {
        val parsed = Experience.parse(document) // Invalid input never starts a write.
        val output = file.startWrite()
        try {
            output.write(document.toByteArray(Charsets.UTF_8))
            file.finishWrite(output)
        } catch (failure: Exception) {
            file.failWrite(output)
            throw failure
        }
        return Loaded(parsed)
    }

    fun reset(): Loaded {
        val restored = import(defaultDocument())
        check(legacy.edit().clear().commit())
        return restored
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
