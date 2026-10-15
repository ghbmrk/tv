package local.sovereigntv.control

import android.app.Application
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import java.io.ByteArrayOutputStream
import java.security.cert.X509Certificate
import java.util.concurrent.Executors

class ControlModel(app: Application) : AndroidViewModel(app) {
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val trust = PairedStore(app)
    private var closed = false
    var device by mutableStateOf<X509Certificate?>(null); private set
    var paired by mutableStateOf<X509Certificate?>(null); private set
    var trustUnavailable by mutableStateOf(false); private set
    var pending by mutableStateOf<X509Certificate?>(null); private set
    var addresses by mutableStateOf(emptyList<String>()); private set
    var busy by mutableStateOf(false); private set
    var message by mutableStateOf("Preparing local identity"); private set
    init { refresh() }
    private fun <T> work(progress: String, action: () -> T, success: (T) -> Unit) {
        if (busy || closed) return
        busy = true; message = progress
        worker.execute {
            val result = runCatching(action)
            main.post { if (!closed) { busy = false; result.onSuccess(success).onFailure { message = "Operation refused • saved identity and trust preserved" } } }
        }
    }
    fun refresh() = work("Reading local identity", {
        Triple(Identity.ensure(), runCatching { trust.paired() }, LocalAddresses.current().mapNotNull { it.hostAddress })
    }) { (identity, controller, local) -> device = identity; trustUnavailable = controller.isFailure; paired = controller.getOrNull(); addresses = local; message = if (trustUnavailable) "Stored trust unreadable • remove it locally before pairing" else if (paired == null) "No agent trusted" else "One agent trusted" }
    fun importCertificate(uri: Uri) = work("Checking public certificate", {
        val stream = requireNotNull(getApplication<Application>().contentResolver.openInputStream(uri))
        val bytes = stream.use {
            val output = ByteArrayOutputStream(); val block = ByteArray(4096)
            while (true) { val n = it.read(block); if (n < 0) break; require(n > 0 && output.size() + n <= 16384); output.write(block, 0, n) }
            output.toByteArray()
        }
        Identity.certificate(bytes)
    }) { pending = it; message = "Review access before connecting" }
    fun cancel() { if (!busy) { pending = null; message = "Certificate not approved" } }
    fun approve() {
        val candidate = pending ?: return
        if (paired != null || trustUnavailable || ControlStatus.active) { message = "Remove the existing agent first"; return }
        work("Saving owner approval", { trust.approve(candidate) }) { paired = candidate; pending = null; message = "Agent trusted • local control remains off" }
    }
    fun revoke() {
        getApplication<Application>().stopService(Intent(getApplication(), LocalControlService::class.java))
        work("Removing agent • finishing any started change", { trust.revoke() }) { paired = null; trustUnavailable = false; pending = null; message = "Agent removed • existing connections closed" }
    }
    fun export(uri: Uri) {
        val certificate = device ?: return
        work("Exporting public device certificate", {
            requireNotNull(getApplication<Application>().contentResolver.openOutputStream(uri, "wt")).use { it.write(Identity.pem(certificate).toByteArray(Charsets.US_ASCII)) }
        }) { message = "Public certificate exported • verify its fingerprint on the executor" }
    }
    fun start(address: String) {
        if (busy || paired == null || address !in addresses) return
        getApplication<Application>().startForegroundService(Intent(getApplication(), LocalControlService::class.java).putExtra("address", address))
    }
    fun stop() { getApplication<Application>().stopService(Intent(getApplication(), LocalControlService::class.java)); message = "Connection closed • reconcile any change whose reply was lost" }
    override fun onCleared() { closed = true; worker.shutdownNow() }
}
