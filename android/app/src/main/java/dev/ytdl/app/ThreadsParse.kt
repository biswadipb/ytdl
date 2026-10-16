package dev.ytdl.app

import org.json.JSONObject

val THREADS_POST = Regex("""^https?://(?:www\.)?threads\.(?:net|com)/@([\w.]+)/post/([\w-]+)""", RegexOption.IGNORE_CASE)
private val THREADS_SHORT = Regex("""^https?://(?:www\.)?threads\.(?:net|com)/t/([\w-]+)""", RegexOption.IGNORE_CASE)

fun isThreadsUrl(url: String) = url.trim().let { THREADS_POST.containsMatchIn(it) || THREADS_SHORT.containsMatchIn(it) }

/** What the page script reports back: the linked post's own videos, its caption and a picture. */
class ThreadsScrape(val videos: List<String>, val title: String, val image: String?)

class ThreadsPost(val user: String, val code: String, val title: String, val thumbnail: String?, val videos: List<String>)

/**
 * Runs inside the loaded Threads page. Videos in the first post container are the linked post's;
 * replies and suggested posts further down have their own containers and are ignored.
 */
const val THREADS_SCRIPT = """(function () {
  var post = document.querySelector('[data-pressable-container="true"]');
  var vids = post ? Array.prototype.slice.call(post.querySelectorAll('video')) : [];
  var srcs = [];
  vids.forEach(function (v) {
    var s = v.currentSrc || v.src;
    if (s && s.indexOf('http') === 0 && srcs.indexOf(s) < 0) srcs.push(s);
  });
  var m = document.querySelector('meta[property="og:image"]');
  return JSON.stringify({videos: srcs, title: document.title || '', image: m ? m.content : ''});
})()"""

/** The script's answer arrives as a JSON string wrapped in another layer of JSON quoting. */
fun parseThreadsScrape(raw: String?): ThreadsScrape? {
    if (raw.isNullOrBlank() || raw == "null") return null
    val inner = try { org.json.JSONTokener(raw).nextValue() as? String ?: raw } catch (e: Exception) { raw }
    val obj = try { JSONObject(inner) } catch (e: Exception) { return null }
    val arr = obj.optJSONArray("videos")
    val videos = (0 until (arr?.length() ?: 0)).map { arr!!.getString(it) }
    return ThreadsScrape(videos, obj.optString("title"), obj.optString("image").ifEmpty { null })
}

/** (user, code) from a post link, or null. */
fun threadsParts(url: String): Pair<String, String>? =
    THREADS_POST.find(url.trim())?.let { it.groupValues[1] to it.groupValues[2] }

/** Characters that can't appear in a file name, or that yt-dlp's output template treats specially. */
fun safeFileText(text: String): String =
    text.replace(Regex("""[%/\\:*?"<>|\r\n]"""), " ").replace(Regex("\\s+"), " ").trim()

/** The file name (no extension) and sub-folder a Threads clip is saved under, following the user's naming rules. */
fun threadsNaming(post: ThreadsPost, index: Int, total: Int, naming: String, folders: String): Pair<String, String> {
    val caption = safeFileText(post.title).take(80).ifEmpty { "Threads post ${post.code}" }
    val part = if (total > 1) " (${index + 1}-of-$total)" else ""
    val id = if (total > 1) "${post.code}-${index + 1}" else post.code
    val base = when (naming) {
        "title" -> "$caption$part"
        "channel-title" -> "${post.user} - $caption$part"
        else -> "$caption$part [$id]"
    }
    val folder = when (folders) {
        "channel" -> "${post.user}/"
        "site" -> "Threads/"
        "site-channel" -> "Threads/${post.user}/"
        else -> ""
    }
    return base to folder
}
