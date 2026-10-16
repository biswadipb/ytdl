package dev.ytdl.app

import android.content.Context
import org.json.JSONObject

/** The format chosen once for links shared into ytdl, and whether to use it without asking. */
object SharePrefs {
    private fun prefs(c: Context) = c.getSharedPreferences("ytdl", Context.MODE_PRIVATE)

    fun auto(c: Context) = prefs(c).getBoolean("share_auto", false)
    fun setAuto(c: Context, on: Boolean) = prefs(c).edit().putBoolean("share_auto", on).apply()
    fun asked(c: Context) = prefs(c).getBoolean("share_asked", false)
    fun setAsked(c: Context) = prefs(c).edit().putBoolean("share_asked", true).apply()

    fun save(c: Context, o: Options) {
        val j = JSONObject().put("format", o.format).put("quality", o.quality).put("extras", o.extras)
            .put("naming", o.naming).put("folders", o.folders).put("subLang", o.subLang ?: JSONObject.NULL)
        prefs(c).edit().putString("share_preset", j.toString()).apply()
    }

    /** The remembered options, with login added when you're signed in at the time of sharing. Never a whole playlist. */
    fun preset(c: Context): Options? {
        val raw = prefs(c).getString("share_preset", null) ?: return null
        return try {
            val j = JSONObject(raw)
            Options(j.getString("format"), j.optString("quality", "best"), false, null, null, j.optBoolean("extras", true),
                CookieStore.merged(c) != null, j.optString("naming", "title-id"), j.optString("folders", "flat"),
                if (j.isNull("subLang")) null else j.optString("subLang"))
        } catch (e: Exception) { null }
    }

    fun summary(c: Context): String = preset(c)?.let {
        it.format + if (it.audioOnly) "" else ", ${it.quality} quality"
    } ?: "not saved yet"
}
