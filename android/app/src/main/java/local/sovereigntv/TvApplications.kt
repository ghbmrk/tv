package local.sovereigntv

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import org.json.JSONArray
import org.json.JSONObject

/** Read the installed TV entry points; experience documents never carry components or intents. */
class TvApplications(private val context: Context) {
    data class Entry(val target: String, val title: String, val aliases: List<String>, val component: ComponentName)
    data class Catalog(val entries: List<Entry>, val truncated: Boolean) {
        fun json(): JSONObject {
            val items = JSONArray(entries.map { entry -> JSONObject().put("target", entry.target)
                .put("title", entry.title).put("aliases", JSONArray(entry.aliases)) })
            return JSONObject().put("applications", items).put("truncated", truncated)
                .put("catalog_sha256", ExperienceJournal.sha256(items.toString()))
                .put("launch_is_playback_qualification", false)
        }
    }
    @Suppress("DEPRECATION")
    private fun entryPoints(): List<Pair<ComponentName, android.content.pm.ResolveInfo>> {
        val manager = context.packageManager
        val candidates = manager.queryIntentActivities(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER), 0)
        return candidates.mapNotNull { resolved ->
            val activity = resolved.activityInfo ?: return@mapNotNull null
            if (!activity.exported || !activity.enabled || !activity.applicationInfo.enabled || activity.packageName == context.packageName)
                return@mapNotNull null
            if (activity.permission != null && manager.checkPermission(activity.permission, context.packageName) != PackageManager.PERMISSION_GRANTED)
                return@mapNotNull null
            if (activity.packageName == "local.sovereigntv.control" && manager.checkSignatures(context.packageName, activity.packageName) != PackageManager.SIGNATURE_MATCH)
                return@mapNotNull null
            ComponentName(activity.packageName, activity.name) to resolved
        }.distinctBy { it.first }.sortedBy { it.first.flattenToString() }
    }

    // Launch validation needs no app labels or presentation resources.
    fun resolve(target: String): ComponentName? = entryPoints().take(MAX_APPLICATIONS).firstOrNull { (component, _) ->
        TvApplications.target(component) == target || LEGACY[target] == component.packageName
    }?.first

    fun discover(): Catalog {
        val manager = context.packageManager
        val eligible = entryPoints()
        // Select deterministically; disclose truncation instead of silently treating an incomplete list as complete.
        val selected = eligible.take(MAX_APPLICATIONS)
        val claimedAliases = mutableSetOf<String>()
        val entries = selected.map { (component, resolved) ->
            val alias = LEGACY.entries.firstOrNull { it.value == component.packageName }?.key
                ?.takeIf { claimedAliases.add(it) }
            val raw = resolved.loadLabel(manager).toString().filterNot { Character.isISOControl(it) }
            val title = raw.take(raw.offsetByCodePoints(0, minOf(120, raw.codePointCount(0, raw.length))))
                .takeIf { it.isNotBlank() && Charsets.UTF_8.newEncoder().canEncode(it) } ?: "TV application"
            Entry(target(component), title, listOfNotNull(alias), component)
        }
        return Catalog(entries, eligible.size > MAX_APPLICATIONS)
    }
    companion object {
        const val MAX_APPLICATIONS = 256
        fun target(component: ComponentName) = "app_" + ExperienceJournal.sha256(component.flattenToString()).take(60)
        private val LEGACY = mapOf("netflix" to "com.netflix.ninja", "prime_video" to "com.amazon.amazonvideo.livingroom",
            "disney_plus" to "com.disney.disneyplus", "youtube" to "com.google.android.youtube.tv", "local_control" to "local.sovereigntv.control")
    }
}
