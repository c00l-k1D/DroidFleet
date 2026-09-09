from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import psutil

from . import config


PROCESS_DEFINITIONS = dict(config.DEFAULT_PROCESS_DEFINITIONS)


def _roblox_command() -> str | None:
    configured = os.environ.get("DROIDFLEET_ROBLOX", "").strip()
    if configured:
        return configured
    roots = (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Roblox" / "Versions",
        Path(os.environ.get("PROGRAMFILES", "")) / "Roblox" / "Versions",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Roblox" / "Versions",
    )
    candidates = []
    for root in roots:
        if root.exists():
            candidates.extend(root.glob("*/RobloxPlayerBeta.exe"))
    if not candidates:
        return None
    return str(max(candidates, key=lambda item: item.stat().st_mtime))


def _process_command(variable: str) -> str | None:
    if variable == "DROIDFLEET_ROBLOX":
        return _roblox_command()
    value = os.environ.get(variable, "").strip()
    return value or None


def configure_processes(definitions: dict) -> None:
    global PROCESS_DEFINITIONS
    if isinstance(definitions, dict) and definitions:
        PROCESS_DEFINITIONS = {
            str(name): {"match": str(item["match"]), "command": str(item["command"])}
            for name, item in definitions.items()
            if isinstance(item, dict) and item.get("match") and item.get("command")
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
    variable = definition["command"]
    command = _process_command(variable)
    if not command:
        raise RuntimeError(
            f"Process '{name}' is not configured. Set {variable} on the target Windows PC "
            f"to the full launch command, for example: "
            f'setx {variable} "C:\\\\Path\\\\app.exe --arg"'
        )
    subprocess.Popen(
        shlex.split(command, posix=os.name != "nt"),
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return {"process": name, "started": True}


def restart_process(name: str) -> dict:
    stop_process(name)
    return start_process(name)
