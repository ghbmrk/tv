package local.sovereigntv

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.BackHandler
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
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private val model by lazy { ViewModelProvider(this)[ExperienceViewModel::class.java] }
    private val importer = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) model.importDocument(uri)
    }
    private val artworkImporter = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) model.importArtwork(uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                val doc = model.preview?.experience ?: model.experience
                if (doc == null) {
                    Box(Modifier.fillMaxSize().background(Color(0xff101b28)).padding(40.dp)) { Text(model.message, color = Color.White) }
                    return@MaterialTheme
                }
                var focusedId by rememberSaveable { mutableStateOf<String?>(null) }
                var collectionId by rememberSaveable { mutableStateOf<String?>(null) }
                var entryId by rememberSaveable { mutableStateOf<String?>(null) }
                var artworkId by rememberSaveable { mutableStateOf<String?>(null) }
                val collection = doc.collections.firstOrNull { it.id == collectionId }
                val artwork = collection?.items?.firstOrNull { it.id == artworkId && it.visible && it.kind == "artwork" }
                BackHandler(enabled = collectionId != null || artworkId != null) {
                    if (artworkId != null) artworkId = null else collectionId = null
                }
                LaunchedEffect(doc) {
                    if (collectionId != null && collection == null) { collectionId = null; artworkId = null }
                    if (artworkId != null && artwork == null) artworkId = null
                }
                if (artwork != null) {
                    ArtworkScreen(collection, artwork, doc.artworkIntervalSeconds, model.preview != null,
                        load = { id, width, height -> withContext(model.diskDispatcher) { model.loadArtwork(id, width, height) } },
                        select = { artworkId = it.id; entryId = it.id }, back = { artworkId = null })
                    return@MaterialTheme
                }
                var resumeGeneration by remember { mutableIntStateOf(0) }
                DisposableEffect(lifecycle) {
                    val observer = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) resumeGeneration++ }
                    lifecycle.addObserver(observer)
                    onDispose { lifecycle.removeObserver(observer) }
                }
                val visibleIds = (collection?.items ?: doc.sections.flatMap { it.items }).filter { it.visible }.map { it.id }
                val restoreId = (if (collection != null) entryId else focusedId)?.takeIf { it in visibleIds } ?: visibleIds.firstOrNull()
                fun activate(tile: Tile) {
                    when (tile.kind) {
                        "collection" -> { collectionId = tile.target; entryId = null }
                        "artwork" -> { entryId = tile.id; artworkId = tile.id }
                        else -> model.launchIntent(tile)?.let { intent -> runCatching { startActivity(intent) }.onFailure { model.launchFailed() } }
                    }
                }
                val background = when (doc.theme) { "warm" -> Color(0xff2a211c); "light" -> Color(0xffe7e8e0); else -> Color(0xff101b28) }
                val foreground = if (doc.theme == "light") Color(0xff17292d) else Color.White
                LazyColumn(Modifier.fillMaxSize().background(background), contentPadding = PaddingValues(40.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
                    item(key = "header") { Text(collection?.title ?: doc.title, color = foreground, fontSize = (34 * doc.textScale).sp) }
                    item(key = "status") { Text(model.message, color = foreground) }
                    item(key = "controls") { Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        if (model.unconfirmed) {
                            Button(enabled = !model.busy, onClick = { model.retryChange() }) { Text("Retry change") }
                        } else if (model.preview != null) {
                            Button(enabled = !model.busy, onClick = { model.applyPreview() }) { Text("Apply preview") }
                            Button(enabled = !model.busy, onClick = { model.cancelPreview() }) { Text("Cancel preview") }
                        } else {
                            Button(enabled = !model.busy && model.revision > 0, onClick = { importer.launch(arrayOf("application/json", "text/plain", "application/zip")) }) { Text("Import experience") }
                            Button(enabled = !model.busy && model.revision > 0, onClick = { artworkImporter.launch(arrayOf("image/png")) }) { Text("Import artwork") }
                            Button(enabled = !model.busy && model.revision > 0, onClick = { model.reset() }) { Text("Restore default") }
                            Button(enabled = !model.busy && model.revision > 1, onClick = { model.undo() }) { Text("Undo last change") }
                        }
                    } }
                    if (collectionId != null) {
                        item(key = "back-home") { Button(onClick = { collectionId = null }) { Text("Back to Home") } }
                        if (collection == null || collection.items.none { it.visible }) {
                            item(key = "empty-collection") { Text("No visible items in this collection. Import local artwork or edit its contents.", color = foreground) }
                        }
                    }
                    if (model.message == "Experience changed; reload saved before editing") {
                        item(key = "reload") { Button(enabled = !model.busy, onClick = { model.reload() }) { Text("Reload saved") } }
                    }
                    items(if (collection != null) listOf(Section(collection.id, "Collection", "grid", collection.items)) else if (collectionId != null) emptyList() else doc.sections, key = { "section:${it.id}" }) { section ->
                        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            Text(section.title, color = foreground, fontSize = (24 * doc.textScale).sp)
                            if (section.layout == "row") {
                                LazyRow(contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                                    items(section.items.filter { it.visible }, key = { it.id }) { tile ->
                                        TileButton(tile, tile.id == restoreId, resumeGeneration, { activate(tile) }) { if (collection != null) entryId = tile.id else focusedId = tile.id }
                                    }
                                }
                            } else {
                                section.items.filter { it.visible }.chunked(3).forEach { row ->
                                    Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                                        row.forEach { tile -> key(tile.id) { TileButton(tile, tile.id == restoreId, resumeGeneration, { activate(tile) }) { if (collection != null) entryId = tile.id else focusedId = tile.id } } }
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

    @Composable private fun TileButton(tile: Tile, restore: Boolean, generation: Int, activate: () -> Unit, focused: () -> Unit) {
        val requester = remember(tile.id) { FocusRequester() }
        LaunchedEffect(tile.id, generation, restore) { if (restore) requester.requestFocus() }
        Button(onClick = activate,
            modifier = Modifier.width(190.dp).height(92.dp).focusRequester(requester).onFocusChanged { if (it.isFocused) focused() }) {
            Text(tile.title)
        }
    }
}
