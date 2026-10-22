package dev.ytdl.minimal

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

private val REDDIT_POST = Regex("""^https?://(?:[\w-]+\.)?reddit\.com/(?:(?:r|user|u)/[\w-]+/)?comments/(\w+)""", RegexOption.IGNORE_CASE)
private val REDDIT_SHORT = Regex("""^https?://redd\.it/(\w+)""", RegexOption.IGNORE_CASE)
private val REDDIT_SHARE = Regex("""^https?://(?:[\w-]+\.)?reddit\.com/r/[\w-]+/s/\w+""", RegexOption.IGNORE_CASE)
private val IMAGE_EXT = Regex("""\.(jpe?g|png|gif|webp)(?:\?|$)""", RegexOption.IGNORE_CASE)
private val IMAGE_HOSTS = setOf("i.redd.it", "i.imgur.com", "preview.redd.it")
private val MIME_EXT = mapOf("image/jpg" to "jpg", "image/jpeg" to "jpg", "image/png" to "png", "image/gif" to "gif", "image/webp" to "webp")

fun isRedditUrl(url: String) = url.trim().let { REDDIT_POST.containsMatchIn(it) || REDDIT_SHORT.containsMatchIn(it) || REDDIT_SHARE.containsMatchIn(it) }

fun redditPostId(url: String): String? = url.trim().let { (REDDIT_POST.find(it) ?: REDDIT_SHORT.find(it))?.groupValues?.get(1) }

/** One picture: addresses to try in order (the original first), and its file extension. */
class RedditPicture(val choices: List<String>, val ext: String)

private fun unescape(s: String) = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"")

/** The pictures in a Reddit post's data. Empty for video posts, text posts and links to other sites. Pure, so it is tested. */
fun redditPictures(post: JSONObject): List<RedditPicture> {
    val parents = post.optJSONArray("crosspost_parent_list")
    if (parents != null && parents.length() > 0) return redditPictures(parents.getJSONObject(0))
    if (post.optBoolean("is_video") || post.optString("post_hint").contains("video") ||
        post.optJSONObject("media")?.has("reddit_video") == true) return emptyList()
    if (post.optBoolean("is_gallery")) {
        val meta = post.optJSONObject("media_metadata") ?: return emptyList()
        val items = post.optJSONObject("gallery_data")?.optJSONArray("items") ?: JSONArray()
        val out = mutableListOf<RedditPicture>()
        for (i in 0 until items.length()) {
            val id = items.getJSONObject(i).optString("media_id")
            val m = meta.optJSONObject(id) ?: continue
            if (m.has("status") && m.optString("status") != "valid") continue
            val s = m.optJSONObject("s")
            val ext = MIME_EXT[m.optString("m")] ?: ""
            when {
                m.optString("e") == "AnimatedImage" && s?.optString("gif").orEmpty().isNotEmpty() ->
                    out.add(RedditPicture(listOf(unescape(s!!.getString("gif"))), "gif"))
                m.optString("e") == "Image" && ext.isNotEmpty() ->
                    out.add(RedditPicture(listOfNotNull("https://i.redd.it/$id.$ext", s?.optString("u")?.takeIf { it.isNotEmpty() }?.let(::unescape)), ext))
            }
        }
        return out
    }
    val link = unescape(post.optString("url_overridden_by_dest").ifEmpty { post.optString("url") })
    val host = Regex("""^https?://([^/]+)/""").find(link)?.groupValues?.get(1)?.lowercase()
    val ext = IMAGE_EXT.find(link)?.groupValues?.get(1)
    return if (ext != null && host in IMAGE_HOSTS) listOf(RedditPicture(listOf(link), ext.lowercase().replace("jpeg", "jpg"))) else emptyList()
}

fun redditFileName(title: String, id: String, index: Int, count: Int, ext: String): String {
    val clean = title.replace(Regex("""[\\/:*?"<>|\u0000-\u001f]"""), "").trim(' ', '.').take(100).trim(' ', '.').ifEmpty { "reddit" }
    val base = "$clean [$id]"
    return if (count == 1) "$base.$ext" else "$base (${index + 1} of $count).$ext"
}

class RedditPost(val id: String, val title: String, val pictures: List<RedditPicture>)

object RedditImages {
    private const val UA = "Mozilla/5.0 (compatible; ytdl; +https://github.com/biswadipb/ytdl)"

    private fun open(url: String): HttpURLConnection = (URL(url).openConnection() as HttpURLConnection).apply {
        setRequestProperty("User-Agent", UA); connectTimeout = 20_000; readTimeout = 30_000; instanceFollowRedirects = true
    }

    /** The picture post behind a link, or null if it is a video, can't be read, or has no pictures (yt-dlp then gets its turn). */
    suspend fun resolve(url: String): RedditPost? = withContext(Dispatchers.IO) {
        try {
            var link = url.trim()
            if (REDDIT_SHARE.containsMatchIn(link)) {       // share links redirect to the real post
                val c = open(link); c.inputStream.close(); link = c.url.toString(); c.disconnect()
            }
            val id = redditPostId(link) ?: return@withContext null
            for (host in listOf("www.reddit.com", "old.reddit.com")) {
                try {
                    val c = open("https://$host/comments/$id.json?raw_json=1")
                    val body = c.inputStream.bufferedReader().use { it.readText() }
                    c.disconnect()
                    val data = JSONArray(body).getJSONObject(0).getJSONObject("data").getJSONArray("children").getJSONObject(0).getJSONObject("data")
                    val pictures = redditPictures(data)
                    return@withContext if (pictures.isEmpty()) null else RedditPost(id, data.optString("title"), pictures)
                } catch (e: Exception) { /* blocked or unreadable here: try the next address */ }
            }
            null
        } catch (e: Exception) { null }
    }

    /** Saves every picture into [dir]. [progress] gets 0..1 and should throw to cancel. */
    suspend fun download(post: RedditPost, dir: File, progress: (Float) -> Unit): List<File> = withContext(Dispatchers.IO) {
        val files = mutableListOf<File>()
        val count = post.pictures.size
        post.pictures.forEachIndexed { i, pic ->
            val dest = File(dir, redditFileName(post.title, post.id, i, count, pic.ext))
            var last: Exception? = null
            val ok = pic.choices.any { address ->
                try {
                    val c = open(address)
                    val total = c.contentLengthLong
                    c.inputStream.use { input ->
                        dest.outputStream().use { out ->
                            val buf = ByteArray(65536)
                            var done = 0L
                            while (true) {
                                val n = input.read(buf)
                                if (n < 0) break
                                out.write(buf, 0, n)
                                done += n
                                progress((i + if (total > 0) done.toFloat() / total else 0f) / count)
                            }
                        }
                    }
                    c.disconnect()
                    true
                } catch (e: java.util.concurrent.CancellationException) { throw e
                } catch (e: Exception) { last = e; dest.delete(); false }
            }
            if (!ok) error("Couldn't download the picture (${last?.message ?: "network error"}).")
            files.add(dest)
            progress((i + 1f) / count)
        }
        files
    }
}
