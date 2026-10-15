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
class LocalListener(address: InetAddress, port: Int, private val trust: PairedStore, private val gateway: LocalProtocol.Gateway, private val budgets: Budgets = Budgets()) : Closeable {
    data class Budgets(val socketMillis: Int = 5000, val inputMillis: Long = 10000, val lifetimeMillis: Long = 45000) {
        init { require(socketMillis in 100..5000 && inputMillis in 100..10000 && lifetimeMillis in 100..45000) }
    }
    private val closed = AtomicBoolean(false)
    private val sockets = ConcurrentHashMap.newKeySet<Socket>()
    private val timers = ScheduledThreadPoolExecutor(1).apply { removeOnCancelPolicy = true }
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
    internal val pendingDeadlines get() = timers.queue.size
    internal val activeWorkers get() = workers.activeCount
    internal val terminated get() = workers.isTerminated && timers.isTerminated && !acceptor.isAlive
    private val acceptor = Thread({
        android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_BACKGROUND)
        while (!closed.get()) {
            val socket = try { server.accept() as SSLSocket } catch (_: Exception) { break }
            sockets.add(socket)
            try { workers.execute { serve(socket) } }
            catch (_: RejectedExecutionException) { sockets.remove(socket); socket.close() }
        }
    }, "local-control-accept").apply { start() }
    private fun serve(socket: SSLSocket) {
        android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_BACKGROUND)
        // Absolute lifetime also bounds slow trickles and stalled output; SO_TIMEOUT alone does not.
        val timeout = try { timers.schedule({ runCatching { socket.close() } }, budgets.lifetimeMillis, TimeUnit.MILLISECONDS) }
            catch (_: RejectedExecutionException) { sockets.remove(socket); socket.close(); return }
        try {
            socket.soTimeout = budgets.socketMillis; socket.startHandshake()
            val peer = socket.session.peerCertificates.single() as X509Certificate
            val pin = Identity.pin(peer)
            authenticatedConnections.incrementAndGet()
            val readTimeout = timers.schedule({ runCatching { socket.close() } }, budgets.inputMillis, TimeUnit.MILLISECONDS)
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
