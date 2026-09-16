import argparse
import shlex
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adb.client import AdbClient
from app.adb.commands import KEY_BACK, KEY_HOME, KEY_POWER, KEY_RECENTS, keyevent, screencap, shell
from app.actions.apps import close_app, install_apk, launch_app, push_account_file
from app import config
from app.accounts.repository import AccountRepository
from app.actions.input import send_swipe, send_tap, send_zoom


def _online_devices(client):
    return [(serial, state) for serial, state in client.device_states() if state == "device"]


def _select_devices(client, group=None):
    devices = _online_devices(client)
    if not group:
        return devices
    selected = []
    for serial, state in devices:
        try:
            info = client.hardware_info(serial)
        except Exception as exc:
            print(f"WARN {serial}: не удалось определить производителя: {exc}", file=sys.stderr)
            continue
        if info.manufacturer.casefold() == group.casefold():
            selected.append((serial, state))
    return selected


def _targets_parser(parser, *, required=True):
    selection = parser.add_mutually_exclusive_group(required=required)
    selection.add_argument("--all", action="store_true", help="Все подключённые устройства")
    selection.add_argument("--group", help="Фильтр по производителю")


def _run_on_targets(client, group, action):
    targets = _select_devices(client, group)
    if not targets:
        print("Нет подходящих подключённых устройств.", file=sys.stderr)
        return 1
    failed = 0
    for serial, _ in targets:
        try:
            result = action(serial)
            output = getattr(result, "stdout", b"").decode(errors="replace").strip()
            errors = getattr(result, "stderr", b"").decode(errors="replace").strip()
            if output:
                print(f"[{serial}]\n{output}")
            else:
                print(f"{serial}: {'OK' if result.returncode == 0 else 'ERROR'}")
            if errors:
                print(f"[{serial}] {errors}", file=sys.stderr)
            failed += result.returncode != 0
        except Exception as exc:
            print(f"[{serial}] ERROR: {exc}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def devices_command(client):
    print(f"{'SERIAL':<14}{'MODEL':<16}{'STATUS'}")
    for serial, state in client.device_states():
        model = "--"
        if state == "device":
            try:
                model = client.hardware_info(serial).model
            except Exception:
                pass
        status = "ONLINE" if state == "device" else state.upper()
        print(f"{serial:<14}{model:<16}{status}")
    return 0


def exec_command(client, command, group=None):
    targets = _select_devices(client, group)
    if not targets:
        print("Нет подходящих подключённых устройств.", file=sys.stderr)
        return 1
    args = shlex.split(command, posix=True)
    if not args:
        print("Команда не может быть пустой.", file=sys.stderr)
        return 2
    failed = 0
    for serial, _ in targets:
        result = client.run(shell(args), serial, timeout=30)
        output = result.stdout.decode(errors="replace").strip()
        errors = result.stderr.decode(errors="replace").strip()
        print(f"[{serial}]")
        if output:
            print(output)
        if errors:
            print(errors, file=sys.stderr)
        failed += result.returncode != 0
    return 1 if failed else 0


def reboot_command(client, group=None):
    return _run_on_targets(client, group, lambda serial: client.run(shell(["reboot"]), serial, timeout=10))


def info_command(client, group=None):
    targets = _select_devices(client, group)
    if not targets:
        print("Нет подходящих подключённых устройств.", file=sys.stderr)
        return 1
    failed = 0
    for serial, _ in targets:
        try:
            info = client.hardware_info(serial)
            print(f"{serial}: {info.manufacturer} {info.model}, Android {info.android_version}, "
                f"screen {info.screen}, battery {info.battery}")
        except Exception as exc:
            print(f"{serial}: ERROR: {exc}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def screenshot_command(client, output_dir, group=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return _run_on_targets(client, group, lambda serial: _save_screenshot(client, serial, output_dir))


def account_import_command(client, source, group=None):
    source = Path(source)
    if not source.is_file():
        print(f"Файл аккаунтов не найден: {source}", file=sys.stderr)
        return 2
    targets = _select_devices(client, group)
    if not targets:
        print("Нет подходящих подключённых устройств.", file=sys.stderr)
        return 1
    serials = [serial for serial, _ in targets]
    AccountRepository(config.ACCOUNTS_FILE).add_import(source, serials)
    return _run_on_targets(client, group, lambda serial: push_account_file(client, serial, str(source)))


def _save_screenshot(client, serial, output_dir):
    result = client.run(screencap(), serial, timeout=10)
    if result.returncode == 0:
        path = output_dir / f"{serial}.png"
        path.write_bytes(result.stdout)
        print(f"{serial}: {path}")
    return result


def build_parser():
    parser = argparse.ArgumentParser(prog="droidfleet", description="Управление Android-устройствами через ADB")
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("devices", help="Показать подключённые устройства")
    exec_parser = subparsers.add_parser("exec", help="Выполнить shell-команду")
    selection = exec_parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="Выполнить на всех online-устройствах")
    selection.add_argument("--group", help="Фильтр по производителю, например samsung")
    exec_parser.add_argument("shell_command", help="Команда Android shell в кавычках")
    info_parser = subparsers.add_parser("info", help="Показать сведения об устройствах")
    _targets_parser(info_parser)
    reboot_parser = subparsers.add_parser("reboot", help="Перезагрузить устройства")
    _targets_parser(reboot_parser)
    key_parser = subparsers.add_parser("key", help="Отправить Android keyevent")
    _targets_parser(key_parser)
    key_parser.add_argument("key", choices=[KEY_HOME, KEY_BACK, KEY_RECENTS, KEY_POWER], help="Код клавиши")
    tap_parser = subparsers.add_parser("tap", help="Нажать координату экрана")
    _targets_parser(tap_parser)
    tap_parser.add_argument("x", type=int)
    tap_parser.add_argument("y", type=int)
    swipe_parser = subparsers.add_parser("swipe", help="Выполнить свайп")
    _targets_parser(swipe_parser)
    for name in ("x1", "y1", "x2", "y2"):
        swipe_parser.add_argument(name, type=int)
    swipe_parser.add_argument("--duration", type=int, default=180)
    zoom_parser = subparsers.add_parser("zoom", help="Масштабировать экран")
    _targets_parser(zoom_parser)
    zoom_parser.add_argument("x", type=int)
    zoom_parser.add_argument("y", type=int)
    zoom_parser.add_argument("direction", choices=("in", "out"))
    apk_parser = subparsers.add_parser("install", help="Установить APK")
    _targets_parser(apk_parser)
    apk_parser.add_argument("apk", type=Path)
    app_parser = subparsers.add_parser("app", help="Запустить или остановить приложение")
    _targets_parser(app_parser)
    app_parser.add_argument("action", choices=("launch", "close"))
    app_parser.add_argument("package")
    screenshot_parser = subparsers.add_parser("screenshot", help="Сохранить скриншоты")
    _targets_parser(screenshot_parser)
    screenshot_parser.add_argument("--output", default="screenshots", help="Папка для PNG")
    reconnect_parser = subparsers.add_parser("reconnect", help="Переподключить ADB")
    _targets_parser(reconnect_parser)
    account_parser = subparsers.add_parser("account", help="Управление файлами аккаунтов")
    account_subparsers = account_parser.add_subparsers(dest="account_action", required=True)
    import_parser = account_subparsers.add_parser("import", help="Передать файл аккаунтов на устройства")
    _targets_parser(import_parser)
    import_parser.add_argument("file", type=Path)
    subparsers.add_parser("gui", help="Запустить графический интерфейс")
    subparsers.add_parser("web", help="Запустить отдельный веб-интерфейс DroidLeet")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.subcommand is None:
        build_parser().print_help()
        return 0
    if args.subcommand == "gui":
        from app.main import main as gui_main
        gui_main()
        return 0
    if args.subcommand == "web":
        from app.web_ui import run_web_interface
        run_web_interface()
        return 0
    client = AdbClient()
    if not client.executable:
        print("ADB не найден. Добавьте platform-tools в PATH.", file=sys.stderr)
        return 1
    if args.subcommand == "devices":
        return devices_command(client)
    if args.subcommand == "info":
        return info_command(client, args.group)
    if args.subcommand == "exec":
        return exec_command(client, args.shell_command, args.group)
    if args.subcommand == "reboot":
        return reboot_command(client, args.group)
    if args.subcommand == "key":
        return _run_on_targets(client, args.group, lambda serial: client.run(keyevent(args.key), serial, timeout=3))
    if args.subcommand == "tap":
        return _run_on_targets(client, args.group, lambda serial: send_tap(client, serial, args.x, args.y))
    if args.subcommand == "swipe":
        return _run_on_targets(client, args.group, lambda serial: send_swipe(client, serial, args.x1, args.y1, args.x2, args.y2, args.duration))
    if args.subcommand == "zoom":
        return _run_on_targets(client, args.group, lambda serial: send_zoom(client, serial, args.x, args.y, args.direction == "in"))
    if args.subcommand == "install":
        if not args.apk.is_file():
            print(f"APK не найден: {args.apk}", file=sys.stderr)
            return 2
        return _run_on_targets(client, args.group, lambda serial: install_apk(client, serial, str(args.apk)))
    if args.subcommand == "app":
        action = launch_app if args.action == "launch" else close_app
        return _run_on_targets(client, args.group, lambda serial: action(client, serial, args.package))
    if args.subcommand == "screenshot":
        return screenshot_command(client, args.output, args.group)
    if args.subcommand == "reconnect":
        return _run_on_targets(client, args.group, lambda serial: client.reconnect(serial))
    if args.subcommand == "account" and args.account_action == "import":
        return account_import_command(client, args.file, args.group)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())