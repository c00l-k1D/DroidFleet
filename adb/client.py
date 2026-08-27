import os
import shutil
import subprocess
from pathlib import Path

from .device import HardwareInfo, parse_battery, parse_getprop, parse_screen


class AdbClient:
    def __init__(self, executable: str | None = None):
        self.executable = executable or self.find_adb()

    @staticmethod
    def find_adb() -> str | None:
        found = shutil.which("adb")
        if found:
            return found
        candidates = [
            Path(r"C:\platform-tools\adb.exe"),
            Path(r"C:\Android\platform-tools\adb.exe"),
            Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe",
            Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools/adb.exe",
            Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools/adb.exe",
            Path(__file__).resolve().parents[2] / "platform-tools/adb.exe",
        ]
        return next((str(path) for path in candidates if path.exists()), None)

    def run(self, args: list[str], serial: str | None = None, timeout: int = 5):
        if not self.executable:
            raise RuntimeError("ADB не найден.")
        command = [self.executable]
        if serial:
            command += ["-s", serial]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(command + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, creationflags=flags)

    def devices(self) -> list[str]:
        result = self.run(["devices"])
        if result.returncode != 0:
            return []
        devices = []
        for line in result.stdout.decode(errors="replace").splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def reconnect(self, serial: str):
        return self.run(["reconnect", serial], timeout=5)

    def hardware_info(self, serial: str) -> HardwareInfo:
        properties_result = self.run(["shell", "getprop"], serial, timeout=5)
        battery_result = self.run(["shell", "dumpsys", "battery"], serial, timeout=5)
        screen_result = self.run(["shell", "wm", "size"], serial, timeout=5)
        properties = parse_getprop(properties_result.stdout.decode(errors="replace"))
        battery, temperature = parse_battery(battery_result.stdout.decode(errors="replace"))
        screen = parse_screen(screen_result.stdout.decode(errors="replace"))
        manufacturer = properties.get("ro.product.manufacturer") or properties.get("ro.product.vendor.manufacturer", "--")
        model = properties.get("ro.product.model") or properties.get("ro.product.vendor.model", "--")
        android = properties.get("ro.build.version.release") or properties.get("ro.build.version.sdk", "--")
        return HardwareInfo(manufacturer=manufacturer, model=model, screen=screen, battery=battery, temperature=temperature, android_version=android)
