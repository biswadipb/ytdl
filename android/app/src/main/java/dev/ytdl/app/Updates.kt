package dev.ytdl.app

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

private const val REPO = "biswadipb/ytdl"

class ReleaseInfo(val version: String, val url: String)

/** Asks GitHub for the newest release. Returns it only when it is newer than [current]. Never installs anything. */
fun checkForNewRelease(current: String?): ReleaseInfo? {
    if (parseVersion(current) == null) return null // debug or source build
    val conn = URL("https://api.github.com/repos/$REPO/releases/latest").openConnection() as HttpURLConnection
    try {
        conn.connectTimeout = 10_000
        conn.readTimeout = 10_000
        conn.setRequestProperty("Accept", "application/vnd.github+json")
        conn.setRequestProperty("User-Agent", "ytdl-update-check")
        if (conn.responseCode != 200) return null
        val json = JSONObject(conn.inputStream.bufferedReader().readText())
        val tag = json.optString("tag_name")
        if (!isNewer(current, tag)) return null
        return ReleaseInfo(tag.removePrefix("v"), json.optString("html_url", "https://github.com/$REPO/releases/latest"))
    } finally {
        conn.disconnect()
    }
}
