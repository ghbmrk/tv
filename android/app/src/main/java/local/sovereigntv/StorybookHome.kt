package local.sovereigntv

import android.graphics.BitmapFactory
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.*
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

private val Paper = Color(0xfff2dfb5)
private val Ink = Color(0xff302c24)

/** Static local illustrations; no provider feeds, timers, hover playback or automatic advance. */
@Composable fun StorybookHome(doc: Experience, restoreId: String?, enabled: Boolean, generation: Int,
    availability: (String) -> String, notice: String?, activate: (Tile) -> Unit, focused: (String) -> Unit,
    settings: () -> Unit, load: suspend (String, Int, Int) -> android.graphics.Bitmap) {
    val context = LocalContext.current
    val background by produceState<ImageBitmap?>(null) {
        value = withContext(Dispatchers.IO) { context.assets.open("storybook/background.png").use { BitmapFactory.decodeStream(it).asImageBitmap() } }
    }
    val posters by produceState<ImageBitmap?>(null) {
        value = withContext(Dispatchers.IO) { context.assets.open("storybook/posters.png").use { BitmapFactory.decodeStream(it).asImageBitmap() } }
    }
    val sectionsState = rememberLazyListState()
    // A retained tile ID may move outside a lazy viewport after curation. Compose its
    // section first, then its row item, before the tile requests focus. Do not animate
    // this recovery or reset the scroll offset when the selection is already visible.
    LaunchedEffect(doc.sections, restoreId, enabled, generation) {
        val index = doc.sections.indexOfFirst { section -> section.items.any { it.visible && it.id == restoreId } }
        if (enabled && index >= 0 && sectionsState.layoutInfo.visibleItemsInfo.none { it.index == index }) {
            sectionsState.scrollToItem(index)
        }
    }
    BoxWithConstraints(Modifier.fillMaxSize().background(Paper).testTag("storybook-home")
        .then(if (!enabled) Modifier.clearAndSetSemantics { } else Modifier)) {
        val unit = maxWidth / 960f
        background?.let { Image(it, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
        LazyColumn(Modifier.fillMaxSize(), state = sectionsState, contentPadding = PaddingValues(start = unit * 60f, end = unit * 60f,
            top = unit * 150f, bottom = unit * 72f), verticalArrangement = Arrangement.spacedBy(unit * 30f)) {
            items(doc.sections, key = { it.id }) { section ->
                val movies = section.items.any { it.kind == "movie" }
                val tileWidth = unit * if (movies) 128f else 104f
                val arrangement = Arrangement.spacedBy(unit * 12f, if (movies) Alignment.Start else Alignment.CenterHorizontally)
                val visible = section.items.filter { it.visible }
                val rowState = rememberLazyListState()
                LaunchedEffect(visible, restoreId, enabled, generation) {
                    val index = visible.indexOfFirst { it.id == restoreId }
                    if (enabled && section.layout == "row" && index >= 0 && rowState.layoutInfo.visibleItemsInfo.none { it.index == index }) {
                        rowState.scrollToItem(index)
                    }
                }
                if (section.layout == "row") LazyRow(Modifier.fillMaxWidth(), state = rowState, horizontalArrangement = arrangement,
                    contentPadding = PaddingValues(horizontal = unit * 5f, vertical = unit * 8f)) {
                    items(visible, key = { it.id }) { tile ->
                        StorybookTile(tile, tileWidth, if (movies) unit * 190f else unit * 72f, posters, background,
                            tile.id == restoreId, enabled, generation, availability(tile.target),
                            { activate(tile) }, { focused(tile.id) }, load)
                    }
                } else Column(verticalArrangement = Arrangement.spacedBy(unit * 12f)) {
                    visible.chunked(6).forEach { row ->
                        Row(horizontalArrangement = arrangement, modifier = Modifier.fillMaxWidth().padding(5.dp)) {
                            row.forEach { tile -> key(tile.id) {
                                StorybookTile(tile, tileWidth, if (movies) unit * 190f else unit * 72f, posters, background,
                                    tile.id == restoreId, enabled, generation, availability(tile.target),
                                    { activate(tile) }, { focused(tile.id) }, load)
                            } }
                        }
                    }
                }
            }
        }
        var settingsFocus by remember { mutableStateOf(false) }
        Canvas(Modifier.align(Alignment.TopEnd).padding(unit * 30f).size(unit * 30f)
            .clip(RoundedCornerShape(30.dp)).background(if (settingsFocus) Paper else Color.Transparent)
            .focusProperties { canFocus = enabled }.onFocusChanged { settingsFocus = it.isFocused }
            .semantics { contentDescription = "Settings"; role = Role.Button }
            .clickable(enabled = enabled, onClick = settings).testTag("storybook-settings")) {
            val r = size.minDimension
            drawCircle(Ink.copy(alpha = if (settingsFocus) 1f else .5f), r * .22f, style = Stroke(r * .06f))
            repeat(8) { i ->
                val angle = i * Math.PI / 4
                val v = Offset(kotlin.math.cos(angle).toFloat(), kotlin.math.sin(angle).toFloat())
                drawLine(Ink.copy(alpha = if (settingsFocus) 1f else .5f), center + v * (r * .23f), center + v * (r * .34f), r * .07f)
            }
        }
        if (notice != null) Canvas(Modifier.align(Alignment.BottomEnd).padding(unit * 30f).size(unit * 20f)
            .semantics { contentDescription = notice; liveRegion = LiveRegionMode.Polite }.testTag("storybook-notice")) {
            drawCircle(Ink.copy(alpha = .75f), style = Stroke(2.dp.toPx()))
            drawLine(Ink, Offset(center.x, size.height * .25f), Offset(center.x, size.height * .55f), 2.dp.toPx())
            drawCircle(Ink, 1.5.dp.toPx(), Offset(center.x, size.height * .75f))
        }
    }
}

@Composable private fun StorybookTile(tile: Tile, width: Dp, height: Dp, atlas: ImageBitmap?, texture: ImageBitmap?, restore: Boolean,
    enabled: Boolean, generation: Int, availability: String, activate: () -> Unit, focused: () -> Unit,
    load: suspend (String, Int, Int) -> android.graphics.Bitmap) {
    val requester = remember(tile.id) { FocusRequester() }
    var selected by remember(tile.id) { mutableStateOf(false) }
    val shape = RoundedCornerShape(5.dp)
    val density = LocalDensity.current
    val pixelWidth = with(density) { width.toPx().toInt().coerceIn(1, 640) }
    val pixelHeight = with(density) { height.toPx().toInt().coerceIn(1, 960) }
    val external by produceState<ImageBitmap?>(null, tile.poster, pixelWidth, pixelHeight) {
        val poster = tile.poster
        value = if (poster != null && Regex("[a-f0-9]{64}").matches(poster)) runCatching { load(poster, pixelWidth, pixelHeight).asImageBitmap() }.getOrNull() else null
    }
    LaunchedEffect(tile.id, restore, enabled, generation) { if (restore && enabled) requester.requestFocus() }
    val description = when {
        tile.kind == "movie" && tile.playback == null -> "Playback link not configured"
        tile.kind == "movie" -> "Playback unavailable: stop-at-end provider integration is not qualified"
        else -> availability
    }
    Box(Modifier.width(width).height(height).shadow(if (selected) 9.dp else 4.dp, shape)
        .border(if (selected) 3.dp else 1.dp, if (selected) Color(0xffffebad) else Ink.copy(alpha = .65f), shape)
        .padding(if (selected) 3.dp else 1.dp).clip(shape)
        .background(appColor(tile.target)).focusRequester(requester).focusProperties { canFocus = enabled }
        .onFocusChanged { selected = it.isFocused; if (it.isFocused) focused() }
        .semantics { contentDescription = tile.title; stateDescription = description; role = Role.Button }
        .clickable(enabled = enabled, onClick = activate).testTag("storybook-tile:${tile.id}")) {
        if (tile.kind != "movie" && texture != null) Canvas(Modifier.fillMaxSize()) {
            drawImage(texture, srcOffset = IntOffset(texture.width / 3, texture.height / 3),
                srcSize = IntSize(texture.width / 3, texture.height / 3), dstSize = IntSize(size.width.toInt(), size.height.toInt()),
                colorFilter = ColorFilter.tint(appColor(tile.target), BlendMode.Multiply))
        }
        val index = MovieLink.POSTERS.indexOf(tile.poster)
        if (external != null) Image(external!!, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        else if (tile.kind == "movie" && atlas != null && index >= 0) Canvas(Modifier.fillMaxSize()) {
            val cell = IntSize(atlas.width / 3, atlas.height / 2)
            drawImage(atlas, srcOffset = IntOffset(index % 3 * cell.width, index / 3 * cell.height), srcSize = cell,
                dstSize = IntSize(size.width.toInt(), size.height.toInt()), filterQuality = FilterQuality.Medium)
        } else AppMark(tile.target, Modifier.fillMaxSize().padding(horizontal = width * .23f, vertical = height * .18f))
        // The image remains a static picture even while focused. Focus changes only the paper edge.
    }
}

private fun appColor(target: String): Color = when (target) {
    "netflix" -> Color(0xff282621); "disney_plus" -> Color(0xff28394c); "youtube" -> Color(0xffdfcda8)
    "prime_video" -> Color(0xff3e6371); "hulu" -> Color(0xff52684e); "apple_tv" -> Color(0xff3b352f)
    else -> Color(0xff777465)
}

/** Small path-based marks, never text labels or network-fetched branding. */
@Composable internal fun AppMark(target: String, modifier: Modifier = Modifier) {
    Canvas(modifier) {
        val sx = size.width / 100f; val sy = size.height / 70f
        fun path(color: Color, block: Path.() -> Unit) { val p = Path().apply(block); p.transform(Matrix().apply { scale(sx, sy, 1f) }); drawPath(p, color) }
        val cream = Color(0xffe9d9b6)
        when (target) {
            "netflix" -> {
                path(Color(0xffa23d2d)) { moveTo(28f, 0f); lineTo(42f, 0f); lineTo(42f, 70f); lineTo(28f, 70f); close(); moveTo(60f, 0f); lineTo(74f, 0f); lineTo(74f, 70f); lineTo(60f, 70f); close() }
                path(Color(0xffbc4b35)) { moveTo(28f,0f); lineTo(44f,0f); lineTo(74f,70f); lineTo(58f,70f); close() }
            }
            "youtube" -> { drawRoundRect(Color(0xffad4937), Offset(0f,size.height * .08f), Size(size.width,size.height * .84f), androidx.compose.ui.geometry.CornerRadius(10.dp.toPx())); path(cream) { moveTo(42f,19f); lineTo(68f,35f); lineTo(42f,51f); close() } }
            "disney_plus" -> {
                path(cream) { moveTo(15f,65f); lineTo(15f,45f); lineTo(25f,45f); lineTo(25f,31f); lineTo(30f,22f); lineTo(35f,31f); lineTo(35f,45f); lineTo(44f,45f); lineTo(44f,16f); lineTo(50f,0f); lineTo(56f,16f); lineTo(56f,45f); lineTo(65f,45f); lineTo(65f,31f); lineTo(70f,22f); lineTo(75f,31f); lineTo(75f,45f); lineTo(85f,45f); lineTo(85f,65f); close() }
                drawArc(cream, 195f, 150f, false, Offset(0f,-size.height * .04f), Size(size.width,size.height * .8f), style = Stroke(1.dp.toPx()))
            }
            "prime_video" -> {
                path(cream) { moveTo(8f,34f); cubicTo(30f,60f,68f,63f,90f,30f); cubicTo(68f,45f,35f,48f,8f,34f); close(); moveTo(76f,25f); lineTo(96f,24f); lineTo(91f,46f); lineTo(87f,32f); close() }
            }
            "hulu" -> path(Color(0xffd2d6ad)) { moveTo(25f,0f); lineTo(40f,0f); lineTo(40f,27f); cubicTo(68f,16f,78f,28f,78f,45f); lineTo(78f,70f); lineTo(62f,70f); lineTo(62f,45f); cubicTo(62f,34f,40f,36f,40f,46f); lineTo(40f,70f); lineTo(25f,70f); close() }
            "apple_tv" -> path(cream) { moveTo(52f,19f); cubicTo(65f,8f,87f,21f,76f,34f); cubicTo(68f,42f,76f,48f,80f,49f); cubicTo(73f,72f,63f,73f,52f,66f); cubicTo(40f,75f,26f,65f,22f,43f); cubicTo(18f,24f,33f,12f,52f,19f); close(); moveTo(51f,14f); cubicTo(49f,1f,64f,-4f,67f,0f); cubicTo(67f,8f,60f,14f,51f,14f); close() }
            else -> { repeat(4) { i -> drawRoundRect(cream, Offset((i % 2) * size.width * .53f, (i / 2) * size.height * .53f), Size(size.width * .4f,size.height * .4f), androidx.compose.ui.geometry.CornerRadius(3.dp.toPx())) } }
        }
    }
}
