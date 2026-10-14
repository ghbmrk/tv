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

/** Synthetic read-only fixtures, test APK only. Framework-only for its separate process. */
public class FixtureProvider extends ContentProvider {
    @Override public boolean onCreate() { return true; }
    @Override public String getType(Uri uri) { return "application/json"; }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) {
        MatrixCursor cursor = new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
        cursor.addRow(new Object[]{"experience.json", 1024});
        return cursor;
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws java.io.FileNotFoundException {
        if (!"r".equals(mode)) throw new SecurityException("Read only");
        String name = uri.getLastPathSegment();
        if (!"valid".equals(name) && !"invalid".equals(name) && !"oversized".equals(name)) throw new SecurityException("Unknown fixture");
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (InputStream stream = getContext().getAssets().open("experience.json")) {
                byte[] buffer = new byte[1024]; int count;
                while ((count = stream.read(buffer)) != -1) bytes.write(buffer, 0, count);
            }
            String sample = bytes.toString("UTF-8");
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
}
