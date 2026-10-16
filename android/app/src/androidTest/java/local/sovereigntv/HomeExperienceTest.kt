package local.sovereigntv

import android.graphics.Bitmap
import android.os.Handler
import android.os.HandlerThread
import android.view.FrameMetrics
import android.view.Window
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.espresso.Espresso
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.Collections

/** Instrumented debug-emulator diagnostics, never physical remote latency qualification. */
@OptIn(ExperimentalTestApi::class)
@RunWith(AndroidJUnit4::class)
class HomeExperienceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private fun waitFor(text: String) = compose.waitUntil(10000) {
        compose.onAllNodesWithText(text).fetchSemanticsNodes().isNotEmpty()
    }
    private fun activate(text: String) {
        compose.onNodeWithText(text).performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        compose.onNodeWithText(text).performKeyInput { pressKey(Key.DirectionCenter) }
    }
    @Test fun settingsRoundTripsPreserveSelectionAndRecordFrameDiagnostics() {
        useLegacyHome(compose)
        compose.onNodeWithText("Import experience").assertDoesNotExist()
        compose.onNodeWithText("Restore default").assertDoesNotExist()
        compose.onNodeWithText("Netflix").performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        compose.onNodeWithText("Netflix").performKeyInput { pressKey(Key.DirectionRight) }
        compose.onNodeWithText("Prime Video").assertIsFocused()
        compose.waitUntil(10000) { compose.onAllNodes(hasText("Netflix") and hasText("NOT INSTALLED")).fetchSemanticsNodes().isNotEmpty() }
        val frameMs = Collections.synchronizedList(mutableListOf<Double>())
        val components = Collections.synchronizedList(mutableListOf<Map<String, Double>>())
        val droppedReports = java.util.concurrent.atomic.AtomicInteger()
        val metricIds = linkedMapOf("input" to FrameMetrics.INPUT_HANDLING_DURATION, "layout_measure" to FrameMetrics.LAYOUT_MEASURE_DURATION,
            "draw" to FrameMetrics.DRAW_DURATION, "sync" to FrameMetrics.SYNC_DURATION,
            "command_issue" to FrameMetrics.COMMAND_ISSUE_DURATION, "swap_buffers" to FrameMetrics.SWAP_BUFFERS_DURATION,
            "gpu" to FrameMetrics.GPU_DURATION, "unknown_delay" to FrameMetrics.UNKNOWN_DELAY_DURATION)
        val handlerThread = HandlerThread("home-test-frames").also { it.start() }
        val listener = Window.OnFrameMetricsAvailableListener { _, metrics, dropped ->
            droppedReports.addAndGet(dropped)
            if (metrics.getMetric(FrameMetrics.FIRST_DRAW_FRAME) == 0L) {
                frameMs.add(metrics.getMetric(FrameMetrics.TOTAL_DURATION) / 1_000_000.0)
                components.add(metricIds.mapValues { (_, id) -> metrics.getMetric(id) / 1_000_000.0 })
            }
        }
        val roundTripMs = mutableListOf<Double>()
        compose.runOnUiThread { compose.activity.window.addOnFrameMetricsAvailableListener(listener, Handler(handlerThread.looper)) }
        try {
            repeat(30) { round ->
                val start = System.nanoTime()
                activate("Settings")
                waitFor("Your TV, your rules.")
                compose.onNodeWithText("Netflix").assertDoesNotExist()
                if (round == 0) {
                    compose.onNodeWithText("Back to Home").performKeyInput { pressKey(Key.DirectionDown) }
                    compose.onNodeWithText("Import experience").assertIsFocused()
                    compose.onNodeWithText("Import experience").performKeyInput { pressKey(Key.DirectionRight) }
                    compose.onNodeWithText("Import artwork").assertIsFocused()
                }
                Espresso.pressBack()
                waitFor("Settings")
                compose.onNodeWithText("Prime Video").assertIsFocused()
                roundTripMs.add((System.nanoTime() - start) / 1_000_000.0)
            }
        } finally {
            compose.runOnUiThread { compose.activity.window.removeOnFrameMetricsAvailableListener(listener) }
            handlerThread.quitSafely(); handlerThread.join(5000)
        }
        fun summary(values: List<Double>): JSONObject {
            val sorted = values.sorted()
            return JSONObject().put("samples", sorted.size).also { result ->
                if (sorted.isNotEmpty()) result.put("p50_ms", sorted[(sorted.size - 1) / 2])
                    .put("p95_ms", sorted[kotlin.math.ceil(sorted.size * .95).toInt() - 1]).put("worst_ms", sorted.last())
            }
        }
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val frames = synchronized(frameMs) { frameMs.toList() }
        val componentSamples = synchronized(components) { components.toList() }
        val componentSummary = JSONObject()
        metricIds.keys.forEach { name -> componentSummary.put(name, summary(componentSamples.mapNotNull { it[name]?.takeIf { value -> value >= 0 } })) }
        val report = JSONObject().put("scope", "API ${android.os.Build.VERSION.SDK_INT} TV emulator; instrumented debug build; software GPU")
            .put("abi", android.os.Build.SUPPORTED_ABIS.first())
            .put("round_trip_includes", "test focus requests, injected keys, screen composition and test idle waits")
            .put("round_trip", summary(roundTripMs)).put("frame_total_duration", summary(frames))
            .put("frame_components", componentSummary).put("dropped_frame_reports", droppedReports.get())
            .put("component_samples_ms", JSONArray(componentSamples))
            .put("frames_ms", JSONArray(frames)).put("physical_remote_latency_qualified", false)
        File(context.filesDir, "home-diagnostics.json").writeText(report.toString(2))
        assertEquals(30, roundTripMs.size)
        assertTrue("Frame listener must observe actual rendered frames", frames.isNotEmpty())
        compose.mainClock.advanceTimeBy(6500)
        compose.waitForIdle()
        compose.onNodeWithText("Default Home restored").assertDoesNotExist()
        compose.onRoot().captureToImage().asAndroidBitmap().let { image ->
            val bounds = compose.onNodeWithText("Prime Video").fetchSemanticsNode().boundsInRoot
            assertEquals("Focused tile must visibly show the focus color", 0xffd5e6b4.toInt(), image.getPixel(bounds.center.x.toInt(), (bounds.top + bounds.height * .45f).toInt()))
            File(context.filesDir, "home-proof.png").outputStream().use { image.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
        activate("Settings")
        compose.activityRule.scenario.recreate()
        waitFor("Your TV, your rules.")
        activate("Back to Home")
        compose.onNodeWithText("Prime Video").assertIsFocused()
    }
}
