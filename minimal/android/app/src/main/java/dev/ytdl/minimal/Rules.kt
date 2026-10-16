package dev.ytdl.minimal

val LINK_PATTERN = Regex(
    "https?://([\\w-]+\\.)*(youtube\\.com|youtu\\.be|instagram\\.com|x\\.com|twitter\\.com|" +
        "facebook\\.com|fb\\.watch|threads\\.(net|com)|dailymotion\\.com|dai\\.ly|tiktok\\.com|reddit\\.com|redd\\.it|" +
        "vimeo\\.com|twitch\\.tv|soundcloud\\.com)/\\S+", RegexOption.IGNORE_CASE
)

val VIDEO_CHOICES = listOf("Best" to "best", "1080p" to "1080", "720p" to "720", "480p" to "480")
val AUDIO_CHOICES = listOf("MP3" to "mp3", "M4A" to "m4a")

/** The first supported link in a block of text (copied or shared text usually has words around it). */
fun firstLink(text: String?): String? =
    text?.let { LINK_PATTERN.find(it)?.value?.trimEnd('.', ',', ')', ']') }

/** Channels, profiles and playlists could mean hundreds of downloads, which minimal doesn't do. */
private val NOT_SINGLE = Regex(
    """(youtube\.com/(@[^/?#]+|channel/|c/|user/)[^?#]*$|youtube\.com/playlist|/sets/|instagram\.com/[^/?#]+/?$)""",
    RegexOption.IGNORE_CASE
)

fun isChannelOrPlaylist(url: String) = NOT_SINGLE.containsMatchIn(url.trim())

/** yt-dlp options for one download: (flag, value or null). Pure, so it can be tested without a phone. */
fun downloadOptions(audio: Boolean, choice: String, outDir: String, name: String): List<Pair<String, String?>> {
    val o = mutableListOf<Pair<String, String?>>("--no-playlist" to null, "--windows-filenames" to null, "--embed-metadata" to null)
    if (audio) {
        o += "-x" to null
        o += "--audio-format" to choice
        if (choice == "mp3") { o += "--embed-thumbnail" to null; o += "--convert-thumbnails" to "jpg" }
    } else {
        val h = if (choice == "best") "" else "[height<=$choice]"
        o += "-f" to "bv*$h+ba/b$h"
        o += "--merge-output-format" to "mp4"
        o += "--remux-video" to "mp4"
    }
    o += "-o" to "$outDir/$name.%(ext)s"
    return o
}

/** The file name template (no extension). Audio gets a suffix so it never replaces a video of the same name. */
fun fileName(audio: Boolean, threadsLabel: String? = null): String {
    val base = threadsLabel ?: "%(title).150B [%(id)s]"
    return if (audio) "$base (audio)" else base
}

/** Errors that retrying can't fix. */
private val PERMANENT = listOf(
    "unsupported url", "private", "sign in", "log in", "login", "not available", "unavailable", "removed",
    "copyright", "age-restricted", "members-only", "no video could be found", "requested format",
    "does not exist", "not a valid url", "no video found",
)

fun isTransient(message: String): Boolean = PERMANENT.none { it in message.lowercase() }

/** One line a person can read from a long yt-dlp error. */
fun friendlyError(raw: String?): String {
    val line = raw?.lineSequence()?.firstOrNull { it.contains("ERROR") }?.substringAfter("ERROR:")?.trim()
        ?: raw?.lineSequence()?.firstOrNull { it.isNotBlank() } ?: "Download failed"
    return line.replace(Regex("""^\[[^\]]+\]\s*\S*:\s*"""), "").take(90)
}
