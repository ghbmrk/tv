package local.sovereigntv

import android.app.Application
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import java.util.UUID
import kotlinx.coroutines.asCoroutineDispatcher

/** Disk, parsing and package discovery never run on the navigation/frame path. */
class ExperienceViewModel(application: Application) : AndroidViewModel(application) {
    private val repository by lazy(LazyThreadSafetyMode.NONE) { ExperienceRepository(application) }
    private val worker = Executors.newSingleThreadExecutor()
    val diskDispatcher = worker.asCoroutineDispatcher()
    private val artwork by lazy(LazyThreadSafetyMode.NONE) { ArtworkStore(application) }
    fun loadArtwork(id: String, width: Int, height: Int) = artwork.bitmap(id, width, height)
    private val main = Handler(Looper.getMainLooper())
    private val closed = AtomicBoolean(false)
    private var activities by mutableStateOf(emptyMap<String, ComponentName>())
    private var catalogReady by mutableStateOf(false)
    private var catalogPending = false
    private var refreshQueued = false
    private var refreshAgain = false
    private var externalPending = false
    var experience by mutableStateOf<Experience?>(null)
        private set
    var preview by mutableStateOf<ExperienceRepository.Loaded?>(null)
        private set
    var revision by mutableLongStateOf(0L)
        private set
    var unconfirmed by mutableStateOf(false)
        private set
    private data class Change(val requestId: String, val base: Long, val document: String? = null, val restore: Long? = null, val success: String)
    private var pending: Change? = null
    var busy by mutableStateOf(false)
        private set
    var message by mutableStateOf("Loading local Home")
        private set

    init { update("Loading local Home", "Local Home • no agentOS connection") { repository.load() } }

    fun importDocument(uri: Uri) {
        val base = revision
        work("Preparing preview", {
            val stream = getApplication<Application>().contentResolver.openInputStream(uri) ?: error("File unavailable")
            repository.previewImport(base, stream)
        }) {
            preview = it
            message = "Unsaved preview • apply or cancel"
        }
    }

    fun importArtwork(uri: Uri) {
        val base = revision
        work("Preparing artwork preview", {
            val stream = getApplication<Application>().contentResolver.openInputStream(uri) ?: error("Image unavailable")
            repository.previewArtwork(base, stream)
        }, failure = { message = "Artwork import refused • use plain 8-bit RGB/RGBA PNG within the size limits; saved experience preserved" }) {
            preview = it
            message = "Unsaved artwork preview • apply or cancel"
        }
    }

    fun cancelPreview() {
        if (!busy) { preview = null; message = "Preview cancelled; saved experience unchanged"; drainExternalChange() }
    }

    fun applyPreview() {
        val candidate = preview ?: return
        change(Change(UUID.randomUUID().toString(), candidate.revision, document = candidate.document, success = "Imported local experience"))
    }

    fun undo() {
        val base = revision
        if (base < 2) return
        change(Change(UUID.randomUUID().toString(), base, restore = base - 1, success = "Last change undone"))
    }

    fun reset() {
        val base = revision
        change(Change(UUID.randomUUID().toString(), base, success = "Default Home restored"))
    }

    fun reload() = update("Loading saved experience", "Saved experience loaded") { repository.load() }

    fun retryChange() { pending?.let { change(it, retry = true) } }

    private fun change(request: Change, retry: Boolean = false) {
        if (busy || (pending != null && !retry)) return
        pending = request
        work("Applying local change", {
            var refusal: Exception? = null
            val receipt = try {
                when {
                    request.restore != null -> repository.undo(request.requestId, request.base, request.restore)
                    request.document != null -> repository.apply(request.requestId, request.base, request.document)
                    else -> repository.applyDefault(request.requestId, request.base)
                }
            } catch (error: Exception) {
                val prior = repository.receipt(request.requestId)
                if (prior == null) {
                    if (error is ExperienceJournal.Conflict || error is ExperienceJournal.Capacity || error is IllegalArgumentException) refusal = error else throw error
                }
                prior
            }
            val loaded = repository.load()
            check(!loaded.journalUnavailable)
            if (receipt != null && loaded.revision == receipt.revision) check(ExperienceJournal.sha256(loaded.document) == receipt.documentSha256)
            Triple(loaded, receipt, refusal)
        }, failure = {
            unconfirmed = true
            message = "Result unconfirmed • retry the same change"
        }) { (loaded, receipt, refusal) ->
            experience = loaded.experience
            revision = loaded.revision
            preview = null
            pending = null
            unconfirmed = false
            message = when {
                refusal is ExperienceJournal.Capacity -> "Local edit history full; owner maintenance required"
                refusal != null -> "Change refused; saved experience reloaded"
                receipt?.revision != loaded.revision -> "Change applied; newer saved experience loaded"
                else -> request.success
            }
        }
    }

    private fun update(progress: String, success: String, operation: () -> ExperienceRepository.Loaded) {
        work(progress, operation) {
            experience = it.experience
            revision = it.revision
            preview = null
            message = when {
                it.journalUnavailable -> "Local journal unreadable; default Home available • editing disabled"
                it.restoredDefault -> "Saved experience unreadable; default Home loaded"
                else -> success
            }
        }
    }

    private fun <T> work(progress: String, operation: () -> T, failure: (() -> Unit)? = null, success: (T) -> Unit) {
        if (busy) return
        busy = true
        message = progress
        worker.execute {
            val loaded = runCatching(operation)
            main.post {
                if (!closed.get()) {
                    loaded.onSuccess(success).onFailure {
                        if (failure != null) failure() else message = if (it is ExperienceJournal.Conflict) "Experience changed; reload saved before editing" else "Change refused; previous experience preserved"
                    }
                    busy = false
                    drainExternalChange()
                }
            }
        }
    }

    private fun drainExternalChange() {
        if (externalPending && !busy && !unconfirmed) { externalPending = false; refreshSaved() }
    }

    /** Coalesced advisory notifications always reconcile from the authoritative journal. */
    fun refreshSaved() {
        if (closed.get()) return
        if (busy || unconfirmed) { externalPending = true; return }
        if (refreshQueued) { refreshAgain = true; return }
        refreshQueued = true
        worker.execute {
            val loaded = runCatching { repository.load() }
            main.post {
                refreshQueued = false
                val again = refreshAgain; refreshAgain = false
                if (!closed.get()) {
                    if (busy || unconfirmed) { externalPending = true; return@post }
                    loaded.onSuccess {
                        if (it.journalUnavailable) {
                            revision = 0
                            message = "Local journal unreadable; default Home available • editing disabled"
                        } else if (it.revision != revision) {
                            if (preview != null) {
                                externalPending = true
                                message = "Experience changed; reload saved before editing"
                            } else {
                                experience = it.experience; revision = it.revision
                                message = "Saved experience loaded"
                            }
                        }
                    }.onFailure { message = "Saved experience unavailable; current view preserved" }
                    if (again) refreshSaved()
                }
            }
        }
    }

    fun refreshActivities() {
        if (catalogPending) return
        catalogPending = true
        worker.execute {
            val catalog = runCatching { discover() }
            main.post {
                if (!closed.get()) {
                    catalog.onSuccess { activities = it; catalogReady = true }
                    catalogPending = false
                }
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun discover(): Map<String, ComponentName> {
        val packageManager = getApplication<Application>().packageManager
        val installed = packageManager.queryIntentActivities(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER), PackageManager.MATCH_ALL)
        val hints = mapOf("netflix" to "com.netflix.ninja", "prime_video" to "com.amazon.amazonvideo.livingroom", "disney_plus" to "com.disney.disneyplus", "youtube" to "com.google.android.youtube.tv", "local_control" to "local.sovereigntv.control")
        return hints.mapNotNull { (id, packageName) ->
            installed.firstOrNull { it.activityInfo.packageName == packageName && (id != "local_control" || packageManager.checkSignatures(getApplication<Application>().packageName, packageName) == PackageManager.SIGNATURE_MATCH) && it.activityInfo.exported && it.activityInfo.enabled && it.activityInfo.applicationInfo.enabled }
                ?.let { id to ComponentName(it.activityInfo.packageName, it.activityInfo.name) }
        }.toMap()
    }

    fun appAvailability(target: String): String = if (!catalogReady) "CHECKING" else if (target in activities) "INSTALLED" else "NOT INSTALLED"

    fun launchIntent(tile: Tile): Intent? {
        if (tile.kind != "app") return null
        if (!catalogReady) { message = "Checking installed TV applications"; return null }
        val target = activities[tile.target]
        if (target == null) { message = "No installed TV activity found for ${tile.title}"; return null }
        return Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER).setComponent(target)
    }

    fun controlIntent(): Intent? = launchIntent(Tile("local_control", "Household control", "app", "local_control", true))

    fun launchFailed() { message = "Application launch failed" }

    override fun onCleared() {
        closed.set(true)
        worker.shutdownNow()
        super.onCleared()
    }
}
