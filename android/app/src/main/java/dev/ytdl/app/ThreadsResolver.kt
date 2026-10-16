package dev.ytdl.app

import android.annotation.SuppressLint
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.webkit.WebView
import android.webkit.WebViewClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Threads only reveals a post's video files after its JavaScript has run, and yt-dlp can't read it.
 * So the post is loaded in a hidden WebView (the phone's own browser engine), the video links are
 * read out of the finished page, and they're downloaded like any other file.
 */
object ThreadsResolver {
    private const val UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    private const val TIMEOUT_MS = 30_000L

    @SuppressLint("SetJavaScriptEnabled")
    suspend fun resolve(context: Context, url: String): ThreadsPost = withContext(Dispatchers.Main) {
        suspendCancellableCoroutine { cont ->
            val web = WebView(context.applicationContext)
            val handler = Handler(Looper.getMainLooper())
            val deadline = SystemClock.uptimeMillis() + TIMEOUT_MS
            var finished = false
            var polling = false

            fun finish(result: Result<ThreadsPost>) {
                if (finished) return
                finished = true
                handler.removeCallbacksAndMessages(null)
                web.stopLoading()
                web.destroy()
                result.fold({ cont.resume(it) }, { cont.resumeWithException(it) })
            }

            fun poll() {
                if (finished) return
                web.evaluateJavascript(THREADS_SCRIPT) { raw ->
                    val scrape = parseThreadsScrape(raw)
                    val parts = threadsParts(web.url ?: url) ?: threadsParts(url)
                    when {
                        scrape != null && scrape.videos.isNotEmpty() && parts != null ->
                            finish(Result.success(ThreadsPost(parts.first, parts.second, scrape.title, scrape.image, scrape.videos)))
                        SystemClock.uptimeMillis() > deadline ->
                            finish(Result.failure(IOException(
                                "No video found in that Threads post. It may only have pictures or text, or it may not be public.")))
                        else -> handler.postDelayed({ poll() }, 700)
                    }
                }
            }

            web.settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                mediaPlaybackRequiresUserGesture = true   // never autoplay sound in the background
                userAgentString = UA                       // the desktop page, which carries the video links
            }
            web.webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView, u: String) {
                    if (!polling) { polling = true; poll() }
                }
            }
            cont.invokeOnCancellation { handler.post { if (!finished) { finished = true; web.destroy() } } }
            web.loadUrl(url)
        }
    }
}
