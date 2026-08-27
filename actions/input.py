from app.adb.commands import keyevent


def send_keyevent(client, serial: str, key: str):
    return client.run(keyevent(key), serial, timeout=3)
