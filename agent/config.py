from __future__ import annotations

import os
from pathlib import Path

AGENT_VERSION = "0.1.0"
DEVICE_ID = os.environ.get("DROIDFLEET_DEVICE_ID")
SERVER_URL = os.environ.get("DROIDFLEET_SERVER", "http://127.0.0.1:8765/api/agent/heartbeat")
HEARTBEAT_INTERVAL = int(os.environ.get("DROIDFLEET_HEARTBEAT", "10"))
REQUEST_TIMEOUT = int(os.environ.get("DROIDFLEET_TIMEOUT", "5"))
SCREENSHOT_INTERVAL = int(os.environ.get("DROIDFLEET_SCREENSHOT_INTERVAL", "0"))
SCREENSHOT_QUALITY = int(os.environ.get("DROIDFLEET_SCREENSHOT_QUALITY", "70"))
CONFIG_DIR = Path(os.environ.get("PROGRAMDATA", Path.home())) / "DroidFleet"
STATE_FILE = CONFIG_DIR / "agent.json"
LOG_FILE = CONFIG_DIR / "agent.log"
