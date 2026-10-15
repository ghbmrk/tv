package local.sovereigntv

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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ViewModelProvider
import androidx.tv.material3.Button
import androidx.tv.material3.MaterialTheme
import androidx.tv.material3.Text

class MainActivity : ComponentActivity() {
    private val model by lazy { ViewModelProvider(this)[ExperienceViewModel::class.java] }
    private val importer = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) model.importDocument(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                val doc = model.experience
                if (doc == null) {
                    Box(Modifier.fillMaxSize().background(Color(0xff101b28)).padding(40.dp)) { Text(model.message, color = Color.White) }
                    return@MaterialTheme
                }
                var focusedId by rememberSaveable { mutableStateOf<String?>(null) }
                var resumeGeneration by remember { mutableIntStateOf(0) }
                DisposableEffect(lifecycle) {
                    val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) resumeGeneration++ }
                    lifecycle.addObserver(observer)
                    onDispose { lifecycle.removeObserver(observer) }
                }
                val visibleIds = doc.sections.flatMap { it.items }.filter { it.visible }.map { it.id }
                val restoreId = focusedId?.takeIf { it in visibleIds } ?: visibleIds.firstOrNull()
                val background = when (doc.theme) { "warm" -> Color(0xff2a211c); "light" -> Color(0xffe7e8e0); else -> Color(0xff101b28) }
                val foreground = if (doc.theme == "light") Color(0xff17292d) else Color.White
                LazyColumn(Modifier.fillMaxSize().background(background).padding(40.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
                    item(key = "header") { Text(doc.title, color = foreground, fontSize = (34 * doc.textScale).sp) }
                    item(key = "status") { Text(model.message, color = foreground) }
                    item(key = "controls") { Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        Button(enabled = !model.busy, onClick = { importer.launch(arrayOf("application/json", "text/plain")) }) { Text("Import experience") }
                        Button(enabled = !model.busy, onClick = { model.reset() }) { Text("Restore default") }
                    } }
                    items(doc.sections, key = { "section:${it.id}" }) { section ->
                        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(section.title, color = foreground, fontSize = (24 * doc.textScale).sp)
                            if (section.layout == "row") {
                                LazyRow(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                                    items(section.items.filter { it.visible }, key = { it.id }) { tile ->
                                        TileButton(tile, tile.id == restoreId, resumeGeneration) { focusedId = tile.id }
                                    }
                                }
                            } else {
                                section.items.filter { it.visible }.chunked(3).forEach { row ->
                                    Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                                        row.forEach { tile -> key(tile.id) { TileButton(tile, tile.id == restoreId, resumeGeneration) { focusedId = tile.id } } }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        model.refreshActivities()
    }

    @Composable private fun TileButton(tile: Tile, restore: Boolean, generation: Int, focused: () -> Unit) {
        val requester = remember(tile.id) { FocusRequester() }
        LaunchedEffect(tile.id, generation, restore) { if (restore) requester.requestFocus() }
        Button(onClick = { model.launchIntent(tile)?.let { intent -> runCatching { startActivity(intent) }.onFailure { model.launchFailed() } } },
            modifier = Modifier.width(190.dp).height(92.dp).focusRequester(requester).onFocusChanged { if (it.isFocused) focused() }) {
            Text(tile.title)
        }
    }
}
