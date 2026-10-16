package dev.ytdl.app

import android.app.Application
import android.content.Context
import android.net.Uri
import android.os.Environment
import android.os.StatFs
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Disk-space controls for downloads made by subscriptions. ytdl only deletes files it downloaded for a
 * subscription and recorded here; your own downloads are never touched.
 */
object Storage {
    private lateinit var app: Application
    private val file get() = File(app.filesDir, "sub_files.json")
    private val prefs get() = app.getSharedPreferences("ytdl", Context.MODE_PRIVATE)

    var keepDays by mutableStateOf(0)
        private set
    var maxGb by mutableStateOf(0)
        private set
    var minFreeGb by mutableStateOf(1)
        private set
    var freeBytes by mutableStateOf(0L)
        private set

    @Synchronized
    fun init(application: Application) {
        if (this::app.isInitialized) return
        app = application
        keepDays = prefs.getInt("keep_days", 0)
        maxGb = prefs.getInt("max_gb", 0)
        minFreeGb = prefs.getInt("min_free_gb", 1)
        refresh()
    }

    fun chooseKeepDays(v: Int) { keepDays = v; prefs.edit().putInt("keep_days", v).apply() }
    fun chooseMaxGb(v: Int) { maxGb = v; prefs.edit().putInt("max_gb", v).apply() }
    fun chooseMinFree(v: Int) { minFreeGb = v; prefs.edit().putInt("min_free_gb", v).apply() }

    fun refresh() {
        freeBytes = try {
            StatFs(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).path).availableBytes
        } catch (e: Exception) { 0L }
    }

    /** True when free space is under the warning level (never when the warning is off). */
    fun isLow(): Boolean { refresh(); return minFreeGb > 0 && freeBytes < minFreeGb * 1024L * 1024 * 1024 }

    // ---- records --------------------------------------------------------------------
    private fun read(): List<StoredFile> = try {
        val arr = JSONArray(file.readText())
        (0 until arr.length()).map { arr.getJSONObject(it).let { o -> StoredFile(o.getString("ref"), o.getLong("size"), o.getLong("time")) } }
    } catch (e: Exception) { emptyList() }

    @Synchronized
    private fun write(files: List<StoredFile>) {
        val arr = JSONArray()
        files.forEach { arr.put(JSONObject().put("ref", it.ref).put("size", it.size).put("time", it.time)) }
        file.writeText(arr.toString())
    }

    @Synchronized
    fun record(uri: String, size: Long) = write(read() + StoredFile(uri, size, System.currentTimeMillis()))

    fun pending(): List<StoredFile> = planCleanup(read(), keepDays, maxGb, System.currentTimeMillis())

    /** Deletes what the settings call for. Returns (files removed, bytes freed). */
    @Synchronized
    fun cleanup(): Pair<Int, Long> {
        val doomed = pending()
        var count = 0
        var freed = 0L
        val gone = mutableSetOf<String>()
        for (f in doomed) {
            try {
                val removed = app.contentResolver.delete(Uri.parse(f.ref), null, null)
                if (removed > 0) { count++; freed += f.size }
                gone.add(f.ref)          // deleted, or already gone: either way forget it
            } catch (e: Exception) { /* can't delete right now: keep the record and try later */ }
        }
        write(read().filter { it.ref !in gone })
        refresh()
        return count to freed
    }
}
