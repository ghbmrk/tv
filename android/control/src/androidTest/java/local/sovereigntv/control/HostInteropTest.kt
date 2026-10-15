package local.sovereigntv.control

import android.os.SystemClock
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.net.InetAddress

/** Owned-emulator fixture driven by tools/qualify_control_interop.py, never a production endpoint. */
@RunWith(AndroidJUnit4::class)
class HostInteropTest {
    @Test fun externalExecutorRoundTrip() {
        assumeTrue(InstrumentationRegistry.getArguments().getString("host_interop") == "true")
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val incoming = File(context.filesDir, "interop-client-public.pem")
        val ready = File(context.filesDir, "interop-ready.json")
        val done = File(context.filesDir, "interop-done")
        val trust = PairedStore(context)
        val domain = DomainConnection(context)
        var listener: LocalListener? = null
        try {
            trust.revoke(); trust.approve(Identity.certificate(incoming.readBytes()))
            val until = SystemClock.elapsedRealtime() + 10000
            while (!domain.ready()) { check(SystemClock.elapsedRealtime() < until); SystemClock.sleep(20) }
            fun state() = JSONObject(domain.get().state(System.currentTimeMillis() + 10000).getString("json")!!)
            val before = state()
            listener = LocalListener(InetAddress.getByName("127.0.0.1"), 19443, trust,
                LocalProtocol.Gateway(context.cacheDir, domain, Identity.pin(Identity.ensure())))
            val temporary = File(context.filesDir, "interop-ready.tmp")
            temporary.writeText(JSONObject().put("public_certificate", Identity.pem(Identity.ensure())).toString())
            check(temporary.renameTo(ready))
            val deadline = SystemClock.elapsedRealtime() + 40000
            while (!done.exists()) { check(SystemClock.elapsedRealtime() < deadline); SystemClock.sleep(20) }
            val after = state()
            assertEquals(before.getString("document"), after.getString("document"))
            assertEquals(before.getLong("revision") + 2, after.getLong("revision"))
        } finally {
            listener?.close(); domain.close(); trust.revoke()
            listOf(incoming, ready, done, File(context.filesDir, "interop-ready.tmp")).forEach { it.delete() }
        }
    }
}
