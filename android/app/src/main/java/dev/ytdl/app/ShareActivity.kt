package dev.ytdl.app

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity

/**
 * Receives links shared from other apps. With "Download shared links immediately" on, it queues the link using the
 * remembered format and quality and closes, so you never leave the app you were in. Otherwise (first time, or a
 * channel or playlist link) it opens ytdl with the link filled in so you decide.
 */
class ShareActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val link = firstLink(intent.getStringExtra(Intent.EXTRA_TEXT))
        val preset = if (link != null && isSingleItemLink(link)) SharePrefs.preset(this) else null
        if (link != null && SharePrefs.auto(this) && preset != null) {
            DownloadCenter.init(application)
            DownloadCenter.enqueue(link, preset)
            Toast.makeText(this, "Added to ytdl: ${preset.format}" + if (!preset.audioOnly) ", ${preset.quality}" else "",
                Toast.LENGTH_SHORT).show()
        } else {
            startActivity(
                Intent(this, MainActivity::class.java).setAction(Intent.ACTION_SEND)
                    .putExtra(Intent.EXTRA_TEXT, link ?: intent.getStringExtra(Intent.EXTRA_TEXT))
            )
        }
        finish()
    }
}
