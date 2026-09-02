from app.adb.commands import shell


def run_shell(client, serial: str, args: list[str]):
    return client.run(shell(args), serial, timeout=8)


def install_apk(client, serial: str, apk_path: str):
    return client.run(["install", "-r", apk_path], serial, timeout=120)


def launch_app(client, serial: str, package_name: str):
    return client.run(
        ["shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
        serial,
        timeout=15,
    )


def close_app(client, serial: str, package_name: str):
    return client.run(["shell", "am", "force-stop", package_name], serial, timeout=15)


def push_account_file(client, serial: str, file_path: str):
    destination = "/sdcard/Download/DroidFleet/accounts/"
    client.run(["shell", "mkdir", "-p", destination], serial, timeout=15)
    return client.run(["push", file_path, destination], serial, timeout=120)
