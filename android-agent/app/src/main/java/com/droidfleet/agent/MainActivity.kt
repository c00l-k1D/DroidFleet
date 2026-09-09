package com.droidfleet.agent

import android.content.Intent
import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val status = TextView(this).apply {
            text = "DroidFleet Android Agent\n\nServer:\n${BuildConfig.FLEET_SERVER_URL}\n\nАгент работает в фоне."
            textSize = 16f
            setPadding(32, 48, 32, 32)
        }
        setContentView(status)
        startForegroundService(Intent(this, AgentService::class.java))
    }
}
