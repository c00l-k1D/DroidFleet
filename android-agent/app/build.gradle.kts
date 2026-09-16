plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.droidfleet.agent"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.droidfleet.agent"
        minSdk = 26
        targetSdk = 35
        versionCode = 30
        versionName = "0.3.0"
        val fleetServerUrl = project.findProperty("fleetServerUrl") as String?
            ?: "http://10.0.2.2:8765/api/agent/heartbeat"
        buildConfigField("String", "FLEET_SERVER_URL", "\"$fleetServerUrl\"")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
}
