package local.sovereigntv.control

import android.os.Bundle
import android.os.ParcelFileDescriptor
import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.io.OutputStream
import java.nio.ByteBuffer

/** Provisional v1 TV protocol; this is not the agentOS broker wire contract. */
object LocalProtocol {
    const val MAX_METADATA = 512 * 1024
    const val MAX_ASSET = 8 * 1024 * 1024
    fun read(input: InputStream, maximum: Int): ByteArray {
        fun exact(count: Int): ByteArray {
            val bytes = ByteArray(count); var offset = 0
            while (offset < count) {
                val n = input.read(bytes, offset, count - offset)
                require(n > 0) { "Incomplete frame" }; offset += n
            }
            return bytes
        }
        val size = ByteBuffer.wrap(exact(4)).int
        require(size in 1..maximum) { "Frame bound exceeded" }
        return exact(size)
    }
    fun write(output: OutputStream, bytes: ByteArray) {
        require(bytes.isNotEmpty())
        output.write(ByteBuffer.allocate(4).putInt(bytes.size).array()); output.write(bytes); output.flush()
    }
    fun json(bytes: ByteArray): JSONObject = JSONObject(Charsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(bytes)).toString())
    /** Requests are a strict flat JSON object; duplicate keys and executable/nonstandard syntax fail closed. */
    fun requestJson(bytes: ByteArray): JSONObject {
        val text = Charsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(bytes)).toString()
        val result = JSONObject(); val names = mutableSetOf<String>()
        android.util.JsonReader(java.io.StringReader(text)).use { reader ->
            reader.isLenient = false; reader.beginObject()
            while (reader.hasNext()) {
                val name = reader.nextName(); require(names.add(name) && names.size <= 10)
                when (reader.peek()) {
                    android.util.JsonToken.STRING -> result.put(name, reader.nextString())
                    android.util.JsonToken.NUMBER -> {
                        val number = reader.nextString(); require(number.length <= 64)
                        val integer = number.toLongOrNull()
                        if (integer != null) result.put(name, integer)
                        else result.put(name, number.toDouble().also { require(it.isFinite()) })
                    }
                    else -> throw IllegalArgumentException("Only bounded typed request fields accepted")
                }
            }
            reader.endObject(); require(reader.peek() == android.util.JsonToken.END_DOCUMENT)
        }
        return result
    }
    fun integer(o: JSONObject, key: String): Long {
        val value = o.get(key); require(value is Long || value is Int)
        return (value as Number).toLong()
    }
    fun text(o: JSONObject, key: String): String { val value = o.get(key); require(value is String); return value }
    fun exact(o: JSONObject, fields: Set<String>) = require(o.keys().asSequence().toSet() == fields)

    class Gateway(private val cache: File, private val domain: DomainConnection, private val device: String) {
        data class Reply(val body: JSONObject, val asset: ByteArray? = null)
        private fun response(status: String, value: JSONObject? = null) = JSONObject().put("v", 1).put("device_id", device).put("status", status).apply { if (value != null) put("result", value) }
        fun invalid() = Reply(response("invalid"))
        class Prepared(val invoke: () -> Reply)
        fun prepare(request: JSONObject, input: InputStream): Prepared {
            val operation = text(request, "operation")
            val common = setOf("v", "device_id", "operation", "expires_at_ms")
            val fields = when (operation) {
                "capabilities", "state" -> emptySet()
                "preview" -> setOf("base_revision", "document")
                "apply" -> setOf("request_id", "base_revision", "document")
                "undo" -> setOf("request_id", "base_revision", "restore_revision")
                "restore_default" -> setOf("request_id", "base_revision")
                "receipt" -> setOf("request_id")
                "artwork.put" -> setOf("sha256", "bytes")
                "artwork.open" -> setOf("sha256")
                else -> throw IllegalArgumentException("Unknown operation")
            }
            exact(request, common + fields)
            require(integer(request, "v") == 1L && text(request, "device_id") == device)
            val expiry = integer(request, "expires_at_ms")
            val remaining = Math.subtractExact(expiry, System.currentTimeMillis())
            if (remaining <= 0) return Prepared { Reply(response("expired")) }
            require(remaining <= 30000)
            val base = if ("base_revision" in fields) integer(request, "base_revision").also { require(it > 0) } else 0
            val restore = if ("restore_revision" in fields) integer(request, "restore_revision").also { require(it in 1 until base) } else 0
            val id = if ("request_id" in fields) text(request, "request_id").also { require(Regex("[A-Za-z0-9._-]{1,64}").matches(it)) } else ""
            val document = if ("document" in fields) text(request, "document").also {
                require(Charsets.UTF_8.newEncoder().canEncode(it) && it.toByteArray(Charsets.UTF_8).size <= 65536)
            } else ""
            val digest = if ("sha256" in fields) text(request, "sha256").also { require(Regex("[a-f0-9]{64}").matches(it)) } else ""
            val upload = if (operation == "artwork.put") {
                val size = integer(request, "bytes"); require(size in 1..MAX_ASSET.toLong())
                read(input, MAX_ASSET).also { require(it.size.toLong() == size && Identity.digest(it) == digest) }
            } else null
            // All transport validation/read failures precede invocation. Exceptions after this
            // boundary close the connection; they can never be mislabeled as a definite refusal.
            return Prepared {
                val remote = domain.get()
                val result: Bundle = when (operation) {
                    "capabilities" -> remote.capabilities(expiry)
                    "state" -> remote.state(expiry)
                    "preview" -> remote.preview(base, document, expiry)
                    "apply" -> remote.apply(id, base, document, expiry)
                    "undo" -> remote.undo(id, base, restore, expiry)
                    "restore_default" -> remote.restoreDefault(id, base, expiry)
                    "receipt" -> remote.receipt(id, expiry)
                    "artwork.open" -> remote.openArtwork(digest, expiry)
                    "artwork.put" -> {
                        val file = File.createTempFile("asset-", ".png", cache)
                        try {
                            file.outputStream().use { it.write(requireNotNull(upload)) }
                            ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { remote.putArtwork(digest, it, expiry) }
                        } finally { file.delete() }
                    }
                    else -> error("Unreachable operation")
                }
                check(result.getInt("api_version") == 1)
                val body = response(requireNotNull(result.getString("status")), result.getString("json")?.let(::JSONObject))
                if (operation == "capabilities" && body.optString("status") == "ok") {
                    body.getJSONObject("result").put("mode", "paired-local-controller-prototype").put("screen_capture", false)
                        .put("artwork_read_returns_image", true).put("broker_capture_enforced", false).put("network_endpoint", true).put("paired_service", true)
                        .put("transport", "pinned-mtls-framed-json-v1").put("agentos_qualified", false)
                }
                @Suppress("DEPRECATION") val descriptor = result.getParcelable<ParcelFileDescriptor>("file")
                val asset = descriptor?.let { ParcelFileDescriptor.AutoCloseInputStream(it).use { stream ->
                    val out = java.io.ByteArrayOutputStream(); val block = ByteArray(65536)
                    while (true) { val n = stream.read(block); if (n < 0) break; require(n > 0 && out.size() + n <= MAX_ASSET); out.write(block, 0, n) }
                    out.toByteArray()
                } }
                if (asset != null) { require(asset.isNotEmpty()); body.put("blob_bytes", asset.size) }
                Reply(body, asset)
            }
        }
    }
}
