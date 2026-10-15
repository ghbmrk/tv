package local.sovereigntv.controlprobe;

import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.os.*;
import android.os.Process;
import local.sovereigntv.IExperienceControl;
import org.json.JSONObject;
import java.util.UUID;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/** Test-only, signature-protected caller. No network, arbitrary operation or forwarded handle. */
public final class ControllerProbe extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    private static long expiry() { return System.currentTimeMillis() + 10000; }
    private static String id() { return UUID.randomUUID().toString(); }
    private static JSONObject ok(Bundle response) throws Exception {
        if (!"ok".equals(response.getString("status"))) throw new IllegalStateException("Probe operation refused");
        return new JSONObject(response.getString("json"));
    }
    @Override public Bundle call(String method, String argument, Bundle extras) {
        getContext().enforceCallingPermission("local.sovereigntv.permission.CONTROL_EXPERIENCE", "Owner-signed test caller required");
        if (!"roundtrip".equals(method)) throw new IllegalArgumentException("Unknown probe");
        final long identity = Binder.clearCallingIdentity();
        final LinkedBlockingQueue<IBinder> connected = new LinkedBlockingQueue<>();
        final ServiceConnection connection = new ServiceConnection() {
            @Override public void onServiceConnected(ComponentName name, IBinder binder) { connected.offer(binder); }
            @Override public void onServiceDisconnected(ComponentName name) { }
        };
        boolean bound = false;
        try {
            Context context = getContext();
            bound = context.bindService(new Intent().setComponent(new ComponentName("local.sovereigntv", "local.sovereigntv.ExperienceControlService")), connection, Context.BIND_AUTO_CREATE);
            if (!bound) throw new IllegalStateException("Probe binding refused");
            IBinder binder = connected.poll(10, TimeUnit.SECONDS);
            if (binder == null || binder.queryLocalInterface("local.sovereigntv.IExperienceControl") != null) throw new IllegalStateException("Expected remote domain");
            IExperienceControl control = IExperienceControl.Stub.asInterface(binder);
            JSONObject before = ok(control.state(expiry()));
            String original = before.getString("document");
            JSONObject document = new JSONObject(original).put("title", "Signed controller");
            String exact = document.toString();
            long base = before.getLong("revision");
            String request = id();
            JSONObject committed = ok(control.apply(request, base, exact, expiry())).getJSONObject("receipt");
            JSONObject retried = ok(control.apply(request, base, exact, expiry())).getJSONObject("receipt");
            JSONObject saved = ok(control.state(expiry()));
            if (!committed.toString().equals(retried.toString()) || !exact.equals(saved.getString("document"))) throw new IllegalStateException("Probe read-back mismatch");
            long revision = saved.getLong("revision");
            ok(control.apply(id(), revision, original, expiry()));
            JSONObject restored = ok(control.state(expiry()));
            Bundle result = new Bundle();
            result.putInt("caller_uid", Process.myUid());
            result.putBoolean("remote_domain", true);
            result.putBoolean("read_back", true);
            result.putBoolean("durable_retry", true);
            result.putBoolean("restored", original.equals(restored.getString("document")) && restored.getLong("revision") == base + 2);
            return result;
        } catch (Exception error) { throw new IllegalStateException("Signed controller qualification failed", error); }
        finally {
            if (bound) getContext().unbindService(connection);
            Binder.restoreCallingIdentity(identity);
        }
    }
    @Override public Cursor query(Uri u, String[] p, String s, String[] a, String o) { throw new UnsupportedOperationException(); }
    @Override public String getType(Uri u) { return null; }
    @Override public Uri insert(Uri u, ContentValues v) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri u, String s, String[] a) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { throw new UnsupportedOperationException(); }
}
