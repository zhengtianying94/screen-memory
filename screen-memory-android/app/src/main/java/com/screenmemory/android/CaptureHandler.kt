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

/** Handles screen capture via MediaProjection + VirtualDisplay + ImageReader. */
class CaptureHandler(
    private val mediaProjectionProvider: () -> MediaProjection?,
    private val windowManager: WindowManager,
    private val packageNameProvider: () -> String?,
) {
    fun capture(quality: Int = 80): JSONObject {
        val projection = mediaProjectionProvider()
            ?: return errorResult("MediaProjection not available")

        val metrics = DisplayMetrics()
        windowManager.defaultDisplay.getRealMetrics(metrics)
        val width = metrics.widthPixels
        val height = metrics.heightPixels
        val density = metrics.densityDpi

        val imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)

        var virtualDisplay: VirtualDisplay? = null
        try {
            virtualDisplay = projection.createVirtualDisplay(
                "ScreenMemoryCapture",
                width, height, density,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                imageReader.surface, null, null,
            )

            val image: Image? = waitForFrame(imageReader, maxAttempts = 10, delayMs = 100)
                ?: return errorResult("Failed to capture frame")

            val bitmap = imageToBitmap(image, width, height)
            image.close()

            val jpegBytes = bitmapToJpeg(bitmap, quality)
            val base64Image = Base64.encodeToString(jpegBytes, Base64.NO_WRAP)
            val appPackage = packageNameProvider()

            return JSONObject().apply {
                put("image", base64Image)
                put("width", width)
                put("height", height)
                put("app_package", appPackage ?: JSONObject.NULL)
                put("capture_time_ms", 0L)
            }
        } finally {
            virtualDisplay?.release()
            imageReader.close()
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
