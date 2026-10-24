# DroidFleet — device fleet orchestration platform

[Русская версия](README.md) · **English version**

DroidFleet is a cross-platform device-fleet orchestration platform. The main
GUI runs on Windows while the control plane is designed for HTTPS/self-hosted
operation without a permanent public tunnel.

The platform supports connections to PC systems as well as Android devices and
FarmAgent nodes. This allows the same orchestration model to manage desktop
hosts, mobile devices, and remote worker systems in one control plane.

The project targets Python 3.13 and stores sensitive imported account data in
`data/accounts.enc` rather than in exposed JSON files. The historical name
`AndroidController` remains for compatibility, but the class is the shared UI
controller for both Android and Windows workflows.

## Core capabilities

- Android and PC system discovery and status monitoring.
- Device cards with hardware, battery, ADB/IP, and OS details.
- Embedded scrcpy preview inside the main window.
- Batch actions: screenshot, reboot, reconnect, install/uninstall APK, and allowlisted shell operations.
- Full logcat view with filtering, buffer clearing, and export.
- Windows/Linux FarmAgent heartbeat, screenshots, logs, local process control, and file transfer.
- Separate Android APK agent with a predefined server endpoint.
- Secure-by-default transport: HTTPS-only for remote `SERVER_URL`, loopback only with explicit opt-in.
- Encrypted-at-rest account storage in `data/accounts.enc`.

## Architecture

- GUI: primary DroidFleet interface on Windows.
- Android transport: `adb` via `AdbClient` and `DeviceMonitor`.
- PC systems: host connection and monitoring through the local and network control layer.
- Windows/Linux FarmAgent: heartbeat and commands over HTTPS/self-host endpoints.
- Accounts: `app/accounts/repository.py` stores imported records in encrypted-at-rest storage.
- Device/task runtime state is kept in the project's local registry layer; sensitive secrets are never written in plain text.
- Logs/screenshots: `data/logs` and `data/screenshots` for user-visible artifacts and audit trails.

## Supported platforms

| Component | Windows | Linux/macOS |
|---|---|---|
| Python runtime | Supported | Supported |
| DroidFleet GUI | Primary platform | Not the main production target |
| Android ADB | Supported | Supported |
| Embedded scrcpy | Supported | Not supported |
| FarmAgent input and screenshots | Full Windows implementation | Supported with a desktop session |

## Installation

Requirements: Windows 10/11 and Python 3.13.

1. Install Python 3.13 from <https://www.python.org/downloads/>.
2. Install Android Platform Tools and ensure `adb.exe` is available on `PATH`.

   ```powershell
   $env:DROIDFLEET_ADB = "C:\tools\platform-tools\adb.exe"
   ```

3. Install the package in editable mode:

   ```powershell
   py -3.13 -m pip install -e .
   ```

4. Start the GUI:

   ```powershell
   py -3.13 farm_bot.py
   ```

   Or:

   ```powershell
   py -3.13 -m app.main
   ```

## Connection policy

The production profile only accepts HTTPS server URLs. Loopback access is allowed only when explicitly enabled:

```powershell
$env:DROIDFLEET_SERVER = "https://server.example/api/agent/heartbeat"
$env:DROIDFLEET_ALLOW_INSECURE_LOOPBACK = "true"  # localhost/debug only
```

Supported default transport modes are:

- `self-host` over a protected internal network;
- `external server` with an HTTPS endpoint;
- `localhost` only for local debug and only under explicit permission.

## FarmAgent

The DroidFleet server listens on port `8765`.

```powershell
$env:DROIDFLEET_SERVER = "https://server.example/api/agent/heartbeat"
py -3.13 agent/agent.py
```

Build a standalone Windows agent:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_agent.ps1
```

The output is written to `dist/FarmAgent.exe`.

### Linux FarmAgent

On Linux, install Python 3.13 and `adb` when Android discovery is required, then run:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv
chmod +x build_agent.sh
DROIDFLEET_SERVER="https://your-server.example/api/agent/heartbeat" \
  ./build_agent.sh
```

The resulting binary is `dist/FarmAgent-linux`.

## Android APK farm agent

The separate Android client in [android-agent/](android-agent/) sends heartbeats directly to a configured endpoint and does not replace the desktop ADB flow.

Before building, set the server URL in `android-agent/app/build.gradle.kts`:

```kotlin
buildConfigField("String", "FLEET_SERVER_URL",
    "\"https://your-server.example/api/agent/heartbeat\"")
```

Then build:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_android_agent.ps1 `
  -ServerUrl "https://your-server.example/api/agent/heartbeat"
```

## Security and storage

The project follows production-safe defaults:

- HTTPS-only remote endpoints.
- Loopback only with explicit opt-in.
- Token hashing before persistence.
- Encrypted-at-rest account secrets in `data/accounts.enc`.
- Safe file transfer path and size limits.
- Redaction of secret-bearing values in logs.

## Data and logs

- Accounts: `data/accounts.enc`
- Runtime registry and task state: project data directory with no plaintext secrets stored on disk
- GUI logs: `data/logs`
- Screenshots: `data/screenshots`
- FarmAgent log: `%PROGRAMDATA%\DroidFleet\agent.log`

Do not delete the `data` directory if you want to preserve devices, names, groups, accounts, and tasks.

## CLI examples

```powershell
py -3.13 -m app.cli --help
```

See [docs/production_security.md](docs/production_security.md) for the hardening checklist.

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

Current project version: `0.3.2` (alpha). Unit tests and compilation pass, but
a dedicated 5–10 device load test and a long-running soak test are still
required before a `1.0` release.

## License

MIT. See [LICENSE](LICENSE).
