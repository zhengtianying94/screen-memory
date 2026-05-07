package com.screenmemory.android

import fi.iki.elonen.NanoHTTPD
import org.json.JSONObject
import java.io.IOException

/** NanoHTTPD-based HTTP server on localhost, routes to handlers. */
class HttpServer(
    private val statusHandler: StatusHandler,
    private val captureHandler: CaptureHandler,
    private val ocrHandler: OcrHandler,
) : NanoHTTPD(PORT) {

    companion object {
        const val PORT = 19700
    }

    fun startServer() {
        try {
            start(SOCKET_READ_TIMEOUT, false)
        } catch (e: IOException) {
            // Port may be in use; log but don't crash
        }
    }

    fun stopServer() {
        stop()
    }

    override fun serve(session: IHTTPSession): Response {
        val uri = session.uri ?: return newFixedLengthResponse(
            Response.Status.NOT_FOUND, MIME_PLAINTEXT, "Not found",
        )

        return when {
            // GET /status
            session.method == Method.GET && uri == "/status" -> {
                jsonResponse(statusHandler.handle())
            }

            // POST /capture
            session.method == Method.POST && uri == "/capture" -> {
                val params = parseJsonBody(session)
                val quality = params?.optInt("quality", 80) ?: 80
                jsonResponse(captureHandler.capture(quality))
            }

            // POST /ocr
            session.method == Method.POST && uri == "/ocr" -> {
                val params = parseJsonBody(session)
                val image = params?.optString("image") ?: ""
                if (image.isEmpty()) {
                    jsonResponse(JSONObject().put("error", "Missing 'image' field"), Response.Status.BAD_REQUEST)
                } else {
                    jsonResponse(ocrHandler.recognize(image))
                }
            }

            // POST /capture-and-ocr
            session.method == Method.POST && uri == "/capture-and-ocr" -> {
                val params = parseJsonBody(session)
                val quality = params?.optInt("quality", 80) ?: 80
                val captureResult = captureHandler.capture(quality)
                if (captureResult.has("error")) {
                    jsonResponse(captureResult, Response.Status.INTERNAL_ERROR)
                } else {
                    val imageBase64 = captureResult.optString("image", "")
                    val ocrResult = ocrHandler.recognize(imageBase64)
                    val merged = JSONObject()
                    merged.put("image", imageBase64)
                    merged.put("width", captureResult.optInt("width"))
                    merged.put("height", captureResult.optInt("height"))
                    merged.put("app_package", captureResult.opt("app_package"))
                    merged.put("capture_time_ms", captureResult.optLong("capture_time_ms"))
                    merged.put("text", ocrResult.optString("text"))
                    merged.put("blocks", ocrResult.optJSONArray("blocks"))
                    merged.put("engine", ocrResult.optString("engine"))
                    merged.put("processing_time_ms", ocrResult.optLong("processing_time_ms"))
                    jsonResponse(merged)
                }
            }

            else -> newFixedLengthResponse(
                Response.Status.NOT_FOUND, MIME_PLAINTEXT, "Not found: $uri",
            )
        }
    }

    private fun parseJsonBody(session: IHTTPSession): JSONObject? {
        return try {
            val contentLength = session.headers["content-length"]?.toLongOrNull() ?: 0L
            if (contentLength == 0L) return null
            val bytes = session.inputStream.readNBytes(contentLength.toInt())
            val body = String(bytes, Charsets.UTF_8)
            if (body.isBlank()) null else JSONObject(body)
        } catch (e: Exception) {
            null
        }
    }

    private fun jsonResponse(json: JSONObject, status: Response.Status = Response.Status.OK): Response {
        return newFixedLengthResponse(status, "application/json", json.toString())
    }
}
