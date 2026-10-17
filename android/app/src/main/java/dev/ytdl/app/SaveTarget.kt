package dev.ytdl.app

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import android.webkit.MimeTypeMap
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.documentfile.provider.DocumentFile
import java.io.File
import java.net.URLDecoder

/** A folder as a person would read it, from the address Android gives for a chosen folder. Pure, so it is tested. */
fun prettyFolder(treeUri: String): String {
    val raw = treeUri.substringAfter("/tree/", "")
    if (raw.isEmpty()) return SaveTarget.DEFAULT_LABEL
    val decoded = try { URLDecoder.decode(raw, "UTF-8") } catch (e: Exception) { raw }
    val volume = decoded.substringBefore(":")
    val path = decoded.substringAfter(":", "").trim('/')
    return when {
        ":" !in decoded -> decoded.replaceFirstChar { it.uppercase() }
        volume == "primary" -> path.ifEmpty { "Internal storage" }
        else -> if (path.isEmpty()) "SD card" else "SD card/$path"
    }
}

/**
 * Where finished files go. By default the public Downloads/ytdl folder (no permission needed). You can pick any
 * folder instead with Android's folder chooser; if access to it is ever lost the files go back to the default.
 */
object SaveTarget {
    const val DEFAULT_LABEL = "Downloads/ytdl"
    private const val KEY = "save_tree"

    var label by mutableStateOf(DEFAULT_LABEL)
        private set
    var isCustom by mutableStateOf(false)
        private set
    var note by mutableStateOf("")
        private set

    private fun prefs(c: Context) = c.getSharedPreferences("ytdl", Context.MODE_PRIVATE)

    private fun tree(c: Context): Uri? = prefs(c).getString(KEY, null)?.let { Uri.parse(it) }

    /** Reads the saved choice, and forgets it if Android no longer lets us write there. */
    fun refresh(c: Context) {
        val t = tree(c)
        if (t != null && !canWrite(c, t)) {
            prefs(c).edit().remove(KEY).apply()
            note = "Couldn't use the folder you chose, so files go to $DEFAULT_LABEL."
        } else if (t != null) note = ""
        val now = tree(c)
        isCustom = now != null
        label = now?.let { prettyFolder(it.toString()) } ?: DEFAULT_LABEL
    }

    private fun canWrite(c: Context, t: Uri) = try { DocumentFile.fromTreeUri(c, t)?.canWrite() == true } catch (e: Exception) { false }

    fun choose(c: Context, uri: Uri) {
        c.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        tree(c)?.let { old -> if (old != uri) release(c, old) }
        prefs(c).edit().putString(KEY, uri.toString()).apply()
        note = ""
        refresh(c)
    }

    fun useDefault(c: Context) {
        tree(c)?.let { release(c, it) }
        prefs(c).edit().remove(KEY).apply()
        note = ""
        refresh(c)
    }

    private fun release(c: Context, uri: Uri) {
        try {
            c.contentResolver.releasePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        } catch (e: Exception) { /* already gone */ }
    }

    private fun mimeOf(file: File) = MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension.lowercase())
        ?: if (file.extension.lowercase() == "srt") "application/x-subrip" else "application/octet-stream"

    /** Copies a finished file to the chosen folder (or the default one) and returns the saved file's address. */
    fun save(c: Context, file: File, subFolder: String = ""): String {
        val t = tree(c)
        if (t != null) {
            saveToTree(c, t, file, subFolder)?.let { return it }
            // The folder stopped working (deleted, access revoked): fall back instead of losing the download.
            prefs(c).edit().remove(KEY).apply()
            note = "Couldn't write to the folder you chose, so this went to $DEFAULT_LABEL."
            isCustom = false
            label = DEFAULT_LABEL
        }
        return saveToDownloads(c, file, subFolder)
    }

    private fun saveToTree(c: Context, tree: Uri, file: File, subFolder: String): String? = try {
        var dir = DocumentFile.fromTreeUri(c, tree)?.takeIf { it.canWrite() }
        subFolder.split("/").filter { it.isNotEmpty() }.forEach { part ->
            dir = dir?.let { d -> d.findFile(part)?.takeIf { it.isDirectory } ?: d.createDirectory(part) }
        }
        val target = dir
        if (target == null) null else {
            var name = file.name
            var n = 1
            while (target.findFile(name) != null) { name = "${file.nameWithoutExtension} ($n).${file.extension}"; n++ }
            val doc = target.createFile(mimeOf(file), name)
            if (doc == null) null else {
                c.contentResolver.openOutputStream(doc.uri)!!.use { out -> file.inputStream().use { it.copyTo(out) } }
                doc.uri.toString()
            }
        }
    } catch (e: Exception) { null }

    private fun saveToDownloads(c: Context, file: File, subFolder: String): String {
        val resolver = c.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, file.name)
            put(MediaStore.Downloads.MIME_TYPE, mimeOf(file))
            put(MediaStore.Downloads.RELATIVE_PATH,
                "${Environment.DIRECTORY_DOWNLOADS}/ytdl" + if (subFolder.isNotEmpty()) "/$subFolder" else "")
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: error("Could not create file in Downloads")
        resolver.openOutputStream(uri)!!.use { out -> file.inputStream().use { it.copyTo(out) } }
        return uri.toString()
    }
}
