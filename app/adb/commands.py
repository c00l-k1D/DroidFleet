KEY_HOME = "KEYCODE_HOME"
KEY_BACK = "KEYCODE_BACK"
KEY_RECENTS = "KEYCODE_APP_SWITCH"
KEY_POWER = "KEYCODE_POWER"


def keyevent(key: str) -> list[str]:
    return ["shell", "input", "keyevent", key]


def shell(args: list[str]) -> list[str]:
    return ["shell", *args]


def screencap() -> list[str]:
    return ["exec-out", "screencap", "-p"]
