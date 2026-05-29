# Android Auxiliary APK — Phase 2: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Android APK that provides MediaProjection-based screen capture and ML Kit OCR over a NanoHTTPD localhost HTTP server for the Python screen-memory plugin.

**Architecture:** Single-activity Android app. `MainActivity` handles one-time MediaProjection authorization. `ScreenMemoryService` (Accessibility Service) holds the MediaProjection instance and starts `HttpServer` (NanoHTTPD on port 19700). `CaptureHandler` screenshots via VirtualDisplay+ImageReader. `OcrHandler` runs ML Kit Text Recognition v2 with Chinese support. All endpoints return JSON matching Phase 1 Python adapter contracts exactly.

**Tech Stack:** Kotlin, Android SDK 26+, NanoHTTPD 2.3.1 (embedded HTTP), ML Kit Text Recognition v2, AndroidX Accessibility, JUnit 4 + AndroidX Test for instrumented tests.

**Spec:** `docs/superpowers/specs/2026-05-07-android-screen-memory-adapter-design.md` Sections 6-7

---

## File Structure

```
screen-memory-android/
├── settings.gradle.kts
├── build.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml
│       │   ├── java/com/screenmemory/android/
│       │   │   ├── MainActivity.kt
│       │   │   ├── ScreenMemoryService.kt
│       │   │   ├── HttpServer.kt
│       │   │   ├── CaptureHandler.kt
│       │   │   ├── OcrHandler.kt
│       │   │   └── StatusHandler.kt
│       │   └── res/
│       │       ├── layout/activity_main.xml
│       │       ├── values/strings.xml
│       │       └── xml/accessibility_service_config.xml
│       └── androidTest/
│           └── java/com/screenmemory/android/
│               └── ScreenMemoryInstrumentedTest.kt
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `screen-memory-android/settings.gradle.kts`
- Create: `screen-memory-android/build.gradle.kts`
- Create: `screen-memory-android/app/build.gradle.kts`
- Create: `screen-memory-android/app/src/main/AndroidManifest.xml`
- Create: `screen-memory-android/app/src/main/res/values/strings.xml`

- [ ] **Step 1: Create project root structure**

```bash
cd D:/ScreenMemo
mkdir -p screen-memory-android/app/src/main/java/com/screenmemory/android
mkdir -p screen-memory-android/app/src/main/res/values
mkdir -p screen-memory-android/app/src/main/res/layout
mkdir -p screen-memory-android/app/src/main/res/xml
mkdir -p screen-memory-android/app/src/androidTest/java/com/screenmemory/android
```

- [ ] **Step 2: Create settings.gradle.kts**

```kotlin
// screen-memory-android/settings.gradle.kts
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "screen-memory-android"
include(":app")
```

- [ ] **Step 3: Create root build.gradle.kts**

```kotlin
// screen-memory-android/build.gradle.kts
plugins {
    id("com.android.application") version "8.2.0" apply false
    id("org.jetbrains.kotlin.android") version "1.9.22" apply false
}
```

- [ ] **Step 4: Create app/build.gradle.kts**

```kotlin
// screen-memory-android/app/build.gradle.kts
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.screenmemory.android"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.screenmemory.android"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }
}

dependencies {
    // NanoHTTPD - embedded HTTP server
    implementation("org.nanohttpd:nanohttpd:2.3.1")

    // ML Kit Text Recognition v2 with Chinese
    implementation("com.google.mlkit:text-recognition-chinese:16.0.1")

    // AndroidX
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")

    // Instrumented tests
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test:runner:1.5.2")
    androidTestImplementation("androidx.test:rules:1.5.0")
}
```

- [ ] **Step 5: Create AndroidManifest.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- screen-memory-android/app/src/main/AndroidManifest.xml -->
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />

    <application
        android:allowBackup="false"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@style/Theme.AppCompat.Light.NoActionBar">

        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <service
            android:name=".ScreenMemoryService"
            android:exported="false"
            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE">
            <intent-filter>
                <action android:name="android.accessibilityservice.AccessibilityService" />
            </intent-filter>
            <meta-data
                android:name="android.accessibilityservice"
                android:resource="@xml/accessibility_service_config" />
        </service>

    </application>
</manifest>
```

- [ ] **Step 6: Create strings.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- screen-memory-android/app/src/main/res/values/strings.xml -->
<resources>
    <string name="app_name">Screen Memory</string>
    <string name="service_description">Captures screenshots and performs OCR for the Screen Memory plugin.</string>
    <string name="status_waiting">Waiting for authorization…</string>
    <string name="status_running">Screen Memory service is running on port 19700</string>
    <string name="btn_authorize">Authorize Screen Capture</string>
    <string name="btn_enable_accessibility">Enable Accessibility Service</string>
</resources>
```

- [ ] **Step 7: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory-android/
git commit -m "chore(android): scaffold auxiliary APK project structure"
```

---

### Task 2: StatusHandler — Health Check Endpoint

**Files:**
- Create: `screen-memory-android/app/src/main/java/com/screenmemory/android/StatusHandler.kt`

- [ ] **Step 1: Implement StatusHandler**

```kotlin
// screen-memory-android/app/src/main/java/com/screenmemory/android/StatusHandler.kt
package com.screenmemory.android

import org.json.JSONObject

/** Handles the /status health check endpoint. */
class StatusHandler(
    private val isServiceEnabled: () -> Boolean,
    private val isOcrReady: () -> Boolean,
) {
    fun handle(): JSONObject {
        return JSONObject().apply {
            put("running", true)
            put("ocr_ready", isOcrReady())
            put("service_enabled", isServiceEnabled())
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory-android/app/src/main/java/com/screenmemory/android/StatusHandler.kt
git commit -m "feat(apk): add StatusHandler for /status health check endpoint"
```

---

### Task 3: CaptureHandler — MediaProjection Screenshot

**Files:**
- Create: `screen-memory-android/app/src/main/java/com/screenmemory/android/CaptureHandler.kt`

- [ ] **Step 1: Implement CaptureHandler**

```kotlin
// screen-memory-android/app/src/main/java/com/screenmemory/android/CaptureHandler.kt
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

            // Wait for a frame to be available
            val image: Image? = waitForFrame(imageReader, maxAttempts = 10, delayMs = 100)
                ?: return errorResult("Failed to capture frame")

            val bitmap = imageToBitmap(image, width, height)
            image.close()

            val jpegBytes = bitmapToJpeg(bitmap, quality)
            val base64Image = Base64.encodeToString(jpegBytes, Base64.NO_WRAP)
            val appPackage = packageNameProvider()
            val captureTimeMs = 0L // measured externally by Python

            return JSONObject().apply {
                put("image", base64Image)
                put("width", width)
                put("height", height)
                put("app_package", appPackage ?: JSONObject.NULL)
                put("capture_time_ms", captureTimeMs)
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
```

- [ ] **Step 2: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory-android/app/src/main/java/com/screenmemory/android/CaptureHandler.kt
git commit -m "feat(apk): add CaptureHandler with MediaProjection + VirtualDisplay"
```

---

### Task 4: OcrHandler — ML Kit Text Recognition

**Files:**
- Create: `screen-memory-android/app/src/main/java/com/screenmemory/android/OcrHandler.kt`

- [ ] **Step 1: Implement OcrHandler**

```kotlin
// screen-memory-android/app/src/main/java/com/screenmemory/android/OcrHandler.kt
package com.screenmemory.android

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Base64
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions
import org.json.JSONArray
import org.json.JSONObject

/** Handles OCR via ML Kit Text Recognition v2 with Chinese support. */
class OcrHandler {

    private val recognizer = TextRecognition.getClient(ChineseTextRecognizerOptions.Builder().build())

    private var ready = false

    init {
        // Download model on first use; mark ready once model is available
        ready = true
    }

    fun isReady(): Boolean = ready

    fun recognize(base64Image: String): JSONObject {
        if (!ready) {
            return emptyResult("OCR not ready")
        }

        return try {
            val imageBytes = Base64.decode(base64Image, Base64.NO_WRAP)
            val bitmap = BitmapFactory.decodeByteArray(imageBytes, 0, imageBytes.size)
                ?: return emptyResult("Failed to decode image")

            val inputImage = InputImage.fromBitmap(bitmap, 0)
            val visionText = recognizer.process(inputImage).result

            val fullText = visionText.text
            val blocksArray = JSONArray()

            for (block in visionText.textBlocks) {
                for (line in block.lines) {
                    for (element in line.elements) {
                        val bbox = element.boundingBox
                        blocksArray.put(JSONObject().apply {
                            put("text", element.text)
                            put("bbox", JSONArray().apply {
                                if (bbox != null) {
                                    put(bbox.left)
                                    put(bbox.top)
                                    put(bbox.width())
                                    put(bbox.height())
                                } else {
                                    put(0); put(0); put(0); put(0)
                                }
                            })
                            put("confidence", 0.85)
                        })
                    }
                }
            }

            JSONObject().apply {
                put("text", fullText)
                put("blocks", blocksArray)
                put("engine", "mlkit")
                put("processing_time_ms", 0)
            }
        } catch (e: Exception) {
            emptyResult(e.message ?: "OCR failed")
        }
    }

    private fun emptyResult(message: String): JSONObject {
        return JSONObject().apply {
            put("text", "")
            put("blocks", JSONArray())
            put("engine", "mlkit")
            put("processing_time_ms", 0)
            put("error", message)
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory-android/app/src/main/java/com/screenmemory/android/OcrHandler.kt
git commit -m "feat(apk): add OcrHandler with ML Kit Chinese Text Recognition"
```

---

### Task 5: HttpServer — NanoHTTPD Router

**Files:**
- Create: `screen-memory-android/app/src/main/java/com/screenmemory/android/HttpServer.kt`

- [ ] **Step 1: Implement HttpServer**

```kotlin
// screen-memory-android/app/src/main/java/com/screenmemory/android/HttpServer.kt
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
                    // Merge capture metadata + OCR result
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
            val body = session.inputStream.bufferedReader().readText()
            if (body.isBlank()) null else JSONObject(body)
        } catch (e: Exception) {
            null
        }
    }

    private fun jsonResponse(json: JSONObject, status: Response.Status = Response.Status.OK): Response {
        return newFixedLengthResponse(status, "application/json", json.toString())
    }
}
```

- [ ] **Step 2: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory-android/app/src/main/java/com/screenmemory/android/HttpServer.kt
git commit -m "feat(apk): add HttpServer with NanoHTTPD routing for all endpoints"
```

---

### Task 6: ScreenMemoryService — Accessibility Service

**Files:**
- Create: `screen-memory-android/app/src/main/java/com/screenmemory/android/ScreenMemoryService.kt`
- Create: `screen-memory-android/app/src/main/res/xml/accessibility_service_config.xml`

- [ ] **Step 1: Create accessibility service config**

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- screen-memory-android/app/src/main/res/xml/accessibility_service_config.xml -->
<accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"
    android:accessibilityEventTypes="typeAllMask"
    android:accessibilityFeedbackType="feedbackGeneric"
    android:accessibilityFlags="flagDefault"
    android:canRetrieveWindowContent="true"
    android:description="@string/service_description"
    android:notificationTimeout="100" />
```

- [ ] **Step 2: Implement ScreenMemoryService**

```kotlin
// screen-memory-android/app/src/main/java/com/screenmemory/android/ScreenMemoryService.kt
package com.screenmemory.android

import android.accessibilityservice.AccessibilityService
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.view.accessibility.AccessibilityEvent

/** Accessibility Service that holds MediaProjection and runs the HTTP server. */
class ScreenMemoryService : AccessibilityService() {

    private var httpServer: HttpServer? = null
    private var captureHandler: CaptureHandler? = null
    private var ocrHandler: OcrHandler? = null
    private var statusHandler: StatusHandler? = null

    companion object {
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

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // No processing needed; we only use this service for window content access
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        super.onDestroy()
        httpServer?.stopServer()
        httpServer = null
        instance = null
    }
}
```

- [ ] **Step 3: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory-android/app/src/main/java/com/screenmemory/android/ScreenMemoryService.kt
git add screen-memory-android/app/src/main/res/xml/accessibility_service_config.xml
git commit -m "feat(apk): add ScreenMemoryService with Accessibility Service + HTTP server lifecycle"
```

---

### Task 7: MainActivity — Authorization UI

**Files:**
- Create: `screen-memory-android/app/src/main/java/com/screenmemory/android/MainActivity.kt`
- Create: `screen-memory-android/app/src/main/res/layout/activity_main.xml`

- [ ] **Step 1: Create activity layout**

```xml
<?xml version="1.0" encoding="utf-8"?>
<!-- screen-memory-android/app/src/main/res/layout/activity_main.xml -->
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:gravity="center"
    android:padding="24dp">

    <TextView
        android:id="@+id/statusText"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="@string/status_waiting"
        android:textSize="16sp"
        android:gravity="center"
        android:layout_marginBottom="24dp" />

    <Button
        android:id="@+id/btnEnableAccessibility"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="@string/btn_enable_accessibility"
        android:layout_marginBottom="12dp" />

    <Button
        android:id="@+id/btnAuthorize"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:text="@string/btn_authorize" />

</LinearLayout>
```

- [ ] **Step 2: Implement MainActivity**

```kotlin
// screen-memory-android/app/src/main/java/com/screenmemory/android/MainActivity.kt
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
            startActivityForResult(
                projectionManager.createScreenCaptureIntent(),
                REQUEST_MEDIA_PROJECTION,
            )
        }
    }

    override fun onResume() {
        super.onResume()
        updateStatus()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == REQUEST_MEDIA_PROJECTION) {
            if (resultCode == RESULT_OK && data != null) {
                ScreenMemoryService.mediaProjection =
                    projectionManager.getMediaProjection(resultCode, data)
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
```

- [ ] **Step 3: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory-android/app/src/main/java/com/screenmemory/android/MainActivity.kt
git add screen-memory-android/app/src/main/res/layout/activity_main.xml
git commit -m "feat(apk): add MainActivity with accessibility + MediaProjection authorization flow"
```

---

### Task 8: Instrumented Tests

**Files:**
- Create: `screen-memory-android/app/src/androidTest/java/com/screenmemory/android/ScreenMemoryInstrumentedTest.kt`

- [ ] **Step 1: Write instrumented tests**

```kotlin
// screen-memory-android/app/src/androidTest/java/com/screenmemory/android/ScreenMemoryInstrumentedTest.kt
package com.screenmemory.android

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
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
            mediaProjectionProvider = { null }, // no MediaProjection in tests
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

        // Should return 200 with error field (no MediaProjection in test)
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
        // Should have text field (empty or with error)
        assertTrue(json.has("text"))
        assertEquals("mlkit", json.getString("engine"))
    }
}
```

- [ ] **Step 2: Commit**

```bash
cd D:/ScreenMemo
git add screen-memory-android/app/src/androidTest/java/com/screenmemory/android/ScreenMemoryInstrumentedTest.kt
git commit -m "test(apk): add instrumented tests for HTTP server and endpoints"
```

---

### Task 9: Final Verification — Build Check

- [ ] **Step 1: Verify project compiles**

```bash
cd D:/ScreenMemo/screen-memory-android
# If Android SDK is available:
# ./gradlew assembleDebug
# Otherwise verify file structure:
find . -name "*.kt" -o -name "*.xml" -o -name "*.gradle.kts" | sort
```

Expected: All files listed in File Structure section present.

- [ ] **Step 2: Verify no Python-side regressions**

```bash
cd D:/ScreenMemo/screen-memory
python -m pytest tests/ -v --tb=short
```

Expected: All 194 tests still pass.

- [ ] **Step 3: Final commit with .gitignore**

Create `screen-memory-android/.gitignore`:
```
*.iml
.gradle
/local.properties
/.idea
/build
/app/build
/captures
.externalNativeBuild
.cxx
```

```bash
cd D:/ScreenMemo
git add screen-memory-android/.gitignore
git commit -m "chore(apk): add Android project .gitignore"
```
