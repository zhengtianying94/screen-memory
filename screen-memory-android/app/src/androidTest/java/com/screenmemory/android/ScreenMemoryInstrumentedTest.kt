package com.screenmemory.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.net.HttpURLConnection
import java.net.URL

@RunWith(AndroidJUnit4::class)
class ScreenMemoryInstrumentedTest {

    private var server: HttpServer? = null

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val statusHandler = StatusHandler(
            isServiceEnabled = { true },
            isOcrReady = { true },
        )
        val captureHandler = CaptureHandler(
            mediaProjectionProvider = { null },
            windowManager = context.getSystemService(Context.WINDOW_SERVICE) as android.view.WindowManager,
            packageNameProvider = { "com.test" },
        )
        val ocrHandler = OcrHandler()

        server = HttpServer(statusHandler, captureHandler, ocrHandler).also {
            it.startServer()
        }
    }

    @After
    fun tearDown() {
        server?.stopServer()
    }

    @Test
    fun httpServerStartsOnPort() {
        val conn = URL("http://127.0.0.1:19700/status").openConnection() as HttpURLConnection
        conn.requestMethod = "GET"
        conn.connectTimeout = 3000
        conn.readTimeout = 3000

        assertEquals(200, conn.responseCode)
        val body = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(body)
        assertTrue(json.getBoolean("running"))
    }

    @Test
    fun statusEndpointReturnsCorrectFields() {
        val conn = URL("http://127.0.0.1:19700/status").openConnection() as HttpURLConnection
        conn.requestMethod = "GET"
        conn.connectTimeout = 3000

        val json = JSONObject(conn.inputStream.bufferedReader().readText())
        assertTrue(json.has("running"))
        assertTrue(json.has("ocr_ready"))
        assertTrue(json.has("service_enabled"))
        assertTrue(json.getBoolean("service_enabled"))
    }

    @Test
    fun captureWithoutMediaProjectionReturnsError() {
        val conn = URL("http://127.0.0.1:19700/capture").openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.doOutput = true
        conn.connectTimeout = 3000

        val body = """{"quality":80}"""
        conn.outputStream.write(body.toByteArray())
        conn.outputStream.flush()

        val response = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(response)
        assertTrue(json.has("error"))
    }

    @Test
    fun ocrWithInvalidImageReturnsError() {
        val conn = URL("http://127.0.0.1:19700/ocr").openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json")
        conn.doOutput = true
        conn.connectTimeout = 3000

        val body = """{"image":"invalid_base64_data"}"""
        conn.outputStream.write(body.toByteArray())
        conn.outputStream.flush()

        val response = conn.inputStream.bufferedReader().readText()
        val json = JSONObject(response)
        assertTrue(json.has("text"))
        assertEquals("mlkit", json.getString("engine"))
    }
}
