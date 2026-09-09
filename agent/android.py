from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def adb_path() -> str:
    configured = os.environ.get("DROIDFLEET_ADB", "").strip()
    if configured:
        return configured
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    executable = "adb.exe" if os.name == "nt" else "adb"
    bundled = root / "platform-tools" / executable
    if bundled.is_file():
        return str(bundled)
    return executable


def connected_devices() -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            [adb_path(), "devices", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    devices = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2 or parts[0] == "*":
            continue
        item = {"serial": parts[0], "status": parts[1]}
        for token in parts[2:]:
            if ":" in token:
                key, value = token.split(":", 1)
                if key in {"model", "product", "device"}:
                    item[key] = value
        devices.append(item)
    return devices
