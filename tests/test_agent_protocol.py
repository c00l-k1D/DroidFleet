import time

import pytest

from app.agent_server import AgentStore
from agent.agent import execute_command


def test_agent_store_queues_only_supported_commands():
    store = AgentStore()
    queued = store.queue_command("win-1", "STATUS")
    assert store.next_command("win-1")["command_id"] == queued["command_id"]
    with pytest.raises(ValueError):
        store.queue_command("win-1", "SHELL")


def test_agent_store_marks_stale_agents_offline():
    store = AgentStore(stale_after=1)
    store.update({"device_id": "win-1", "hostname": "test"})
    store._agents["win-1"]["last_seen"] = time.time() - 2
    assert store.list()[0]["status"] == "OFFLINE"


def test_agent_status_command_returns_known_processes():
    result = execute_command({"command": "STATUS", "command_id": "cmd-1"})
    assert result["command"] == "STATUS"
    assert {item["process"] for item in result["processes"]} == {"Roblox", "Python Bot", "Farm Worker"}
