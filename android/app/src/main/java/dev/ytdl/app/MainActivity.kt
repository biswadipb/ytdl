package dev.ytdl.app

import android.Manifest
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
import androidx.activity.viewModels
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat

private val LightScheme = lightColorScheme(
    primary = Color(0xFF4F46E5),
    onPrimary = Color.White,
    secondaryContainer = Color(0xFFE0E0FF),
    onSecondaryContainer = Color(0xFF1E1B6B),
    surfaceTint = Color(0xFF4F46E5),
)

private val DarkScheme = darkColorScheme(
    primary = Color(0xFF9B95FF),
    onPrimary = Color(0xFF1E1B6B),
    secondaryContainer = Color(0xFF38368F),
    onSecondaryContainer = Color(0xFFE0E0FF),
    background = Color(0xFF14141C),
    surface = Color(0xFF14141C),
    surfaceTint = Color(0xFF9B95FF),
)

class MainActivity : ComponentActivity() {
    private val vm: DownloadViewModel by viewModels()

    private val notificationPermission =
        registerForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        takeSharedLink(intent)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)

        enableEdgeToEdge()
        setContent {
            val dark = when (vm.theme) {
                "Dark" -> true
                "Light" -> false
                else -> isSystemInDarkTheme()
            }
            val view = LocalView.current
            SideEffect {
                // Dark icons on a light status bar and vice versa, following the app theme.
                WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = !dark
            }
            MaterialTheme(colorScheme = if (dark) DarkScheme else LightScheme) {
                Surface(Modifier.fillMaxSize()) { Screen(vm, ::openLogin, ::openFile) }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        vm.refreshLogins()
    }

    /** Android only lets the focused app read the clipboard, so check when the window gains focus. */
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (!hasFocus) return
        val clip = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val text = clip.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(this)?.toString() ?: return
        val link = LINK_PATTERN.find(text)?.value ?: return
        if (link !in vm.url && link != lastClipboard) {
            lastClipboard = link
            vm.clipboardLink = link
        }
    }

    private var lastClipboard: String? = null

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        takeSharedLink(intent)
    }

    private fun takeSharedLink(intent: Intent?) {
        if (intent?.action == Intent.ACTION_SEND) {
            intent.getStringExtra(Intent.EXTRA_TEXT)?.let { vm.url = it.trim() }
        }
    }

    private fun openLogin(site: Site) =
        startActivity(Intent(this, LoginActivity::class.java).putExtra("site", site.name))

    private fun openFile(entry: HistoryEntry) {
        val uri = Uri.parse(entry.uri)
        val type = contentResolver.getType(uri)
        try {
            startActivity(
                Intent(Intent.ACTION_VIEW).setDataAndType(uri, type)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            )
        } catch (e: Exception) {
            vm.message = "No app can open ${entry.name}."
        }
    }
}

@Composable
private fun Screen(vm: DownloadViewModel, onLogin: (Site) -> Unit, onOpen: (HistoryEntry) -> Unit) {
    Column(
        Modifier.fillMaxSize().systemBarsPadding().padding(16.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("ytdl", style = MaterialTheme.typography.headlineMedium)

        vm.newRelease?.let { r ->
            val context = LocalContext.current
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("ytdl ${r.version} is available.", Modifier.weight(1f),
                        color = MaterialTheme.colorScheme.onSecondaryContainer)
                    Button(onClick = {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(r.url)))
                    }) { Text("Get it") }
                    TextButton(onClick = { vm.newRelease = null }) { Text("Later") }
                }
            }
        }

        vm.clipboardLink?.let { link ->
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Link copied: ${link.take(60)}", style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSecondaryContainer)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = vm::pasteClipboardLink) { Text("Paste link") }
                        TextButton(onClick = { vm.clipboardLink = null }) { Text("Dismiss") }
                    }
                }
            }
        }

        OutlinedTextField(
            value = vm.url, onValueChange = { vm.url = it },
            label = { Text("Video links") },
            supportingText = { Text("YouTube, Instagram, X/Twitter, Facebook, Threads, Dailymotion. One per line.") },
            modifier = Modifier.fillMaxWidth(), minLines = 1, maxLines = 4,
        )
        OutlinedButton(onClick = vm::loadPreview, enabled = DownloadCenter.ready && !vm.previewLoading && vm.url.isNotBlank()) {
            Text(if (vm.previewLoading) "Loading preview…" else "Preview")
        }
        vm.preview?.let { PreviewCard(it) }
        if (vm.picker.isNotEmpty()) PickerCard(vm)

        SectionTitle("Video format")
        ChipRow(VIDEO_FORMATS, vm.format) { vm.format = it }
        SectionTitle("Audio only")
        ChipRow(AUDIO_FORMATS, vm.format) { vm.format = it }
        if (!vm.audioOnly) {
            SectionTitle("Max quality")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                QUALITIES.forEach { q ->
                    FilterChip(vm.quality == q, { vm.quality = q }, label = { Text(if (q == "best") q else "${q}p") })
                }
            }
        }

        SectionTitle("Clip a section (optional)")
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(vm.clipStart, { vm.clipStart = it }, label = { Text("Start") }, singleLine = true,
                placeholder = { Text("1:30") }, modifier = Modifier.weight(1f))
            OutlinedTextField(vm.clipEnd, { vm.clipEnd = it }, label = { Text("End") }, singleLine = true,
                placeholder = { Text("2:45") }, modifier = Modifier.weight(1f))
        }

        CheckRow("All videos in playlist/post (Preview lists them so you can pick)", vm.playlist) { vm.playlist = it }
        CheckRow("Embed cover art and tags", vm.extras) { vm.extras = it }

        if (!vm.audioOnly) {
            SectionTitle("Subtitles (saved as a separate .srt file)")
            ScrollChips(SUB_LANGS, vm.subLang, { it }, vm::chooseSubLang)
        }
        SectionTitle("File names")
        ScrollChips(NAMING.map { it.key }, vm.naming, { k -> NAMING.first { it.key == k }.label }, vm::chooseNaming)
        SectionTitle("Folders")
        ScrollChips(FOLDERS.map { it.key }, vm.folders, { k -> FOLDERS.first { it.key == k }.label }, vm::chooseFolders)

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = vm::addToQueue, enabled = DownloadCenter.ready) { Text("Add to queue") }
            OutlinedButton(onClick = { DownloadCenter.updateEngine() }, enabled = DownloadCenter.ready) { Text("Update engine") }
        }
        val note = vm.message.ifEmpty { DownloadCenter.engineStatus }
        Text(note, style = MaterialTheme.typography.bodyMedium)

        HorizontalDivider()
        SectionTitle("Queue")
        if (DownloadCenter.items.isEmpty()) {
            Text("Nothing queued.", style = MaterialTheme.typography.bodyMedium)
        } else {
            DownloadCenter.items.forEach { QueueRow(it) }
            TextButton(onClick = DownloadCenter::clearFinished) { Text("Clear finished") }
        }

        SectionTitle("History")
        if (DownloadCenter.history.isEmpty()) {
            Text("Saved files appear here. Tap one to open it.", style = MaterialTheme.typography.bodyMedium)
        } else {
            DownloadCenter.history.take(20).forEach { h ->
                Column(Modifier.fillMaxWidth().clickable { onOpen(h) }.padding(vertical = 4.dp)) {
                    Text(h.name, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(h.whenText, style = MaterialTheme.typography.bodySmall)
                }
            }
            TextButton(onClick = DownloadCenter::clearHistory) { Text("Clear history") }
        }

        HorizontalDivider()
        SectionTitle("Subscriptions")
        Text(
            "Paste a channel or playlist link and tap Follow. New uploads then download by themselves, even when the app is closed.",
            style = MaterialTheme.typography.bodySmall,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = vm::follow, enabled = DownloadCenter.ready && vm.url.isNotBlank() && !vm.followBusy) {
                Text(if (vm.followBusy) "Following…" else "Follow channel")
            }
            OutlinedButton(onClick = vm::checkSubscriptionsNow, enabled = DownloadCenter.ready && Subscriptions.list.isNotEmpty()) {
                Text("Check now")
            }
        }
        Text("When following, also download the latest", style = MaterialTheme.typography.bodySmall)
        ChipRow(listOf("0", "1", "3", "5"), vm.followBackfill.toString()) { vm.followBackfill = it.toInt() }
        Subscriptions.list.forEach { SubscriptionRow(it) }
        SectionTitle("Check every (hours)")
        ChipRow(listOf("1", "3", "6", "12", "24"), Subscriptions.intervalHours.toString()) { Subscriptions.chooseInterval(it.toInt()) }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Switch(Subscriptions.onlyCharging, Subscriptions::chooseCharging)
            Text("Only while charging")
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Switch(Subscriptions.onlyNight, Subscriptions::chooseNight)
            Text("Only at night (11 pm to 7 am)")
        }
        Text(
            "These apply to automatic checks and the downloads they start. Check now and downloads you start yourself are never delayed.",
            style = MaterialTheme.typography.bodySmall,
        )

        HorizontalDivider()
        SectionTitle("Network")
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Switch(DownloadCenter.allowMobileData, DownloadCenter::chooseMobileData)
            Column {
                Text(if (DownloadCenter.allowMobileData) "Downloading on any network" else "Wi-Fi only")
                Text(
                    if (DownloadCenter.allowMobileData) "Mobile data can be used, which may cost money."
                    else "Downloads wait until you're on an unmetered Wi-Fi network.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }

        SectionTitle("Download speed limit")
        ScrollChips(SPEEDS.indices.map { it.toString() }, DownloadCenter.speedIndex.toString(),
            { SPEEDS[it.toInt()].first }) { DownloadCenter.chooseSpeed(it.toInt()) }
        SectionTitle("Downloads at once (the speed limit is shared)")
        ChipRow(listOf("1", "2", "3"), DownloadCenter.parallel.toString()) { DownloadCenter.chooseParallel(it.toInt()) }
        SectionTitle("Retry failed downloads automatically")
        ChipRow(listOf("0", "1", "2", "3"), DownloadCenter.autoRetry.toString()) { DownloadCenter.chooseRetries(it.toInt()) }

        SectionTitle("Login for private posts")
        Text(
            "Sign in once and ytdl can download posts that need an account. Your login stays on this phone.",
            style = MaterialTheme.typography.bodySmall,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Site.entries.take(2).forEach { LoginChip(it, vm.loggedIn, onLogin) }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Site.entries.drop(2).forEach { LoginChip(it, vm.loggedIn, onLogin) }
        }
        if (vm.loggedIn.isNotEmpty()) {
            CheckRow("Use my login when downloading", vm.useLogin) { vm.useLogin = it }
            TextButton(onClick = vm::logOut) { Text("Sign out of everything") }
        }

        SectionTitle("Theme")
        ChipRow(THEMES, vm.theme, vm::chooseTheme)
    }
}

@Composable
private fun SectionTitle(text: String) = Text(text, style = MaterialTheme.typography.labelLarge)

@Composable
private fun ChipRow(options: List<String>, selected: String, onSelect: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { f -> FilterChip(selected == f, { onSelect(f) }, label = { Text(f) }) }
    }
}

@Composable
private fun CheckRow(text: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Checkbox(checked, onChange)
        Text(text)
    }
}

@Composable
private fun LoginChip(site: Site, loggedIn: Set<Site>, onLogin: (Site) -> Unit) {
    val ok = site in loggedIn
    FilterChip(ok, { onLogin(site) }, label = { Text(if (ok) "${site.label}: signed in" else "Sign in to ${site.label}") })
}

@Composable
private fun PreviewCard(p: Preview) {
    Card {
        Row(Modifier.padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            p.thumbnail?.let {
                Image(it, contentDescription = null, modifier = Modifier.width(120.dp).heightIn(max = 90.dp))
            }
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(p.title, style = MaterialTheme.typography.titleSmall, maxLines = 3, overflow = TextOverflow.Ellipsis)
                p.uploader?.let { Text("by $it", style = MaterialTheme.typography.bodySmall) }
                if (p.duration > 0) {
                    val h = p.duration / 3600; val m = p.duration % 3600 / 60; val s = p.duration % 60
                    Text("Length " + if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%d:%02d".format(m, s),
                        style = MaterialTheme.typography.bodySmall)
                }
                if (p.heights.isNotEmpty()) {
                    Text("Qualities: " + p.heights.joinToString(", ") { "${it}p" }, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun QueueRow(item: Item) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(item.title, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    if (item.detail.isNotEmpty() && (item.status == Status.Failed || item.status == Status.Retrying))
                        (if (item.status == Status.Failed) "Failed: " else "") + item.detail
                    else item.status.label,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2, overflow = TextOverflow.Ellipsis,
                )
            }
            if (item.status.active) TextButton(onClick = { DownloadCenter.cancel(item) }) { Text("Cancel") }
            else if (item.status == Status.Failed || item.status == Status.Cancelled)
                TextButton(onClick = { DownloadCenter.retry(item) }) { Text("Retry") }
        }
        if (item.status == Status.Downloading) {
            LinearProgressIndicator(progress = { item.progress }, modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun ScrollChips(keys: List<String>, selected: String, label: (String) -> String, onSelect: (String) -> Unit) {
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        keys.forEach { k -> FilterChip(selected == k, { onSelect(k) }, label = { Text(label(k)) }) }
    }
}

@Composable
private fun PickerCard(vm: DownloadViewModel) {
    Card {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("${vm.picker.size} videos found. Tick the ones you want.", style = MaterialTheme.typography.titleSmall)
            Row {
                TextButton(onClick = { vm.selectAll(true) }) { Text("Select all") }
                TextButton(onClick = { vm.selectAll(false) }) { Text("Select none") }
            }
            Column(Modifier.heightIn(max = 320.dp).verticalScroll(rememberScrollState())) {
                vm.picker.forEach { e ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(e.selected, { e.selected = it })
                        Text(e.title, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

@Composable
private fun SubscriptionRow(sub: Subscription) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(sub.name, maxLines = 1, overflow = TextOverflow.Ellipsis)
        val checked = if (sub.lastChecked == 0L) "never checked"
        else "checked " + android.text.format.DateUtils.getRelativeTimeSpanString(sub.lastChecked)
        Text(
            (if (sub.enabled) "On" else "Paused") + ", $checked" + if (sub.lastError.isNotEmpty()) " (error: ${sub.lastError})" else "",
            style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis,
        )
        Row {
            TextButton(onClick = { Subscriptions.setEnabled(sub.id, !sub.enabled) }) { Text(if (sub.enabled) "Pause" else "Resume") }
            TextButton(onClick = { Subscriptions.unfollow(sub.id) }) { Text("Unfollow") }
        }
    }
}
