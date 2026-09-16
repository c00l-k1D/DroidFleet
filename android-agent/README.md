# DroidFleet Android Agent

This is a separate Android APK client. It does not use ngrok itself: the
preconfigured URL is compiled into `BuildConfig.FLEET_SERVER_URL`, and the
phone sends heartbeats directly to that endpoint.

Set the server before building by changing the `buildConfigField` value in
`app/build.gradle.kts`, for example:

```kotlin
buildConfigField("String", "FLEET_SERVER_URL",
    "\"https://example.ngrok-free.app/api/agent/heartbeat\"")
```

Build with Android Studio or Gradle:

```powershell
.\gradlew.bat :app:assembleDebug
```

The APK is created at `app/build/outputs/apk/debug/app-debug.apk`.
