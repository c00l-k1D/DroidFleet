package com.droidfleet.agent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.provider.Settings
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class AgentService : Service() {
    private val executor = Executors.newSingleThreadExecutor()
    private var running = true
    private val deviceId by lazy {
        "android-" + Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID)
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(1001, notification("Connecting to DroidFleet"))
        executor.execute { loop() }
    }

    private fun loop() {
        while (running) {
            try {
                post(BuildConfig.FLEET_SERVER_URL, heartbeat())
                val commandUrl = BuildConfig.FLEET_SERVER_URL
                    .removeSuffix("/heartbeat") + "/poll?device_id=" + deviceId
                val response = get(commandUrl)
                val command = response.optJSONObject("command")
                if (command != null) {
                    val result = JSONObject()
                        .put("device_id", deviceId)
                        .put("command_id", command.optString("command_id"))
                        .put("command", command.optString("command"))
                        .put("error", "Android APK agent does not support this command")
                    post(BuildConfig.FLEET_SERVER_URL.removeSuffix("/heartbeat") + "/result", result)
                }
            } catch (_: Exception) {
                // The next heartbeat retries after a short backoff.
            }
            Thread.sleep(10_000)
        }
    }

    private fun heartbeat() = JSONObject()
        .put("device_id", deviceId)
        .put("hostname", android.os.Build.MODEL)
        .put("windows_version", "Android " + android.os.Build.VERSION.RELEASE)
        .put("ip", "android")
        .put("status", "ONLINE")
        .put("capabilities", listOf("STATUS"))

    private fun post(url: String, payload: JSONObject) {
        request(url, "POST", payload.toString())
    }

    private fun get(url: String): JSONObject {
        return JSONObject(request(url, "GET", null))
    }

    private fun request(url: String, method: String, body: String?): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = method
        connection.connectTimeout = 5000
        connection.readTimeout = 5000
        connection.setRequestProperty("Content-Type", "application/json")
        if (body != null) {
            connection.doOutput = true
            connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        }
        return connection.inputStream.bufferedReader().use { it.readText() }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel("agent", "DroidFleet Agent", NotificationManager.IMPORTANCE_LOW)
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun notification(text: String): Notification =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, "agent").setContentTitle("DroidFleet Agent").setContentText(text)
                .setSmallIcon(android.R.drawable.stat_notify_sync).build()
        } else {
            Notification.Builder(this).setContentTitle("DroidFleet Agent").setContentText(text)
                .setSmallIcon(android.R.drawable.stat_notify_sync).build()
        }

    override fun onDestroy() {
        running = false
        executor.shutdownNow()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
