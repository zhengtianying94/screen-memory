package com.screenmemory.android

import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.util.Base64
import android.util.DisplayMetrics
import android.view.WindowManager
import org.json.JSONObject
import java.io.ByteArrayOutputStream

/** Handles screen capture via MediaProjection + persistent VirtualDisplay.
 *  Falls back to `screencap` shell command on emulator/rooted devices. */
class CaptureHandler(
    private val mediaProjectionProvider: () -> MediaProjection?,
    private val windowManager: WindowManager,
    private val packageNameProvider: () -> String?,
) {
    private var cachedProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var cachedWidth = 0
    private var cachedHeight = 0

    @Suppress("DEPRECATION")
    private val metrics: DisplayMetrics
        get() {
            val m = DisplayMetrics()
            windowManager.defaultDisplay.getRealMetrics(m)
            return m
        }

    @Synchronized
    fun capture(quality: Int = 80): JSONObject {
        val projection = mediaProjectionProvider()
        return if (projection != null) {
            try {
                captureViaMediaProjection(projection, quality)
            } catch (e: Exception) {
                teardownDisplay()
                errorResult("MediaProjection capture failed: ${e.message}")
            }
        } else {
            teardownDisplay()
            captureViaScreencap(quality)
        }
    }

    @Synchronized
    private fun captureViaMediaProjection(projection: MediaProjection, quality: Int): JSONObject {
        val m = metrics
        val width = m.widthPixels
        val height = m.heightPixels
        val density = m.densityDpi

        // Create VirtualDisplay on first use or when projection changes
        if (projection !== cachedProjection || virtualDisplay == null) {
            teardownDisplay()
            projection.registerCallback(object : MediaProjection.Callback() {}, null)
            val display = projection.createVirtualDisplay(
                "ScreenMemoryCapture",
                width, height, density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                null, null, null,
            )
            cachedProjection = projection
            virtualDisplay = display
            cachedWidth = width
            cachedHeight = height
        }

        // Create a fresh ImageReader for each capture to guarantee a new frame
        val reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        try {
            virtualDisplay?.surface = reader.surface
            val image = waitForFrame(reader, maxAttempts = 15, delayMs = 80)
                ?: return errorResult("Failed to capture frame within timeout")

            try {
                val bitmap = imageToBitmap(image, width, height)
                val jpegBytes = bitmapToJpeg(bitmap, quality)
                val base64Image = Base64.encodeToString(jpegBytes, Base64.NO_WRAP)
                val appPackage = packageNameProvider()

                return JSONObject().apply {
                    put("image", base64Image)
                    put("width", width)
                    put("height", height)
                    put("app_package", appPackage ?: JSONObject.NULL)
                    put("capture_time_ms", System.currentTimeMillis())
                }
            } finally {
                image.close()
            }
        } finally {
            virtualDisplay?.surface = null
            reader.close()
        }
    }

    @Synchronized
    private fun teardownDisplay() {
        virtualDisplay?.release()
        virtualDisplay = null
        cachedProjection = null
        cachedWidth = 0
        cachedHeight = 0
    }

    @Suppress("DEPRECATION")
    private fun captureViaScreencap(quality: Int): JSONObject {
        return try {
            val tmpFile = java.io.File.createTempFile("screenmem", ".png")
            val process = Runtime.getRuntime().exec(
                arrayOf("screencap", "-p", tmpFile.absolutePath)
            )
            process.waitFor()
            if (process.exitValue() != 0 || !tmpFile.exists()) {
                return errorResult("screencap failed")
            }
            val bitmap = android.graphics.BitmapFactory.decodeFile(tmpFile.absolutePath)
                ?: return errorResult("screencap decode failed")
            tmpFile.delete()
            val jpegBytes = bitmapToJpeg(bitmap, quality)
            val base64Image = Base64.encodeToString(jpegBytes, Base64.NO_WRAP)
            val m = metrics
            val appPackage = packageNameProvider()
            JSONObject().apply {
                put("image", base64Image)
                put("width", m.widthPixels)
                put("height", m.heightPixels)
                put("app_package", appPackage ?: JSONObject.NULL)
                put("capture_time_ms", System.currentTimeMillis())
            }
        } catch (e: Exception) {
            errorResult("screencap fallback failed: ${e.message}")
        }
    }

    private fun waitForFrame(reader: ImageReader, maxAttempts: Int, delayMs: Long): Image? {
        repeat(maxAttempts) {
            val image = reader.acquireLatestImage()
            if (image != null) return image
            Thread.sleep(delayMs)
        }
        return reader.acquireLatestImage()
    }

    private fun imageToBitmap(image: Image, width: Int, height: Int): Bitmap {
        val planes = image.planes
        val buffer = planes[0].buffer
        val pixelStride = planes[0].pixelStride
        val rowStride = planes[0].rowStride
        val rowPadding = rowStride - pixelStride * width

        val bitmap = Bitmap.createBitmap(
            width + rowPadding / pixelStride, height, Bitmap.Config.ARGB_8888,
        )
        bitmap.copyPixelsFromBuffer(buffer)
        return if (rowPadding == 0) bitmap else Bitmap.createBitmap(bitmap, 0, 0, width, height)
    }

    private fun bitmapToJpeg(bitmap: Bitmap, quality: Int): ByteArray {
        val stream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, quality, stream)
        return stream.toByteArray()
    }

    private fun errorResult(message: String): JSONObject {
        return JSONObject().apply { put("error", message) }
    }
}
