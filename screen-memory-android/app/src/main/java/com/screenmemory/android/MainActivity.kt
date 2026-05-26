package com.screenmemory.android

import android.accessibilityservice.AccessibilityServiceInfo
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.provider.Settings
import android.view.accessibility.AccessibilityManager
import android.widget.Button
import android.widget.TextView

class MainActivity : Activity() {

    companion object {
        private const val REQUEST_MEDIA_PROJECTION = 1001
    }

    private lateinit var statusText: TextView
    private lateinit var btnAuthorize: Button
    private lateinit var projectionManager: MediaProjectionManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.statusText)
        btnAuthorize = findViewById(R.id.btnAuthorize)
        projectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager

        findViewById<Button>(R.id.btnEnableAccessibility).setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }

        btnAuthorize.setOnClickListener {
            try {
                val service = ScreenMemoryService.instance
                if (service != null) {
                    service.startForegroundNotification()
                }
                startActivityForResult(
                    projectionManager.createScreenCaptureIntent(),
                    REQUEST_MEDIA_PROJECTION,
                )
            } catch (e: Exception) {
                updateStatus()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        updateStatus()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == REQUEST_MEDIA_PROJECTION) {
            if (resultCode == RESULT_OK && data != null) {
                try {
                    val service = ScreenMemoryService.instance
                    if (service != null) {
                        service.startForegroundNotification()
                    }
                    ScreenMemoryService.mediaProjection =
                        projectionManager.getMediaProjection(resultCode, data)
                } catch (e: Exception) {
                    // getMediaProjection may throw SecurityException on some ROMs
                    ScreenMemoryService.mediaProjection = null
                }
                updateStatus()
            }
        }
    }

    private fun updateStatus() {
        val serviceEnabled = isAccessibilityServiceEnabled()
        val projectionReady = ScreenMemoryService.mediaProjection != null

        val status = when {
            !serviceEnabled -> "Step 1: Enable Accessibility Service in Settings"
            !projectionReady -> "Step 2: Tap 'Authorize Screen Capture' below"
            else -> "Screen Memory service is running on port 19700"
        }
        statusText.text = status
    }

    private fun isAccessibilityServiceEnabled(): Boolean {
        val am = getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        val enabled = am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
        return enabled.any { it.resolveInfo.serviceInfo.packageName == packageName }
    }
}
