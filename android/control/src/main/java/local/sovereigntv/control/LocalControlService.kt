package local.sovereigntv.control

import android.app.*
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.net.Inet4Address
import java.net.InetAddress
import java.net.NetworkInterface
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

object ControlStatus {
    var text by mutableStateOf("Local control is off")
        private set
    var active by mutableStateOf(false)
        private set
    fun update(value: String, running: Boolean) { Handler(Looper.getMainLooper()).post { text = value; active = running } }
}
object LocalAddresses {
    fun current(): List<InetAddress> = NetworkInterface.getNetworkInterfaces()?.toList().orEmpty()
        .filter { it.isUp && !it.isLoopback }.flatMap { it.inetAddresses.toList() }
        .filter { it is Inet4Address && it.isSiteLocalAddress && !it.isLinkLocalAddress }.distinctBy { it.hostAddress }
}

/** Explicit local activation only. No boot receiver, exported command channel or sticky restart. */
class LocalControlService : Service() {
    private val worker = Executors.newSingleThreadExecutor()
    private val closed = AtomicBoolean(false)
    private val started = AtomicBoolean(false)
    @Volatile private var failed = false
    @Volatile private var listener: LocalListener? = null
    private var domain: DomainConnection? = null
    override fun onCreate() {
        super.onCreate()
        val channel = NotificationChannel("local-control", "Local control", NotificationManager.IMPORTANCE_LOW)
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        val open = PendingIntent.getActivity(this, 0, Intent(this, ControlActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(this, "local-control").setContentTitle("Sovereign local control")
            .setContentText("Owner-approved local connection active").setSmallIcon(android.R.drawable.ic_lock_lock).setContentIntent(open).setOngoing(true).build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        else startForeground(1, notification)
        domain = runCatching { DomainConnection(this) }.getOrNull()
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (started.compareAndSet(false, true)) {
            val selected = intent?.getStringExtra("address")
            ControlStatus.update("Starting local control", false)
            worker.execute {
                try {
                    cacheDir.listFiles()?.filter { it.name.startsWith("asset-") && it.name.endsWith(".png") }?.forEach { check(it.delete()) }
                    val address = LocalAddresses.current().single { it.hostAddress == selected }
                    val trust = PairedStore(this); check(trust.paired() != null)
                    val identity = Identity.ensure()
                    val bridge = requireNotNull(domain)
                    val server = LocalListener(address, PORT, trust, LocalProtocol.Gateway(cacheDir, bridge, Identity.pin(identity)))
                    listener = server
                    if (closed.get()) { server.close(); return@execute }
                    ControlStatus.update("Listening on ${address.hostAddress}:$PORT", true)
                } catch (_: Exception) {
                    failed = true
                    ControlStatus.update("Could not start • check pairing, local network and the Home app", false)
                    Handler(mainLooper).post { stopSelf() }
                }
            }
        }
        return START_NOT_STICKY
    }
    override fun onBind(intent: Intent): IBinder? = null
    override fun onDestroy() {
        closed.set(true); listener?.close(); domain?.close(); domain = null; worker.shutdownNow()
        if (!failed) ControlStatus.update("Local control is off", false)
        super.onDestroy()
    }
    companion object { const val PORT = 9443 }
}
