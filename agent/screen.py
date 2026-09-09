from __future__ import annotations

import base64
import io
import ctypes

from PIL import Image, ImageGrab


def control_input(action: str, params: dict) -> None:
    import pyautogui
    from agent import config

    pyautogui.FAILSAFE = config.PYAutoGUI_FAILSAFE

    if action == "MOUSE_MOVE":
        pyautogui.moveTo(int(params["x"]), int(params["y"]), duration=0)
    elif action == "MOUSE_DOWN":
        pyautogui.mouseDown(button=str(params.get("button", "left")))
    elif action == "MOUSE_UP":
        pyautogui.mouseUp(button=str(params.get("button", "left")))
    elif action == "KEY":
        key = str(params.get("key", ""))
        if not key or len(key) > 40:
            raise ValueError("invalid key")
        keys = [part.strip() for part in key.split("+") if part.strip()]
        if len(keys) > 1:
            pyautogui.hotkey(*keys)
        else:
            pyautogui.press(key)
    else:
        raise ValueError(f"unsupported input: {action}")


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
    from agent import config

    image = ImageGrab.grab()
    if image.width > config.SCREENSHOT_MAX_WIDTH:
        height = int(image.height * config.SCREENSHOT_MAX_WIDTH / image.width)
        resampling = getattr(Image, "Resampling", Image)
        image = image.resize((config.SCREENSHOT_MAX_WIDTH, height), resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=max(20, min(95, quality)), optimize=True)
    return base64.b64encode(output.getvalue()).decode("ascii")


def screen_info() -> dict:
    try:
        image = ImageGrab.grab()
        return {"available": True, "width": image.width, "height": image.height}
    except (OSError, RuntimeError) as exc:
        return {"available": False, "error": str(exc)}
