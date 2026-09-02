import os
from pathlib import Path

PREVIEW_FPS = 4
PREVIEW_INTERVAL = 1.0 / PREVIEW_FPS
PREVIEW_WIDTH = 180
PREVIEW_HEIGHT = 300
PREVIEW_WORKERS = 8
COMMAND_WORKERS = 12
DEVICE_CHECK_INTERVAL = 1000
HARDWARE_REFRESH_INTERVAL = 15
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
DEVICES_FILE = DATA_DIR / "devices.json"
LANGUAGE = os.environ.get("DROIDFLEET_LANGUAGE", "Русский")
ADB_PATH = os.environ.get("DROIDFLEET_ADB")
SCRCPY_PATH = os.environ.get("DROIDFLEET_SCRCPY")
AGENT_SERVER_HOST = os.environ.get("DROIDFLEET_AGENT_HOST", "0.0.0.0")
AGENT_SERVER_PORT = int(os.environ.get("DROIDFLEET_AGENT_PORT", "8765"))
AGENT_STALE_AFTER = int(os.environ.get("DROIDFLEET_AGENT_STALE", "30"))
AGENT_SCREENSHOT_FPS = max(1, min(10, int(os.environ.get("DROIDFLEET_SCREENSHOT_FPS", "2"))))
TOOLS_DIRS = tuple(
	Path(item) for item in os.environ.get("DROIDFLEET_TOOLS", "").split(os.pathsep) if item
)
