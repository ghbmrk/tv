package local.sovereigntv.control

import java.io.Closeable
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.Socket
import java.security.cert.X509Certificate
import java.util.concurrent.*
import java.util.concurrent.atomic.AtomicBoolean
import javax.net.ssl.SSLServerSocket
import javax.net.ssl.SSLSocket

/** Fixed bounded workers, no outbound connections, no TLS bypass or unauthenticated operation. */
class LocalListener(address: InetAddress, port: Int, private val trust: PairedStore, private val gateway: LocalProtocol.Gateway) : Closeable {
    private val closed = AtomicBoolean(false)
    private val sockets = ConcurrentHashMap.newKeySet<Socket>()
    private val timers = Executors.newSingleThreadScheduledExecutor()
    private val workers = ThreadPoolExecutor(2, 2, 0L, TimeUnit.SECONDS, SynchronousQueue())
    private val certificate = Identity.ensure()
    val deviceId = Identity.pin(certificate)
    internal val authenticatedConnections = java.util.concurrent.atomic.AtomicInteger()
    private val server = (Identity.context(Identity.DEVICE_ALIAS, trust::trusts).serverSocketFactory.createServerSocket() as SSLServerSocket).apply {
        enabledProtocols = supportedProtocols.filter { it == "TLSv1.2" || it == "TLSv1.3" }.toTypedArray()
        needClientAuth = true
        reuseAddress = false
        bind(InetSocketAddress(address, port), 4)
    }
    val port get() = server.localPort
    private val acceptor = Thread({
        while (!closed.get()) {
            val socket = try { server.accept() as SSLSocket } catch (_: Exception) { break }
            sockets.add(socket)
            try { workers.execute { serve(socket) } }
            catch (_: RejectedExecutionException) { sockets.remove(socket); socket.close() }
        }
    }, "local-control-accept").apply { start() }
    private fun serve(socket: SSLSocket) {
        // Absolute lifetime also bounds slow trickles and stalled output; SO_TIMEOUT alone does not.
        val timeout = try { timers.schedule({ runCatching { socket.close() } }, 45, TimeUnit.SECONDS) }
            catch (_: RejectedExecutionException) { sockets.remove(socket); socket.close(); return }
        try {
            socket.soTimeout = 5000; socket.startHandshake()
            val peer = socket.session.peerCertificates.single() as X509Certificate
            val pin = Identity.pin(peer)
            authenticatedConnections.incrementAndGet()
            val readTimeout = timers.schedule({ runCatching { socket.close() } }, 10, TimeUnit.SECONDS)
            try {
                val request = LocalProtocol.requestJson(LocalProtocol.read(socket.inputStream, LocalProtocol.MAX_METADATA))
                trust.authorized(pin) { Unit }
                val prepared = try { gateway.prepare(request, socket.inputStream) }
                    catch (_: IllegalArgumentException) { LocalProtocol.Gateway.Prepared { gateway.invalid() } }
                    catch (_: org.json.JSONException) { LocalProtocol.Gateway.Prepared { gateway.invalid() } }
                    catch (_: ArithmeticException) { LocalProtocol.Gateway.Prepared { gateway.invalid() } }
                readTimeout.cancel(false)
                // Trust lock spans only invocation, not slow request input. After revoke completes,
                // a request from an already-authenticated socket cannot reach the domain.
                val reply = trust.authorized(pin) { prepared.invoke() }
                LocalProtocol.write(socket.outputStream, reply.body.toString().toByteArray(Charsets.UTF_8))
                reply.asset?.let { LocalProtocol.write(socket.outputStream, it) }
            } finally { readTimeout.cancel(false) }
        } catch (_: Exception) {
            // TLS, disconnected clients and Binder uncertainty never become a claimed rollback.
            // No document, certificate, address, exception text or credential is logged.
        } finally { timeout.cancel(false); sockets.remove(socket); runCatching { socket.close() } }
    }
    override fun close() {
        if (closed.compareAndSet(false, true)) {
            server.close(); sockets.forEach { runCatching { it.close() } }
            workers.shutdownNow(); timers.shutdownNow()
        }
    }
}
