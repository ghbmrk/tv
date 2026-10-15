package local.sovereigntv

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.system.Os
import android.system.OsConstants
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.io.RandomAccessFile
import android.os.ParcelFileDescriptor
import java.nio.ByteBuffer
import java.util.zip.CRC32
import java.util.zip.Inflater

/** App-private, content-addressed assets. Never downloads or executes image content. */
class ArtworkStore(context: Context) {
    private val directory = File(context.filesDir, "artwork").apply { check(isDirectory || mkdirs() || isDirectory) }
    data class Info(val width: Int, val height: Int)

    private fun path(id: String): File {
        require(Regex("[a-f0-9]{64}").matches(id))
        return File(directory, "$id.png")
    }

    fun read(id: String): ByteArray = path(id).inputStream().use(::readBounded).also {
        require(ExperienceJournal.sha256Bytes(it) == id) { "Artwork integrity mismatch" }
        inspect(it)
    }

    fun requireAssets(refs: Set<String>) {
        var bytes = 0L
        refs.forEach { bytes += read(it).size; require(bytes <= 32L * 1024 * 1024) { "Experience artwork exceeds 32 MiB" } }
    }

    fun import(stream: InputStream): String = put(stream.use(::readBounded))

    fun openReadOnly(id: String): ParcelFileDescriptor {
        read(id) // Verify immutable content before handing out a read-only descriptor.
        return ParcelFileDescriptor.open(path(id), ParcelFileDescriptor.MODE_READ_ONLY)
    }

    fun put(bytes: ByteArray, expectedDigest: String? = null, guard: () -> Unit = {}): String {
        require(bytes.size <= MAX_BYTES)
        inspect(bytes)
        val digest = ExperienceJournal.sha256Bytes(bytes)
        require(expectedDigest == null || digest == expectedDigest) { "Artwork digest mismatch" }
        synchronized(lock) { RandomAccessFile(File(directory, ".store.lock"), "rw").channel.use { channel -> channel.lock().use {
            guard()
            val destination = path(digest)
            if (destination.exists()) read(digest) else {
                val used = directory.listFiles()?.filter { it.name.endsWith(".png") }?.sumOf { it.length() } ?: 0L
                require(used + bytes.size <= MAX_STORE_BYTES) { "Artwork storage full; saved artwork preserved" }
                val temporary = File.createTempFile(".upload-", ".tmp", directory)
                try {
                    FileOutputStream(temporary).use { it.write(bytes); it.fd.sync() }
                    check(temporary.renameTo(destination))
                } finally { temporary.delete() }
            }
            val fd = Os.open(directory.absolutePath, OsConstants.O_RDONLY, 0)
            try { Os.fsync(fd) } finally { Os.close(fd) }
        } } }
        return digest
    }

    fun bitmap(id: String, width: Int, height: Int): Bitmap {
        val bytes = read(id)
        val info = Info(ByteBuffer.wrap(bytes, 16, 4).int, ByteBuffer.wrap(bytes, 20, 4).int)
        var sample = 1
        while (info.width / (sample * 2) >= width && info.height / (sample * 2) >= height) sample *= 2
        val options = BitmapFactory.Options().apply { inSampleSize = sample; inPreferredConfig = Bitmap.Config.ARGB_8888 }
        return requireNotNull(BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)) { "Artwork cannot be decoded" }
    }

    companion object {
        const val MAX_BYTES = 8 * 1024 * 1024
        const val MAX_PIXELS = 4096L * 2160
        const val MAX_STORE_BYTES = 128L * 1024 * 1024
        private val lock = Any()

        fun readBounded(stream: InputStream): ByteArray {
            val output = java.io.ByteArrayOutputStream()
            val block = ByteArray(65536)
            while (true) {
                val n = stream.read(block, 0, minOf(block.size, MAX_BYTES + 1 - output.size()))
                if (n < 0) break
                require(n > 0) { "Image input made no progress" }
                output.write(block, 0, n)
                require(output.size() <= MAX_BYTES) { "PNG exceeds 8 MiB" }
            }
            return output.toByteArray()
        }

        /** Same bounded PNG profile as the host. Checks CRCs and full scanline length. */
        fun inspect(bytes: ByteArray): Info {
            require(bytes.size in 45..MAX_BYTES && bytes.copyOfRange(0, 8).contentEquals(byteArrayOf(137.toByte(),80,78,71,13,10,26,10))) { "PNG required" }
            fun int(at: Int) = ByteBuffer.wrap(bytes, at, 4).int
            var pos = 8; var width = 0; var height = 0; var channels = 0
            var seen = false; var finished = false
            val compressed = java.io.ByteArrayOutputStream()
            while (pos < bytes.size) {
                require(pos + 12 <= bytes.size)
                val length = int(pos); require(length >= 0 && length <= bytes.size - pos - 12)
                val kind = String(bytes, pos + 4, 4, Charsets.US_ASCII)
                require(Regex("[A-Za-z]{4}").matches(kind))
                val end = pos + 12 + length
                val crc = CRC32().apply { update(bytes, pos + 4, length + 4) }
                require(crc.value == int(end - 4).toLong().and(0xffffffffL))
                require(pos != 8 || kind == "IHDR")
                when (kind) {
                    "IHDR" -> {
                        require(pos == 8 && length == 13)
                        width = int(pos + 8); height = int(pos + 12)
                        val color = bytes[pos + 17].toInt()
                        require(width in 1..8192 && height in 1..8192 && width.toLong() * height <= MAX_PIXELS)
                        require(bytes[pos + 16].toInt() == 8 && color in setOf(2, 6) && (18..20).all { bytes[pos + it].toInt() == 0 })
                        channels = if (color == 2) 3 else 4
                    }
                    "IDAT" -> { seen = true; compressed.write(bytes, pos + 8, length) }
                    "IEND" -> { require(length == 0 && end == bytes.size && seen); finished = true; break }
                    else -> {
                        require(kind in setOf("sRGB", "gAMA", "cHRM", "pHYs") && !seen)
                        require(length == mapOf("sRGB" to 1, "gAMA" to 4, "cHRM" to 32, "pHYs" to 9)[kind])
                    }
                }
                pos = end
            }
            require(finished)
            val stride = 1 + width * channels
            val expected = height * stride
            var count = 0
            val inflater = Inflater()
            try {
                inflater.setInput(compressed.toByteArray())
                val buffer = ByteArray(65536)
                while (!inflater.finished()) {
                    val n = inflater.inflate(buffer, 0, minOf(buffer.size, expected + 1 - count))
                    require(n > 0 || inflater.finished())
                    var offset = (stride - count % stride) % stride
                    while (offset < n) { require(buffer[offset].toInt().and(255) <= 4); offset += stride }
                    count += n; require(count <= expected)
                }
                require(count == expected && inflater.remaining == 0)
            } finally { inflater.end() }
            return Info(width, height)
        }
    }
}
