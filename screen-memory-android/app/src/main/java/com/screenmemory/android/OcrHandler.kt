package com.screenmemory.android

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

    private var ready = true

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
