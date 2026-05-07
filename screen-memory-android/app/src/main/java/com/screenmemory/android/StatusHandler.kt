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
