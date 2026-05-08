package com.screenmemory.android

import android.accessibilityservice.AccessibilityService
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.projection.MediaProjection
import android.os.Build
import android.view.accessibility.AccessibilityEvent

/** Accessibility Service that holds MediaProjection and runs the HTTP server. */
class ScreenMemoryService : AccessibilityService() {

    private var httpServer: HttpServer? = null
    private var captureHandler: CaptureHandler? = null
    private var ocrHandler: OcrHandler? = null
    private var statusHandler: StatusHandler? = null

    companion object {
        const val CHANNEL_ID = "screen_memory_channel"
        const val NOTIFICATION_ID = 1

        @Volatile
        var instance: ScreenMemoryService? = null
            private set

        var mediaProjection: MediaProjection? = null
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this

        ocrHandler = OcrHandler()
        statusHandler = StatusHandler(
            isServiceEnabled = { true },
            isOcrReady = { ocrHandler?.isReady() == true },
        )
        captureHandler = CaptureHandler(
            mediaProjectionProvider = { mediaProjection },
            windowManager = getSystemService(WINDOW_SERVICE) as android.view.WindowManager,
            packageNameProvider = {
                try {
                    rootInActiveWindow?.packageName?.toString()
                } catch (e: Exception) {
                    null
                }
            },
        )

        httpServer = HttpServer(
            statusHandler = statusHandler!!,
            captureHandler = captureHandler!!,
            ocrHandler = ocrHandler!!,
        ).also { it.startServer() }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    override fun onInterrupt() {}

    override fun onDestroy() {
        super.onDestroy()
        httpServer?.stopServer()
        httpServer = null
        instance = null
    }

    fun startForegroundNotification() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID, "Screen Memory", NotificationManager.IMPORTANCE_LOW,
        )
        nm.createNotificationChannel(channel)
        val notification = Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Screen Memory")
            .setContentText("Service running")
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID, notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION,
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }
}
