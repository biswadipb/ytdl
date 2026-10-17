package dev.ytdl.minimal

import android.app.Application
import android.content.ContentValues
import android.content.Context
import android.content.Intent
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
import kotlinx.coroutines.launch
import java.io.File

enum class Status { Queued, Running, Done, Failed, Cancelled }

class Download(val id: Int, val url: String, val audio: Boolean, val choice: String) {
    var title by mutableStateOf(url)
    var status by mutableStateOf(Status.Queued)
    var progress by mutableFloatStateOf(0f)
    var error by mutableStateOf("")
    var uri: String? = null
    @Volatile var cancelRequested = false
    val processId get() = "min-$id"
}

/** This session's downloads, newest first. Runs one at a time. */
object Downloads {
    private lateinit var app: Application
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var runner: Job? = null
    private var nextId = 1
    private val engineReady = CompletableDeferred<Unit>()

    val list = mutableStateListOf<Download>()
    var ready by mutableStateOf(false)
        private set

    @Synchronized
    fun init(application: Application) {
        if (this::app.isInitialized) return
        app = application
        SaveTarget.refresh(application)
        scope.launch {
            try {
                YoutubeDL.getInstance().init(app)
                FFmpeg.getInstance().init(app)
                ready = true
                engineReady.complete(Unit)
                if (isUnmetered()) {   // keep the download engine current without bothering anyone
                    try { YoutubeDL.getInstance().updateYoutubeDL(app, YoutubeDL.UpdateChannel.STABLE) } catch (e: Exception) { }
                }
            } catch (e: Exception) {
                engineReady.completeExceptionally(e)
            }
        }
    }

    private fun isUnmetered(): Boolean {
        val cm = app.getSystemService(ConnectivityManager::class.java)
        return cm.getNetworkCapabilities(cm.activeNetwork)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED) == true
    }

    val activeCount get() = list.count { it.status == Status.Queued || it.status == Status.Running }

    fun submit(url: String, audio: Boolean, choice: String) {
        list.add(0, Download(nextId++, url.trim(), audio, choice))
        wake()
    }

    fun cancel(d: Download) {
        d.cancelRequested = true
        if (d.status == Status.Running) YoutubeDL.getInstance().destroyProcessById(d.processId)
        else if (d.status == Status.Queued) d.status = Status.Cancelled
    }

    fun retry(d: Download) {
        if (d.status != Status.Failed && d.status != Status.Cancelled) return
        d.cancelRequested = false
        d.progress = 0f
        d.error = ""
        d.status = Status.Queued
        wake()
    }

    fun summary(): String {
        val running = list.firstOrNull { it.status == Status.Running }
        return running?.let { "${it.title.take(40)}  ${(it.progress * 100).toInt()}%" } ?: "Starting…"
    }

    fun progressNow() = list.firstOrNull { it.status == Status.Running }?.progress ?: 0f

    /** Fills the list with sample items (used only for the screenshots on the website). */
    fun demo() {
        if (list.isNotEmpty()) return
        list.add(Download(3, "", false, "best").apply { title = "Me at the zoo"; status = Status.Running; progress = 0.62f })
        list.add(Download(2, "", false, "best").apply { title = "Autumn forest in 4K"; status = Status.Done })
        list.add(Download(1, "", true, "mp3").apply { title = "Podcast episode 41"; status = Status.Done })
    }

    private fun wake() {
        try {
            ContextCompat.startForegroundService(app, Intent(app, DownloadService::class.java))
        } catch (e: Exception) { /* not allowed from the background; the download still runs while the app is alive */ }
        startRunner()
    }

    @Synchronized
    private fun startRunner() {
        if (runner?.isActive == true) return
        runner = scope.launch {
            engineReady.await()
            while (true) {
                val next = list.lastOrNull { it.status == Status.Queued } ?: break   // oldest first
                if (next.cancelRequested) { next.status = Status.Cancelled; continue }
                run(next)
            }
        }
        runner?.invokeOnCompletion { if (list.any { it.status == Status.Queued }) startRunner() }
    }

    private suspend fun run(d: Download) {
        d.status = Status.Running
        val dir = File(app.cacheDir, "dl/${d.id}-${System.currentTimeMillis()}").also { it.mkdirs() }
        try {
            for (attempt in 0..1) {      // one automatic retry for hiccups like a dropped connection
                try {
                    val post = if (isThreadsUrl(d.url)) ThreadsResolver.resolve(app, d.url) else null
                    post?.title?.take(60)?.takeIf { it.isNotBlank() }?.let { d.title = it }
                    val label = post?.let { "${safeFileText(it.user)} - ${safeFileText(it.title).take(80).ifEmpty { "Threads post ${it.code}" }} [${it.code}]" }
                    val req = YoutubeDLRequest(post?.videos?.firstOrNull() ?: d.url)
                    downloadOptions(d.audio, d.choice, dir.absolutePath, fileName(d.audio, label)).forEach { (flag, value) ->
                        if (value == null) req.addOption(flag) else req.addOption(flag, value)
                    }
                    YoutubeDL.getInstance().execute(req, d.processId) { p, _, line ->
                        if (p >= 0f) d.progress = maxOf(d.progress, minOf(p / 100f, 0.99f))   // video then audio each count 0-100: never go back
                        if (post == null) Regex("""Destination: (.+)$""").find(line)?.let {
                            d.title = File(it.groupValues[1]).nameWithoutExtension.replace(Regex("""\.f\d+$"""), "")
                                .replace(Regex(""" \[[\w-]{6,}\]| \(audio\)"""), "")
                        }
                    }
                    val files = dir.walkTopDown().filter { it.isFile && it.extension.lowercase() in setOf("mp4", "mp3", "m4a") }.toList()
                    if (files.isEmpty()) error("No file was produced")
                    d.uri = saveToDownloads(files.first())
                    d.progress = 1f
                    d.status = Status.Done
                    return
                } catch (e: Exception) {
                    if (d.cancelRequested) { d.status = Status.Cancelled; return }
                    val message = friendlyError(e.message)
                    if (attempt == 0 && isTransient(message)) continue
                    d.error = message
                    d.status = Status.Failed
                    return
                }
            }
        } finally {
            dir.deleteRecursively()
        }
    }

    /** Copy a finished file to the folder you chose (default: the public Downloads/ytdl folder). */
    private fun saveToDownloads(file: File): String = SaveTarget.save(app, file)
}
