package local.sovereigntv

import android.os.Bundle
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.core.content.ContextCompat
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.BackHandler
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Alignment
import androidx.tv.material3.ButtonDefaults
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
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.clearAndSetSemantics
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
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    private val model by lazy { ViewModelProvider(this)[ExperienceViewModel::class.java] }
    private val importer = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) model.importDocument(uri)
    }
    private val artworkImporter = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) model.importArtwork(uri)
    }

    private val savedChangeReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) { model.refreshSaved() }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ContextCompat.registerReceiver(this, savedChangeReceiver, IntentFilter(ExperienceControlService.CHANGED),
            ExperienceControlService.PERMISSION, null, ContextCompat.RECEIVER_NOT_EXPORTED)
        setContent {
            MaterialTheme {
                val doc = model.preview?.experience ?: model.experience
                if (doc == null) {
                    Box(Modifier.fillMaxSize().background(Color(0xff101b28)).padding(40.dp)) { Text(model.message, color = Color.White) }
                    return@MaterialTheme
                }
                var settingsOpen by rememberSaveable { mutableStateOf(false) }
                val settingsFocus = remember { FocusRequester() }
                val firstSettingsAction = remember { FocusRequester() }
                LaunchedEffect(settingsOpen) { if (settingsOpen) settingsFocus.requestFocus() }
                LaunchedEffect(model.preview) { if (model.preview != null) settingsOpen = false }
                var focusedId by rememberSaveable { mutableStateOf<String?>(null) }
                var collectionId by rememberSaveable { mutableStateOf<String?>(null) }
                var entryId by rememberSaveable { mutableStateOf<String?>(null) }
                var artworkId by rememberSaveable { mutableStateOf<String?>(null) }
                val collection = doc.collections.firstOrNull { it.id == collectionId }
                val artwork = collection?.items?.firstOrNull { it.id == artworkId && it.visible && it.kind == "artwork" }
                BackHandler(enabled = settingsOpen || collectionId != null || artworkId != null) {
                    if (settingsOpen) settingsOpen = false else if (artworkId != null) artworkId = null else collectionId = null
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
                val background = when (doc.theme) { "warm" -> Color(0xff2a211c); "light" -> Color(0xffe7e8e0); else -> Color(0xff141c18) }
                val foreground = if (doc.theme == "light") Color(0xff17292d) else Color.White
                val transientNotice = model.message in setOf("Default Home restored", "Imported local experience", "Last change undone", "Preview cancelled; saved experience unchanged", "Saved experience loaded")
                var noticeVisible by remember(model.message) { mutableStateOf(true) }
                LaunchedEffect(model.message, model.busy) {
                    if (transientNotice && !model.busy) { delay(6000); noticeVisible = false }
                }
                @Composable fun EditingControls(focusFirst: Boolean = false) {
                    val firstModifier = if (focusFirst) Modifier.focusRequester(firstSettingsAction) else Modifier
                    Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        if (model.unconfirmed) {
                            Button(modifier = firstModifier, enabled = !model.busy, onClick = { model.retryChange() }) { Text("Retry change") }
                        } else if (model.preview != null) {
                            Button(modifier = firstModifier, enabled = !model.busy, onClick = { model.applyPreview() }) { Text("Apply preview") }
                            Button(enabled = !model.busy, onClick = { model.cancelPreview() }) { Text("Cancel preview") }
                        } else {
                            Button(modifier = firstModifier, enabled = !model.busy && model.revision > 0, onClick = { importer.launch(arrayOf("application/json", "text/plain", "application/zip")) }) { Text("Import experience") }
                            Button(enabled = !model.busy && model.revision > 0, onClick = { artworkImporter.launch(arrayOf("image/png")) }) { Text("Import artwork") }
                            Button(enabled = !model.busy && model.revision > 0, onClick = { model.reset() }) { Text("Restore default") }
                            Button(enabled = !model.busy && model.revision > 1, onClick = { model.undo() }) { Text("Undo last change") }
                        }
                    }
                }
                var settingsHasFocus by remember { mutableStateOf(false) }
                Column(Modifier.fillMaxSize().background(background).padding(40.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text("sovereign tv", color = foreground.copy(alpha = .65f), fontSize = 16.sp)
                        Button(onClick = { settingsOpen = !settingsOpen },
                            modifier = Modifier.focusRequester(settingsFocus).focusProperties { if (settingsOpen) down = firstSettingsAction }.onFocusChanged { settingsHasFocus = it.isFocused },
                            shape = ButtonDefaults.shape(RoundedCornerShape(8.dp)), scale = ButtonDefaults.scale(focusedScale = 1f),
                            colors = ButtonDefaults.colors(containerColor = if (settingsHasFocus) Color(0xffd5e6b4) else Color.Transparent,
                                contentColor = if (settingsHasFocus) Color(0xff202919) else foreground.copy(alpha = .7f),
                                focusedContainerColor = Color(0xffd5e6b4), focusedContentColor = Color(0xff202919))) {
                            Text(if (!settingsOpen) "Settings" else if (collection != null) "Back to collection" else "Back to Home")
                        }
                    }
                    Spacer(Modifier.height(20.dp))
                    Text(if (settingsOpen) "Your TV, your rules." else collection?.title ?: doc.title,
                        color = foreground, fontSize = (34 * doc.textScale).sp, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                    Spacer(Modifier.height(12.dp))
                    if (model.message != "Local Home • no agentOS connection" && (!transientNotice || noticeVisible)) {
                        Text(model.message, color = foreground.copy(alpha = .65f), fontSize = 13.sp)
                        Spacer(Modifier.height(12.dp))
                    }
                    Box(Modifier.weight(1f)) {
                        // Retain Home's lazy-list state and composition; the hidden surface cannot receive focus or expose semantics.
                        LazyColumn(Modifier.fillMaxSize().focusProperties { canFocus = !settingsOpen }.graphicsLayer { alpha = if (settingsOpen) 0f else 1f }
                            .then(if (settingsOpen) Modifier.clearAndSetSemantics { } else Modifier),
                            contentPadding = PaddingValues(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
                            if (model.preview != null || model.unconfirmed) item(key = "controls") { EditingControls() }
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
                                    Text(section.title, color = foreground, fontSize = (16 * doc.textScale).sp)
                                    if (section.layout == "row") {
                                        LazyRow(contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                                            items(section.items.filter { it.visible }, key = { it.id }) { tile ->
                                                TileButton(tile, doc.textScale, doc.theme == "light", tile.id == restoreId && !settingsOpen, !settingsOpen, resumeGeneration, { activate(tile) }) { if (collection != null) entryId = tile.id else focusedId = tile.id }
                                            }
                                        }
                                    } else {
                                        section.items.filter { it.visible }.chunked(3).forEach { row ->
                                            Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                                                row.forEach { tile -> key(tile.id) { TileButton(tile, doc.textScale, doc.theme == "light", tile.id == restoreId && !settingsOpen, !settingsOpen, resumeGeneration, { activate(tile) }) { if (collection != null) entryId = tile.id else focusedId = tile.id } } }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        if (settingsOpen) LazyColumn(Modifier.fillMaxSize().background(background),
                            contentPadding = PaddingValues(vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(24.dp)) {
                            item { Text(doc.title, color = foreground, fontSize = 18.sp) }
                            item { Text("Local files. Explicit changes. Persistent undo.", color = foreground.copy(alpha = .65f), fontSize = 16.sp) }
                            item { EditingControls(focusFirst = true) }
                            item { Button(onClick = { model.controlIntent()?.let { runCatching { startActivity(it) }.onFailure { model.launchFailed() } } }) { Text("Household control") } }
                        }
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        model.refreshActivities()
        model.refreshSaved()
    }

    override fun onDestroy() {
        unregisterReceiver(savedChangeReceiver)
        super.onDestroy()
    }

    @Composable private fun TileButton(tile: Tile, textScale: Float, light: Boolean, restore: Boolean, focusEnabled: Boolean, generation: Int, activate: () -> Unit, focused: () -> Unit) {
        val requester = remember(tile.id) { FocusRequester() }
        var hasFocus by remember(tile.id) { mutableStateOf(false) }
        LaunchedEffect(tile.id, generation, restore) { if (restore) requester.requestFocus() }
        val accent = when (tile.target) {
            "netflix" -> Color(0xffff887c)
            "prime_video" -> Color(0xff9ed4ed)
            "disney_plus" -> Color(0xffb6c3ff)
            "youtube" -> Color(0xffedbba8)
            else -> Color(0xffd5e6b4)
        }
        Button(onClick = activate,
            shape = ButtonDefaults.shape(RoundedCornerShape(12.dp)),
            colors = ButtonDefaults.colors(containerColor = if (hasFocus) Color(0xffd5e6b4) else if (light) Color(0xffd2d7cb) else Color(0xff26332b), contentColor = if (hasFocus) Color(0xff202919) else if (light) Color(0xff243024) else accent, focusedContainerColor = Color(0xffd5e6b4), focusedContentColor = Color(0xff202919)),
            scale = ButtonDefaults.scale(focusedScale = 1f),
            modifier = Modifier.width(190.dp).height(110.dp).focusProperties { canFocus = focusEnabled }.focusRequester(requester).onFocusChanged { hasFocus = it.isFocused; if (it.isFocused) focused() }) {
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.SpaceBetween) {
                Text(if (tile.kind == "collection") "COLLECTION" else if (tile.kind == "artwork") "ARTWORK" else model.appAvailability(tile.target), fontSize = 10.sp, modifier = Modifier.padding(top = 4.dp))
                Text(tile.title, fontSize = (19 * textScale).sp, maxLines = 2)
            }
        }
    }
}
