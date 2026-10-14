package local.sovereigntv

import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.material3.Button
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Text

class MainActivity : ComponentActivity() {
    private val prefs by lazy { getSharedPreferences("experience", MODE_PRIVATE) }
    private var experience by mutableStateOf<Experience?>(null)
    private var message by mutableStateOf("Local Home prototype • no agentOS connection")
    private val importer = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) runCatching {
            val bytes = contentResolver.openInputStream(uri)?.use { stream ->
                val buffer = ByteArray(65537); var count = 0
                while (count < buffer.size) { val n = stream.read(buffer, count, buffer.size - count); if (n < 0) break; count += n }
                require(count <= 65536); buffer.copyOf(count)
            } ?: error("File unavailable")
            val text = bytes.toString(Charsets.UTF_8)
            val parsed = Experience.parse(text)
            check(prefs.edit().putString("document", text).commit())
            experience = parsed; message = "Imported local experience"
        }.onFailure { message = "Import refused; previous experience preserved" }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        restore()
        setContent {
            MaterialTheme {
                val doc = experience ?: return@MaterialTheme
                val background = when (doc.theme) { "warm" -> Color(0xff2a211c); "light" -> Color(0xffe7e8e0); else -> Color(0xff101b28) }
                val foreground = if (doc.theme == "light") Color(0xff17292d) else Color.White
                LazyColumn(Modifier.fillMaxSize().background(background).padding(40.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
                    item { Text(doc.title, color = foreground, fontSize = (34 * doc.textScale).sp) }
                    item { Text(message, color = foreground) }
                    item { Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        Button(onClick = { importer.launch(arrayOf("application/json", "text/plain")) }) { Text("Import experience") }
                        Button(onClick = { prefs.edit().clear().commit(); restore(); message = "Default Home restored" }) { Text("Restore default") }
                    } }
                    items(doc.sections) { section ->
                        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(section.title, color = foreground, fontSize = (24 * doc.textScale).sp)
                            if (section.layout == "row") {
                                LazyRow(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                                    items(section.items.filter { it.visible }, key = { it.id }) { tile -> TileButton(tile) }
                                }
                            } else {
                                section.items.filter { it.visible }.chunked(3).forEach { row ->
                                    Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) { row.forEach { TileButton(it) } }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    private fun restore() {
        val fallback = assets.open("experience.json").bufferedReader().use { it.readText() }
        experience = runCatching { Experience.parse(prefs.getString("document", fallback) ?: fallback) }.getOrElse { Experience.parse(fallback) }
    }
    @Composable private fun TileButton(tile: Tile) {
        Button(onClick = { launch(tile) }, modifier = Modifier.width(190.dp).height(92.dp)) { Text(tile.title) }
    }
    @Suppress("DEPRECATION") private fun launch(tile: Tile) {
        if (tile.kind != "app") { message = "Collection renderer pending: ${tile.title}"; return }
        // These are hints; only discovered, installed leanback activities are launched.
        val candidates = when (tile.target) {
            "netflix" -> setOf("com.netflix.ninja")
            "prime_video" -> setOf("com.amazon.amazonvideo.livingroom")
            "disney_plus" -> setOf("com.disney.disneyplus")
            "youtube" -> setOf("com.google.android.youtube.tv")
            else -> emptySet()
        }
        val query = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER)
        val found = packageManager.queryIntentActivities(query, PackageManager.MATCH_ALL).firstOrNull { it.activityInfo.packageName in candidates }
        if (found == null) { message = "No qualified installed TV activity found for ${tile.title}"; return }
        runCatching { startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LEANBACK_LAUNCHER).setClassName(found.activityInfo.packageName, found.activityInfo.name)) }
            .onFailure { message = "Application launch failed" }
    }
}
