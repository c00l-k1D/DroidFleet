# DroidFleet

Android device manager for working with multiple devices connected over USB.

DroidFleet uses **ADB** to detect connected Android devices and provides a single interface for monitoring and controlling them. The main idea is simple: instead of opening a separate window for every phone, all connected devices are displayed in one grid.

The project is currently in **v0.1**.

---

## Current version

### v0.1

#### Implemented

* ADB device discovery
* Device grid
* Live screen previews
* Online / offline device status
* Multiple device selection
* Batch commands
* scrcpy integration

#### Planned

* Device details
* Battery status
* Temperature monitoring
* Centralized logs
* APK installation
* Screenshot management

---

## What it looks like

The main window contains a grid of connected devices.

Each device is represented by a card containing its current status and screen preview.

Example:

```text
┌─────────────────────────────────────────────────────────────┐
│ DroidFleet                              12 devices / 11 online│
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ ● ONLINE     │ │ ● ONLINE     │ │ ● OFFLINE    │        │
│  │              │ │              │ │              │        │
│  │    SCREEN    │ │    SCREEN    │ │    SCREEN    │        │
│  │    PREVIEW   │ │    PREVIEW   │ │              │        │
│  │              │ │              │ │              │        │
│  │  Samsung     │ │  Xiaomi      │ │  Pixel       │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐                          │
│  │ ● ONLINE     │ │ ● ONLINE     │                          │
│  │    SCREEN    │ │    SCREEN    │                          │
│  └──────────────┘ └──────────────┘                          │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ HOME │ BACK │ REBOOT │ BATCH │ SCRCPY │ ADB                │
└─────────────────────────────────────────────────────────────┘
```

The exact interface is still being developed.

---

## Why

ADB works well when managing one or a few devices, but working with a larger number of physical devices becomes inconvenient very quickly.

Opening separate tools and windows for every device makes it difficult to see which devices are connected, which ones stopped responding and which device you are currently working with.

DroidFleet puts the devices into one workspace.

For example:

```text
PC
│
├── Device 01  ●
├── Device 02  ●
├── Device 03  ●
├── Device 04  ●
├── Device 05  ○
├── Device 06  ●
└── ...
```

You can select several devices and send an action to all of them at once.

---

## Requirements

* Windows 10 / 11
* Python 3.11+
* Android SDK Platform-Tools
* ADB
* USB drivers for the connected devices
* scrcpy for device control

Android devices must have **USB debugging** enabled.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/DroidFleet.git
cd DroidFleet
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Check ADB:

```bash
adb version
```

Then connect an Android device and run:

```bash
adb devices
```

You should see something similar to:

```text
List of devices attached
R58M123456    device
```

Run DroidFleet:

```bash
python -m app.main
```

---

## Android setup

USB debugging has to be enabled on every device.

On most Android devices:

```text
Settings
    ↓
About phone
    ↓
Build number
    ↓
Tap several times
    ↓
Developer options
    ↓
USB debugging
```

After connecting the device, Android will usually ask whether to allow USB debugging from the computer.

Accept the prompt.

Check the connection:

```bash
adb devices
```

If the device is shown as:

```text
unauthorized
```

unlock the phone and accept the authorization prompt.

If it is shown as:

```text
offline
```

try:

```bash
adb kill-server
adb start-server
adb devices
```

---

## Device states

DroidFleet uses the state reported by ADB rather than relying on the video preview to determine whether a device is connected.

For example:

```text
ONLINE
OFFLINE
UNAUTHORIZED
```

This is important because the screen preview and the actual ADB connection are two different things.

A device can have a failed preview while ADB is still completely functional.

---

## Multi-device control

Multiple devices can be selected from the grid.

For example:

```text
☑ Device 01
☑ Device 02
☑ Device 03
☐ Device 04
☐ Device 05
```

An action can then be executed on all selected devices.

Conceptually:

```text
Selected devices
       │
       ▼
 Batch Executor
       │
 ┌─────┼─────┐
 ▼     ▼     ▼
D01   D02   D03
```

The batch layer is responsible for executing commands independently for each device and collecting the results.

---

## ADB

DroidFleet uses ADB as the main communication layer.

Typical operations include:

```bash
adb devices
```

```bash
adb shell input tap 500 500
```

```bash
adb shell input keyevent KEYCODE_HOME
```

```bash
adb shell input swipe 500 1200 500 300 300
```

The application handles the device serial automatically when executing commands for a specific device.

---

## scrcpy

scrcpy is used for interactive device control and high-quality screen streaming.

It is useful when you need to work with a particular device rather than just monitor its preview in the grid.

For example:

```text
Device Grid
     │
     │ click device
     ▼
Selected Device
     │
     ▼
scrcpy
     │
     ▼
Full device control
```

scrcpy is developed by Genymobile and is licensed separately from DroidFleet.

See the `THIRD_PARTY_LICENSES` directory for third-party license information.

---

## Performance

The grid is intended primarily for monitoring.

It is not necessary to display every device at maximum resolution and FPS simultaneously.

The intended approach is:

```text
Many devices
    │
    ▼
Small low-FPS previews
    │
    ▼
Select a device
    │
    ▼
Full-quality interactive stream
```

This makes it possible to monitor a larger number of devices without wasting resources decoding and rendering unnecessary high-resolution video.

Actual limits depend heavily on the PC, USB controllers, hubs, Android devices and video backend.

---

## Project structure

The project is being separated into several components:

```text
DroidFleet/
│
├── app/
│   ├── adb/
│   │   ├── client.py
│   │   ├── device.py
│   │   ├── commands.py
│   │   └── monitor.py
│   │
│   ├── video/
│   │   ├── preview.py
│   │   ├── stream.py
│   │   └── decoder.py
│   │
│   ├── ui/
│   │   ├── dashboard.py
│   │   ├── device_card.py
│   │   └── dialogs.py
│   │
│   ├── actions/
│   │   ├── batch.py
│   │   ├── input.py
│   │   └── apps.py
│   │
│   └── main.py
│
├── tests/
├── assets/
├── docs/
│
├── requirements.txt
├── pyproject.toml
├── README.md
└── LICENSE
```

The structure may change while the project is being developed.

---

## Roadmap

### v0.1

* [x] ADB discovery
* [x] Device grid
* [x] Screen preview
* [x] Online / offline status
* [x] Multi-select
* [x] Batch commands
* [x] scrcpy integration

### v0.2

* [ ] Device details
* [ ] Battery monitoring
* [ ] Temperature monitoring
* [ ] Logs
* [ ] APK installation
* [ ] Screenshot manager

### Later

* [ ] Device groups
* [ ] Search and filters
* [ ] Application management
* [ ] Improved preview performance
* [ ] Profiles / macros
* [ ] Operation queue
* [ ] Better error handling
* [ ] Linux support
* [ ] macOS support
* [ ] Remote device workers
* [ ] Web interface
* [ ] REST API

The roadmap is not a strict schedule and may change as the project develops.

---

## Contributing

Pull requests are welcome.

If you want to work on the project:

```bash
git clone https://github.com/YOUR_USERNAME/DroidFleet.git
cd DroidFleet
```

Create a branch:

```bash
git checkout -b feature/my-feature
```

Make your changes, test them and open a pull request.

For larger changes, it is better to open an issue first so the implementation can be discussed before spending time on it.

---

## Bug reports

If something does not work, include:

* Windows version
* Python version
* ADB version
* Android version
* device model
* relevant logs
* steps to reproduce the problem

Do not post:

* ADB private keys
* personal files
* passwords
* authentication tokens
* other sensitive information

---

## Security

DroidFleet is intended for devices that you own or are authorized to manage.

ADB provides significant control over an Android device. Because of this, DroidFleet should not be exposed directly to an untrusted network.

If remote management is added in the future, authentication, authorization and command restrictions will be required.

---

## Third-party software

DroidFleet relies on external software and libraries.

Current major dependencies include:

* Android SDK Platform-Tools / ADB
* scrcpy
* Python
* PySide6 / Qt or other UI dependencies used by the current build

Their licenses remain separate from the DroidFleet license.

Third-party notices are kept in:

```text
THIRD_PARTY_LICENSES/
```

---

## License

DroidFleet is released under the MIT License.

See [`LICENSE`](LICENSE).

---

## Status

DroidFleet is currently under active development.

The project is usable as a **v0.1 prototype**, but the architecture and UI may still change significantly before the first stable release.

If you find a bug or have an idea for the project, open an issue or pull request.

---

**DroidFleet**
One interface for a lot of Android devices.
