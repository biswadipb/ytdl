package dev.ytdl.app

/** A video in a channel or playlist listing. */
class Entry(val id: String, val url: String, val title: String, val upcoming: Boolean)

const val PEEK = 15            // how many of the newest videos each check looks at
const val SEEN_LIMIT = 500     // how many video ids a subscription remembers
const val MAX_FAILS = 3        // give up on a video after this many failed checks

private val CHANNEL_ROOT =
    Regex("""^(https?://(?:www\.|m\.)?youtube\.com/(?:@[^/?#]+|channel/[^/?#]+|c/[^/?#]+|user/[^/?#]+))/?(?:\?.*)?$""")

/** A YouTube channel link means its Videos tab; anything else is used as given. */
fun listingUrl(url: String): String {
    val u = url.trim()
    return CHANNEL_ROOT.find(u)?.let { it.groupValues[1] + "/videos" } ?: u
}

/** Entries not seen before, oldest first. Scheduled livestreams wait for a later check. */
fun newEntries(seen: Set<String>, entries: List<Entry>): List<Entry> =
    entries.asReversed().filter { it.id !in seen && !it.upcoming }

fun mergeSeen(seen: List<String>, added: Collection<String>): List<String> =
    (added.toList() + seen.filter { it !in added }).take(SEEN_LIMIT)

fun isDue(lastCheckedMillis: Long, nowMillis: Long, intervalHours: Int): Boolean =
    nowMillis - lastCheckedMillis >= intervalHours * 3_600_000L - 60_000L

/** Night is 11 pm to 7 am. */
fun isNight(hourOfDay: Int): Boolean = hourOfDay >= 23 || hourOfDay < 7

/** The next check time rule for the background job: every subscription is checked hourly, if it is due. */
const val CHECK_PERIOD_HOURS = 1L

private val NO_PROFILES = mapOf(
    "x.com" to "X", "twitter.com" to "X", "threads.com" to "Threads", "threads.net" to "Threads", "facebook.com" to "Facebook",
)

/** Why a link can't be followed, when we already know. Null means "worth trying". */
fun unlistableReason(url: String): String? {
    val host = Regex("""^https?://([^/]+)""").find(url.trim())?.groupValues?.get(1)?.lowercase()
        ?.removePrefix("www.")?.removePrefix("m.")?.removePrefix("mobile.") ?: return null
    val name = NO_PROFILES[host] ?: return null
    return "$name doesn't let ytdl list a profile's posts, so profiles can't be followed. You can still download individual $name posts."
}

/** A plain-language message for a failed channel listing. */
fun explainListingError(url: String, error: String): String = when {
    "instagram.com" in url.lowercase() ->
        "Instagram wouldn't list this profile. It usually needs you to be signed in (see Login for private posts), " +
            "and Instagram often blocks profile listing even then. Individual posts and reels still download."
    "Unsupported URL" in error ->
        "ytdl can't follow that kind of link. Follow a YouTube channel or playlist, or another playlist-style link."
    else -> error.lineSequence().firstOrNull { it.isNotBlank() }?.removePrefix("ERROR:")?.trim()?.take(200) ?: "Couldn't read that link."
}
