from .input import send_keyevent
from app.adb.commands import KEY_POWER


def power(client, serial: str):
    return send_keyevent(client, serial, KEY_POWER)
