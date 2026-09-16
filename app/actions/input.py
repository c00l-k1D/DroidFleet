from app.adb.commands import keyevent


def send_keyevent(client, serial: str, key: str):
    return client.run(keyevent(key), serial, timeout=3)


def send_text(client, serial: str, text: str):
    if not text or len(text) > 1000:
        raise ValueError("Текст должен содержать от 1 до 1000 символов")
    escaped = text.replace("%", "%25").replace(" ", "%s").replace("&", "%26").replace("|", "%7C")
    escaped = escaped.replace("<", "%3C").replace(">", "%3E").replace("'", "%27").replace('"', "%22")
    return client.run(["shell", "input", "text", escaped], serial, timeout=3)


def send_tap(client, serial: str, x: int, y: int):
    """Send a tap event at device pixel coordinates (x, y)."""
    return client.run(["shell", "input", "tap", str(x), str(y)], serial, timeout=3)


def send_swipe(client, serial: str, x1: int, y1: int, x2: int, y2: int, duration: int = 180):
    """Send a swipe event from (x1, y1) to (x2, y2) with given duration in ms."""
    return client.run(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)], serial, timeout=3)


def send_zoom(client, serial: str, cx: int, cy: int, zoom_in: bool = True, offset: int = 120):
    """Send zoom in/out gestures centered at (cx, cy)."""
    if zoom_in:
        first = ["shell", "input", "swipe", str(cx - offset), str(cy), str(cx + offset), str(cy), "180"]
        second = ["shell", "input", "swipe", str(cx + offset), str(cy), str(cx - offset), str(cy), "180"]
    else:
        first = ["shell", "input", "swipe", str(cx + offset), str(cy), str(cx - offset), str(cy), "180"]
        second = ["shell", "input", "swipe", str(cx - offset), str(cy), str(cx + offset), str(cy), "180"]
    client.run(first, serial, timeout=3)
    return client.run(second, serial, timeout=3)

