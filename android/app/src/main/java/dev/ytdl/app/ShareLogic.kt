package dev.ytdl.app

import java.net.URI

/** The first supported link in a block of shared text (apps usually add a title around it). */
fun firstLink(text: String?): String? =
    text?.let { LINK_PATTERN.find(it)?.value?.trimEnd('.', ',', ')', ']') }

private fun parts(url: String): Triple<String, String, String>? = try {
    val u = URI(url.trim())
    val host = (u.host ?: return null).lowercase().removePrefix("www.").removePrefix("m.")
    Triple(host, u.path ?: "", u.query ?: "")
} catch (e: Exception) { null }

/**
 * True only for links that clearly point at ONE video, post or track. Channels, profiles and playlists
 * could mean hundreds of downloads, so those are never started automatically.
 */
fun isSingleItemLink(url: String): Boolean {
    if (isThreadsUrl(url)) return true
    val (host, path, query) = parts(url) ?: return false
    val segments = path.split("/").filter { it.isNotEmpty() }
    return when {
        host == "youtu.be" -> segments.size == 1
        host.endsWith("youtube.com") ->
            (path == "/watch" && Regex("""(^|&)v=""").containsMatchIn(query)) ||
                segments.firstOrNull() in setOf("shorts", "live", "embed") && segments.size >= 2
        host.endsWith("instagram.com") -> segments.firstOrNull() in setOf("p", "reel", "reels", "tv", "stories") && segments.size >= 2
        host == "x.com" || host.endsWith("twitter.com") -> segments.getOrNull(1) == "status" && segments.size >= 3
        host == "fb.watch" -> segments.isNotEmpty()
        host.endsWith("facebook.com") ->
            segments.firstOrNull() in setOf("watch", "reel", "share") || "videos" in segments
        host == "dai.ly" -> segments.isNotEmpty()
        host.endsWith("dailymotion.com") -> segments.firstOrNull() == "video" && segments.size >= 2
        host.endsWith("tiktok.com") -> host.startsWith("vm.") || host.startsWith("vt.") || "video" in segments || segments.firstOrNull() == "t"
        host == "redd.it" -> segments.isNotEmpty()
        host.endsWith("reddit.com") -> "comments" in segments
        host.endsWith("vimeo.com") -> segments.lastOrNull()?.all { it.isDigit() } == true
        host == "clips.twitch.tv" -> segments.isNotEmpty()
        host.endsWith("twitch.tv") -> segments.firstOrNull() in setOf("videos") && segments.size >= 2 || "clip" in segments
        host == "on.soundcloud.com" -> segments.isNotEmpty()
        host.endsWith("soundcloud.com") -> segments.size == 2 && segments[1] !in setOf("sets", "tracks", "albums", "likes")
        else -> false
    }
}

/** What to keep from a download for the storage rules. */
class StoredFile(val ref: String, val size: Long, val time: Long)

/** Which recorded files to delete: ones older than [keepDays], then the oldest until the total fits [maxGb]. */
fun planCleanup(files: List<StoredFile>, keepDays: Int, maxGb: Int, nowMillis: Long, gb: Long = 1024L * 1024 * 1024): List<StoredFile> {
    val day = 86_400_000L
    val doomed = mutableListOf<StoredFile>()
    val kept = files.filter { f ->
        val old = keepDays > 0 && nowMillis - f.time > keepDays * day
        if (old) doomed.add(f)
        !old
    }.sortedBy { it.time }.toMutableList()
    if (maxGb > 0) {
        var total = kept.sumOf { it.size }
        while (kept.isNotEmpty() && total > maxGb * gb) {
            val victim = kept.removeAt(0)
            doomed.add(victim)
            total -= victim.size
        }
    }
    return doomed
}

fun humanSize(bytes: Long): String {
    var n = bytes.toDouble()
    for (unit in listOf("B", "KB", "MB", "GB")) {
        if (n < 1024 || unit == "GB") return if (unit == "B") "%d B".format(bytes) else "%.1f %s".format(n, unit)
        n /= 1024
    }
    return "$bytes B"
}
