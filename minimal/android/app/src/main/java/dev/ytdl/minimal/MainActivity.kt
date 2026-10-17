package dev.ytdl.minimal

import android.Manifest
import android.app.DownloadManager
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.compose.ui.graphics.Path as GPath

class Palette(
    val bg: Color, val fg: Color, val muted: Color, val field: Color, val ring: Color, val accent: Color,
    val btn: Color, val btnFg: Color, val seg: Color, val segOn: Color, val segOnFg: Color, val segFg: Color,
    val drop: Color, val line: Color, val track: Color, val tickFg: Color, val bad: Color, val dark: Boolean,
)

private val Light = Palette(
    Color(0xFFFFFFFF), Color(0xFF17172B), Color(0xFF6B6B85), Color(0xFFFFFFFF), Color(0xFFE8E7FD), Color(0xFF4F46E5),
    Color(0xFF4F46E5), Color(0xFFFFFFFF), Color(0xFFF0F0F7), Color(0xFFFFFFFF), Color(0xFF17172B), Color(0xFF6B6B85),
    Color(0xFFF0F0F7), Color(0xFFEEEEF6), Color(0xFFE3E3EE), Color(0xFFFFFFFF), Color(0xFFD93F3F), false,
)
private val Dark = Palette(
    Color(0xFF14141D), Color(0xFFECECF6), Color(0xFF8D8DA8), Color(0xFF1F1F2D), Color(0xFF2D2A66), Color(0xFF7B73F5),
    Color(0xFF7B73F5), Color(0xFF14141D), Color(0xFF1F1F2D), Color(0xFF2D2A66), Color(0xFFC9C5FF), Color(0xFFA3A3BB),
    Color(0xFF1F1F2D), Color(0xFF26263A), Color(0xFF26263A), Color(0xFF14141D), Color(0xFFFF7B7B), true,
)

class MainActivity : ComponentActivity() {
    private val vm: MinimalViewModel by viewModels()

    private val folderPicker = registerForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri != null) SaveTarget.choose(this, uri)
    }

    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Downloads.init(application)
        takeIntent(intent)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)

        enableEdgeToEdge()
        setContent {
            val system = isSystemInDarkTheme()
            val p = if (when (vm.theme) { "dark" -> true; "light" -> false; else -> system }) Dark else Light
            val view = LocalView.current
            SideEffect { WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !p.dark }
            MaterialTheme(colorScheme = if (p.dark) darkColorScheme(surface = p.field, onSurface = p.fg) else lightColorScheme()) {
                Screen(vm, p, ::openFile, ::openDownloads, ::pasteFromClipboard) { folderPicker.launch(null) }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        takeIntent(intent)
    }

    private fun takeIntent(intent: Intent?) {
        if (intent?.action == Intent.ACTION_SEND) {
            intent.getStringExtra(Intent.EXTRA_TEXT)?.let { vm.link = firstLink(it) ?: it.trim() }
        }
        if (BuildConfig.DEBUG && intent?.getBooleanExtra("demo", false) == true) Downloads.demo()   // for screenshots only
    }

    /** A copied link fills the box when you come back. It never downloads by itself. */
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus && vm.link.isEmpty()) clipboardLink()?.let { vm.link = it }
    }

    private fun clipboardLink(): String? {
        val clip = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        return firstLink(clip.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(this)?.toString())
    }

    private fun pasteFromClipboard() {
        val clip = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val raw = clip.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(this)?.toString()
        val text = firstLink(raw) ?: raw?.trim()
        if (text.isNullOrEmpty()) vm.message = "Nothing to paste. Copy a video link first." else { vm.link = text; vm.message = "" }
    }

    private fun openFile(d: Download) {
        val uri = Uri.parse(d.uri ?: return)
        try {
            startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, contentResolver.getType(uri))
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
        } catch (e: Exception) { vm.message = "No app can open that file." }
    }

    private fun openDownloads() = startActivity(Intent(DownloadManager.ACTION_VIEW_DOWNLOADS))
}

@Composable
private fun LogoMark(size: Int) {
    Canvas(Modifier.size(size.dp)) {
        val k = this.size.width / 160f
        drawRoundRect(Color(0xFF4F46E5), size = this.size, cornerRadius = androidx.compose.ui.geometry.CornerRadius(36f * k))
        val stroke = Stroke(14f * k, cap = StrokeCap.Round, join = StrokeJoin.Round)
        val path = GPath().apply {
            moveTo(80f * k, 34f * k); lineTo(80f * k, 88f * k)
            moveTo(54f * k, 66f * k); lineTo(80f * k, 92f * k); lineTo(106f * k, 66f * k)
            moveTo(44f * k, 108f * k); lineTo(44f * k, 126f * k); lineTo(116f * k, 126f * k); lineTo(116f * k, 108f * k)
        }
        drawPath(path, Color.White, style = stroke)
    }
}

@Composable
private fun Screen(vm: MinimalViewModel, p: Palette, onOpen: (Download) -> Unit, onFolder: () -> Unit, onPaste: () -> Unit, onPickFolder: () -> Unit) {
    Column(
        Modifier.fillMaxSize().background(p.bg).systemBarsPadding().imePadding().padding(horizontal = 22.dp).padding(top = 14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(9.dp)) {
            LogoMark(26)
            Text("ytdl", color = p.fg, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            SegmentedControl(THEME_LABELS, THEMES.indexOf(vm.theme), { vm.chooseTheme(THEMES[it]) }, p,
                Modifier.width(168.dp), height = 30.dp, fontSize = 11.sp, corner = 9.dp, inner = 7.dp)
        }
        Spacer(Modifier.height(14.dp))
        LinkField(vm, p, onPaste)
        Spacer(Modifier.height(12.dp))
        Box(
            Modifier.fillMaxWidth().height(48.dp).clip(RoundedCornerShape(14.dp)).background(p.btn).clickable { vm.download() },
            contentAlignment = Alignment.Center,
        ) { Text("Download", color = p.btnFg, fontWeight = FontWeight.Bold, fontSize = 15.sp) }
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth()) {
            Segmented(vm, p, Modifier.weight(2.2f))
            Spacer(Modifier.width(8.dp))
            QualityDropdown(vm, p, Modifier.weight(1f))
        }
        val context = LocalContext.current
        Spacer(Modifier.height(10.dp))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Saving to ${SaveTarget.label}", color = p.muted, fontSize = 12.sp, maxLines = 1,
                overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
            Spacer(Modifier.weight(1f))
            if (SaveTarget.isCustom) {
                Text("Default", color = p.accent, fontSize = 12.sp, modifier = Modifier.clickable { SaveTarget.useDefault(context) })
                Spacer(Modifier.width(12.dp))
            }
            Text("Change", color = p.accent, fontSize = 12.sp, modifier = Modifier.clickable { onPickFolder() })
        }
        if (SaveTarget.note.isNotEmpty()) Text(SaveTarget.note, color = p.muted, fontSize = 11.sp)
        if (vm.message.isNotEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text(vm.message, color = p.muted, fontSize = 12.sp)
        }
        Spacer(Modifier.height(16.dp))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("THIS SESSION", color = p.muted, fontSize = 11.sp, letterSpacing = 0.6.sp)
            Spacer(Modifier.weight(1f))
            Text("Open Downloads", color = p.accent, fontSize = 12.sp, modifier = Modifier.clickable { onFolder() })
        }
        LazyColumn(Modifier.fillMaxWidth().weight(1f)) {
            items(Downloads.list, key = { it.id }) { SessionRow(it, p, onOpen) }
        }
    }
}

@Composable
private fun LinkField(vm: MinimalViewModel, p: Palette, onPaste: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(17.dp)).background(if (focused) p.ring else Color.Transparent).padding(3.dp)) {
        Row(
            Modifier.fillMaxWidth().height(48.dp).clip(RoundedCornerShape(14.dp)).background(p.field)
                .border(if (focused) 1.5.dp else 1.dp, if (focused || vm.link.isNotEmpty()) p.accent else p.line, RoundedCornerShape(14.dp))
                .padding(horizontal = 15.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.weight(1f)) {
                if (vm.link.isEmpty()) Text("Paste a video link", color = p.muted, fontSize = 14.sp)
                BasicTextField(
                    value = vm.link, onValueChange = { vm.link = it }, singleLine = true,
                    textStyle = androidx.compose.ui.text.TextStyle(color = p.fg, fontSize = 14.sp),
                    cursorBrush = SolidColor(p.accent), modifier = Modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused },
                )
            }
            Text("Paste", color = p.accent, fontWeight = FontWeight.SemiBold, fontSize = 13.sp,
                modifier = Modifier.padding(start = 10.dp).clickable { onPaste() })
        }
    }
}

/** One switch used everywhere: Video | Audio, and Auto | Light | Dark. */
@Composable
private fun SegmentedControl(
    labels: List<String>, selected: Int, onSelect: (Int) -> Unit, p: Palette, modifier: Modifier = Modifier,
    height: androidx.compose.ui.unit.Dp = 40.dp, fontSize: androidx.compose.ui.unit.TextUnit = 13.sp,
    corner: androidx.compose.ui.unit.Dp = 12.dp, inner: androidx.compose.ui.unit.Dp = 9.dp,
) {
    Row(modifier.height(height).clip(RoundedCornerShape(corner)).background(p.seg).padding(3.dp)) {
        labels.forEachIndexed { i, label ->
            val on = i == selected
            Box(
                Modifier.weight(1f).fillMaxHeight().clip(RoundedCornerShape(inner)).background(if (on) p.segOn else Color.Transparent)
                    .clickable { onSelect(i) },
                contentAlignment = Alignment.Center,
            ) { Text(label, color = if (on) p.segOnFg else p.segFg, fontSize = fontSize, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal) }
        }
    }
}

@Composable
private fun Segmented(vm: MinimalViewModel, p: Palette, modifier: Modifier) =
    SegmentedControl(listOf("Video", "Audio"), if (vm.audio) 1 else 0, { vm.chooseMode(it == 1) }, p, modifier)

@Composable
private fun QualityDropdown(vm: MinimalViewModel, p: Palette, modifier: Modifier) {
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        Row(
            Modifier.fillMaxWidth().height(40.dp).clip(RoundedCornerShape(12.dp)).background(p.drop).clickable { open = true }
                .padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(vm.choices[vm.choiceIndex].first, color = p.fg, fontSize = 13.sp, modifier = Modifier.weight(1f), maxLines = 1)
            Text("▾", color = p.muted, fontSize = 13.sp)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            vm.choices.forEachIndexed { i, (label, _) ->
                DropdownMenuItem(text = { Text(label) }, onClick = { vm.chooseQuality(i); open = false })
            }
        }
    }
}

@Composable
private fun SessionRow(d: Download, p: Palette, onOpen: (Download) -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        HorizontalDivider(color = p.line)
        Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.Top) {
            StatusDot(d.status, p)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(d.title, color = p.fg, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (d.status == Status.Running || d.status == Status.Queued) {
                    Spacer(Modifier.height(5.dp))
                    Box(Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)).background(p.track)) {
                        Box(Modifier.fillMaxWidth(d.progress.coerceIn(0.02f, 1f)).fillMaxHeight().background(p.accent))
                    }
                }
                if (d.status == Status.Failed || d.status == Status.Cancelled) {
                    Text(if (d.status == Status.Failed) d.error else "Cancelled", color = p.muted, fontSize = 12.sp, maxLines = 2)
                }
            }
            Spacer(Modifier.width(10.dp))
            when (d.status) {
                Status.Queued, Status.Running -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(if (d.status == Status.Running && d.progress > 0) "${(d.progress * 100).toInt()}%" else "Waiting",
                        color = p.muted, fontSize = 12.sp)
                    Text("Cancel", color = p.accent, fontSize = 12.sp, modifier = Modifier.padding(start = 10.dp).clickable { Downloads.cancel(d) })
                }
                Status.Done -> Text("Open", color = p.accent, fontSize = 12.sp, modifier = Modifier.clickable { onOpen(d) })
                else -> Text("Retry", color = p.accent, fontSize = 12.sp, modifier = Modifier.clickable { Downloads.retry(d) })
            }
        }
    }
}

@Composable
private fun StatusDot(status: Status, p: Palette) {
    when (status) {
        Status.Done, Status.Failed, Status.Cancelled -> Canvas(Modifier.size(16.dp)) {
            val w = size.width
            drawCircle(if (status == Status.Done) p.accent else p.bad)
            val mark = Stroke(w * 0.11f, cap = StrokeCap.Round, join = StrokeJoin.Round)
            if (status == Status.Done) {
                val tick = GPath().apply {
                    moveTo(w * 0.28f, w * 0.53f); lineTo(w * 0.44f, w * 0.68f); lineTo(w * 0.73f, w * 0.34f)
                }
                drawPath(tick, p.tickFg, style = mark)
            } else {
                drawLine(p.tickFg, Offset(w * 0.5f, w * 0.27f), Offset(w * 0.5f, w * 0.58f), strokeWidth = w * 0.11f, cap = StrokeCap.Round)
                drawCircle(p.tickFg, radius = w * 0.07f, center = Offset(w * 0.5f, w * 0.74f))
            }
        }
        else -> Canvas(Modifier.size(16.dp)) {
            drawCircle(p.accent, radius = size.width / 2 - 1.5f, style = Stroke(3f))
            drawArc(p.bg, 60f, 100f, false, topLeft = Offset(1.5f, 1.5f), size = Size(size.width - 3f, size.height - 3f), style = Stroke(4f))
        }
    }
}
