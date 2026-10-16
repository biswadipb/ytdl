package dev.ytdl.minimal

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Keeps downloads going, with a progress notification, if you leave the app. */
class DownloadService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var watcher: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("downloads", "Downloads", NotificationManager.IMPORTANCE_LOW))
        startForeground(1, build("Starting…", 0f), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        if (watcher?.isActive != true) {
            watcher = scope.launch {
                while (Downloads.activeCount > 0) {
                    nm.notify(1, build(Downloads.summary(), Downloads.progressNow()))
                    delay(800)
                }
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }

    private fun build(text: String, progress: Float): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, "downloads")
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle("ytdl")
            .setContentText(text)
            .setProgress(100, (progress * 100).toInt(), progress <= 0f)
            .setContentIntent(open)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }
}
