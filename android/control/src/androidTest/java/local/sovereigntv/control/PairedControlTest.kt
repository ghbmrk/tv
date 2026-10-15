package local.sovereigntv.control

import android.content.Context
import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.net.InetAddress
import java.security.cert.X509Certificate
import java.util.UUID
import javax.net.ssl.SSLSocket

@RunWith(AndroidJUnit4::class)
class PairedControlTest {
    private val context: Context get() = InstrumentationRegistry.getInstrumentation().targetContext
    private lateinit var trust: PairedStore
    private lateinit var domain: DomainConnection
    private lateinit var server: LocalListener
    private lateinit var client: X509Certificate
    private lateinit var initial: JSONObject
    private val alias = "fixture-client"
    private val other = "fixture-unpaired"
    private fun expiry() = System.currentTimeMillis() + 10000
    private fun id() = UUID.randomUUID().toString()
    private fun await(condition: () -> Boolean) {
        val until = SystemClock.elapsedRealtime() + 10000
        while (!condition()) { check(SystemClock.elapsedRealtime() < until) { "Timed out" }; SystemClock.sleep(20) }
    }
    private fun ok(response: JSONObject): JSONObject { assertEquals(response.toString(), "ok", response.getString("status")); return response.getJSONObject("result") }
    private fun directState(): JSONObject = JSONObject(domain.get().state(expiry()).getString("json")!!)
    private fun request(op: String) = JSONObject().put("v", 1).put("device_id", server.deviceId).put("operation", op).put("expires_at_ms", expiry())
    private fun connect(identity: String = alias, expected: String = server.deviceId): SSLSocket {
        val ssl = Identity.context(identity) { require(Identity.pin(it) == expected) }
        return (ssl.socketFactory.createSocket("127.0.0.1", server.port) as SSLSocket).apply { soTimeout = 5000; startHandshake() }
    }
    private fun exchange(body: JSONObject, bytes: ByteArray? = null): Pair<JSONObject, ByteArray?> = connect().use { socket ->
        LocalProtocol.write(socket.outputStream, body.toString().toByteArray(Charsets.UTF_8))
        bytes?.let { LocalProtocol.write(socket.outputStream, it) }
        val response = LocalProtocol.json(LocalProtocol.read(socket.inputStream, LocalProtocol.MAX_METADATA))
        response to if (response.has("blob_bytes")) LocalProtocol.read(socket.inputStream, LocalProtocol.MAX_ASSET) else null
    }
    @Before fun start() {
        trust = PairedStore(context); trust.revoke()
        client = Identity.ensure(alias); trust.approve(client)
        domain = DomainConnection(context); await { domain.ready() }
        initial = directState()
        server = LocalListener(InetAddress.getByName("127.0.0.1"), 0, trust,
            LocalProtocol.Gateway(context.cacheDir, domain, Identity.pin(Identity.ensure())))
    }
    @After fun close() {
        if (::server.isInitialized) server.close()
        if (::trust.isInitialized) trust.revoke()
        if (::domain.isInitialized) domain.close()
        Identity.keyStore().apply { deleteEntry(alias); deleteEntry(other) }
    }

    @Test fun realMutualTlsEditsReadBackRetriesAndUndoAcrossUids() {
        val capabilities = ok(exchange(request("capabilities")).first)
        assertTrue(capabilities.getBoolean("paired_service")); assertFalse(capabilities.getBoolean("agentos_qualified"))
        val before = initial.getLong("revision")
        val document = JSONObject(initial.getString("document")).put("title", "Paired evening").toString()
        val preview = request("preview").put("base_revision", before).put("document", document)
        assertFalse(ok(exchange(preview).first).getBoolean("saved"))
        val apply = request("apply").put("request_id", id()).put("base_revision", before).put("document", document)
        val receipt = ok(exchange(apply).first).getJSONObject("receipt")
        assertEquals(before + 1, receipt.getLong("revision"))
        assertEquals(document, ok(exchange(request("state")).first).getString("document"))
        assertEquals(receipt.toString(), ok(exchange(apply).first).getJSONObject("receipt").toString())
        assertEquals("conflict", exchange(JSONObject(apply.toString()).put("document", document + " ")).first.getString("status"))
        val undo = request("undo").put("request_id", id()).put("base_revision", before + 1).put("restore_revision", before)
        ok(exchange(undo).first)
        assertEquals(initial.getString("document"), directState().getString("document"))
        assertNotEquals(context.applicationInfo.uid, context.packageManager.getApplicationInfo("local.sovereigntv", 0).uid)
        assertNull(Identity.keyStore().getKey(Identity.DEVICE_ALIAS, null).encoded)
    }

    @Test fun wrongPeerWrongDeviceAndRevokedAdmittedSessionCannotEdit() {
        Identity.ensure(other)
        assertThrows(Exception::class.java) { connect(other).use { LocalProtocol.write(it.outputStream, request("state").toString().toByteArray()); LocalProtocol.read(it.inputStream, LocalProtocol.MAX_METADATA) } }
        assertThrows(Exception::class.java) { connect(expected = "0".repeat(64)).close() }
        assertEquals("invalid", exchange(request("state").put("device_id", "0".repeat(64))).first.getString("status"))
        val count = server.authenticatedConnections.get()
        connect().use { admitted ->
            await { server.authenticatedConnections.get() > count }
            trust.revoke() // Complete while the authenticated socket is waiting for its command.
            LocalProtocol.write(admitted.outputStream, request("restore_default").put("request_id", id()).put("base_revision", initial.getLong("revision")).toString().toByteArray())
            assertThrows(Exception::class.java) { LocalProtocol.read(admitted.inputStream, LocalProtocol.MAX_METADATA) }
        }
        assertEquals(initial.getLong("revision"), directState().getLong("revision"))
        assertNull(PairedStore(context).paired())
    }

    @Test fun lostReplyReconcilesWithoutAnotherCommit() {
        val before = initial.getLong("revision"); val requestId = id()
        val apply = request("apply").put("request_id", requestId).put("base_revision", before)
            .put("document", JSONObject(initial.getString("document")).put("title", "Reply lost").toString())
        connect().use { LocalProtocol.write(it.outputStream, apply.toString().toByteArray()) } // Intentionally do not read its reply.
        await { domain.get().receipt(requestId, expiry()).getString("status") == "ok" }
        val receipt = ok(exchange(request("receipt").put("request_id", requestId)).first)
        assertEquals(before + 1, receipt.getLong("revision"))
        assertEquals(receipt.toString(), ok(exchange(apply).first).getJSONObject("receipt").toString())
        assertEquals(before + 1, directState().getLong("revision"))
        ok(exchange(request("undo").put("request_id", id()).put("base_revision", before + 1).put("restore_revision", before)).first)
    }

    @Test fun malformedStaleExpiredAndOversizedFramesCannotCreateAReceipt() {
        val before = initial.getLong("revision"); val invalid = id()
        val apply = request("apply").put("request_id", invalid).put("base_revision", before).put("document", "{")
        assertEquals("invalid", exchange(apply).first.getString("status"))
        assertEquals("expired", exchange(request("restore_default").put("request_id", invalid).put("base_revision", before).put("expires_at_ms", 1)).first.getString("status"))
        assertEquals("invalid", exchange(request("state").put("arbitrary_shell", "refused")).first.getString("status"))
        assertEquals("invalid", exchange(request("state").put("expires_at_ms", 1.5)).first.getString("status"))
        connect().use { socket ->
            socket.outputStream.write(java.nio.ByteBuffer.allocate(4).putInt(LocalProtocol.MAX_METADATA + 1).array()); socket.outputStream.flush()
            assertThrows(Exception::class.java) { LocalProtocol.read(socket.inputStream, LocalProtocol.MAX_METADATA) }
        }
        for (malformed in listOf("{operation:'state'}", "{\"v\":1,\"v\":2}", request("state").toString() + " trailing")) {
            connect().use { socket ->
                LocalProtocol.write(socket.outputStream, malformed.toByteArray())
                assertThrows(Exception::class.java) { LocalProtocol.read(socket.inputStream, LocalProtocol.MAX_METADATA) }
            }
        }
        assertEquals("not_found", domain.get().receipt(invalid, expiry()).getString("status"))
        assertEquals(before, directState().getLong("revision"))
    }

    @Test fun certificatePersistenceRejectsPrivateKeyInputAndRecreatedListenerRetainsIdentity() {
        val device = server.deviceId
        assertEquals(Identity.pin(client), Identity.pin(PairedStore(context).paired()!!))
        assertEquals(Identity.pin(client), Identity.pin(Identity.certificate(Identity.pem(client).toByteArray())))
        assertThrows(Exception::class.java) { Identity.certificate((Identity.pem(client) + "-----BEGIN " + "PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----").toByteArray()) }
        server.close()
        server = LocalListener(InetAddress.getByName("127.0.0.1"), 0, PairedStore(context), LocalProtocol.Gateway(context.cacheDir, domain, device))
        assertEquals(device, server.deviceId)
        ok(exchange(request("state")).first)
    }
    @Test fun corruptTrustCannotBeSilentlyReplaced() {
        server.close()
        val file = java.io.File(context.noBackupFilesDir, "paired-controller.der")
        file.writeText("synthetic corrupt trust")
        assertThrows(Exception::class.java) { trust.paired() }
        assertThrows(Exception::class.java) { trust.approve(client) }
        assertEquals("synthetic corrupt trust", file.readText())
        trust.revoke(); trust.approve(client)
        assertEquals(Identity.pin(client), Identity.pin(PairedStore(context).paired()!!))
    }

    @Test fun boundedArtworkTransferUsesNativeStorageAndReturnsExactBytes() {
        val output = java.io.ByteArrayOutputStream()
        output.write(byteArrayOf(137.toByte(),80,78,71,13,10,26,10))
        fun chunk(kind: String, bytes: ByteArray) {
            val data = java.io.DataOutputStream(output); data.writeInt(bytes.size); val name = kind.toByteArray(Charsets.US_ASCII)
            data.write(name); data.write(bytes)
            val crc = java.util.zip.CRC32().apply { update(name); update(bytes) }; data.writeInt(crc.value.toInt())
        }
        val header = java.io.ByteArrayOutputStream().apply { java.io.DataOutputStream(this).apply { writeInt(1); writeInt(1); write(byteArrayOf(8,2,0,0,0)) } }.toByteArray()
        chunk("IHDR", header)
        val compressed = java.io.ByteArrayOutputStream().apply { java.util.zip.DeflaterOutputStream(this).use { it.write(byteArrayOf(0,71,113,99)) } }.toByteArray()
        chunk("IDAT", compressed); chunk("IEND", byteArrayOf())
        val png = output.toByteArray(); val digest = Identity.digest(png)
        val upload = request("artwork.put").put("sha256", digest).put("bytes", png.size)
        ok(exchange(upload, png).first)
        ok(exchange(upload, png).first) // Content hash retries never create another asset.
        val (metadata, returned) = exchange(request("artwork.open").put("sha256", digest))
        ok(metadata); assertArrayEquals(png, returned)
        assertEquals("invalid", exchange(JSONObject(upload.toString()).put("sha256", "0".repeat(64)), png).first.getString("status"))
        assertTrue(context.cacheDir.listFiles()!!.none { it.name.startsWith("asset-") })
    }

}
