# DroidFleet — device fleet orchestration platform

[Русская версия](README.md) · **English version**

DroidFleet is a device-fleet management and orchestration platform. The main
GUI runs on Windows and manages Android devices through ADB and Windows
computers through FarmAgent. The FarmAgent protocol and server are independent
of Android and can be used over a LAN, ngrok, or an external server.

The main controller still has the historical class name `AndroidController`;
in practice it is the shared UI controller and orchestrator for both Android
and Windows targets.

## Features

- Automatic Android discovery for `device`, `offline`, and `unauthorized`
  states.
- Persistent Android device cards, groups, tags, filters, and search.
- Android hardware information: model, Android version, SDK, RAM, storage,
  battery, temperature, resolution, IP address, and status.
- Embedded scrcpy preview with mouse and keyboard control.
- Batch screenshots, reboot, reconnect, shell commands, APK installation,
  launch, stop, uninstall, and application data cleanup.
- Full logcat viewer with filtering, buffer clearing, refresh, and export.
- Worker pools and persistent task storage in `data/tasks.json`.
- Windows FarmAgent heartbeat, live view, remote access, screenshots, logs,
  process control, remote update, and file transfer.
- FarmAgent RTT ping shown in Windows cards.
- FarmAgent logs written to `%PROGRAMDATA%\DroidFleet\agent.log` with rotation.
- FarmAgent EXE includes Android Platform Tools and reports Android devices
  connected to the managed Windows computer.
- Separate Android FarmAgent APK with a predefined server endpoint.
- Connection modes: `self-host`, `ngrok`, and `external server`.
- Android ADB transport is separate from FarmAgent networking:
  `auto`, `USB`, and `Wi-Fi ADB`.

## Platform support

| Component | Windows | Linux/macOS |
|---|---:|---:|
| Python package and FarmAgent protocol | Supported | Supported |
| DroidFleet GUI | Primary platform | Not production-tested |
| Android ADB modules and CLI | Supported with `adb` | Supported with `adb` |
| Embedded scrcpy window | Supported | Not supported |
| FarmAgent input and screenshots | Full Windows implementation | Supported when a desktop session is available |

Linux FarmAgent can run as a Python process or systemd service, uses `adb` from
`PATH`, and reports `Linux` in the host card. Screenshot/input operations on
Linux require an available desktop session (`DISPLAY` or a Wayland-compatible
environment).

## Installation

Requirements: Windows 10/11 and Python 3.10 or newer.

1. Install Python from <https://www.python.org/downloads/>.
2. Install Android Platform Tools and make sure `adb.exe` is available on
   `PATH`, or configure it:

   ```powershell
   $env:DROIDFLEET_ADB = "C:\tools\platform-tools\adb.exe"
   ```

3. Open the project directory and install it in editable mode:

   ```powershell
   py -3 -m pip install -e .
   ```

4. Start the GUI:

   ```powershell
   py -3 farm_bot.py
   ```

   Alternative:

   ```powershell
   py -3 -m app.main
   ```

## Android and ADB

Enable USB debugging on the Android device and accept the RSA prompt.

```bash
adb devices
```

The device should be in the `device` state. For wireless ADB, use the standard
`adb tcpip` and `adb connect` commands. The Android transport setting can be
configured globally and separately for each device.

Android ADB does not use ngrok. The `NGROK` label applies only to FarmAgent
cards. DroidFleet and scrcpy use the same discovered ADB binary, preventing
stalls caused by competing ADB servers. DroidFleet uses isolated ADB port
`5038` by default instead of the shared `5037`; configure it with
`DROIDFLEET_ADB_SERVER_PORT`.

## FarmAgent

The DroidFleet server listens on port `8765`. To start an agent manually:

```powershell
$env:DROIDFLEET_SERVER = "http://SERVER_IP:8765/api/agent/heartbeat"
py -3 agent/agent.py
```

Build a standalone Windows agent:

```powershell
powershell -ExecutionPolicy Bypass -File build_agent.ps1
```

The result is `dist/FarmAgent.exe`. The build script downloads the official
Windows Platform Tools when needed and embeds `adb.exe`, `AdbWinApi.dll`, and
`AdbWinUsbApi.dll` into the executable. In restricted networks, place the
Platform Tools archive contents in the local `platform-tools` directory first.

The managed Windows computer can therefore report its connected Android
devices to the DroidFleet host. Replace the old executable on that computer
with the newly built `FarmAgent.exe`.

### Linux FarmAgent

On Linux, install Python 3.10+, `adb` (when Android discovery is needed), and
run:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv
chmod +x build_agent.sh
DROIDFLEET_SERVER="https://your-server.example/api/agent/heartbeat" \
  ./build_agent.sh
```

The result is `dist/FarmAgent-linux`. Copy it to the Linux computer and run:

```bash
chmod +x FarmAgent-linux
DROIDFLEET_SERVER="https://your-server.example/api/agent/heartbeat" \
  ./FarmAgent-linux
```

The Linux agent uses a stable `linux-*` identity and stores state under
`~/.local/state/droidfleet`. It can run directly or as a systemd service. The
GUI also provides a “Build Linux FarmAgent” button when Bash/WSL is available.

Process paths are configured with:

- `DROIDFLEET_ROBLOX`
- `DROIDFLEET_PYTHON_BOT`
- `DROIDFLEET_FARM_WORKER`

FarmAgent does not execute arbitrary commands received from the network.

### File transfer

Use the `SEND FILE` action in the Windows FarmAgent view to select a local file
and a destination path on the managed PC. Files are transferred through the
current self-host/ngrok/external-server channel, verified with SHA-256, and
limited to 50 MB. An empty destination uses the remote user's `Downloads`
directory.

### Remote update

The `UPDATE` action downloads the new EXE, verifies its SHA-256 checksum,
replaces the running executable through a temporary launcher, and restarts the
agent. If `FarmAgent-start.cmd` is not published, the agent creates a launcher
locally.

### Network errors

`SSL: UNEXPECTED_EOF_WHILE_READING` indicates a temporary TLS/ngrok tunnel
disconnect before an HTTP response, not an Android ADB failure. FarmAgent
retries with exponential backoff and creates a fresh TLS context for each
attempt. The endpoint can be checked with:

```text
https://your-ngrok-host.example/api/agent/config
```

Multiple FarmAgent instances can use the same ngrok endpoint. Command polling
defaults to one request per second with a small random jitter so agents do not
create a synchronized request burst. Override it with
`DROIDFLEET_COMMAND_POLL` if needed.

## Android FarmAgent APK

The separate native Android client does not use ADB or replace the desktop
Android controller. It sends heartbeat and status polling requests directly to
the configured server.

Build it with:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_android_agent.ps1 `
  -ServerUrl "https://your-server.example/api/agent/heartbeat"
```

The APK is generated at:

`android-agent/app/build/outputs/apk/release/app-release.apk`

## Data and logs

- Devices: `data/devices.json`
- Tasks: `data/tasks.json`
- Accounts: `data/accounts.json`
- GUI logs: `data/logs`
- Screenshots: `data/screenshots`
- FarmAgent log: `%PROGRAMDATA%\DroidFleet\agent.log`

Do not delete the `data` directory if you want to preserve devices, names,
groups, accounts, and tasks.

## CLI examples

After installing the project in editable mode:

```powershell
droidfleet devices
droidfleet info --all
droidfleet screenshot --all --output data/screenshots
droidfleet reconnect --group samsung
droidfleet reboot --group samsung
```

## Validation

```powershell
py -3 -m pytest -q
py -3 -m compileall -q app agent tests
```

Current project version: `0.3.0` (alpha). Unit tests and compilation pass, but
a dedicated 5–10 device load test and a long-running soak test are still
required before a `1.0` release.

## License

MIT. See [LICENSE](LICENSE).
