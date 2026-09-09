from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import psutil

from . import config


def _stable_device_id() -> str:
    if config.DEVICE_ID:
        return config.DEVICE_ID
    try:
        if config.STATE_FILE.exists():
            saved = json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
            if saved.get("device_id"):
                return saved["device_id"]
    except (OSError, ValueError, TypeError):
        pass
    platform_name = {
        "Windows": "win",
        "Linux": "linux",
        "Darwin": "mac",
    }.get(platform.system(), platform.system().casefold() or "agent")
    device_id = f"{platform_name}-{uuid.uuid5(uuid.NAMESPACE_DNS, socket.gethostname()).hex[:12]}"
    try:
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config.STATE_FILE.write_text(json.dumps({"device_id": device_id}), encoding="utf-8")
    except OSError:
        pass
    return device_id


def _gpu_name() -> str:
    if os.name == "nt":
        command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_VideoController).Name"]
    elif shutil.which("nvidia-smi"):
        command = ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]
    elif shutil.which("lspci"):
        command = ["lspci"]
    else:
        return "--"
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return ", ".join(names) or "--"
    except (OSError, subprocess.SubprocessError):
        return "--"


def snapshot(status: str = "ONLINE") -> dict[str, str | int]:
    memory = psutil.virtual_memory()
    return {
        "device_id": _stable_device_id(),
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "os_version": platform.platform(),
        "windows_version": platform.platform(),
        "cpu": f"{psutil.cpu_percent(interval=0.2):.1f}% ({psutil.cpu_count(logical=True) or 0} cores)",
        "ram": f"{memory.percent:.1f}% ({memory.used // (1024 ** 3)} / {memory.total // (1024 ** 3)} GB)",
        "gpu": _gpu_name(),
        "ip": socket.gethostbyname(socket.gethostname()),
        "uptime": int(time.time() - psutil.boot_time()),
        "status": status,
        "agent_version": config.AGENT_VERSION,
    }
