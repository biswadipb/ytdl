package dev.ytdl.minimal

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel

/** What's on screen and what you chose last time. */
class MinimalViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = app.getSharedPreferences("ytdl_minimal", Application.MODE_PRIVATE)

    var link by mutableStateOf("")
    var message by mutableStateOf("")
    var audio by mutableStateOf(prefs.getString("mode", "video") == "audio")
        private set
    private var videoIndex by mutableStateOf(prefs.getInt("video_q", 0).coerceIn(VIDEO_CHOICES.indices))
    private var audioIndex by mutableStateOf(prefs.getInt("audio_q", 0).coerceIn(AUDIO_CHOICES.indices))

    var theme by mutableStateOf(prefs.getString("theme", "auto")?.takeIf { it in THEMES } ?: "auto")
        private set

    fun cycleTheme() { theme = nextTheme(theme); prefs.edit().putString("theme", theme).apply() }

    val choices get() = if (audio) AUDIO_CHOICES else VIDEO_CHOICES
    val choiceIndex get() = if (audio) audioIndex else videoIndex

    fun chooseMode(isAudio: Boolean) { audio = isAudio; save() }
    fun chooseQuality(i: Int) { if (audio) audioIndex = i else videoIndex = i; save() }

    private fun save() = prefs.edit().putString("mode", if (audio) "audio" else "video")
        .putInt("video_q", videoIndex).putInt("audio_q", audioIndex).apply()

    fun download() {
        val url = firstLink(link) ?: link.trim().takeIf { it.startsWith("http") }
        when {
            url == null -> message = "Paste a video link first."
            isChannelOrPlaylist(url) -> message = "That looks like a channel or playlist. The full ytdl app handles those."
            else -> {
                message = ""
                Downloads.submit(url, audio, choices[choiceIndex].second)
                link = ""
            }
        }
    }
}
