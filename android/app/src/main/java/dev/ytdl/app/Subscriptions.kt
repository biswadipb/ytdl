package dev.ytdl.app

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.Calendar
import java.util.UUID
import java.util.concurrent.TimeUnit

data class Subscription(
    val id: String,
    val url: String,
    val name: String,
    val options: Options,
    val seen: List<String>,
    val enabled: Boolean,
    val lastChecked: Long,
    val lastError: String,
    val fails: Map<String, Int>,
)

/**
 * Followed channels and playlists. Each remembers which videos it has seen; a check lists the newest
 * videos and queues the ones it hasn't. Checks run from a background job (WorkManager), so they
 * happen even when the app is closed.
 */
object Subscriptions {
    private const val WORK = "subscriptions"
    private lateinit var app: Application
    private val mutex = Mutex()
    private val pending = mutableSetOf<String>() // "subId:videoId" queued but not finished

    val list = mutableStateListOf<Subscription>()
    var intervalHours by mutableStateOf(6)
        private set
    var onlyCharging by mutableStateOf(false)
        private set
    var onlyNight by mutableStateOf(false)
        private set
    var lastNote by mutableStateOf("")
        private set

    private val prefs get() = app.getSharedPreferences("ytdl", Context.MODE_PRIVATE)
    private val file get() = File(app.filesDir, "subscriptions.json")

    @Synchronized
    fun init(application: Application, schedule: Boolean) {
        if (!this::app.isInitialized) {
            app = application
            intervalHours = prefs.getInt("sub_interval", 6)
            onlyCharging = prefs.getBoolean("sub_charging", false)
            onlyNight = prefs.getBoolean("sub_night", false)
            load()
        }
        if (schedule) reschedule()
    }

    // ---- settings -----------------------------------------------------------------
    fun chooseInterval(hours: Int) { intervalHours = hours; prefs.edit().putInt("sub_interval", hours).apply() }
    fun chooseCharging(on: Boolean) { onlyCharging = on; prefs.edit().putBoolean("sub_charging", on).apply(); reschedule() }
    fun chooseNight(on: Boolean) { onlyNight = on; prefs.edit().putBoolean("sub_night", on).apply() }

    /** The background job runs hourly and each subscription decides if it is due; conditions are job constraints. */
    fun reschedule() {
        val work = WorkManager.getInstance(app)
        if (list.none { it.enabled }) { work.cancelUniqueWork(WORK); return }
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(if (DownloadCenter.allowMobileData) NetworkType.CONNECTED else NetworkType.UNMETERED)
            .setRequiresCharging(onlyCharging)
            .build()
        val request = PeriodicWorkRequestBuilder<SubscriptionWorker>(CHECK_PERIOD_HOURS, TimeUnit.HOURS)
            .setConstraints(constraints).build()
        work.enqueueUniquePeriodicWork(WORK, ExistingPeriodicWorkPolicy.UPDATE, request)
    }

    // ---- listing ------------------------------------------------------------------
    /** (name, newest videos first). Blocks, so call from a background thread. */
    fun fetchEntries(url: String, limit: Int, options: Options? = null): Pair<String, List<Entry>> {
        unlistableReason(url)?.let { throw IOException(it) }
        val req = YoutubeDLRequest(listingUrl(url))
        req.addOption("--flat-playlist")
        req.addOption("--dump-single-json")
        req.addOption("--playlist-end", "$limit")
        if (options?.useLogin != false) CookieStore.merged(app)?.let { req.addOption("--cookies", it.absolutePath) }
        val out = try {
            YoutubeDL.getInstance().execute(req).out
        } catch (e: Exception) {
            throw IOException(explainListingError(url, e.message ?: ""))
        }
        val json = JSONObject(out.substring(out.indexOf('{')))
        if (json.optString("_type") != "playlist") {
            throw IOException("That link is a single video. Follow a channel or playlist link instead.")
        }
        val arr = json.optJSONArray("entries") ?: JSONArray()
        val entries = (0 until arr.length()).mapNotNull { i ->
            val e = arr.optJSONObject(i) ?: return@mapNotNull null
            val link = e.optString("url").ifEmpty { e.optString("webpage_url") }
            if (!link.startsWith("http")) null
            else Entry(e.optString("id").ifEmpty { link }, link, e.optString("title", link),
                e.optString("live_status") in setOf("is_upcoming", "is_live"))
        }
        val name = json.optString("channel").ifEmpty { json.optString("uploader") }
            .ifEmpty { json.optString("title").removeSuffix(" - Videos") }.ifEmpty { url }
        return name to entries
    }

    // ---- actions ------------------------------------------------------------------
    /** Starts following. Everything already on the channel counts as seen, except the newest [backfill] videos, which download now. */
    suspend fun follow(url: String, options: Options, backfill: Int): Pair<Subscription, Int> = withContext(Dispatchers.IO) {
        DownloadCenter.awaitReady()
        val clean = options.copy(playlist = false, clipStart = null, clipEnd = null)
        val (name, entries) = fetchEntries(url, maxOf(PEEK, backfill), clean)
        if (list.any { it.url == url.trim() }) throw IOException("You already follow $name.")
        val sub = Subscription(UUID.randomUUID().toString().take(8), url.trim(), name, clean,
            entries.map { it.id }.take(SEEN_LIMIT), true, System.currentTimeMillis(), "", emptyMap())
        list.add(sub)
        save()
        entries.take(backfill).asReversed().forEach { enqueue(sub, it) }
        reschedule()
        sub to minOf(backfill, entries.size)
    }

    fun unfollow(id: String) { list.removeAll { it.id == id }; save(); reschedule() }
    fun setEnabled(id: String, on: Boolean) { update(id) { it.copy(enabled = on) }; reschedule() }

    private fun enqueue(sub: Subscription, entry: Entry) {
        val key = "${sub.id}:${entry.id}"
        synchronized(pending) { if (!pending.add(key)) return }
        DownloadCenter.enqueue(entry.url, sub.options, entry.title, sub.id, entry.id)
    }

    /** Looks for new uploads. [force] ignores the interval (the "Check now" button). Returns how many were queued. */
    suspend fun checkAll(force: Boolean): Int = mutex.withLock {
        withContext(Dispatchers.IO) {
            DownloadCenter.awaitReady()
            if (Storage.isLow()) { lastNote = "Paused: only ${humanSize(Storage.freeBytes)} free."; return@withContext 0 }
            lastNote = ""
            var queued = 0
            for (sub in list.toList()) {
                val now = System.currentTimeMillis()
                if (!sub.enabled || (!force && !isDue(sub.lastChecked, now, intervalHours))) continue
                try {
                    val (_, entries) = fetchEntries(sub.url, PEEK, sub.options)
                    val fresh = newEntries(sub.seen.toSet(), entries)
                        .filter { synchronized(pending) { "${sub.id}:${it.id}" !in pending } }
                    fresh.forEach { enqueue(sub, it) }
                    queued += fresh.size
                    update(sub.id) { it.copy(lastChecked = now, lastError = "") }
                } catch (e: Exception) {
                    update(sub.id) { it.copy(lastChecked = now, lastError = e.message?.lineSequence()?.firstOrNull().orEmpty().take(120)) }
                }
            }
            queued
        }
    }

    /** A queued video finished. Success (or the user cancelling) marks it seen; repeated failure gives up on it. */
    fun onItemResult(subId: String, videoId: String, ok: Boolean) {
        synchronized(pending) { pending.remove("$subId:$videoId") }
        update(subId) { s ->
            val failed = (s.fails[videoId] ?: 0) + 1
            when {
                ok || failed >= MAX_FAILS -> s.copy(seen = mergeSeen(s.seen, listOf(videoId)), fails = s.fails - videoId)
                else -> s.copy(fails = s.fails + (videoId to failed))
            }
        }
    }

    // ---- storage ------------------------------------------------------------------
    @Synchronized
    private fun update(id: String, change: (Subscription) -> Subscription) {
        val i = list.indexOfFirst { it.id == id }
        if (i >= 0) { list[i] = change(list[i]); save() }
    }

    @Synchronized
    private fun save() {
        val arr = JSONArray()
        list.forEach { s ->
            arr.put(JSONObject()
                .put("id", s.id).put("url", s.url).put("name", s.name).put("enabled", s.enabled)
                .put("lastChecked", s.lastChecked).put("lastError", s.lastError)
                .put("seen", JSONArray(s.seen)).put("fails", JSONObject(s.fails as Map<*, *>))
                .put("options", optionsToJson(s.options)))
        }
        file.writeText(JSONObject().put("subs", arr).toString())
    }

    private fun load() {
        val root = try { JSONObject(file.readText()) } catch (e: Exception) { return }
        val arr = root.optJSONArray("subs") ?: return
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val seen = o.optJSONArray("seen")?.let { a -> (0 until a.length()).map { a.getString(it) } }.orEmpty()
            val failsJson = o.optJSONObject("fails") ?: JSONObject()
            list.add(Subscription(o.getString("id"), o.getString("url"), o.getString("name"),
                optionsFromJson(o.getJSONObject("options")), seen, o.optBoolean("enabled", true),
                o.optLong("lastChecked"), o.optString("lastError"),
                failsJson.keys().asSequence().associateWith { failsJson.getInt(it) }))
        }
    }

    private fun optionsToJson(o: Options) = JSONObject()
        .put("format", o.format).put("quality", o.quality).put("extras", o.extras).put("useLogin", o.useLogin)
        .put("naming", o.naming).put("folders", o.folders).put("subLang", o.subLang ?: JSONObject.NULL)

    private fun optionsFromJson(j: JSONObject) = Options(
        j.optString("format", "mp4"), j.optString("quality", "best"), false, null, null,
        j.optBoolean("extras", true), j.optBoolean("useLogin", false),
        j.optString("naming", "title-id"), j.optString("folders", "flat"),
        if (j.isNull("subLang")) null else j.optString("subLang"))
}

/** Runs about hourly in the background. Conditions (charging, Wi-Fi) are applied by Android as job constraints. */
class SubscriptionWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext as Application
        DownloadCenter.init(app)
        Subscriptions.init(app, schedule = false)
        if (Subscriptions.onlyNight && !isNight(Calendar.getInstance().get(Calendar.HOUR_OF_DAY))) return Result.success()
        return try {
            Storage.cleanup()
            val queued = Subscriptions.checkAll(force = false)
            // The downloads run in this process, so stay alive until they finish (the system allows about ten minutes).
            if (queued > 0) DownloadCenter.awaitIdle(9 * 60_000L)
            Storage.cleanup()
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}
