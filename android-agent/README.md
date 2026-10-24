# DroidFleet Android Agent

This is a separate Android APK client. It sends heartbeats directly to the
preconfigured `BuildConfig.FLEET_SERVER_URL` endpoint without replacing the
desktop ADB flow.

Set the server before building by changing the `buildConfigField` value in
`app/build.gradle.kts`, for example:

```kotlin
buildConfigField("String", "FLEET_SERVER_URL",
    "\"https://server.example/api/agent/heartbeat\"")
```

Build with Android Studio or Gradle:

```powershell
.\gradlew.bat :app:assembleDebug
```

The APK is created at `app/build/outputs/apk/debug/app-debug.apk`.
