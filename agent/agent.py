from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import config
from agent.network import primary_address
from agent.process import PROCESS_DEFINITIONS, process_status, restart_process, start_process, stop_process
from agent.screen import screenshot_jpeg
from agent.system import snapshot

LOGGER = logging.getLogger("FarmAgent")


def collect_payload() -> dict:
    payload = snapshot()
    payload["ip"] = primary_address()
    return payload


def send_heartbeat(payload: dict) -> None:
    request_json(config.SERVER_URL, payload)


def request_json(url: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST" if body else "GET")
    with urlopen(request, timeout=config.REQUEST_TIMEOUT) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"server returned HTTP {response.status}")
        data = response.read()
        return json.loads(data.decode("utf-8")) if data else {}


def poll_command(device_id: str) -> dict | None:
    poll_url = config.SERVER_URL.rsplit("/heartbeat", 1)[0] + "/poll?device_id=" + device_id
    response = request_json(poll_url)
    return response.get("command")


def send_result(result: dict, device_id: str) -> None:
    result["device_id"] = device_id
    request_json(config.SERVER_URL.rsplit("/heartbeat", 1)[0] + "/result", result)


def execute_command(command: dict) -> dict:
    action = str(command.get("command", "")).upper()
    process = str(command.get("process", ""))
    if action == "STATUS":
        return {"command_id": command.get("command_id"), "command": action, "processes": [process_status(name) for name in PROCESS_DEFINITIONS]}
    if action == "GET_LOGS":
        try:
            lines = config.LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
        except OSError:
            lines = []
        return {"command_id": command.get("command_id"), "command": action, "logs": lines}
    if action == "SCREENSHOT":
        return {"command_id": command.get("command_id"), "command": action, "screenshot": screenshot_jpeg(config.SCREENSHOT_QUALITY)}
    if process not in PROCESS_DEFINITIONS:
        raise ValueError("a valid process is required")
    handlers = {"START": start_process, "STOP": stop_process, "RESTART": restart_process}
    if action not in handlers:
        raise ValueError(f"unsupported command: {action}")
    return {"command_id": command.get("command_id"), "command": action, **handlers[action](process)}


def run(once: bool = False) -> int:
    LOGGER.info("FarmAgent started; server=%s", config.SERVER_URL)
    last_screenshot = 0.0
    while True:
        try:
            payload = collect_payload()
            send_heartbeat(payload)
            command = poll_command(payload["device_id"])
            if command:
                try:
                    send_result(execute_command(command), payload["device_id"])
                except (OSError, RuntimeError, ValueError) as exc:
                    send_result({"command_id": command.get("command_id"), "command": command.get("command"), "error": str(exc)}, payload["device_id"])
            if config.SCREENSHOT_INTERVAL > 0 and time.monotonic() - last_screenshot >= config.SCREENSHOT_INTERVAL:
                send_result({"command_id": "periodic", "command": "SCREENSHOT", "screenshot": screenshot_jpeg(config.SCREENSHOT_QUALITY)}, payload["device_id"])
                last_screenshot = time.monotonic()
            LOGGER.info("heartbeat sent")
        except (OSError, RuntimeError, URLError, ValueError) as exc:
            LOGGER.warning("heartbeat failed: %s", exc)
        if once:
            return 0
        time.sleep(max(1, config.HEARTBEAT_INTERVAL))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="FarmAgent", description="DroidFleet Windows agent")
    parser.add_argument("--once", action="store_true", help="send one heartbeat and exit")
    parser.add_argument("--server", help="heartbeat URL")
    args = parser.parse_args(argv)
    if args.server:
        config.SERVER_URL = args.server
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_FILE, encoding="utf-8")])
    return run(args.once)


if __name__ == "__main__":
    raise SystemExit(main())
