package dev.ytdl.app

import android.app.Application
import android.content.ContentValues
import android.os.Environment
import android.provider.MediaStore
import android.webkit.MimeTypeMap
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

val QUALITIES = listOf("best", "1080", "720", "480", "360")
val VIDEO_FORMATS = listOf("mp4", "mkv", "webm")
val AUDIO_FORMATS = listOf("mp3", "m4a", "opus", "wav", "flac")

class DownloadViewModel(app: Application) : AndroidViewModel(app) {
    var url by mutableStateOf("")
    var quality by mutableStateOf("best")
    var format by mutableStateOf("mp4")
    var playlist by mutableStateOf(false)
    val audioOnly get() = format in AUDIO_FORMATS
    var progress by mutableStateOf(0f)
    var status by mutableStateOf("Starting up…")
    var busy by mutableStateOf(false)
    var ready by mutableStateOf(false)

    private var job: Job? = null

    init {
        viewModelScope.launch(Dispatchers.IO) {
            try {
                YoutubeDL.getInstance().init(app)
                FFmpeg.getInstance().init(app)
                ready = true
                status = "Paste a link and tap Download."
            } catch (e: Exception) {
                status = "Setup failed: ${e.message}"
            }
        }
    }

    fun start() {
        val link = url.trim()
        if (!ready || busy || link.isEmpty()) return
        busy = true
        progress = 0f
        status = "Downloading…"
        job = viewModelScope.launch(Dispatchers.IO) {
            val dir = File(getApplication<Application>().cacheDir, "dl/${System.currentTimeMillis()}")
            dir.mkdirs()
            try {
                val req = YoutubeDLRequest(link)
                if (!playlist) req.addOption("--no-playlist")
                req.addOption("--windows-filenames")
                if (audioOnly) {
                    // Suffix keeps audio from clobbering a same-named video.
                    req.addOption("-o", "${dir.absolutePath}/%(title).150B [%(id)s] (audio).%(ext)s")
                    req.addOption("-x")
                    req.addOption("--audio-format", format)
                } else {
                    req.addOption("-o", "${dir.absolutePath}/%(title).150B [%(id)s].%(ext)s")
                    val h = if (quality == "best") "" else "[height<=$quality]"
                    req.addOption("-f", "bv*$h+ba/b$h")
                    req.addOption("--merge-output-format", format)
                    // Single-file sources (Instagram, X, ...) skip the merge step, so convert them too.
                    req.addOption(if (format == "webm") "--recode-video" else "--remux-video", format)
                }
                YoutubeDL.getInstance().execute(req, "ytdl") { p, _, _ -> progress = p.coerceAtLeast(0f) / 100f }

                val files = dir.listFiles { f -> f.extension !in setOf("part", "ytdl", "temp") }.orEmpty()
                if (files.isEmpty()) error("No file was produced")
                files.forEach { saveToDownloads(it) }
                progress = 1f
                status = "Saved to Downloads/ytdl:\n" + files.joinToString("\n") { it.name }
            } catch (e: Exception) {
                status = "Failed: ${e.message?.lineSequence()?.firstOrNull { it.isNotBlank() } ?: e}"
            } finally {
                dir.deleteRecursively()
                busy = false
            }
        }
    }

    fun cancel() {
        YoutubeDL.getInstance().destroyProcessById("ytdl")
        job?.cancel()
        busy = false
        status = "Cancelled."
    }

    /** Copy a finished file into the public Downloads/ytdl folder (no storage permission needed). */
    private suspend fun saveToDownloads(file: File) = withContext(Dispatchers.IO) {
        val resolver = getApplication<Application>().contentResolver
        val mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension) ?: "application/octet-stream"
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, file.name)
            put(MediaStore.Downloads.MIME_TYPE, mime)
            put(MediaStore.Downloads.RELATIVE_PATH, "${Environment.DIRECTORY_DOWNLOADS}/ytdl")
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: error("Could not create file in Downloads")
        resolver.openOutputStream(uri)!!.use { out -> file.inputStream().use { it.copyTo(out) } }
    }

    /** yt-dlp breaks when YouTube changes; this fetches the newest version. */
    fun updateEngine() {
        viewModelScope.launch(Dispatchers.IO) {
            status = "Updating yt-dlp…"
            status = try {
                val r = YoutubeDL.getInstance().updateYoutubeDL(getApplication(), YoutubeDL.UpdateChannel.STABLE)
                "yt-dlp update: ${r ?: "done"}"
            } catch (e: Exception) {
                "Update failed: ${e.message}"
            }
        }
    }
}
