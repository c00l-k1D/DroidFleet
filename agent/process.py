from __future__ import annotations

import os
import shlex
import subprocess

import psutil


PROCESS_DEFINITIONS = {
    "Roblox": {"match": "RobloxPlayerBeta.exe", "command": "DROIDFLEET_ROBLOX"},
    "Python Bot": {"match": "python", "command": "DROIDFLEET_PYTHON_BOT"},
    "Farm Worker": {"match": "farm_worker", "command": "DROIDFLEET_FARM_WORKER"},
}


def list_processes(limit: int = 20) -> list[dict[str, str | float | int]]:
    processes = []
    for process in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_percent"]):
        try:
            data = process.info
            processes.append({
                "pid": data["pid"],
                "name": data.get("name") or "--",
                "user": data.get("username") or "--",
                "cpu": round(data.get("cpu_percent") or 0.0, 1),
                "memory": round(data.get("memory_percent") or 0.0, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(processes, key=lambda item: (item["cpu"], item["memory"]), reverse=True)[:limit]


def _definition(name: str) -> dict:
    if name not in PROCESS_DEFINITIONS:
        raise ValueError(f"unknown process: {name}")
    return PROCESS_DEFINITIONS[name]


def process_status(name: str) -> dict[str, str | int | bool]:
    definition = _definition(name)
    matches = [item for item in psutil.process_iter(["pid", "name"]) if (item.info.get("name") or "").casefold() == definition["match"].casefold() or definition["match"].casefold() in (item.info.get("name") or "").casefold()]
    return {"process": name, "running": bool(matches), "count": len(matches), "pids": [item.info["pid"] for item in matches]}


def stop_process(name: str) -> dict:
    definition = _definition(name)
    stopped = 0
    for process in psutil.process_iter(["name"]):
        if definition["match"].casefold() in (process.info.get("name") or "").casefold():
            try:
                process.terminate()
                stopped += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    return {"process": name, "stopped": stopped}


def start_process(name: str) -> dict:
    definition = _definition(name)
    command = os.environ.get(definition["command"])
    if not command:
        raise RuntimeError(f"set {definition['command']} to start {name}")
    subprocess.Popen(shlex.split(command, posix=False), close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return {"process": name, "started": True}


def restart_process(name: str) -> dict:
    stop_process(name)
    return start_process(name)
