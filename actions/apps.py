from app.adb.commands import shell


def run_shell(client, serial: str, args: list[str]):
    return client.run(shell(args), serial, timeout=8)


def install_apk(client, serial: str, apk_path: str):
    return client.run(["install", "-r", apk_path], serial, timeout=120)
