import time
import base64
import hashlib
from urllib.error import HTTPError

import pytest

from app.agent_server import AgentStore
from agent.agent import collect_payload, execute_command, execute_command_safely
from agent.agent import request_json


def test_agent_store_queues_only_supported_commands():
    store = AgentStore()
    queued = store.queue_command("win-1", "STATUS")
    assert store.next_command("win-1")["command_id"] == queued["command_id"]
    with pytest.raises(ValueError):
        store.queue_command("win-1", "SHELL")
    assert store.queue_command("win-1", "UPDATE")["command"] == "UPDATE"


def test_agent_store_keeps_process_configuration_for_agents():
    store = AgentStore()
    definitions = {"Custom Bot": {"match": "custom.exe", "command": "DROIDFLEET_CUSTOM"}}
    store.set_process_definitions(definitions)
    assert store.process_definitions() == definitions


def test_agent_store_marks_stale_agents_offline():
    store = AgentStore(stale_after=1)
    store.update({"device_id": "win-1", "hostname": "test"})
    store._agents["win-1"]["last_seen"] = time.time() - 2
    assert store.list()[0]["status"] == "OFFLINE"


def test_agent_store_marks_update_and_clears_after_reconnect():
    store = AgentStore()
    store.update({"device_id": "win-1", "hostname": "test"})
    store.queue_command("win-1", "UPDATE")
    assert store.list()[0]["status"] == "UPDATING"
    store.update({"device_id": "win-1", "hostname": "test", "update_completed": True})
    assert store.list()[0]["status"] == "ONLINE"


def test_agent_store_clears_update_on_failure():
    store = AgentStore()
    store.update({"device_id": "win-1", "hostname": "test"})
    store.queue_command("win-1", "UPDATE")
    store.add_result({"device_id": "win-1", "command": "UPDATE", "error": "download failed"})
    assert store.list()[0]["status"] == "ONLINE"


def test_agent_store_prioritizes_remote_input():
    store = AgentStore()
    store.queue_command("win-1", "STATUS")
    store.queue_command("win-1", "MOUSE_MOVE", params={"x": 10, "y": 20})
    assert store.next_command("win-1")["command"] == "MOUSE_MOVE"


def test_agent_status_command_returns_known_processes():
    result = execute_command({"command": "STATUS", "command_id": "cmd-1"})
    assert result["command"] == "STATUS"
    assert {item["process"] for item in result["processes"]} == {"Roblox", "Python Bot", "Farm Worker"}


def test_agent_store_accepts_only_explicit_remote_input_commands():
    store = AgentStore()
    queued = store.queue_command("win-1", "KEY", params={"key": "enter"})
    assert queued["params"] == {"key": "enter"}
    with pytest.raises(ValueError):
        store.queue_command("win-1", "SHELL", params={"command": "whoami"})


def test_agent_store_coalesces_live_view_commands():
    store = AgentStore()
    first = store.queue_command("win-1", "SCREENSHOT")
    second = store.queue_command("win-1", "SCREENSHOT")
    assert store.next_command("win-1")["command_id"] == second["command_id"]
    assert first["command_id"] != second["command_id"]


def test_agent_store_tracks_latest_stream_frame_version():
    store = AgentStore()
    store.add_result({"device_id": "win-1", "command": "SCREENSHOT", "screenshot": "frame-1"})
    assert store.screenshot_state("win-1") == ("frame-1", 1)
    store.add_result({"device_id": "win-1", "command": "SCREENSHOT", "screenshot": "frame-2"})
    assert store.screenshot_state("win-1") == ("frame-2", 2)


def test_agent_command_errors_are_returned_without_crashing():
    result = execute_command_safely({"command": "SCREENSHOT", "command_id": "cmd-1"})
    assert result["command_id"] == "cmd-1"
    assert "error" not in result or isinstance(result["error"], str)


def test_agent_supports_system_info_and_process_list_commands(monkeypatch):
    monkeypatch.setattr("agent.agent.snapshot", lambda: {"hostname": "test"})
    monkeypatch.setattr("agent.agent.screen_info", lambda: {"available": False})
    assert execute_command({"command": "SYSTEM_INFO", "command_id": "cmd-2"}) == {
        "command_id": "cmd-2",
        "command": "SYSTEM_INFO",
        "system": {"hostname": "test"},
        "screen": {"available": False},
    }
    result = execute_command({"command": "LIST_PROCESSES", "command_id": "cmd-3"})
    assert result["command"] == "LIST_PROCESSES"
    assert isinstance(result["processes"], list)


def test_agent_heartbeat_contains_capabilities_and_uptime(monkeypatch):
    monkeypatch.setattr("agent.agent.snapshot", lambda: {"hostname": "test"})
    monkeypatch.setattr("agent.agent.primary_address", lambda: "192.0.2.10")
    monkeypatch.setattr("agent.agent.screen_info", lambda: {"available": False})
    payload = collect_payload()
    assert payload["ip"] == "192.0.2.10"
    assert payload["agent_uptime"] >= 0
    assert "SYSTEM_INFO" in payload["capabilities"]
    assert "LIST_PROCESSES" in payload["capabilities"]


def test_agent_heartbeat_includes_last_ping(monkeypatch):
    monkeypatch.setattr("agent.agent.snapshot", lambda: {"hostname": "test"})
    monkeypatch.setattr("agent.agent.primary_address", lambda: "192.0.2.10")
    monkeypatch.setattr("agent.agent.screen_info", lambda: {"available": False})
    monkeypatch.setattr("agent.config.LAST_PING_MS", 42.5)
    assert collect_payload()["ping_ms"] == 42.5


def test_agent_heartbeat_includes_managed_android_devices(monkeypatch):
    monkeypatch.setattr("agent.agent.snapshot", lambda: {"hostname": "test"})
    monkeypatch.setattr("agent.agent.primary_address", lambda: "192.0.2.10")
    monkeypatch.setattr("agent.agent.screen_info", lambda: {"available": False})
    monkeypatch.setattr("agent.agent.connected_devices", lambda: [{"serial": "ABC", "status": "device", "model": "Pixel"}])
    assert collect_payload()["android_devices"][0]["model"] == "Pixel"


def test_agent_receives_file_with_checksum(tmp_path):
    target = tmp_path / "received.bin"
    content = b"farmagent transfer"
    result = execute_command({
        "command": "SEND_FILE",
        "command_id": "cmd-file",
        "params": {
            "name": "received.bin",
            "destination": str(target),
            "content": base64.b64encode(content).decode("ascii"),
            "sha256": hashlib.sha256(content).hexdigest(),
        },
    })
    assert result["ok"] is True
    assert target.read_bytes() == content


def test_request_json_recreates_tls_context_on_retry(monkeypatch):
    contexts = []
    calls = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b"{}"

    def make_context():
        context = object()
        contexts.append(context)
        return context

    def fake_urlopen(request, timeout, context):
        calls.append(context)
        if len(calls) == 1:
            raise OSError("unexpected eof")
        return Response()

    monkeypatch.setattr("agent.agent.ssl.create_default_context", make_context)
    monkeypatch.setattr("agent.agent.urlopen", fake_urlopen)
    monkeypatch.setattr("agent.agent.time.sleep", lambda _: None)
    assert request_json("https://example.test/api") == {}
    assert len(calls) == 2
    assert calls[0] is not calls[1]


def test_request_json_uses_keep_alive_for_long_running_agents(monkeypatch):
    captured = {}

    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout, context):
        captured["connection"] = request.get_header("Connection")
        return Response()

    monkeypatch.setattr("agent.agent.urlopen", fake_urlopen)
    assert request_json("https://example.test/api") == {}
    assert captured["connection"] == "keep-alive"


def test_request_json_retries_transient_ngrok_http_errors(monkeypatch):
    calls = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout, context):
        calls.append(request)
        if len(calls) == 1:
            raise HTTPError(request.full_url, 502, "ngrok edge", {}, None)
        return Response()

    monkeypatch.setattr("agent.agent.urlopen", fake_urlopen)
    monkeypatch.setattr("agent.agent.time.sleep", lambda _: None)
    assert request_json("https://example.test/api") == {}
    assert len(calls) == 2


def test_command_poll_interval_has_safe_multi_agent_default():
    from agent import config

    assert config.COMMAND_POLL_INTERVAL >= 0.5
