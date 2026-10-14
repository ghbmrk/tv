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
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** Disk, parsing and package discovery never run on the navigation/frame path. */
class ExperienceViewModel(application: Application) : AndroidViewModel(application) {
    private val repository by lazy(LazyThreadSafetyMode.NONE) { ExperienceRepository(application) }
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val closed = AtomicBoolean(false)
    private var activities = emptyMap<String, ComponentName>()
    private var catalogReady = false
    private var catalogPending = false
    var experience by mutableStateOf<Experience?>(null)
        private set
    var busy by mutableStateOf(false)
        private set
    var message by mutableStateOf("Loading local Home")
        private set

    init { update("Loading local Home", "Local Home • no agentOS connection") { repository.load() } }

    fun importDocument(uri: Uri) = update("Importing experience", "Imported local experience") {
        val stream = getApplication<Application>().contentResolver.openInputStream(uri) ?: error("File unavailable")
        repository.import(stream)
    }

    fun reset() = update("Restoring default Home", "Default Home restored") { repository.reset() }

    private fun update(progress: String, success: String, operation: () -> ExperienceRepository.Loaded) {
        if (busy) return
        busy = true
        message = progress
        worker.execute {
            val loaded = runCatching(operation)
            main.post {
                if (!closed.get()) {
                    loaded.onSuccess {
                        experience = it.experience
                        message = if (it.restoredDefault) "Saved experience unreadable; default Home loaded" else success
                    }.onFailure { message = "Change refused; previous experience preserved" }
                    busy = false
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
        val hints = mapOf("netflix" to "com.netflix.ninja", "prime_video" to "com.amazon.amazonvideo.livingroom", "disney_plus" to "com.disney.disneyplus", "youtube" to "com.google.android.youtube.tv")
        return hints.mapNotNull { (id, packageName) ->
            installed.firstOrNull { it.activityInfo.packageName == packageName && it.activityInfo.exported && it.activityInfo.enabled && it.activityInfo.applicationInfo.enabled }
                ?.let { id to ComponentName(it.activityInfo.packageName, it.activityInfo.name) }
        }.toMap()
    }

    fun launchIntent(tile: Tile): Intent? {
        if (tile.kind != "app") { message = "Collection renderer pending: ${tile.title}"; return null }
        if (!catalogReady) { message = "Checking installed TV applications"; return null }
        val target = activities[tile.target]
        if (target == null) { message = "No installed TV activity found for ${tile.title}"; return null }
        return Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER).setComponent(target)
    }

    fun launchFailed() { message = "Application launch failed" }

    override fun onCleared() {
        closed.set(true)
        worker.shutdownNow()
        super.onCleared()
    }
}
