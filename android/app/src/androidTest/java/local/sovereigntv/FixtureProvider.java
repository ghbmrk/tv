package local.sovereigntv;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.io.DataOutputStream;
import java.util.zip.CRC32;
import java.util.zip.DeflaterOutputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.json.JSONArray;
import org.json.JSONObject;

/** Synthetic read-only fixtures, test APK only. Framework-only for its separate process. */
public class FixtureProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    @Override public android.os.Bundle call(String method, String arg, android.os.Bundle extras) {
        if (!"bridge-denials".equals(method)) throw new SecurityException("Unknown fixture operation");
        android.os.Bundle result = new android.os.Bundle();
        try {
            result.putBoolean("different_uid", android.os.Process.myUid() != getContext().getPackageManager().getApplicationInfo("local.sovereigntv", 0).uid);
        } catch (Exception error) { throw new IllegalStateException("Fixture target missing"); }
        android.content.ServiceConnection connection = new android.content.ServiceConnection() {
            public void onServiceConnected(android.content.ComponentName name, android.os.IBinder service) { }
            public void onServiceDisconnected(android.content.ComponentName name) { }
        };
        try {
            boolean bound = getContext().bindService(new android.content.Intent().setComponent(new android.content.ComponentName("local.sovereigntv", "local.sovereigntv.ExperienceControlService")), connection, android.content.Context.BIND_AUTO_CREATE);
            if (bound) getContext().unbindService(connection);
            result.putBoolean("bind_denied", false);
        } catch (SecurityException denied) { result.putBoolean("bind_denied", true); }
        android.os.Parcel data = android.os.Parcel.obtain(), reply = android.os.Parcel.obtain();
        try {
            data.writeInterfaceToken("local.sovereigntv.IExperienceControl");
            data.writeLong(System.currentTimeMillis() + 5000);
            extras.getBinder("forwarded").transact(android.os.IBinder.FIRST_CALL_TRANSACTION, data, reply, 0);
            reply.readException();
            result.putBoolean("forwarded_handle_denied", false);
        } catch (SecurityException denied) { result.putBoolean("forwarded_handle_denied", true);
        } catch (android.os.RemoteException error) { throw new IllegalStateException("Fixture IPC failed");
        } finally { data.recycle(); reply.recycle(); }
        try {
            getContext().getContentResolver().call(Uri.parse("content://local.sovereigntv.controlprobe"), "roundtrip", null, null);
            result.putBoolean("probe_denied", false);
        } catch (SecurityException denied) { result.putBoolean("probe_denied", true); }
        return result;
    }
    @Override public String getType(Uri uri) { return "bundle".equals(uri.getLastPathSegment()) ? "application/zip" : "application/json"; }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) {
        MatrixCursor cursor = new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
        cursor.addRow(new Object[]{"experience.json", 1024});
        return cursor;
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws java.io.FileNotFoundException {
        if (!"r".equals(mode)) throw new SecurityException("Read only");
        String name = uri.getLastPathSegment();
        if (!"valid".equals(name) && !"invalid".equals(name) && !"oversized".equals(name) && !"bundle".equals(name)) throw new SecurityException("Unknown fixture");
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream stream = getContext().getAssets().open("experience.json")) {
                byte[] buffer = new byte[1024]; int count;
                while ((count = stream.read(buffer)) != -1) bytes.write(buffer, 0, count);
            }
            String sample = bytes.toString("UTF-8");
            if ("bundle".equals(name)) {
                File file = new File(getContext().getCacheDir(), "fixture-bundle.zip");
                try (FileOutputStream stream = new FileOutputStream(file)) { stream.write(bundle(sample)); }
                return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
            }
            String content;
            if ("valid".equals(name)) content = sample.replace("Household TV", "Runtime household")
                .replace("\"id\": \"watch\"", "\"id\": \"header\"")
                .replace("\"night\"", "\"warm\"")
                .replace("\"target\": \"netflix\"", "\"target\": \"missing_fixture\"");
            else if ("invalid".equals(name)) content = sample.replace("\"night\"", "\"unsupported\"");
            else { char[] oversized = new char[65537]; java.util.Arrays.fill(oversized, 'x'); content = new String(oversized); }
            File file = new File(getContext().getCacheDir(), "fixture-" + name + ".json");
            try (FileOutputStream stream = new FileOutputStream(file)) { stream.write(content.getBytes(StandardCharsets.UTF_8)); }
            return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
        } catch (IOException error) { throw new java.io.FileNotFoundException(error.getMessage()); }
    }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new SecurityException("Read only"); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new SecurityException("Read only"); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new SecurityException("Read only"); }

    public static byte[] png(int red, int green, int blue) throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        result.write(new byte[]{(byte)137,80,78,71,13,10,26,10});
        ByteArrayOutputStream header = new ByteArrayOutputStream();
        DataOutputStream fields = new DataOutputStream(header);
        fields.writeInt(2); fields.writeInt(2); fields.write(new byte[]{8,2,0,0,0});
        chunk(result, "IHDR", header.toByteArray());
        ByteArrayOutputStream compressed = new ByteArrayOutputStream();
        try (DeflaterOutputStream z = new DeflaterOutputStream(compressed)) {
            for (int row = 0; row < 2; row++) { z.write(0); for (int col = 0; col < 2; col++) z.write(new byte[]{(byte)red,(byte)green,(byte)blue}); }
        }
        chunk(result, "IDAT", compressed.toByteArray()); chunk(result, "IEND", new byte[0]);
        return result.toByteArray();
    }
    private static void chunk(ByteArrayOutputStream result, String kind, byte[] payload) throws IOException {
        byte[] type = kind.getBytes(StandardCharsets.US_ASCII);
        DataOutputStream out = new DataOutputStream(result); out.writeInt(payload.length); out.write(type); out.write(payload);
        CRC32 crc = new CRC32(); crc.update(type); crc.update(payload); out.writeInt((int)crc.getValue());
    }
    public static byte[] bundle(String sample) throws IOException {
        try {
            byte[] first = png(50,120,180), second = png(180,100,50);
            String a = digest(first), b = digest(second);
            JSONObject root = new JSONObject(sample).put("schema_version", 2).put("title", "Runtime gallery");
            JSONArray items = new JSONArray();
            items.put(new JSONObject().put("id","first_art").put("title","First artwork").put("kind","artwork").put("target",a).put("visible",true));
            items.put(new JSONObject().put("id","second_art").put("title","Second artwork").put("kind","artwork").put("target",b).put("visible",true));
            items.put(new JSONObject().put("id","hidden_art").put("title","Hidden artwork").put("kind","artwork").put("target",a).put("visible",false));
            root.put("collections", new JSONArray().put(new JSONObject().put("id","artwork").put("title","Local artwork").put("items",items)));
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            try (ZipOutputStream zip = new ZipOutputStream(output)) {
                zip.putNextEntry(new ZipEntry("experience.json")); zip.write(root.toString().getBytes(StandardCharsets.UTF_8)); zip.closeEntry();
                zip.putNextEntry(new ZipEntry("artwork/" + a + ".png")); zip.write(first); zip.closeEntry();
                zip.putNextEntry(new ZipEntry("artwork/" + b + ".png")); zip.write(second); zip.closeEntry();
            }
            return output.toByteArray();
        } catch (org.json.JSONException error) { throw new IOException(error); }
    }
    private static String digest(byte[] data) throws IOException {
        try {
            byte[] hash = java.security.MessageDigest.getInstance("SHA-256").digest(data);
            StringBuilder result = new StringBuilder();
            for (byte value : hash) result.append(String.format(java.util.Locale.ROOT, "%02x", value));
            return result.toString();
        } catch (java.security.NoSuchAlgorithmException error) { throw new IOException(error); }
    }
}
