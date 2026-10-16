package dev.ytdl.app

import android.annotation.SuppressLint
import android.content.Context
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import java.io.File

/** Sites where signing in unlocks private or login-only posts. */
enum class Site(val label: String, val loginUrl: String, val cookieUrls: List<String>, val domains: List<String>) {
    Instagram("Instagram", "https://www.instagram.com/accounts/login/",
        listOf("https://www.instagram.com"), listOf(".instagram.com")),
    Facebook("Facebook", "https://m.facebook.com/login/",
        listOf("https://www.facebook.com", "https://m.facebook.com"), listOf(".facebook.com")),
    X("X / Twitter", "https://x.com/i/flow/login",
        listOf("https://x.com", "https://twitter.com"), listOf(".x.com", ".twitter.com")),
    Threads("Threads", "https://www.threads.com/login",
        listOf("https://www.threads.com", "https://www.threads.net"), listOf(".threads.com", ".threads.net")),
    Vimeo("Vimeo", "https://vimeo.com/log_in", listOf("https://vimeo.com"), listOf(".vimeo.com")),
}

/** Cookies captured from the in-app browser, stored privately and handed to yt-dlp as cookies.txt. */
object CookieStore {
    private fun dir(c: Context) = File(c.filesDir, "cookies").also { it.mkdirs() }
    private fun file(c: Context, s: Site) = File(dir(c), "${s.name}.txt")

    fun isLoggedIn(c: Context, s: Site) = file(c, s).exists()

    fun save(c: Context, s: Site) {
        val cm = CookieManager.getInstance()
        val expiry = System.currentTimeMillis() / 1000 + 60L * 60 * 24 * 365
        val lines = StringBuilder("# Netscape HTTP Cookie File\n")
        var count = 0
        s.cookieUrls.forEachIndexed { i, url ->
            val domain = s.domains.getOrElse(i) { s.domains.last() }
            cm.getCookie(url)?.split(";")?.map { it.trim() }?.filter { "=" in it }?.forEach { pair ->
                val (name, value) = pair.split("=", limit = 2)
                lines.append("$domain\tTRUE\t/\tTRUE\t$expiry\t$name\t$value\n")
                count++
            }
        }
        if (count > 0) file(c, s).writeText(lines.toString())
    }

    fun logOut(c: Context) {
        dir(c).deleteRecursively()
        CookieManager.getInstance().removeAllCookies(null)
        CookieManager.getInstance().flush()
    }

    /** All saved logins combined into one cookies.txt, or null when signed out everywhere. */
    fun merged(c: Context): File? {
        val parts = Site.entries.map { file(c, it) }.filter { it.exists() }
        if (parts.isEmpty()) return null
        val out = File(c.cacheDir, "cookies.txt")
        out.writeText("# Netscape HTTP Cookie File\n" + parts.joinToString("") {
            it.readLines().filter { l -> !l.startsWith("#") }.joinToString("") { l -> "$l\n" }
        })
        return out
    }
}

class LoginActivity : ComponentActivity() {
    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val site = Site.entries.firstOrNull { it.name == intent.getStringExtra("site") } ?: return finish()

        val web = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            // Some sites refuse the "wv" WebView marker, so present as ordinary mobile Chrome.
            settings.userAgentString = settings.userAgentString.replace("; wv", "")
            webViewClient = WebViewClient()
            layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f)
        }
        val done = Button(this).apply {
            text = "I'm signed in. Save and close"
            setOnClickListener {
                CookieManager.getInstance().flush()
                CookieStore.save(this@LoginActivity, site)
                finish()
            }
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            fitsSystemWindows = true
            addView(done)
            addView(web)
        })
        CookieManager.getInstance().setAcceptCookie(true)
        web.loadUrl(site.loginUrl)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else finish()
            }
        })
    }
}
