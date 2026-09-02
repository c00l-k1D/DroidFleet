import argparse
import shlex
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adb.client import AdbClient
from app.adb.commands import shell


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
    targets = _select_devices(client, group)
    if not targets:
        print("Нет подходящих подключённых устройств.", file=sys.stderr)
        return 1
    failed = 0
    for serial, _ in targets:
        result = client.run(shell(["reboot"]), serial, timeout=10)
        print(f"{serial}: {'OK' if result.returncode == 0 else 'ERROR'}")
        failed += result.returncode != 0
    return 1 if failed else 0


def build_parser():
    parser = argparse.ArgumentParser(prog="droidfleet", description="Управление Android-устройствами через ADB")
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("devices", help="Показать подключённые устройства")
    exec_parser = subparsers.add_parser("exec", help="Выполнить shell-команду")
    selection = exec_parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="Выполнить на всех online-устройствах")
    selection.add_argument("--group", help="Фильтр по производителю, например samsung")
    exec_parser.add_argument("shell_command", help="Команда Android shell в кавычках")
    reboot_parser = subparsers.add_parser("reboot", help="Перезагрузить устройства")
    reboot_parser.add_argument("--group", required=True, help="Производитель, например samsung")
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
    if args.subcommand == "exec":
        return exec_command(client, args.shell_command, args.group)
    return reboot_command(client, args.group)


if __name__ == "__main__":
    raise SystemExit(main())