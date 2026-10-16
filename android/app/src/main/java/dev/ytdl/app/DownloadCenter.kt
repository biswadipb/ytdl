package dev.ytdl.app

import android.app.Application
import android.content.ContentValues
import android.content.Context
import android.app.PendingIntent
import android.content.Intent
import android.net.Uri
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Environment
import android.provider.MediaStore
import android.webkit.MimeTypeMap
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

val QUALITIES = listOf("best", "1080", "720", "480", "360")
val VIDEO_FORMATS = listOf("mp4", "mkv", "webm")
val AUDIO_FORMATS = listOf("mp3", "m4a", "opus", "wav", "flac")
val THEMES = listOf("System", "Light", "Dark")

class NameStyle(val key: String, val label: String, val template: String)

val NAMING = listOf(
    NameStyle("title-id", "Title [id]", "%(title).150B [%(id)s]"),
    NameStyle("title", "Title only", "%(title).150B"),
    NameStyle("channel-title", "Channel - Title", "%(uploader,channel|Unknown)s - %(title).120B"),
    NameStyle("date-title", "Date - Title", "%(upload_date>%Y-%m-%d|undated)s - %(title).120B"),
)
val FOLDERS = listOf(
    NameStyle("flat", "One folder", ""),
    NameStyle("channel", "Per channel", "%(uploader,channel|Unknown)s/"),
    NameStyle("site", "Per site", "%(extractor_key)s/"),
    NameStyle("site-channel", "Site, then channel", "%(extractor_key)s/%(uploader,channel|Unknown)s/"),
)
val SUB_LANGS = listOf("Off", "en", "es", "fr", "de", "pt", "it", "ru", "ja", "ko", "zh", "ar", "hi", "bn", "tr")
val SPEEDS = listOf("Unlimited" to 0L, "500 KB/s" to 500_000L, "1 MB/s" to 1_000_000L,
    "2 MB/s" to 2_000_000L, "5 MB/s" to 5_000_000L, "10 MB/s" to 10_000_000L)

/** Formats whose cover art can be embedded with the ffmpeg that ships in the app. */
private val COVER_FORMATS = setOf("mp3", "flac", "opus", "mkv")
private val MEDIA_EXTENSIONS = setOf("mp4", "mkv", "webm", "mp3", "m4a", "opus", "wav", "flac", "mov", "ogg", "srt")
val LINK_PATTERN = Regex(
    "https?://([\\w-]+\\.)*(youtube\\.com|youtu\\.be|instagram\\.com|x\\.com|twitter\\.com|" +
        "facebook\\.com|fb\\.watch|threads\\.(net|com)|dailymotion\\.com|dai\\.ly)/\\S+", RegexOption.IGNORE_CASE
)

enum class Status(val label: String) {
    Queued("Queued"), WaitingForWifi("Waiting for Wi-Fi"), Retrying("Retrying"), Downloading("Downloading"),
    Done("Done"), Failed("Failed"), Cancelled("Cancelled");

    val active get() = this == Queued || this == WaitingForWifi || this == Downloading || this == Retrying
}

data class Options(
    val format: String,
    val quality: String,
    val playlist: Boolean,
    val clipStart: Double?,
    val clipEnd: Double?,
    val extras: Boolean,
    val useLogin: Boolean,
    val naming: String = "title-id",
    val folders: String = "flat",
    val subLang: String? = null,
) {
    val audioOnly get() = format in AUDIO_FORMATS
    val clipped get() = clipStart != null || clipEnd != null
}

class Item(
    val id: Int, val url: String, val options: Options, presetTitle: String? = null,
    val subId: String? = null, val videoId: String? = null,
) {
    var title by mutableStateOf(presetTitle ?: url)
    var attempts = 0
    var resultUri: String? = null
    var status by mutableStateOf(Status.Queued)
    var progress by mutableFloatStateOf(0f)
    var detail by mutableStateOf("")
    @Volatile var cancelRequested = false
    val processId get() = "ytdl-$id"
}

data class HistoryEntry(val name: String, val uri: String, val whenText: String)

object DownloadCenter {
    private lateinit var app: Application
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var runner: Job? = null
    private var nextId = 1
    private val engineReady = CompletableDeferred<Unit>()

    val items = mutableStateListOf<Item>()
    val history = mutableStateListOf<HistoryEntry>()
    var engineStatus by mutableStateOf("Starting up…")
    var ready by mutableStateOf(false)
    var allowMobileData by mutableStateOf(false)
        private set
    var speedIndex by mutableStateOf(0)
        private set
    var parallel by mutableStateOf(2)
        private set
    var autoRetry by mutableStateOf(2)
        private set

    private val prefs get() = app.getSharedPreferences("ytdl", Context.MODE_PRIVATE)

    @Synchronized
    fun init(application: Application) {
        if (this::app.isInitialized) return
        app = application
        allowMobileData = prefs.getBoolean("mobile_data", false)
        speedIndex = prefs.getInt("speed", 0).coerceIn(SPEEDS.indices)
        parallel = prefs.getInt("parallel", 2).coerceIn(1, 3)
        autoRetry = prefs.getInt("retries", 2).coerceIn(0, 3)
        loadHistory()
        scope.launch {
            try {
                YoutubeDL.getInstance().init(app)
                FFmpeg.getInstance().init(app)
                ready = true
                engineStatus = "Paste a link and tap Add to queue."
                engineReady.complete(Unit)
                if (isUnmetered()) updateEngine(quiet = true)
            } catch (e: Exception) {
                engineStatus = "Setup failed: ${e.message}"
                engineReady.completeExceptionally(e)
            }
        }
    }

    fun chooseMobileData(allow: Boolean) {
        allowMobileData = allow
        prefs.edit().putBoolean("mobile_data", allow).apply()
        Subscriptions.reschedule() // the background job's network requirement follows this switch
    }

    fun chooseSpeed(i: Int) { speedIndex = i; prefs.edit().putInt("speed", i).apply() }
    fun chooseParallel(n: Int) { parallel = n; prefs.edit().putInt("parallel", n).apply() }
    fun chooseRetries(n: Int) { autoRetry = n; prefs.edit().putInt("retries", n).apply() }

    /** yt-dlp breaks when sites change; this fetches the newest version. */
    fun updateEngine(quiet: Boolean = false) {
        scope.launch {
            engineReady.await()
            if (!quiet) engineStatus = "Updating yt-dlp…"
            try {
                val r = YoutubeDL.getInstance().updateYoutubeDL(app, YoutubeDL.UpdateChannel.STABLE)
                if (!quiet) engineStatus = "yt-dlp update: ${r ?: "done"}"
            } catch (e: Exception) {
                if (!quiet) engineStatus = "Update failed: ${e.message}"
            }
        }
    }

    fun isUnmetered(): Boolean {
        val cm = app.getSystemService(ConnectivityManager::class.java)
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
    }

    private fun networkOk() = allowMobileData || isUnmetered()

    fun enqueue(url: String, options: Options, title: String? = null, subId: String? = null, videoId: String? = null) {
        items.add(Item(nextId++, url.trim(), options, title, subId, videoId))
        wake()
    }

    private fun wake() {
        try {
            ContextCompat.startForegroundService(app, Intent(app, DownloadService::class.java))
        } catch (e: Exception) {
            // Android refuses to start the notification service from the background (a scheduled check);
            // the download still runs because the check keeps the app alive while it works.
        }
        startRunner()
    }

    suspend fun awaitReady() = engineReady.await()

    /** Waits until nothing is queued or downloading, or the time runs out. */
    suspend fun awaitIdle(timeoutMillis: Long) {
        val end = System.currentTimeMillis() + timeoutMillis
        while (activeCount > 0 && System.currentTimeMillis() < end) delay(2000)
    }

    fun cancel(item: Item) {
        if (!item.status.active) return
        item.cancelRequested = true
        if (item.status == Status.Downloading) YoutubeDL.getInstance().destroyProcessById(item.processId)
        else item.status = Status.Cancelled
    }

    fun retry(item: Item) {
        if (item.status != Status.Failed && item.status != Status.Cancelled) return
        item.cancelRequested = false
        item.attempts = 0
        item.progress = 0f
        item.detail = ""
        item.status = Status.Queued
        wake()
    }

    fun clearFinished() = items.removeAll { !it.status.active }

    val activeCount get() = items.count { it.status.active }

    @Synchronized
    private fun startRunner() {
        if (runner?.isActive == true) return
        runner = scope.launch {
            engineReady.await()
            val running = java.util.concurrent.atomic.AtomicInteger(0)
            while (true) {
                val next = items.firstOrNull { it.status == Status.Queued || it.status == Status.WaitingForWifi }
                if (next == null) {
                    if (running.get() == 0 && items.none { it.status == Status.Retrying }) break
                    delay(500)
                    continue
                }
                if (next.cancelRequested) { next.status = Status.Cancelled; continue }
                if (!networkOk()) {
                    next.status = Status.WaitingForWifi
                    delay(3000)
                    continue
                }
                if (running.get() >= parallel) { delay(400); continue }
                next.status = Status.Downloading // claim it before launching so it isn't picked twice
                running.incrementAndGet()
                scope.launch {
                    try { run(next) } finally { running.decrementAndGet() }
                }
            }
        }
        // An item added just as the runner was finishing must not be stranded.
        runner?.invokeOnCompletion { if (items.any { it.status == Status.Queued }) startRunner() }
    }

    private fun buildRequest(item: Item, source: String, post: ThreadsPost?, index: Int, total: Int, dir: File): YoutubeDLRequest {
        val o = item.options
        val req = YoutubeDLRequest(source)
        if (!o.playlist) req.addOption("--no-playlist")
        req.addOption("--windows-filenames")
        if (o.useLogin) CookieStore.merged(app)?.let { req.addOption("--cookies", it.absolutePath) }
        SPEEDS[speedIndex].second.takeIf { it > 0 }?.let { req.addOption("--limit-rate", "${it / parallel}") }

        // Threads clips are plain video files, so yt-dlp can't name them from metadata; ytdl names them itself.
        var (name, folder) = if (post != null) threadsNaming(post, index, total, o.naming, o.folders)
        else (NAMING.firstOrNull { it.key == o.naming } ?: NAMING[0]).template to
            (FOLDERS.firstOrNull { it.key == o.folders } ?: FOLDERS[0]).template
        if (o.clipped) {
            val start = (o.clipStart ?: 0.0)
            val end = o.clipEnd?.toString() ?: "inf"
            req.addOption("--download-sections", "*$start-$end")
            req.addOption("--force-keyframes-at-cuts")
            name += " [clip ${start.toInt()}s-${o.clipEnd?.toInt()?.let { "${it}s" } ?: "end"}]"
        }
        if (o.audioOnly) {
            name += " (audio)"
            req.addOption("-x")
            req.addOption("--audio-format", o.format)
        } else {
            val h = if (o.quality == "best") "" else "[height<=${o.quality}]"
            req.addOption("-f", "bv*$h+ba/b$h")
            req.addOption("--merge-output-format", o.format)
            // Single-file sources (Instagram, X, ...) skip the merge step, so convert them too.
            req.addOption(if (o.format == "webm") "--recode-video" else "--remux-video", o.format)
            if (o.subLang != null && post == null) {
                // Saved as a separate .srt next to the video (embedding needs ffprobe, which isn't bundled).
                req.addOption("--write-subs")
                req.addOption("--write-auto-subs")
                req.addOption("--sub-langs", o.subLang)
                req.addOption("--convert-subs", "srt")
            }
        }
        if (o.extras) {
            req.addOption("--embed-metadata")
            if (o.format in COVER_FORMATS && post == null) {
                req.addOption("--embed-thumbnail")
                req.addOption("--convert-thumbnails", "jpg")
            }
        }
        req.addOption("-o", "${dir.absolutePath}/$folder$name.%(ext)s")
        return req
    }

    private suspend fun run(item: Item) {
        val o = item.options
        item.progress = 0f
        val dir = File(app.cacheDir, "dl/${item.id}-${System.currentTimeMillis()}").also { it.mkdirs() }
        try {
            val post = if (isThreadsUrl(item.url)) {
                ThreadsResolver.resolve(app, item.url).also { p -> p.title.take(60).takeIf { it.isNotBlank() }?.let { item.title = it } }
            } else null
            val sources = when {
                post == null -> listOf(item.url)
                o.playlist -> post.videos
                else -> post.videos.take(1)
            }
            sources.forEachIndexed { index, source ->
                if (item.cancelRequested) error("cancelled")
                val req = buildRequest(item, source, post, index, sources.size, dir)
                YoutubeDL.getInstance().execute(req, item.processId) { p, _, line ->
                    if (p >= 0f) item.progress = (index + p / 100f) / sources.size
                    if (post == null) Regex("""Destination: (.+)$""").find(line)?.let {
                        val base = File(it.groupValues[1]).nameWithoutExtension
                        item.title = base.replace(Regex("""\.f\d+$"""), "")
                            .replace(Regex(""" \[[\w-]{6,}\]| \(audio\)| \[clip [^\]]*\]"""), "")
                    }
                }
            }

            val files = dir.walkTopDown().filter { it.isFile && it.extension.lowercase() in MEDIA_EXTENSIONS }.toList()
            if (files.none { it.extension.lowercase() != "srt" }) error("No file was produced")
            var first: HistoryEntry? = null
            files.forEach { f ->
                val sub = f.parentFile?.relativeTo(dir)?.path.orEmpty()
                val entry = saveToDownloads(f, sub)
                if (f.extension.lowercase() != "srt") {
                    addHistory(entry)
                    if (first == null) first = entry
                }
            }
            item.resultUri = first?.uri
            item.progress = 1f
            item.status = Status.Done
            finishedForSubscription(item, true)
            notifyResult(item, "Finished: ${item.title}", first?.uri)
        } catch (e: Exception) {
            if (item.cancelRequested) {
                item.status = Status.Cancelled
                finishedForSubscription(item, true) // the user said no to this one; don't offer it again
            } else {
                val message = e.message?.lineSequence()?.firstOrNull { it.contains("ERROR") }
                    ?.substringAfter("ERROR:")?.trim()
                    ?: e.message?.lineSequence()?.firstOrNull { it.isNotBlank() } ?: e.toString()
                if (item.attempts < autoRetry && isTransientError(message)) {
                    item.attempts++
                    item.status = Status.Retrying
                    item.detail = "Retrying (${item.attempts}/$autoRetry): $message"
                    var waited = 0
                    while (waited < 3000 * item.attempts && !item.cancelRequested) { delay(250); waited += 250 }
                    item.status = if (item.cancelRequested) Status.Cancelled else Status.Queued
                } else {
                    item.status = Status.Failed
                    item.detail = message
                    finishedForSubscription(item, false)
                    notifyResult(item, "Failed: ${item.title}", null, message)
                }
            }
        } finally {
            dir.deleteRecursively()
        }
    }

    private fun finishedForSubscription(item: Item, ok: Boolean) {
        val sub = item.subId ?: return
        val video = item.videoId ?: return
        Subscriptions.onItemResult(sub, video, ok)
    }

    private fun notifyResult(item: Item, title: String, uri: String?, text: String? = null) {
        val nm = NotificationManagerCompat.from(app)
        if (!nm.areNotificationsEnabled()) return
        nm.createNotificationChannel(
            NotificationChannelCompat.Builder("results", NotificationManagerCompat.IMPORTANCE_DEFAULT)
                .setName("Finished downloads").build()
        )
        val intent = if (uri != null) {
            val u = Uri.parse(uri)
            Intent(Intent.ACTION_VIEW).setDataAndType(u, app.contentResolver.getType(u))
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } else Intent(app, MainActivity::class.java)
        val pending = PendingIntent.getActivity(app, item.id, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = NotificationCompat.Builder(app, "results")
            .setSmallIcon(if (uri != null) android.R.drawable.stat_sys_download_done else android.R.drawable.stat_notify_error)
            .setContentTitle(title)
            .setContentText(text ?: "Tap to open")
            .setContentIntent(pending)
            .setAutoCancel(true)
            .build()
        try { nm.notify(1000 + item.id, n) } catch (e: SecurityException) { /* notifications denied */ }
    }

    /** Copy a finished file into the public Downloads/ytdl folder (no storage permission needed). */
    private fun saveToDownloads(file: File, subFolder: String = ""): HistoryEntry {
        val resolver = app.contentResolver
        val mime = if (file.extension.lowercase() == "srt") "application/x-subrip"
        else MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension) ?: "application/octet-stream"
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, file.name)
            put(MediaStore.Downloads.MIME_TYPE, mime)
            put(MediaStore.Downloads.RELATIVE_PATH,
                "${Environment.DIRECTORY_DOWNLOADS}/ytdl" + if (subFolder.isNotEmpty()) "/$subFolder" else "")
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: error("Could not create file in Downloads")
        resolver.openOutputStream(uri)!!.use { out -> file.inputStream().use { it.copyTo(out) } }
        val whenText = SimpleDateFormat("MMM d, HH:mm", Locale.getDefault()).format(Date())
        return HistoryEntry(file.name, uri.toString(), whenText)
    }

    private fun addHistory(entry: HistoryEntry) {
        history.add(0, entry)
        while (history.size > 100) history.removeAt(history.size - 1)
        saveHistory()
    }

    fun clearHistory() {
        history.clear()
        saveHistory()
    }

    private fun saveHistory() {
        val arr = JSONArray()
        history.forEach { arr.put(JSONObject().put("n", it.name).put("u", it.uri).put("w", it.whenText)) }
        prefs.edit().putString("history", arr.toString()).apply()
    }

    private fun loadHistory() {
        val arr = try { JSONArray(prefs.getString("history", "[]")) } catch (e: Exception) { JSONArray() }
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            history.add(HistoryEntry(o.getString("n"), o.getString("u"), o.getString("w")))
        }
    }

    /** One-line summary for the notification. */
    fun summary(): String {
        val running = items.firstOrNull { it.status == Status.Downloading }
        val waiting = items.firstOrNull { it.status == Status.WaitingForWifi }
        if (running == null && waiting == null) items.firstOrNull { it.status == Status.Retrying }?.let { return "Retrying: ${it.title.take(40)}" }
        val left = activeCount
        return when {
            running != null -> "${running.title.take(40)}  ${(running.progress * 100).toInt()}%" + if (left > 1) "  (+${left - 1} more)" else ""
            waiting != null -> "Waiting for Wi-Fi ($left queued)"
            else -> "Starting…"
        }
    }

    fun overallProgress(): Float = items.firstOrNull { it.status == Status.Downloading }?.progress ?: 0f
}
