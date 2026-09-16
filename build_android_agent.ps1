param(
    [string]$ServerUrl = ""
)

$project = Join-Path $PSScriptRoot "android-agent"
Push-Location $project
try {
    $gradle = if (Test-Path ".\gradlew.bat") { ".\gradlew.bat" } else { (Get-Command gradle -ErrorAction Stop).Source }
    $properties = if ($ServerUrl) { @("-PfleetServerUrl=$ServerUrl") } else { @() }
    & $gradle @properties :app:assembleRelease
    if ($LASTEXITCODE -ne 0) {
        throw "Android APK build failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
