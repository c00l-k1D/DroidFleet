import subprocess

from app import config


class ScrcpyStream:
    def __init__(self, executable: str | None):
        self.executable = executable
        self.process = None

    @staticmethod
    def find(executable_dir=None):
        import shutil
        from pathlib import Path
        if config.SCRCPY_PATH and Path(config.SCRCPY_PATH).exists():
            return config.SCRCPY_PATH
        found = shutil.which("scrcpy")
        if found:
            return found
        candidates = [Path(r"C:\scrcpy\scrcpy.exe"), Path(r"C:\Program Files\scrcpy\scrcpy.exe"), Path(r"C:\Program Files (x86)\scrcpy\scrcpy.exe"), Path.home() / "Downloads/scrcpy/scrcpy.exe"]
        if executable_dir:
            candidates.append(Path(executable_dir) / "scrcpy.exe")
        candidates.extend(path / "scrcpy.exe" for path in config.TOOLS_DIRS)
        return next((str(p) for p in candidates if p.exists()), None)

    def start(self, serial):
        if not self.executable:
            raise RuntimeError("scrcpy.exe не найден.\n\nДобавь папку scrcpy в PATH.")
        self.stop()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen([self.executable, "-s", serial, "--video-codec=h264", "--max-fps", "60", "--max-size", "1920", "--video-bit-rate", "16M", "--no-audio", "--stay-awake", "--window-title", "Android - " + serial], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)

    def stop(self):
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass
            self.process = None
