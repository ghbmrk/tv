package local.sovereigntv.control

import android.content.*
import android.os.IBinder
import local.sovereigntv.IExperienceControl
import java.io.Closeable
import java.util.concurrent.atomic.AtomicReference

/** A dead Binder is never treated as a failed/rolled-back effect or blindly replayed. */
class DomainConnection(private val context: Context) : Closeable {
    private val endpoint = AtomicReference<IExperienceControl?>()
    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, binder: IBinder) { endpoint.set(IExperienceControl.Stub.asInterface(binder)) }
        override fun onServiceDisconnected(name: ComponentName) { endpoint.set(null) }
        override fun onBindingDied(name: ComponentName) { endpoint.set(null) }
    }
    private val bound = context.bindService(Intent().setComponent(ComponentName("local.sovereigntv", "local.sovereigntv.ExperienceControlService")), connection, Context.BIND_AUTO_CREATE)
    fun ready() = endpoint.get() != null
    fun get(): IExperienceControl = requireNotNull(endpoint.get()) { "Domain unavailable" }
    override fun close() { if (bound) context.unbindService(connection); endpoint.set(null) }
}
