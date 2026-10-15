package local.sovereigntv

import android.app.Service
import android.content.Intent
import android.os.Binder
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.IBinder
import android.os.Parcel
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.system.Os
import android.system.OsConstants
import org.json.JSONArray
import org.json.JSONObject

/** Signature-protected domain bridge for an owner-signed controller, never a guest/LAN endpoint. */
class ExperienceControlService : Service() {
    private val repository by lazy { ExperienceRepository(this) }
    private val artwork by lazy { ArtworkStore(this) }
    private class Expired : IllegalStateException()
    private fun authority() = enforceCallingPermission(PERMISSION, "Owner-signed control permission required")
    private fun deadline(utc: Long, uid: Int): () -> Unit {
        val remaining = Math.subtractExact(utc, System.currentTimeMillis())
        if (remaining <= 0) throw Expired()
        require(remaining <= 30000)
        val limit = SystemClock.elapsedRealtime() + remaining
        return { if (checkPermission(PERMISSION, -1, uid) != PackageManager.PERMISSION_GRANTED) throw SecurityException(); if (SystemClock.elapsedRealtime() >= limit) throw Expired() }
    }
    private fun result(code: String, value: JSONObject? = null, file: ParcelFileDescriptor? = null) = Bundle().apply {
        putInt("api_version", 1); putString("status", code)
        if (value != null) putString("json", value.toString())
        if (file != null) putParcelable("file", file)
    }
    private fun call(utc: Long, effect: Boolean = false, operation: (guard: () -> Unit) -> Bundle): Bundle {
        val uid = Binder.getCallingUid()
        val identity = Binder.clearCallingIdentity()
        try {
            val guard = deadline(utc, uid); guard(); return operation(guard)
        } catch (_: Expired) { return result("expired")
        } catch (_: SecurityException) { return result("unauthorized")
        } catch (_: ExperienceJournal.Conflict) { return result("conflict")
        } catch (_: ExperienceJournal.Capacity) { return result("capacity")
        } catch (_: org.json.JSONException) { return result("invalid")
        } catch (_: java.util.zip.DataFormatException) { return result("invalid")
        } catch (_: ArithmeticException) { return result("invalid")
        } catch (_: IllegalArgumentException) { return result("invalid")
        } catch (_: Exception) { return result(if (effect) "unknown" else "unavailable")
        } finally { Binder.restoreCallingIdentity(identity) }
    }

    private fun stateJson(loaded: ExperienceRepository.Loaded): JSONObject {
        check(!loaded.journalUnavailable)
        return JSONObject().put("revision", loaded.revision).put("document", loaded.document)
            .put("document_sha256", ExperienceJournal.sha256(loaded.document)).put("recovered_default", loaded.restoredDefault)
    }
    private fun receiptJson(receipt: ExperienceJournal.Receipt) = JSONObject()
        .put("request_id", receipt.requestId).put("revision", receipt.revision)
        .put("previous_revision", receipt.previousRevision).put("document_sha256", receipt.documentSha256)
    private fun committed(receipt: ExperienceJournal.Receipt): Bundle {
        val saved = repository.load()
        if (saved.revision == receipt.revision) check(ExperienceJournal.sha256(saved.document) == receipt.documentSha256)
        val response = result("ok", JSONObject().put("receipt", receiptJson(receipt)).put("state", stateJson(saved)))
        sendBroadcast(Intent(CHANGED).setPackage(packageName), PERMISSION)
        return response
    }

    private val control = object : IExperienceControl.Stub() {
        override fun onTransact(code: Int, data: Parcel, reply: Parcel?, flags: Int): Boolean {
            // Binding permission alone is insufficient if a trusted client passes its Binder handle onward.
            if (code != IBinder.INTERFACE_TRANSACTION) {
                authority()
                // Every declared method is synchronous: reject raw one-way calls before any effect.
                require(flags and IBinder.FLAG_ONEWAY == 0) { "Synchronous reply required" }
            }
            return super.onTransact(code, data, reply, flags)
        }
        override fun capabilities(expiresAtUtcMillis: Long) = call(expiresAtUtcMillis) {
            result("ok", JSONObject().put("mode", "signature-protected-native-domain")
                .put("operations", JSONArray(listOf("state", "preview", "apply", "undo", "receipt", "artwork.put", "artwork.open", "restore_default")))
                .put("network_endpoint", false).put("paired_service", false).put("agentos_qualified", false)
                .put("hardware_control", false).put("capture", false).put("max_deadline_ms", 30000)
                .put("max_document_bytes", 65536).put("max_artwork_bytes", ArtworkStore.MAX_BYTES))
        }
        override fun state(expiresAtUtcMillis: Long) = call(expiresAtUtcMillis) { result("ok", stateJson(repository.load())) }
        override fun preview(baseRevision: Long, document: String?, expiresAtUtcMillis: Long) = call(expiresAtUtcMillis) { guard ->
            val preview = repository.preview(baseRevision, requireNotNull(document)); guard()
            result("ok", stateJson(preview).put("saved", false).put("displayed_on_tv", false))
        }
        override fun apply(requestId: String?, baseRevision: Long, document: String?, expiresAtUtcMillis: Long) = call(expiresAtUtcMillis, true) { guard ->
            committed(repository.apply(requireNotNull(requestId), baseRevision, requireNotNull(document), guard))
        }
        override fun restoreDefault(requestId: String?, baseRevision: Long, expiresAtUtcMillis: Long) = call(expiresAtUtcMillis, true) { guard ->
            committed(repository.applyDefault(requireNotNull(requestId), baseRevision, guard))
        }
        override fun undo(requestId: String?, baseRevision: Long, restoreRevision: Long, expiresAtUtcMillis: Long) = call(expiresAtUtcMillis, true) { guard ->
            committed(repository.undo(requireNotNull(requestId), baseRevision, restoreRevision, guard))
        }
        override fun receipt(requestId: String?, expiresAtUtcMillis: Long) = call(expiresAtUtcMillis) {
            repository.receipt(requireNotNull(requestId))?.let { result("ok", receiptJson(it)) } ?: result("not_found")
        }
        override fun putArtwork(digest: String?, source: ParcelFileDescriptor?, expiresAtUtcMillis: Long): Bundle = source.use { descriptor ->
            call(expiresAtUtcMillis, true) { guard ->
                require(Regex("[a-f0-9]{64}").matches(requireNotNull(digest)) && descriptor != null)
                val stat = Os.fstat(descriptor.fileDescriptor)
                require(OsConstants.S_ISREG(stat.st_mode) && stat.st_size in 1..ArtworkStore.MAX_BYTES.toLong())
                val bytes = ParcelFileDescriptor.AutoCloseInputStream(descriptor).use(ArtworkStore::readBounded)
                guard(); artwork.put(bytes, digest, guard)
                result("ok", JSONObject().put("sha256", digest).put("bytes", bytes.size))
            }
        }
        override fun openArtwork(digest: String?, expiresAtUtcMillis: Long) = call(expiresAtUtcMillis) { guard ->
            val file = artwork.openReadOnly(requireNotNull(digest))
            try { guard(); result("ok", JSONObject().put("sha256", digest), file) }
            catch (error: Exception) { file.close(); throw error }
        }
    }
    override fun onBind(intent: Intent): IBinder = control
    companion object {
        const val PERMISSION = "local.sovereigntv.permission.CONTROL_EXPERIENCE"
        const val CHANGED = "local.sovereigntv.EXPERIENCE_CHANGED"
    }
}
