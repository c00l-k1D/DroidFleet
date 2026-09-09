from __future__ import annotations

import json
import hashlib
import threading
import time
import uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class AgentStore:
    def __init__(self, stale_after: int = 30):
        self.stale_after = stale_after
        self._agents: dict[str, dict] = {}
        self._commands: dict[str, list[dict]] = {}
        self._results: list[dict] = []
        self._screenshots: dict[str, str] = {}
        self._screenshot_versions: dict[str, int] = {}
        self._process_definitions: dict[str, dict[str, str]] = {}
        self._agent_base_url = ""
        self._updating: set[str] = set()
        self._lock = threading.Lock()

    def update(self, payload: dict):
        device_id = str(payload.get("device_id", "")).strip()
        if not device_id:
            raise ValueError("device_id is required")
        record = dict(payload)
        record["last_seen"] = time.time()
        with self._lock:
            if payload.get("update_completed"):
                self._updating.discard(device_id)
            record["status"] = "UPDATING" if device_id in self._updating else "ONLINE"
            self._agents[device_id] = record

    def list(self) -> list[dict]:
        now = time.time()
        with self._lock:
            result = []
            for item in self._agents.values():
                record = dict(item)
                device_id = str(record.get("device_id", ""))
                if device_id not in self._updating and now - record.get("last_seen", 0) > self.stale_after:
                    record["status"] = "OFFLINE"
                result.append(record)
            return sorted(result, key=lambda item: item.get("hostname", "").casefold())

    def queue_command(self, device_id: str, command: str, process: str = "", params: dict | None = None):
        allowed = {"START", "STOP", "RESTART", "STATUS", "SCREENSHOT", "START_STREAM", "STOP_STREAM", "GET_LOGS", "SEND_FILE", "MOUSE_MOVE", "MOUSE_DOWN", "MOUSE_UP", "KEY", "SYSTEM_INFO", "LIST_PROCESSES", "UPDATE"}
        command = command.upper().strip()
        if command not in allowed:
            raise ValueError(f"unsupported command: {command}")
        item = {"command_id": f"cmd-{uuid.uuid4().hex}", "command": command, "process": process, "params": dict(params or {})}
        with self._lock:
            queue = self._commands.setdefault(device_id, [])
            if command == "SCREENSHOT":
                queue[:] = [queued for queued in queue if queued.get("command") != "SCREENSHOT"]
            elif command == "MOUSE_MOVE":
                queue[:] = [queued for queued in queue if queued.get("command") != "MOUSE_MOVE"]
                queue.insert(0, item)
                return item
            elif command in {"MOUSE_DOWN", "MOUSE_UP", "KEY"}:
                queue.insert(0, item)
                return item
            elif command == "UPDATE":
                self._updating.add(device_id)
                if device_id in self._agents:
                    self._agents[device_id]["status"] = "UPDATING"
            queue.append(item)
        return item

    def next_command(self, device_id: str):
        with self._lock:
            queue = self._commands.get(device_id, [])
            return queue.pop(0) if queue else None

    def add_result(self, result: dict):
        with self._lock:
            record = dict(result)
            screenshot = record.pop("screenshot", None)
            if screenshot:
                device_id = str(record.get("device_id", ""))
                self._screenshots[device_id] = screenshot
                self._screenshot_versions[device_id] = self._screenshot_versions.get(device_id, 0) + 1
            if record.get("command") == "UPDATE" and record.get("error"):
                self._updating.discard(str(record.get("device_id", "")))
                device_id = str(record.get("device_id", ""))
                if device_id in self._agents:
                    self._agents[device_id]["status"] = "ONLINE"
            if record.get("command") == "UPDATE" and record.get("updated"):
                device_id = str(record.get("device_id", ""))
                if device_id in self._agents:
                    self._agents[device_id]["status"] = "UPDATING"
            self._results.append(record)
            if len(self._results) > 100:
                self._results = self._results[-100:]

    def results(self) -> list[dict]:
        with self._lock:
            return list(self._results)

    def screenshot(self, device_id: str) -> str | None:
        with self._lock:
            return self._screenshots.get(device_id)

    def screenshot_state(self, device_id: str) -> tuple[str | None, int]:
        with self._lock:
            return self._screenshots.get(device_id), self._screenshot_versions.get(device_id, 0)

    def set_process_definitions(self, definitions: dict) -> None:
        with self._lock:
            self._process_definitions = dict(definitions)

    def process_definitions(self) -> dict:
        with self._lock:
            return dict(self._process_definitions)

    def set_agent_base_url(self, value: str) -> None:
        with self._lock:
            self._agent_base_url = str(value or "").rstrip("/")

    def agent_base_url(self) -> str:
        with self._lock:
            return self._agent_base_url


class AgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "DroidFleetAgentServer/1.0"

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path):
        if not path.is_file():
            self._send_json({"error": f"FarmAgent build not found: {path}"}, 404)
            return
        body = path.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-DroidFleet-SHA256", digest)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/agents":
            self._send_json({"agents": self.server.store.list()})
            return
        if parsed.path.startswith("/api/agents/") and parsed.path.endswith("/screenshot"):
            device_id = parsed.path.split("/")[3]
            screenshot = self.server.store.screenshot(device_id)
            if screenshot:
                self._send_json({"device_id": device_id, "screenshot": screenshot})
            else:
                self._send_json({"error": "screenshot unavailable"}, 404)
            return
        if parsed.path == "/api/agent/poll":
            device_id = parse_qs(parsed.query).get("device_id", [""])[0]
            self._send_json({"command": self.server.store.next_command(device_id)})
            return
        if parsed.path == "/api/agent/config":
            self._send_json({
                "process_definitions": self.server.store.process_definitions(),
                "server_url": self.server.store.agent_base_url(),
            })
            return
        if parsed.path == "/api/agent/update":
            self._send_file(self.server.update_file)
            return
        if parsed.path == "/api/agent/update-launcher":
            self._send_file(self.server.update_file.with_name("FarmAgent-start.cmd"))
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/agents/command":
            try:
                payload = self._read_json()
                item = self.server.store.queue_command(payload.get("device_id", ""), payload.get("command", ""), payload.get("process", ""), payload.get("params"))
                self._send_json(item, 202)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send_json({"error": str(exc)}, 400)
            return
        if parsed.path == "/api/agent/result":
            try:
                self.server.store.add_result(self._read_json())
                self._send_json({"ok": True})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send_json({"error": str(exc)}, 400)
            return
        if parsed.path != "/api/agent/heartbeat":
            self._send_json({"error": "not found"}, 404)
            return
        try:
            payload = self._read_json()
            self.server.store.update(payload)
            self._send_json({"ok": True})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, 400)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length))

    def log_message(self, format, *args):
        return


class AgentServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, address, store=None, update_file=None):
        super().__init__(address, AgentRequestHandler)
        self.store = store or AgentStore()
        self.update_file = Path(update_file) if update_file else Path(__file__).resolve().parents[1] / "dist" / "FarmAgent.exe"

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="agent-server", daemon=True)
        thread.start()
        return thread

    def close(self):
        self.shutdown()
        self.server_close()
