$ErrorActionPreference = "Stop"

$platformTools = Join-Path $PSScriptRoot "platform-tools"
$adb = Join-Path $platformTools "adb.exe"
if (-not (Test-Path $adb)) {
    $archive = Join-Path $env:TEMP "platform-tools-latest.zip"
    Write-Host "Downloading Android Platform Tools..."
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $archive
    if (Test-Path $platformTools) { Remove-Item $platformTools -Recurse -Force }
    Expand-Archive -Path $archive -DestinationPath $PSScriptRoot -Force
    Remove-Item $archive -Force
}
if (-not (Test-Path $adb)) { throw "adb.exe was not found in platform-tools" }

py -3 -m pip install pyinstaller psutil pyngrok Pillow PyAutoGUI
py -3 -m PyInstaller --noconfirm --clean --onefile --name FarmAgent `
    --add-binary "$platformTools\adb.exe;platform-tools" `
    --add-binary "$platformTools\AdbWinApi.dll;platform-tools" `
    --add-binary "$platformTools\AdbWinUsbApi.dll;platform-tools" `
    agent/agent.py
Write-Host "Built dist/FarmAgent.exe"
