import json
import os
from pathlib import Path
from app.connection import ConnectionMode, ConnectionProfile

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
TASKS_FILE = DATA_DIR / "tasks.json"
LANGUAGE = os.environ.get("DROIDFLEET_LANGUAGE", "Русский")
ADB_PATH = os.environ.get("DROIDFLEET_ADB")
ADB_SERVER_PORT = int(os.environ.get("DROIDFLEET_ADB_SERVER_PORT", "5038"))
SCRCPY_PATH = os.environ.get("DROIDFLEET_SCRCPY")
AGENT_SERVER_HOST = os.environ.get("DROIDFLEET_AGENT_HOST", "0.0.0.0")
AGENT_SERVER_PORT = int(os.environ.get("DROIDFLEET_AGENT_PORT", "8765"))
AGENT_STALE_AFTER = int(os.environ.get("DROIDFLEET_AGENT_STALE", "30"))
AGENT_SCREENSHOT_FPS = max(1, min(30, int(os.environ.get("DROIDFLEET_SCREENSHOT_FPS", "30"))))
CONNECTION_MODE = ConnectionProfile.from_value(os.environ.get("DROIDFLEET_CONNECTION_MODE", ConnectionMode.SELF_HOST.value)).config_value
ANDROID_CONNECTION_MODE = os.environ.get("DROIDFLEET_ANDROID_CONNECTION_MODE", "auto").casefold()
NGROK_AUTHTOKEN = os.environ.get("DROIDFLEET_NGROK_AUTHTOKEN", "")
NGROK_REGION = os.environ.get("DROIDFLEET_NGROK_REGION", "")
USER_CONFIG_FILE = Path(os.environ.get("DROIDFLEET_CONFIG", Path.home() / ".droidfleet" / "settings.json"))
PROCESS_DEFINITIONS = {
	"Roblox": {"match": "RobloxPlayerBeta.exe", "command": "DROIDFLEET_ROBLOX"},
	"Python Bot": {"match": "python", "command": "DROIDFLEET_PYTHON_BOT"},
	"Farm Worker": {"match": "farm_worker", "command": "DROIDFLEET_FARM_WORKER"},
}
TOOLS_DIRS = tuple(
	Path(item) for item in os.environ.get("DROIDFLEET_TOOLS", "").split(os.pathsep) if item
)


def load_user_settings() -> None:
	global CONNECTION_MODE, ANDROID_CONNECTION_MODE, ADB_SERVER_PORT, AGENT_SERVER_HOST, AGENT_SERVER_PORT, NGROK_REGION, NGROK_AUTHTOKEN, PROCESS_DEFINITIONS
	try:
		values = json.loads(USER_CONFIG_FILE.read_text(encoding="utf-8"))
	except (OSError, ValueError, TypeError):
		return
	try:
		CONNECTION_MODE = ConnectionProfile.from_value(values.get("connection_mode", CONNECTION_MODE)).config_value
		ANDROID_CONNECTION_MODE = str(values.get("android_connection_mode", ANDROID_CONNECTION_MODE)).casefold()
		ADB_SERVER_PORT = int(values.get("adb_server_port", ADB_SERVER_PORT))
		if ANDROID_CONNECTION_MODE not in {"auto", "usb", "wifi"}:
			ANDROID_CONNECTION_MODE = "auto"
		AGENT_SERVER_HOST = str(values.get("agent_server_host", AGENT_SERVER_HOST))
		AGENT_SERVER_PORT = int(values.get("agent_server_port", AGENT_SERVER_PORT))
		NGROK_REGION = str(values.get("ngrok_region", NGROK_REGION))
		NGROK_AUTHTOKEN = str(values.get("ngrok_authtoken", NGROK_AUTHTOKEN))
		configured_processes = values.get("process_definitions", PROCESS_DEFINITIONS)
		if isinstance(configured_processes, dict) and configured_processes:
			PROCESS_DEFINITIONS = configured_processes
	except (ValueError, TypeError):
		return


def save_user_settings() -> None:
	USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
	USER_CONFIG_FILE.write_text(json.dumps({
		"connection_mode": CONNECTION_MODE,
		"android_connection_mode": ANDROID_CONNECTION_MODE,
		"adb_server_port": ADB_SERVER_PORT,
		"agent_server_host": AGENT_SERVER_HOST,
		"agent_server_port": AGENT_SERVER_PORT,
		"ngrok_region": NGROK_REGION,
		"ngrok_authtoken": NGROK_AUTHTOKEN,
		"process_definitions": PROCESS_DEFINITIONS,
	}, ensure_ascii=False, indent=2), encoding="utf-8")


load_user_settings()
