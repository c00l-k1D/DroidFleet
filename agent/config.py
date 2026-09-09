from __future__ import annotations

import os
import time
from pathlib import Path

AGENT_VERSION = "0.3.0"
DEVICE_ID = os.environ.get("DROIDFLEET_DEVICE_ID")
SERVER_URL = os.environ.get("DROIDFLEET_SERVER", "http://127.0.0.1:8765/api/agent/heartbeat")
HEARTBEAT_INTERVAL = int(os.environ.get("DROIDFLEET_HEARTBEAT", "10"))
COMMAND_POLL_INTERVAL = max(0.5, float(os.environ.get("DROIDFLEET_COMMAND_POLL", "1.0")))
REQUEST_TIMEOUT = int(os.environ.get("DROIDFLEET_TIMEOUT", "5"))
NETWORK_RETRIES = max(2, min(12, int(os.environ.get("DROIDFLEET_NETWORK_RETRIES", "8"))))
NETWORK_BACKOFF = max(0.2, min(30.0, float(os.environ.get("DROIDFLEET_NETWORK_BACKOFF", "1.0"))))
NETWORK_MAX_BACKOFF = max(15.0, min(600.0, float(os.environ.get("DROIDFLEET_NETWORK_MAX_BACKOFF", "120"))))
SCREENSHOT_INTERVAL = int(os.environ.get("DROIDFLEET_SCREENSHOT_INTERVAL", "0"))
SCREENSHOT_QUALITY = int(os.environ.get("DROIDFLEET_SCREENSHOT_QUALITY", "55"))
SCREENSHOT_MAX_WIDTH = int(os.environ.get("DROIDFLEET_SCREENSHOT_MAX_WIDTH", "1280"))
MAX_TRANSFER_BYTES = max(1, int(os.environ.get("DROIDFLEET_MAX_TRANSFER_MB", "50"))) * 1024 * 1024
STREAM_FPS = max(1, min(30, int(os.environ.get("DROIDFLEET_STREAM_FPS", "30"))))
PYAutoGUI_FAILSAFE = os.environ.get("DROIDFLEET_PYAUTOGUI_FAILSAFE", "0").casefold() in {"1", "true", "yes", "on"}
UPDATE_COMPLETED = False
LAST_PING_MS = None
STARTED_AT = time.time()
DEFAULT_PROCESS_DEFINITIONS = {
	"Roblox": {"match": "RobloxPlayerBeta.exe", "command": "DROIDFLEET_ROBLOX"},
	"Python Bot": {"match": "python", "command": "DROIDFLEET_PYTHON_BOT"},
	"Farm Worker": {"match": "farm_worker", "command": "DROIDFLEET_FARM_WORKER"},
}
if os.name == "nt":
    CONFIG_DIR = Path(os.environ.get("PROGRAMDATA", Path.home())) / "DroidFleet"
else:
    CONFIG_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "droidfleet"
STATE_FILE = CONFIG_DIR / "agent.json"
LOG_FILE = CONFIG_DIR / "agent.log"
