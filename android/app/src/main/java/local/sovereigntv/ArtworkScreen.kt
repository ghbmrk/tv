package local.sovereigntv

import android.graphics.Bitmap
import androidx.compose.foundation.focusable
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.input.key.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.layout.ContentScale
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalAccessibilityManager
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.tv.material3.Button
import androidx.tv.material3.Text
import kotlinx.coroutines.delay

/** Local gallery presentation; not the panel's low-power Art Mode. */
@Composable fun ArtworkScreen(collection: Collection, selected: Tile, intervalSeconds: Int, preview: Boolean,
    load: suspend (String, Int, Int) -> Bitmap, select: (Tile) -> Unit, back: () -> Unit) {
    val entries = collection.items.filter { it.visible && it.kind == "artwork" }
    val backFocus = remember { FocusRequester() }
    val surfaceFocus = remember { FocusRequester() }
    var controlsVisible by remember { mutableStateOf(true) }
    var interaction by remember { mutableIntStateOf(0) }
    var revealKey by remember { mutableStateOf<Key?>(null) }
    val controlsTimeout = LocalAccessibilityManager.current?.calculateRecommendedTimeoutMillis(6000, containsText = true, containsControls = true) ?: 6000L
    LaunchedEffect(controlsVisible) { if (controlsVisible) backFocus.requestFocus() else surfaceFocus.requestFocus() }
    val index = entries.indexOfFirst { it.id == selected.id }.coerceAtLeast(0)
    var playing by rememberSaveable(collection.id) { mutableStateOf(false) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var resumed by remember { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) }
    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, _ -> resumed = lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED) }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }
    BoxWithConstraints(Modifier.fillMaxSize().background(Color.Black).testTag("artwork-surface")
        .focusRequester(surfaceFocus).onPreviewKeyEvent { event ->
            if (revealKey == event.key) {
                if (event.type == KeyEventType.KeyUp) revealKey = null
                true
            } else if (event.type == KeyEventType.KeyDown && event.key in setOf(Key.DirectionUp, Key.DirectionDown, Key.DirectionLeft, Key.DirectionRight, Key.DirectionCenter, Key.Enter)) {
                interaction++
                if (!controlsVisible) { revealKey = event.key; controlsVisible = true; true } else false
            } else false
        }.focusable()) {
        val width = constraints.maxWidth.coerceAtLeast(1)
        val height = constraints.maxHeight.coerceAtLeast(1)
        var failed by remember(selected.target) { mutableStateOf(false) }
        val bitmap by produceState<Bitmap?>(null, selected.target, width, height) {
            value = null
            failed = false
            try { value = load(selected.target, width, height) }
            catch (error: Exception) {
                if (error is kotlinx.coroutines.CancellationException) throw error
                failed = true
            }
        }
        LaunchedEffect(controlsVisible, interaction, resumed, bitmap != null, controlsTimeout) {
            if (controlsVisible && resumed && bitmap != null) { delay(controlsTimeout); controlsVisible = false }
        }
        LaunchedEffect(playing, resumed, selected.id, intervalSeconds, bitmap != null) {
            if (playing && resumed && bitmap != null && entries.size > 1) {
                delay(intervalSeconds * 1000L)
                select(entries[(index + 1) % entries.size])
            }
        }
        if (bitmap != null) Image(bitmap!!.asImageBitmap(), selected.title, Modifier.fillMaxSize().testTag("artwork-image"), contentScale = ContentScale.Fit)
        if (bitmap == null) Text(if (failed) "Artwork unavailable; Home and saved configuration remain available" else "Loading local artwork", color = Color.White, modifier = Modifier.align(Alignment.Center))
        if (controlsVisible) Column(Modifier.align(Alignment.BottomStart).fillMaxWidth().background(Color.Black.copy(alpha = 0.75f)).padding(24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("${selected.title} • ${index + 1}/${entries.size}" + if (preview) " • Unsaved preview" else "", color = Color.White)
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Button(onClick = back, modifier = Modifier.focusRequester(backFocus)) { Text("Back to collection") }
                Button(enabled = entries.size > 1, onClick = { select(entries[(index - 1 + entries.size) % entries.size]) }) { Text("Previous artwork") }
                Button(enabled = entries.size > 1, onClick = { playing = !playing }) { Text(if (playing) "Pause slideshow" else "Start slideshow") }
                Button(enabled = entries.size > 1, onClick = { select(entries[(index + 1) % entries.size]) }) { Text("Next artwork") }
            }
        }
    }
}
