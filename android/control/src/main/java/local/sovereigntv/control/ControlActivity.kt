package local.sovereigntv.control

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.testTag
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModelProvider
import androidx.tv.material3.*

class ControlActivity : ComponentActivity() {
    private lateinit var model: ControlModel
    private val pick = registerForActivityResult(ActivityResultContracts.OpenDocument()) { it?.let(model::importCertificate) }
    private val export = registerForActivityResult(ActivityResultContracts.CreateDocument("application/x-pem-file")) { it?.let(model::export) }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        model = ViewModelProvider(this)[ControlModel::class.java]
        setContent {
            MaterialTheme {
                val safeFocus = remember { FocusRequester() }
                LaunchedEffect(model.pending) { if (model.pending != null) safeFocus.requestFocus() }
                Column(Modifier.fillMaxSize().background(Color(0xFF10191F)).padding(horizontal = 48.dp, vertical = 28.dp)) {
                    Text("SOVEREIGN TV", color = Color(0xFF9BB9B2), fontSize = 13.sp)
                    Text("Local control", color = Color(0xFFF3F0E8), fontSize = 36.sp, modifier = Modifier.padding(top = 8.dp))
                    Text(ControlStatus.text, color = Color(0xFF9CCDBF), fontSize = 18.sp, modifier = Modifier.padding(top = 10.dp))
                    Text(model.message, color = Color(0xFFD8D7CF), fontSize = 15.sp, modifier = Modifier.padding(top = 5.dp, bottom = 20.dp))
                    Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        if (model.pending != null) {
                            Text("Connect your household agent", color = Color.White, fontSize = 23.sp)
                            Text("Allow this agent to read and edit Home, collections and local artwork. Match the code with your agent’s setup screen.", color = Color(0xFFD8D7CF), fontSize = 17.sp)
                            Fingerprint(Identity.pin(model.pending!!))
                            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                                Action("Trust this agent", !model.busy && model.paired == null) { model.approve() }
                                Action("Cancel", !model.busy, Modifier.focusRequester(safeFocus)) { model.cancel() }
                            }
                        } else {
                            Text(if (model.paired == null) "Private until paired" else "Household agent", color = Color.White, fontSize = 23.sp)
                            Text(if (model.paired == null) "Export this TV’s public certificate, then import your agent’s public certificate. Approve access here with the remote." else "Only this agent can connect. Home works independently when local control is off.", color = Color(0xFFD8D7CF), fontSize = 17.sp)
                            model.paired?.let { Fingerprint(Identity.pin(it)) }
                            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                                Action("Export TV certificate", !model.busy && model.device != null) { export.launch("sovereign-tv-public.pem") }
                                if (model.paired == null && !model.trustUnavailable) Action("Import agent certificate", !model.busy) { pick.launch(arrayOf("*/*")) }
                                else Action("Remove agent", !model.busy) { model.revoke() }
                            }
                            if (ControlStatus.active) Action("Turn local control off", !model.busy) { model.stop() }
                            else if (model.paired != null) {
                                model.addresses.forEach { address -> Action("Enable on $address", !model.busy) { model.start(address) } }
                                if (model.addresses.isEmpty()) Text("No private IPv4 interface available", color = Color(0xFFD8D7CF))
                            }
                            Action("Refresh local status", !model.busy) { model.refresh() }
                            Text("TV identity", color = Color(0xFF9BB9B2), fontSize = 15.sp, modifier = Modifier.padding(top = 12.dp))
                            model.device?.let { Fingerprint(Identity.pin(it)) }
                            Text("Pairing and control stay local. Enable the connection here when you need it.", color = Color(0xFFAFB7B4), fontSize = 15.sp)
                        }
                    }
                }
            }
        }
    }
}
@Composable private fun Fingerprint(value: String) {
    Text(value.chunked(4).chunked(8).joinToString("\n") { it.joinToString(" ") }, fontFamily = FontFamily.Monospace, color = Color(0xFFC6DBD3), fontSize = 18.sp)
}
@Composable private fun Action(label: String, enabled: Boolean, modifier: Modifier = Modifier, click: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val ink = Color(0xFF152019); val accent = Color(0xFFD5E6B4); val idle = Color(0xFF25343B)
    Button(onClick = click, enabled = enabled, modifier = modifier.testTag("control-action:$label").onFocusChanged { focused = it.isFocused },
        shape = ButtonDefaults.shape(RoundedCornerShape(8.dp)), scale = ButtonDefaults.scale(focusedScale = 1f),
        colors = ButtonDefaults.colors(containerColor = if (focused) accent else idle, contentColor = if (focused) ink else Color(0xFFF3F0E8),
            focusedContainerColor = accent, focusedContentColor = ink)) { Text(label, fontSize = 16.sp) }
}
