import subprocess
import ctypes
import os
import time
from ctypes import wintypes

from app import config


class ScrcpyStream:
    def __init__(self, executable: str | None, adb_executable: str | None = None):
        self.executable = executable
        self.adb_executable = adb_executable
        self.process = None
        self.window_handle = None

    @staticmethod
    def find(executable_dir=None):
        import shutil
        from pathlib import Path
        if config.SCRCPY_PATH and Path(config.SCRCPY_PATH).exists():
            return config.SCRCPY_PATH
        found = shutil.which("scrcpy")
        if found:
            return found
        candidates = [
            Path(r"C:\scrcpy\scrcpy.exe"),
            Path(r"C:\Program Files\scrcpy\scrcpy.exe"),
            Path(r"C:\Program Files (x86)\scrcpy\scrcpy.exe"),
            Path.home() / "Downloads/scrcpy/scrcpy.exe",
            Path("/usr/bin/scrcpy"),
            Path("/usr/local/bin/scrcpy"),
        ]
        if executable_dir:
            candidates.append(Path(executable_dir) / "scrcpy.exe")
        candidates.extend(path / "scrcpy.exe" for path in config.TOOLS_DIRS)
        return next((str(p) for p in candidates if p.exists()), None)

    def start(self, serial):
        if not self.executable:
            raise RuntimeError("scrcpy не найден. Добавьте scrcpy в PATH.")
        self.stop()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = [
            self.executable, "-s", serial,
            "--video-codec=h264", "--max-fps", "60", "--max-size", "1280",
            "--window-width", "480", "--window-height", "800",
            "--window-x", "0", "--window-y", "0",
            "--video-bit-rate", "16M", "--no-audio", "--stay-awake",
            "--window-title", "Android - " + serial,
        ]
        environment = os.environ.copy()
        environment["ADB_SERVER_PORT"] = str(config.ADB_SERVER_PORT)
        self._set_adb_environment(environment)
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            env=environment,
        )

    def start_embedded(self, serial):
        if not self.executable:
            raise RuntimeError("scrcpy не найден. Добавьте scrcpy в PATH.")
        self.stop()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = [
            self.executable, "-s", serial,
            "--video-codec=h264", "--max-fps", "60", "--max-size", "1280",
            "--window-width", "900", "--window-height", "700",
            "--video-bit-rate", "16M", "--no-audio", "--stay-awake",
            "--window-title", "DroidFleet scrcpy - " + serial,
        ]
        environment = os.environ.copy()
        environment["ADB_SERVER_PORT"] = str(config.ADB_SERVER_PORT)
        self._set_adb_environment(environment)
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=flags,
            env=environment,
        )
        return self.process

    def _set_adb_environment(self, environment: dict[str, str]) -> None:
        """Use the controller's ADB without relying on scrcpy's optional flags."""
        if not self.adb_executable:
            return
        from pathlib import Path

        adb_dir = str(Path(self.adb_executable).resolve().parent)
        current_path = environment.get("PATH", "")
        if adb_dir not in current_path.split(os.pathsep):
            environment["PATH"] = adb_dir + os.pathsep + current_path

    def embed(self, parent_handle, title, timeout=5.0):
        if not self.process:
            raise RuntimeError("scrcpy не запущен")
        if not hasattr(ctypes, "windll"):
            raise RuntimeError("Встраивание scrcpy поддерживается только в Windows")

        user32 = ctypes.windll.user32
        deadline = time.monotonic() + timeout
        window_handle = None

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def find_window(handle, _):
            nonlocal window_handle
            length = user32.GetWindowTextLengthW(handle)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, buffer, length + 1)
            if title.casefold() in buffer.value.casefold() and user32.IsWindowVisible(handle):
                window_handle = handle
                return False
            return True

        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stderr = ""
                if self.process.stderr:
                    stderr = self.process.stderr.read().strip()
                details = stderr[-1000:] if stderr else "scrcpy не вернул подробности"
                raise RuntimeError(f"scrcpy завершился до встраивания окна: {details}")
            user32.EnumWindows(find_window, 0)
            if window_handle:
                break
            time.sleep(0.05)
        if not window_handle:
            raise RuntimeError("Окно scrcpy не найдено")

        GWL_STYLE = -16
        WS_CHILD = 0x40000000
        WS_VISIBLE = 0x10000000
        WS_CLIPSIBLINGS = 0x04000000
        WS_POPUP = 0x80000000
        style = user32.GetWindowLongW(window_handle, GWL_STYLE)
        user32.SetWindowLongW(
            window_handle,
            GWL_STYLE,
            (style | WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS) & ~WS_POPUP,
        )
        user32.SetParent(window_handle, parent_handle)
        self.window_handle = window_handle
        user32.ShowWindow(window_handle, 5)
        self.resize_embedded(parent_handle)
        return window_handle

    def resize_embedded(self, parent_handle):
        if not self.window_handle or not hasattr(ctypes, "windll"):
            return
        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        if user32.GetClientRect(parent_handle, ctypes.byref(rect)):
            user32.MoveWindow(
                self.window_handle,
                0,
                0,
                max(1, rect.right - rect.left),
                max(1, rect.bottom - rect.top),
                True,
            )
            user32.SetWindowPos(
                self.window_handle,
                0,
                0,
                0,
                max(1, rect.right - rect.left),
                max(1, rect.bottom - rect.top),
                0x0040,
            )

    def stop(self):
        self.window_handle = None
        if self.process:
            try:
                self.process.terminate()
                self.process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass
            self.process = None
