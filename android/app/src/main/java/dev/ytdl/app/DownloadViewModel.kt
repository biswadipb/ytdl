package dev.ytdl.app

import android.app.Application
import android.graphics.BitmapFactory
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.net.URL

class Preview(
    val title: String,
    val uploader: String?,
    val duration: Int,
    val heights: List<Int>,
    val thumbnail: ImageBitmap?,
)

class PickEntry(val title: String, val url: String, val duration: Int, selected: Boolean = true) {
    var selected by mutableStateOf(selected)
}

class DownloadViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("ytdl", Application.MODE_PRIVATE)

    var url by mutableStateOf("")
    var format by mutableStateOf("mp4")
    var quality by mutableStateOf("best")
    var playlist by mutableStateOf(false)
    var extras by mutableStateOf(true)
    var useLogin by mutableStateOf(true)
    var clipStart by mutableStateOf("")
    var clipEnd by mutableStateOf("")
    var naming by mutableStateOf(prefs.getString("naming", "title-id") ?: "title-id")
        private set
    var folders by mutableStateOf(prefs.getString("folders", "flat") ?: "flat")
        private set
    var subLang by mutableStateOf(prefs.getString("sub_lang", "Off") ?: "Off")
        private set
    val audioOnly get() = format in AUDIO_FORMATS

    var message by mutableStateOf("")
    var preview by mutableStateOf<Preview?>(null)
    var previewLoading by mutableStateOf(false)
    val picker = mutableStateListOf<PickEntry>()
    private var pickerUrl: String? = null
    var clipboardLink by mutableStateOf<String?>(null)
    var loggedIn by mutableStateOf(setOf<Site>())
    var newRelease by mutableStateOf<ReleaseInfo?>(null)
    var sharePrompt by mutableStateOf(false)
    var shareAuto by mutableStateOf(SharePrefs.auto(app))
        private set
    var shareSummary by mutableStateOf(SharePrefs.summary(app))
        private set
    var followBackfill by mutableStateOf(0)
    var followBusy by mutableStateOf(false)

    var theme by mutableStateOf(prefs.getString("theme", "System") ?: "System")
        private set

    init {
        DownloadCenter.init(app)
        Subscriptions.init(app, schedule = true)
        refreshLogins()
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val current = app.packageManager.getPackageInfo(app.packageName, 0).versionName
                newRelease = checkForNewRelease(current)
            } catch (e: Exception) { /* offline or rate limited: try next launch */ }
        }
    }

    fun chooseTheme(choice: String) { theme = choice; prefs.edit().putString("theme", choice).apply() }
    fun chooseNaming(key: String) { naming = key; prefs.edit().putString("naming", key).apply() }
    fun chooseFolders(key: String) { folders = key; prefs.edit().putString("folders", key).apply() }
    fun chooseSubLang(lang: String) { subLang = lang; prefs.edit().putString("sub_lang", lang).apply() }

    fun refreshLogins() {
        loggedIn = Site.entries.filter { CookieStore.isLoggedIn(getApplication(), it) }.toSet()
    }

    fun logOut() {
        CookieStore.logOut(getApplication())
        refreshLogins()
    }

    fun addToQueue() {
        val links = url.lines().map { it.trim() }.filter { it.isNotEmpty() }
        if (links.isEmpty()) { message = "Paste at least one link."; return }
        val start: Double?
        val end: Double?
        try {
            start = parseClock(clipStart)
            end = parseClock(clipEnd)
        } catch (e: NumberFormatException) {
            message = "Clip times look like 1:30 or 90."
            return
        }
        if (end != null && end <= (start ?: 0.0)) { message = "Clip end must be after its start."; return }
        val chosen = picker.filter { it.selected }
        if (pickerUrl in links && picker.isNotEmpty() && chosen.isEmpty()) {
            message = "Select at least one video from the list."
            return
        }
        val lowSpace = Storage.isLow()
        val opts = Options(format, quality, playlist, start, end, extras, useLogin && loggedIn.isNotEmpty(),
            naming, folders, subLang.takeIf { it != "Off" && !audioOnly })
        links.forEach { link ->
            if (link == pickerUrl && chosen.isNotEmpty()) {
                // Picked videos become separate downloads, so each can be cancelled or retried on its own.
                chosen.forEach { DownloadCenter.enqueue(it.url, opts.copy(playlist = false), it.title) }
            } else {
                DownloadCenter.enqueue(link, opts)
            }
        }
        val count = if (pickerUrl in links && chosen.isNotEmpty()) chosen.size + links.size - 1 else links.size
        url = ""
        preview = null
        clearPicker()
        message = (if (count == 1) "Added to the queue." else "Added $count downloads to the queue.") +
            if (lowSpace) " Warning: only ${humanSize(Storage.freeBytes)} of space is free." else ""
    }

    private fun clearPicker() { picker.clear(); pickerUrl = null }

    private fun cookieArgs(req: YoutubeDLRequest) {
        if (useLogin) CookieStore.merged(getApplication())?.let { req.addOption("--cookies", it.absolutePath) }
    }

    private fun friendly(e: Exception) =
        e.message?.lineSequence()?.firstOrNull { it.contains("ERROR") }?.substringAfter("ERROR:")?.trim()
            ?: e.message?.lineSequence()?.firstOrNull { it.isNotBlank() } ?: e.toString()

    fun loadPreview() {
        val link = url.lines().map { it.trim() }.firstOrNull { it.isNotEmpty() }
        if (link == null) { message = "Paste a link to preview."; return }
        if (!DownloadCenter.ready || previewLoading) return
        previewLoading = true
        message = ""
        viewModelScope.launch(Dispatchers.IO) {
            try {
                if (isThreadsUrl(link)) {
                    val post = ThreadsResolver.resolve(getApplication(), link)
                    val bitmap = post.thumbnail?.let {
                        try { URL(it).openStream().use { s -> BitmapFactory.decodeStream(s) }?.asImageBitmap() } catch (e: Exception) { null }
                    }
                    clearPicker()
                    preview = Preview(post.title.ifBlank { "Threads post ${post.code}" }, post.user, 0, emptyList(), bitmap)
                    return@launch
                }
                if (playlist && loadPlaylist(link)) return@launch
                val req = YoutubeDLRequest(link)
                cookieArgs(req)
                val info = YoutubeDL.getInstance().getInfo(req)
                val bitmap = info.thumbnail?.let {
                    try {
                        URL(it).openStream().use { s -> BitmapFactory.decodeStream(s) }?.asImageBitmap()
                    } catch (e: Exception) { null }
                }
                val heights = info.formats?.map { it.height }?.filter { it > 0 }?.distinct()?.sorted().orEmpty()
                clearPicker()
                preview = Preview(info.title ?: "Untitled", info.uploader, info.duration, heights, bitmap)
            } catch (e: Exception) {
                preview = null
                message = "Couldn't load a preview: ${friendly(e)}"
            } finally {
                previewLoading = false
            }
        }
    }

    /** Lists the videos in a playlist or multi-video post. Returns false when the link is a single video. */
    private fun loadPlaylist(link: String): Boolean {
        val req = YoutubeDLRequest(link)
        req.addOption("--flat-playlist")
        req.addOption("--dump-single-json")
        cookieArgs(req)
        val out = YoutubeDL.getInstance().execute(req).out
        val json = JSONObject(out.substring(out.indexOf('{')))
        val arr = json.optJSONArray("entries") ?: return false
        val entries = (0 until arr.length()).mapNotNull { i ->
            val e = arr.optJSONObject(i) ?: return@mapNotNull null
            val u = e.optString("url").ifEmpty { e.optString("webpage_url") }
            if (!u.startsWith("http")) null else PickEntry(e.optString("title", u), u, e.optInt("duration", 0))
        }
        if (entries.size < 2) return false
        preview = null
        picker.clear()
        picker.addAll(entries)
        pickerUrl = link
        return true
    }

    fun selectAll(on: Boolean) = picker.forEach { it.selected = on }

    private fun currentOptions() = Options(format, quality, false, null, null, extras, useLogin && loggedIn.isNotEmpty(),
        naming, folders, subLang.takeIf { it != "Off" && !audioOnly })

    /** Follow the first link as a channel or playlist. */
    fun follow() {
        val link = url.lines().map { it.trim() }.firstOrNull { it.isNotEmpty() }
        if (link == null) { message = "Paste a channel or playlist link, then tap Follow."; return }
        if (!DownloadCenter.ready || followBusy) return
        followBusy = true
        message = "Following…"
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val (sub, count) = Subscriptions.follow(link, currentOptions(), followBackfill)
                url = ""
                message = "Following ${sub.name}." + if (count > 0) " Downloading the latest $count." else " New uploads download automatically."
            } catch (e: Exception) {
                message = "Couldn't follow that link: ${friendly(e)}"
            } finally {
                followBusy = false
            }
        }
    }

    fun checkSubscriptionsNow() {
        if (!DownloadCenter.ready) return
        message = "Checking subscriptions…"
        viewModelScope.launch(Dispatchers.IO) {
            val queued = Subscriptions.checkAll(force = true)
            message = if (queued > 0) "$queued new upload(s) added to the queue." else "No new uploads."
        }
    }

    /** Remember the format and quality currently selected for links shared into ytdl. */
    fun saveSharePreset() {
        SharePrefs.save(getApplication(), currentOptions())
        shareSummary = SharePrefs.summary(getApplication())
    }

    fun chooseShareAuto(on: Boolean) {
        if (on && SharePrefs.preset(getApplication()) == null) saveSharePreset()
        SharePrefs.setAuto(getApplication(), on)
        shareAuto = on
    }

    /** First shared link: the user picked a format on screen, so download with it now and do the same next time. */
    fun downloadAndRemember() {
        saveSharePreset()
        chooseShareAuto(true)
        sharePrompt = false
        addToQueue()
    }

    fun dismissSharePrompt() {
        SharePrefs.setAsked(getApplication())
        sharePrompt = false
    }

    fun pasteClipboardLink() {
        clipboardLink?.let { url = if (url.isBlank()) it else url.trimEnd() + "\n" + it }
        clipboardLink = null
    }
}
