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
