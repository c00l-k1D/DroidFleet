from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class AgentStore:
    def __init__(self, stale_after: int = 30):
        self.stale_after = stale_after
        self._agents: dict[str, dict] = {}
        self._commands: dict[str, list[dict]] = {}
        self._results: list[dict] = []
        self._screenshots: dict[str, str] = {}
        self._lock = threading.Lock()

    def update(self, payload: dict):
        device_id = str(payload.get("device_id", "")).strip()
        if not device_id:
            raise ValueError("device_id is required")
        record = dict(payload)
        record["last_seen"] = time.time()
        record["status"] = "ONLINE"
        with self._lock:
            self._agents[device_id] = record

    def list(self) -> list[dict]:
        now = time.time()
        with self._lock:
            result = []
            for item in self._agents.values():
                record = dict(item)
                if now - record.get("last_seen", 0) > self.stale_after:
                    record["status"] = "OFFLINE"
                result.append(record)
            return sorted(result, key=lambda item: item.get("hostname", "").casefold())

    def queue_command(self, device_id: str, command: str, process: str = ""):
        allowed = {"START", "STOP", "RESTART", "STATUS", "SCREENSHOT", "GET_LOGS"}
        command = command.upper().strip()
        if command not in allowed:
            raise ValueError(f"unsupported command: {command}")
        item = {"command_id": f"cmd-{time.time_ns()}", "command": command, "process": process}
        with self._lock:
            self._commands.setdefault(device_id, []).append(item)
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
                self._screenshots[str(record.get("device_id", ""))] = screenshot
            self._results.append(record)
            if len(self._results) > 100:
                self._results = self._results[-100:]

    def results(self) -> list[dict]:
        with self._lock:
            return list(self._results)

    def screenshot(self, device_id: str) -> str | None:
        with self._lock:
            return self._screenshots.get(device_id)


class AgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "DroidFleetAgentServer/1.0"

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/agents/command":
            try:
                payload = self._read_json()
                item = self.server.store.queue_command(payload.get("device_id", ""), payload.get("command", ""), payload.get("process", ""))
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

    def __init__(self, address, store=None):
        super().__init__(address, AgentRequestHandler)
        self.store = store or AgentStore()

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="agent-server", daemon=True)
        thread.start()
        return thread

    def close(self):
        self.shutdown()
        self.server_close()
