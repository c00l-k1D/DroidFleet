from __future__ import annotations

import base64
import io
import ctypes

from PIL import ImageGrab


def lock_workstation() -> bool:
    try:
        return bool(ctypes.windll.user32.LockWorkStation())
    except (AttributeError, OSError):
        return False


def display_count() -> int:
    try:
        return int(ctypes.windll.user32.GetSystemMetrics(80))
    except (AttributeError, OSError):
        return 1


def screenshot_jpeg(quality: int = 75) -> str:
    image = ImageGrab.grab()
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=max(20, min(95, quality)), optimize=True)
    return base64.b64encode(output.getvalue()).decode("ascii")
