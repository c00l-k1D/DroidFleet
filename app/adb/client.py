import os
import shutil
import subprocess
from pathlib import Path

from app import config
from .device import HardwareInfo, parse_battery, parse_getprop, parse_ip, parse_ram, parse_screen, parse_storage


class AdbClient:
    def __init__(self, executable: str | None = None):
        self.executable = executable or self.find_adb()

    @staticmethod
    def find_adb() -> str | None:
        if config.ADB_PATH and Path(config.ADB_PATH).exists():
            return config.ADB_PATH
        executable = "adb.exe" if os.name == "nt" else "adb"
        candidates = [
            Path(r"C:\platform-tools") / executable,
            Path(r"C:\Android\platform-tools") / executable,
            Path.home() / "AppData/Local/Android/Sdk/platform-tools" / executable,
            Path(os.environ.get("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools" / executable,
            Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools" / executable,
            Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools" / executable,
            Path(__file__).resolve().parents[2] / "platform-tools" / executable,
            Path("/opt/android-sdk/platform-tools") / executable,
            Path("/usr/local/android-sdk/platform-tools") / executable,
        ]
        bundled = next((path for path in candidates if path.exists()), None)
        if bundled:
            return str(bundled)
        found = shutil.which(executable)
        if found:
            return found
        candidates.extend(path / executable for path in config.TOOLS_DIRS)
        return next((str(path) for path in candidates if path.exists()), None)

    def run(self, args: list[str], serial: str | None = None, timeout: int = 5):
        if not self.executable:
            raise RuntimeError("ADB не найден.")
        command = [self.executable]
        if serial:
            command += ["-s", serial]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        environment = os.environ.copy()
        environment["ADB_SERVER_PORT"] = str(config.ADB_SERVER_PORT)
        try:
            return subprocess.run(
                command + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                creationflags=flags,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ADB command timed out after {timeout}s: {' '.join(command + args)}") from exc

    def devices(self) -> list[str]:
        return [serial for serial, state in self.device_states() if state == "device"]

    def device_states(self) -> list[tuple[str, str]]:
        try:
            result = self.run(["devices"])
        except RuntimeError:
            raise
        if result.returncode != 0:
            error = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"ADB devices failed: {error or 'unknown error'}")
        devices = []
        for line in result.stdout.decode(errors="replace").splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0] != "List":
                devices.append((parts[0], parts[1]))
        return devices

    def reconnect(self, serial: str):
        # `adb reconnect` accepts only an optional transport selector, not a
        # device serial. The daemon reconnects all eligible transports.
        return self.run(["reconnect"], timeout=5)

    def disconnect(self, serial: str):
        return self.run(["disconnect", serial], timeout=5)

    def hardware_info(self, serial: str) -> HardwareInfo:
        properties_result = self.run(["shell", "getprop"], serial, timeout=5)
        battery_result = self.run(["shell", "dumpsys", "battery"], serial, timeout=5)
        screen_result = self.run(["shell", "wm", "size"], serial, timeout=5)
        network_result = self.run(["shell", "ip", "route"], serial, timeout=5)
        memory_result = self.run(["shell", "cat", "/proc/meminfo"], serial, timeout=5)
        storage_result = self.run(["shell", "df", "-h", "/data"], serial, timeout=5)
        properties = parse_getprop(properties_result.stdout.decode(errors="replace"))
        battery, temperature = parse_battery(battery_result.stdout.decode(errors="replace"))
        screen = parse_screen(screen_result.stdout.decode(errors="replace"))
        manufacturer = properties.get("ro.product.manufacturer") or properties.get("ro.product.vendor.manufacturer", "--")
        model = properties.get("ro.product.model") or properties.get("ro.product.vendor.model", "--")
        android = properties.get("ro.build.version.release") or properties.get("ro.build.version.sdk", "--")
        sdk = properties.get("ro.build.version.sdk", "--")
        cpu = properties.get("ro.soc.model") or properties.get("ro.product.board") or properties.get("ro.product.cpu.abi", "--")
        return HardwareInfo(
            manufacturer=manufacturer,
            model=model,
            screen=screen,
            battery=battery,
            temperature=temperature,
            android_version=android,
            sdk=sdk,
            cpu=cpu,
            ram=parse_ram(memory_result.stdout.decode(errors="replace")),
            storage=parse_storage(storage_result.stdout.decode(errors="replace")),
            ip=parse_ip(network_result.stdout.decode(errors="replace")),
        )

    def get_device_resolution(self, serial: str) -> tuple[int, int]:
        """Get device screen resolution (width, height) in pixels."""
        try:
            result = self.run(["shell", "wm", "size"], serial, timeout=3)
            output = result.stdout.decode(errors="replace").strip()
            for line in output.splitlines():
                if "Physical size:" in line or "Override size:" in line:
                    parts = line.split(":")[-1].strip().split("x")
                    if len(parts) == 2:
                        return (int(parts[0]), int(parts[1]))
                elif line.strip() and "x" in line:
                    parts = line.strip().split("x")
                    if len(parts) == 2:
                        try:
                            return (int(parts[0]), int(parts[1]))
                        except ValueError:
                            pass
        except Exception:
            pass
        return (1080, 1920)  # Default fallback
