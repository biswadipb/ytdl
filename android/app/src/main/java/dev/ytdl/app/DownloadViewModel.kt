package dev.ytdl.app

import android.app.Application
import android.graphics.BitmapFactory
import androidx.compose.runtime.getValue
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
import java.net.URL

class Preview(
    val title: String,
    val uploader: String?,
    val duration: Int,
    val heights: List<Int>,
    val thumbnail: ImageBitmap?,
)

class DownloadViewModel(app: Application) : AndroidViewModel(app) {
    var url by mutableStateOf("")
    var format by mutableStateOf("mp4")
    var quality by mutableStateOf("best")
    var playlist by mutableStateOf(false)
    var extras by mutableStateOf(true)
    var useLogin by mutableStateOf(true)
    var clipStart by mutableStateOf("")
    var clipEnd by mutableStateOf("")
    val audioOnly get() = format in AUDIO_FORMATS

    var message by mutableStateOf("")
    var preview by mutableStateOf<Preview?>(null)
    var previewLoading by mutableStateOf(false)
    var clipboardLink by mutableStateOf<String?>(null)
    var loggedIn by mutableStateOf(setOf<Site>())

    private val prefs = app.getSharedPreferences("ytdl", Application.MODE_PRIVATE)
    var theme by mutableStateOf(prefs.getString("theme", "System") ?: "System")
        private set

    init {
        DownloadCenter.init(app)
        refreshLogins()
    }

    fun chooseTheme(choice: String) {
        theme = choice
        prefs.edit().putString("theme", choice).apply()
    }

    fun refreshLogins() {
        loggedIn = Site.entries.filter { CookieStore.isLoggedIn(getApplication(), it) }.toSet()
    }

    fun logOut() {
        CookieStore.logOut(getApplication())
        refreshLogins()
    }

    /** "90", "1:30" or "1:02:03" to seconds; blank is null; anything else throws. */
    private fun seconds(text: String): Double? {
        val t = text.trim()
        if (t.isEmpty()) return null
        return t.split(":").fold(0.0) { acc, part -> acc * 60 + part.toDouble() }
    }

    fun addToQueue() {
        val links = url.lines().map { it.trim() }.filter { it.isNotEmpty() }
        if (links.isEmpty()) { message = "Paste at least one link."; return }
        val start: Double?
        val end: Double?
        try {
            start = seconds(clipStart)
            end = seconds(clipEnd)
        } catch (e: NumberFormatException) {
            message = "Clip times look like 1:30 or 90."
            return
        }
        if (end != null && end <= (start ?: 0.0)) { message = "Clip end must be after its start."; return }
        val opts = Options(format, quality, playlist, start, end, extras, useLogin && loggedIn.isNotEmpty())
        links.forEach { DownloadCenter.enqueue(it, opts) }
        url = ""
        preview = null
        message = if (links.size == 1) "Added to the queue." else "Added ${links.size} links to the queue."
    }

    fun loadPreview() {
        val link = url.lines().map { it.trim() }.firstOrNull { it.isNotEmpty() }
        if (link == null) { message = "Paste a link to preview."; return }
        if (!DownloadCenter.ready || previewLoading) return
        previewLoading = true
        message = ""
        viewModelScope.launch(Dispatchers.IO) {
            try {
                val req = YoutubeDLRequest(link)
                if (useLogin) CookieStore.merged(getApplication())?.let { req.addOption("--cookies", it.absolutePath) }
                val info = YoutubeDL.getInstance().getInfo(req)
                val bitmap = info.thumbnail?.let {
                    try {
                        URL(it).openStream().use { s -> BitmapFactory.decodeStream(s) }?.asImageBitmap()
                    } catch (e: Exception) { null }
                }
                val heights = info.formats?.map { it.height }?.filter { it > 0 }?.distinct()?.sorted().orEmpty()
                preview = Preview(info.title ?: "Untitled", info.uploader, info.duration, heights, bitmap)
            } catch (e: Exception) {
                preview = null
                message = "Couldn't load a preview: " +
                    (e.message?.lineSequence()?.firstOrNull { it.contains("ERROR") }?.substringAfter("ERROR:")?.trim()
                        ?: e.message?.lineSequence()?.firstOrNull { it.isNotBlank() } ?: e.toString())
            } finally {
                previewLoading = false
            }
        }
    }

    fun pasteClipboardLink() {
        clipboardLink?.let { url = if (url.isBlank()) it else url.trimEnd() + "\n" + it }
        clipboardLink = null
    }
}
