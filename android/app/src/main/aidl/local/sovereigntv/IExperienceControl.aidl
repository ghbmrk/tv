package local.sovereigntv;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
/** Owner-signed local domain bridge. Not a LAN or guest-facing interface. */
interface IExperienceControl {
    Bundle capabilities(long expiresAtUtcMillis);
    Bundle state(long expiresAtUtcMillis);
    Bundle preview(long baseRevision, @nullable String document, long expiresAtUtcMillis);
    Bundle apply(@nullable String requestId, long baseRevision, @nullable String document, long expiresAtUtcMillis);
    Bundle undo(@nullable String requestId, long baseRevision, long restoreRevision, long expiresAtUtcMillis);
    Bundle receipt(@nullable String requestId, long expiresAtUtcMillis);
    Bundle putArtwork(@nullable String digest, in @nullable ParcelFileDescriptor source, long expiresAtUtcMillis);
    Bundle openArtwork(@nullable String digest, long expiresAtUtcMillis);
    Bundle restoreDefault(@nullable String requestId, long baseRevision, long expiresAtUtcMillis);
    Bundle applications(long expiresAtUtcMillis);
}
