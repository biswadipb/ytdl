package dev.ytdl.app

/** "v2.1.0" to [2, 1, 0]; text without digits (like "dev") to null. */
fun parseVersion(text: String?): List<Int>? {
    val nums = Regex("""\d+""").findAll(text ?: "").map { it.value.toInt() }.take(3).toList()
    return if (nums.isEmpty()) null else nums + List(3 - nums.size) { 0 }
}

fun isNewer(current: String?, latest: String?): Boolean {
    val c = parseVersion(current) ?: return false
    val l = parseVersion(latest) ?: return false
    for (i in 0 until 3) if (l[i] != c[i]) return l[i] > c[i]
    return false
}

/** "90", "1:30" or "1:02:03" to seconds; blank is null; anything else throws NumberFormatException. */
fun parseClock(text: String): Double? {
    val t = text.trim()
    if (t.isEmpty()) return null
    val parts = t.split(":")
    if (parts.size > 3) throw NumberFormatException(t)
    return parts.fold(0.0) { acc, part -> acc * 60 + part.toDouble() }
}

/** Errors that retrying can't fix (private posts, bad links, missing formats). */
private val PERMANENT_ERRORS = listOf(
    "unsupported url", "private", "sign in", "log in", "login", "not available", "unavailable", "removed",
    "copyright", "age-restricted", "members-only", "no video could be found", "requested format",
    "does not exist", "not a valid url", "ffmpeg",
)

fun isTransientError(message: String): Boolean {
    val m = message.lowercase()
    return PERMANENT_ERRORS.none { it in m }
}
