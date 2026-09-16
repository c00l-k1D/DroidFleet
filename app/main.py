import sys
import time
import base64
import hashlib
import io
import json
import subprocess
import socket
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageTk

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config
from app.connection import ConnectionProfile
from app.accounts.repository import AccountRepository
from app.agent_server import AgentServer, AgentStore
from app.ngrok import NgrokTunnel
from app.devices.registry import DeviceRegistry
from app.fleet_logging import FleetLogger
from app.adb.client import AdbClient
from app.adb.device import adb_transport
from app.adb.monitor import DeviceMonitor
from app.adb.reconnect import ReconnectService
from app.actions.batch import BatchExecutor
from app.actions.input import send_keyevent, send_text, send_tap, send_swipe, send_zoom
from app.adb.commands import screencap
from app.actions.coordinates import normalize_to_device
from app.actions.apps import cleanup_app, close_app, install_apk, launch_app, logcat, push_account_file, run_shell, uninstall_app
from app.ui.dashboard import Dashboard
from app.ui.dialogs import error, warning
from app.ui.toolbar import Toolbar
from app.ui.log_viewer import LogViewer
from app.video.preview import PreviewService
from app.video.stream import ScrcpyStream
from app.tasks.repository import TaskRepository


class AndroidController:
    @staticmethod
    def local_agent_base_url() -> str:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("192.0.2.1", 80))
            address = probe.getsockname()[0]
            probe.close()
        except OSError:
            address = socket.gethostbyname(socket.gethostname())
        return f"http://{address}:{config.AGENT_SERVER_PORT}/api/agent"

    def __init__(self, root):
        self.root = root
        self.logger = FleetLogger()
        self.account_repository = AccountRepository(config.ACCOUNTS_FILE)
        self.device_registry = DeviceRegistry(config.DEVICES_FILE)
        root.title("DroidFleet")
        root.geometry("1450x900")
        root.minsize(1100, 700)
        self.client = AdbClient()
        self.scrcpy = ScrcpyStream(
            ScrcpyStream.find(Path(__file__).resolve().parents[1]),
            self.client.executable,
        )
        self.devices = []
        self.hardware_info = {}
        self.group_filter = "Все устройства"
        self.group_mode = "Без групп"
        self.selected = None
        self.selected_devices = set()
        self.selected_agents = set()
        self.android_embedded_serial = None
        self.android_embedded_label = None
        self.android_embedded_host = None
        self.preview_images = {}
        self.preview = PreviewService(root, self.client, self.update_preview, self.preview_failed, config.PREVIEW_WIDTH, config.PREVIEW_HEIGHT, config.PREVIEW_WORKERS)
        self.commands = BatchExecutor(config.COMMAND_WORKERS)
        self.input_executor = ThreadPoolExecutor(max_workers=1)
        self.hardware_executor = ThreadPoolExecutor(max_workers=config.PREVIEW_WORKERS)
        self.reconnect_executor = ThreadPoolExecutor(max_workers=2)
        self.monitor_executor = ThreadPoolExecutor(max_workers=1)
        self._monitor_busy = False
        self._last_hardware_refresh = {}
        self.task_repository = TaskRepository(config.TASKS_FILE)
        self.tasks = self.task_repository.load()
        self.language = config.LANGUAGE if config.LANGUAGE in ("Русский", "English") else "Русский"
        self.reconnect = ReconnectService(self.client, self.logger)
        self.monitor = DeviceMonitor(self.client, self._on_devices_changed)
        self.agent_server = None
        self.ngrok = None
        self.connection_profile = ConnectionProfile.from_value(config.CONNECTION_MODE)
        style = ttk.Style(root)
        style.configure("Sidebar.TFrame", background="#eef2f5")
        style.configure("Sidebar.TLabel", background="#eef2f5", foreground="#4b5a66")
        style.configure("Sidebar.TLabelframe", background="#eef2f5", bordercolor="#d7e0e6")
        style.configure("Sidebar.TLabelframe.Label", background="#eef2f5", foreground="#34424d")
        style.configure("Sidebar.TButton", padding=(8, 5), font=("Segoe UI", 9))
        style.configure("Sidebar.TCheckbutton", background="#eef2f5", foreground="#4b5a66")
        style.configure("Sidebar.TRadiobutton", background="#eef2f5", foreground="#4b5a66")
        root.configure(bg="#0b1117")
        header = tk.Frame(root, bg="#101923", height=58)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="DROIDFLEET", bg="#101923", fg="#f1f7fb", font=("Segoe UI", 16, "bold")).pack(side="left", padx=20)
        self.server_status = tk.Label(header, text="● SERVER STARTING", bg="#101923", fg="#ffd34d", font=("Segoe UI", 10, "bold"))
        self.server_status.pack(side="right", padx=20)
        tk.Button(
            header, text="РУКОВОДСТВО / GUIDE", command=self.show_guide,
            bg="#246c70", fg="#ffffff", relief="flat", padx=10, pady=5,
        ).pack(side="right", padx=(0, 12))
        try:
            update_file = Path(__file__).resolve().parents[1] / "dist" / "FarmAgent.exe"
            self.agent_server = AgentServer((config.AGENT_SERVER_HOST, config.AGENT_SERVER_PORT), AgentStore(config.AGENT_STALE_AFTER), update_file)
            self.agent_server.store.set_process_definitions(config.PROCESS_DEFINITIONS)
            self.agent_server.start_background()
            self.server_status.config(text="● SERVER OK", fg="#51d88a")
            if self.connection_profile.requires_tunnel:
                self.ngrok = NgrokTunnel(config.AGENT_SERVER_PORT, authtoken=config.NGROK_AUTHTOKEN, region=config.NGROK_REGION)
                public_url = self.ngrok.start()
                self.connection_profile.configure_store(self.agent_server.store, self.local_agent_base_url(), public_url)
                self.server_status.config(text=f"● {self.connection_profile.label} {public_url}", fg="#51d88a")
                self.logger.info(f"Ngrok endpoint: {public_url}/api/agent/heartbeat")
            else:
                self.connection_profile.configure_store(self.agent_server.store, self.local_agent_base_url())
        except (OSError, RuntimeError) as exc:
            self.logger.error(f"Не удалось запустить сервер агентов: {exc}")
            self.server_status.config(text="● SERVER ERROR", fg="#ff9f43")
        if self.agent_server and self.agent_server.store.agent_base_url():
            self.logger.info(f"{self.connection_profile.label} FarmAgent endpoint: {self.agent_server.store.agent_base_url()}/heartbeat")
        workspace = tk.Frame(root, bg="#0b1117")
        workspace.pack(side="top", fill="both", expand=True)
        left = tk.Frame(workspace, bg="#eef2f5"); left.pack(side="left", fill="y", padx=(12, 0), pady=12)
        self.toolbar = Toolbar(left, self)
        self.toolbar.set_language(self.language)
        self.dashboard = Dashboard(workspace, self)
        self.restore_saved_devices()
        self.refresh_devices()
        root.after(1000, self.agent_monitor_loop)
        root.after(config.DEVICE_CHECK_INTERVAL, self.device_monitor_loop)
        root.after(250, self.preview_loop)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def device_monitor_loop(self):
        if self.preview.running:
            self.refresh_devices()
            self.root.after(config.DEVICE_CHECK_INTERVAL, self.device_monitor_loop)

    def refresh_devices(self):
        if not self.client.executable:
            self.toolbar.status.config(text="ADB не найден")
            self.logger.error("ADB не найден")
            return
        if self._monitor_busy:
            return
        self._monitor_busy = True
        self.monitor_executor.submit(self._refresh_devices_worker)

    def agent_monitor_loop(self):
        if self.agent_server:
            agents = self.agent_server.store.list()
            current = {str(agent.get("device_id")): agent for agent in agents if agent.get("device_id")}
            for device_id, record in current.items():
                self.dashboard.add_agent(record)
            for device_id in set(self.dashboard.agent_cards) - set(current):
                self.dashboard.remove_agent(device_id)
                self.selected_agents.discard(device_id)
        if self.root.winfo_exists():
            self.root.after(2000, self.agent_monitor_loop)

    def build_farm_agent(self):
        script = Path(__file__).resolve().parents[1] / "build_agent.ps1"
        if not script.exists():
            error("FarmAgent", "Файл сборки build_agent.ps1 не найден.")
            return
        server_url = ""
        if self.connection_profile.requires_agent_url:
            public_url = (self.ngrok.public_url if self.ngrok else "") or ""
            initial_url = self.connection_profile.build_agent_url(public_url)
            server_url = simpledialog.askstring(
                "FarmAgent connection",
                "Ссылка для подключения агента:",
                initialvalue=initial_url,
                parent=self.root,
            )
            if not server_url:
                return
            server_url = server_url.strip().rstrip("/")
            if not self.connection_profile.validate_agent_url(server_url):
                error("FarmAgent", "Укажите ссылку вида https://домен/api/agent/heartbeat")
                return
        self._set_status("Сборка FarmAgent запущена...")

        def build():
            return subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                cwd=str(script.parent), capture_output=True, text=True, check=False,
            )

        def finished(result):
            output = (result.stdout + "\n" + result.stderr).strip()
            if result.returncode == 0:
                launcher = script.parent / "dist" / "FarmAgent-start.cmd"
                if server_url:
                    launcher.parent.mkdir(parents=True, exist_ok=True)
                    launcher.write_text(
                        "@echo off\n"
                        "cd /d \"%~dp0\"\n"
                        f'start "FarmAgent" "%~dp0FarmAgent.exe" --server "{server_url}"\n',
                        encoding="utf-8",
                    )
                self.logger.info(output or "FarmAgent собран")
                self._set_status("FarmAgent собран: dist/FarmAgent.exe")
                message = "Агент собран в dist/FarmAgent.exe"
                if server_url:
                    message += f"\n\nСоздан запускатель dist/FarmAgent-start.cmd ({self.connection_profile.label})."
                messagebox.showinfo("FarmAgent", message)
            else:
                self.logger.error(output or "Сборка FarmAgent завершилась ошибкой")
                error("FarmAgent", "Сборка не удалась. Подробности записаны в журнал.")

        future = self.hardware_executor.submit(build)
        future.add_done_callback(lambda completed: self.root.after(0, lambda: finished(completed.result())))

    def build_linux_farm_agent(self):
        script = Path(__file__).resolve().parents[1] / "build_agent.sh"
        if not script.exists():
            error("Linux FarmAgent", "Файл сборки build_agent.sh не найден.")
            return
        bash = shutil.which("bash")
        wsl = shutil.which("wsl.exe")
        if not bash and not wsl:
            error("Linux FarmAgent", "Для сборки нужен Bash или WSL. Запустите build_agent.sh на Linux.")
            return
        server_url = simpledialog.askstring(
            "Linux FarmAgent connection",
            "Ссылка для подключения Linux-агента:",
            initialvalue=self.connection_profile.build_agent_url(
                (self.ngrok.public_url if self.ngrok else "") or ""
            ),
            parent=self.root,
        )
        if not server_url:
            return
        server_url = server_url.strip().rstrip("/")
        if not self.connection_profile.validate_agent_url(server_url):
            error("Linux FarmAgent", "Укажите ссылку вида https://домен/api/agent/heartbeat")
            return
        self._set_status("Сборка Linux FarmAgent запущена...")

        def build():
            if bash:
                command = [bash, str(script)]
                cwd = str(script.parent)
            else:
                linux_path = subprocess.run(
                    [wsl, "wslpath", "-a", str(script.parent)],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
                command = [wsl, "bash", f"{linux_path}/build_agent.sh"]
                cwd = None
            return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)

        def finished(result):
            output = (result.stdout + "\n" + result.stderr).strip()
            if result.returncode != 0:
                self.logger.error(output or "Сборка Linux FarmAgent завершилась ошибкой")
                error(
                    "Linux FarmAgent",
                    "Сборка не удалась.\n\n"
                    f"{output[-3000:] or 'Команда не вернула подробности.'}",
                )
                return
            launcher = script.parent / "dist" / "FarmAgent-linux-start.sh"
            launcher.write_text(
                "#!/usr/bin/env bash\n"
                "set -e\n"
                "cd \"$(dirname \"$0\")\"\n"
                f'export DROIDFLEET_SERVER="{server_url}"\n'
                "exec ./FarmAgent-linux\n",
                encoding="utf-8",
            )
            self.logger.info(output or "Linux FarmAgent собран")
            self._set_status("Linux FarmAgent собран: dist/FarmAgent-linux")
            messagebox.showinfo(
                "Linux FarmAgent",
                "Агент собран в dist/FarmAgent-linux.\n"
                "Скопируйте бинарник и FarmAgent-linux-start.sh на Linux-PC.",
            )

        future = self.hardware_executor.submit(build)
        future.add_done_callback(lambda completed: self.root.after(0, lambda: finished(completed.result())))

    def build_android_farm_agent(self):
        script = Path(__file__).resolve().parents[1] / "build_android_agent.ps1"
        if not script.exists():
            error("Android FarmAgent", "Файл сборки build_android_agent.ps1 не найден.")
            return
        server_url = simpledialog.askstring(
            "Android FarmAgent",
            "Ссылка сервера для APK (/api/agent/heartbeat):",
            initialvalue=self.connection_profile.build_agent_url((self.ngrok.public_url if self.ngrok else "") or ""),
            parent=self.root,
        )
        if not server_url:
            return
        server_url = server_url.strip().rstrip("/")
        if not self.connection_profile.validate_agent_url(server_url):
            error("Android FarmAgent", "Укажите ссылку вида https://домен/api/agent/heartbeat")
            return
        self._set_status("Сборка Android APK запущена...")

        def build():
            return subprocess.run(
                [
                    "powershell", "-ExecutionPolicy", "Bypass", "-File", str(script),
                    "-ServerUrl", server_url,
                ],
                cwd=str(script.parent), capture_output=True, text=True, check=False,
            )

        def finished(result):
            output = (result.stdout + "\n" + result.stderr).strip()
            if result.returncode == 0:
                apk = script.parent / "android-agent" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
                self.logger.info(output or "Android FarmAgent APK собран")
                self._set_status(f"Android APK собран: {apk}")
                messagebox.showinfo("Android FarmAgent", f"APK собран:\n{apk}")
            else:
                self.logger.error(output or "Сборка Android APK завершилась ошибкой")
                error("Android FarmAgent", "Сборка APK не удалась. Проверьте Android Studio/Gradle и журнал.")

        future = self.hardware_executor.submit(build)
        future.add_done_callback(lambda completed: self.root.after(0, lambda: finished(completed.result())))

    def _refresh_devices_worker(self):
        try:
            devices = [
                serial for serial, state in self.client.device_states()
                if state == "device" and self._android_transport_allowed(serial)
            ]
            self.root.after(0, lambda: self._on_devices_changed(devices))
        except Exception as exc:
            self.logger.error(f"Ошибка обновления устройств: {exc}")
        finally:
            self._monitor_busy = False

    def restore_saved_devices(self):
        for serial, record in self.device_registry.records.items():
            if serial not in self.dashboard.cards:
                self.dashboard.add(serial)
            record.status = "ONLINE" if serial in self.devices else "OFFLINE"
            self.dashboard.cards[serial].update_device(record)
        self.dashboard._update_summary()

    @staticmethod
    def android_connection_label(serial):
        return adb_transport(serial)

    def _android_transport_allowed(self, serial):
        record = self.device_registry.get_or_create(serial)
        mode = record.transport_mode if record.transport_mode in {"auto", "usb", "wifi"} else config.ANDROID_CONNECTION_MODE
        return mode == "auto" or (mode == "usb" and adb_transport(serial) == "ADB USB") or (
            mode == "wifi" and adb_transport(serial) == "ADB WI-FI"
        )

    def _on_devices_changed(self, devices):
        old = set(self.devices); current = set(devices); self.devices = devices
        for serial in old - current:
            self.logger.warning(f"Устройство отключилось: {serial}")
            record = self.device_registry.get_or_create(serial)
            record.status = "OFFLINE"
            self.device_registry.save()
            card = self.dashboard.cards.get(serial)
            if card:
                card.update_device(record)
            self.preview_images.pop(serial, None); self.hardware_info.pop(serial, None); self.selected_devices.discard(serial)
            # Clear device resolution cache
            if serial in self.preview.device_resolutions:
                del self.preview.device_resolutions[serial]
            self.reconnect_executor.submit(self.reconnect.reconnect, serial)
        for serial in current - old:
            self.logger.info(f"Устройство подключено: {serial}")
            record = self.device_registry.get_or_create(serial)
            record.status = "ONLINE"
            record.last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.device_registry.save()
            if serial not in self.dashboard.cards:
                self.dashboard.add(serial)
            self.dashboard.cards[serial].update_device(record)
        if self.selected not in current: self.selected = None
        self.toolbar.count.config(text=f"ADB ONLINE: {len(devices)}")
        self.update_card_selection()
        now = time.monotonic()
        for serial in devices:
            if serial not in old or now - self._last_hardware_refresh.get(serial, 0) >= config.HARDWARE_REFRESH_INTERVAL:
                self._last_hardware_refresh[serial] = now
                self.hardware_executor.submit(self._load_hardware, serial)
        self.dashboard._update_summary()
        self._set_status()

    def _load_hardware(self, serial):
        try:
            info = self.client.hardware_info(serial)
            resolution = self._parse_resolution(info.screen)
            self.root.after(0, lambda: self._apply_hardware(serial, info, resolution))
        except Exception as exc:
            self.logger.error(f"Ошибка чтения данных {serial}: {exc}")
            self.root.after(0, lambda: self._mark_device_error(serial))

    def _mark_device_error(self, serial):
        record = self.device_registry.get_or_create(serial)
        record.status = "OFFLINE" if serial not in self.devices else "ERROR"
        card = self.dashboard.cards.get(serial)
        if card:
            card.update_device(record)

    @staticmethod
    def _parse_resolution(screen):
        try:
            width, height = str(screen).lower().split("x", 1)
            return int(width), int(height)
        except (TypeError, ValueError):
            return None

    def _apply_hardware(self, serial, info, resolution=None):
        card = self.dashboard.cards.get(serial)
        if card and serial in self.devices:
            self.hardware_info[serial] = info
            record = self.device_registry.get_or_create(serial)
            record.status = "ONLINE"
            record.model = info.model
            record.os = info.android_version
            record.sdk = info.sdk
            record.battery = info.battery
            record.cpu = info.cpu
            record.ram = info.ram
            record.storage = info.storage
            record.temperature = info.temperature
            record.ip = info.ip
            record.last_seen = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.device_registry.save()
            card.update_hardware(info)
            card.update_device(record)
            self._update_groups()
            
            # Use one fixed preview canvas so every grid card has the same size.
            self.preview.set_device_resolution(serial, config.PREVIEW_WIDTH, config.PREVIEW_HEIGHT)

    def _update_groups(self):
        groups = set(self.device_registry.groups())
        manufacturers = set()
        for record in self.device_registry.records.values():
            groups.update(record.tags)
        for info in self.hardware_info.values():
            if info.manufacturer != "--":
                manufacturers.add(info.manufacturer)
                groups.add(info.manufacturer)
            if info.manufacturer != "--" and info.model != "--":
                groups.add(f"{info.manufacturer} {info.model}")
        self.toolbar.set_groups(groups)
        self.toolbar.set_manufacturers(manufacturers)

    def set_group_filter(self, group):
        self.group_filter = group
        self.apply_filters()

    def apply_filters(self):
        self.dashboard.set_filter(self._matches_device)

    def set_group_mode(self, mode):
        self.group_mode = mode
        self.dashboard.set_grouping(self._device_group)

    def _matches_device(self, serial):
        record = self.device_registry.get_or_create(serial)
        info = self.hardware_info.get(serial)
        manufacturer = info.manufacturer if info else "--"
        status = record.status if serial in self.devices else "OFFLINE"
        selected_manufacturer = self.toolbar.manufacturer_var.get()
        selected_group = self.toolbar.group_var.get()
        selected_status = self.toolbar.status_var.get()
        search = self.toolbar.search_var.get().strip().casefold()
        if selected_manufacturer != "Все устройства" and manufacturer != selected_manufacturer:
            return False
        if selected_group != "Все группы" and selected_group not in (record.group, *record.tags):
            return False
        if selected_status != "Все статусы" and status != selected_status:
            return False
        haystack = " ".join((record.display_name, record.serial, record.device_id, record.model, manufacturer, *record.tags)).casefold()
        return not search or search in haystack

    def _device_group(self, serial):
        info = self.hardware_info.get(serial)
        if not info or self.group_mode == "Без групп":
            return None
        return info.manufacturer if self.group_mode == "Производитель" else info.model

    def _matches_group(self, serial):
        if self.group_filter == "Все устройства":
            return True
        info = self.hardware_info.get(serial)
        record = self.device_registry.get_or_create(serial)
        values = [record.group, *record.tags]
        if info:
            values.extend((info.manufacturer, f"{info.manufacturer} {info.model}"))
        return self.group_filter in values

    def toggle_device_selection(self, serial):
        if serial in self.selected_devices: self.selected_devices.remove(serial)
        else: self.selected_devices.add(serial)
        self.selected = serial; self.update_card_selection()
        self._set_status(f"Последнее: {serial}")

    def toggle_agent_selection(self, device_id):
        if device_id in self.selected_agents:
            self.selected_agents.remove(device_id)
        else:
            self.selected_agents.add(device_id)
        self.dashboard.rebuild()
        self._set_status(f"Выбрано FarmAgent: {len(self.selected_agents)}")

    def update_agent_selection(self):
        self.dashboard.rebuild()

    @staticmethod
    def _show_context_menu(menu, event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def show_android_context_menu(self, serial, event):
        self.selected_devices = {serial}
        self.selected = serial
        self.update_card_selection()
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Открыть scrcpy", command=lambda: self.open_device_scrcpy(serial))
        menu.add_command(label="Переподключить устройство", command=lambda: self.reconnect_selected([serial]))
        menu.add_command(label="Отключить устройство", command=lambda: self.disconnect_device(serial))
        menu.add_command(label="Удалить устройство", command=lambda: self.delete_device(serial))
        menu.add_separator()
        menu.add_command(label="Открыть подробности", command=lambda: self.show_device_details(serial))
        menu.add_command(label="Добавить задание", command=self.show_tasks_view)
        menu.add_command(label="Создать группу", command=self.show_groups_view)
        self._show_context_menu(menu, event)

    def disconnect_device(self, serial):
        if adb_transport(serial) != "ADB WI-FI":
            warning("ADB", "USB-устройство нельзя программно отключить через ADB. Отсоедините кабель.")
            return
        self.commands.run([serial], lambda value: self.client.disconnect(value))
        self._set_status(f"ADB disconnect отправлен: {serial}")

    def delete_device(self, serial):
        if not messagebox.askyesno("Удалить устройство", f"Удалить {serial} из сохранённых устройств?", parent=self.root):
            return
        self.device_registry.delete(serial)
        self.devices = [item for item in self.devices if item != serial]
        self.selected_devices.discard(serial)
        self.preview_images.pop(serial, None)
        self.hardware_info.pop(serial, None)
        self.dashboard.remove(serial)
        self.update_card_selection()
        self._set_status(f"Устройство удалено: {serial}")

    def show_windows_context_menu(self, device_id, event):
        self.selected_agents = {device_id}
        self.update_agent_selection()
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Открыть подробности", command=lambda: self.show_windows_view(device_id))
        menu.add_command(label="Открыть live view", command=lambda: self.show_windows_view(device_id, "LIVE VIEW"))
        menu.add_command(label="Remote access", command=lambda: self.show_windows_view(device_id, "REMOTE ACCESS"))
        menu.add_command(label="Screenshot", command=lambda: self.show_windows_view(device_id, "SCREENSHOT"))
        menu.add_command(label="Logs", command=lambda: self.show_windows_view(device_id, "GET_LOGS"))
        menu.add_separator()
        menu.add_command(label="Добавить задание", command=self.show_tasks_view)
        menu.add_command(label="Создать группу", command=self.show_groups_view)
        self._show_context_menu(menu, event)

    def show_device_details(self, serial):
        record = self.device_registry.get_or_create(serial)
        window = tk.Toplevel(self.root)
        window.title(f"DroidFleet - {record.display_name}")
        window.geometry("460x560")
        body = tk.Frame(window, padx=18, pady=14)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=record.display_name, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        status = tk.Label(body, text=f"● {record.status}", fg="#42ff42" if record.status == "ONLINE" else "#ff9f43", font=("Segoe UI", 10, "bold"))
        status.pack(anchor="w", pady=(2, 12))
        details = tk.Label(body, justify="left", anchor="w", font=("Consolas", 9))
        details.pack(fill="x")
        details.config(text=(f"General\nName       {record.display_name}\nID         {record.device_id}\nType       {record.device_type}\nModel      {record.model}\nOS         {record.os}\nIP         {record.ip}\nConnection {self.android_connection_label(serial)}\n\nSystem\nBattery    {record.battery}\nCPU        {record.cpu}\nRAM        {record.ram}\nTemperature {record.temperature}\nLast Seen  {record.last_seen}\n\nOrganization\nGroup      {record.group}\nTags       {', '.join(record.tags) or '--'}"))
        editor = tk.Frame(body)
        editor.pack(fill="x", pady=14)
        name_var, group_var, tags_var = tk.StringVar(value=record.name), tk.StringVar(value=record.group), tk.StringVar(value=", ".join(record.tags))
        transport_var = tk.StringVar(value=record.transport_mode or config.ANDROID_CONNECTION_MODE)
        for label, variable in (("Name", name_var), ("Group", group_var), ("Tags", tags_var)):
            tk.Label(editor, text=label).pack(anchor="w")
            tk.Entry(editor, textvariable=variable).pack(fill="x", pady=(0, 4))
        tk.Label(editor, text="Android connection preference").pack(anchor="w")
        ttk.Combobox(editor, textvariable=transport_var, state="readonly", values=("auto", "usb", "wifi")).pack(fill="x", pady=(0, 4))
        def save():
            record.name = name_var.get().strip()
            record.group = group_var.get().strip() or "Без группы"
            record.tags = [tag.strip() for tag in tags_var.get().split(",") if tag.strip()]
            record.transport_mode = transport_var.get()
            self.device_registry.save()
            self.refresh_devices()
            self.dashboard.cards.get(serial) and self.dashboard.cards[serial].update_device(record)
            self._update_groups()
            window.destroy()
        buttons = tk.Frame(body)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Edit / Save", command=save).pack(side="left")
        ttk.Button(buttons, text="Screenshot", command=self.capture_selected_screenshots).pack(side="left", padx=6)
        ttk.Button(buttons, text="Reconnect", command=lambda: self.reconnect_selected([serial])).pack(side="left")

    def capture_selected_screenshots(self):
        targets = self.get_targets()
        if not targets:
            warning("Screenshot", "Нет выбранных устройств.")
            return
        target_dir = config.DATA_DIR / "screenshots"
        target_dir.mkdir(parents=True, exist_ok=True)
        self.commands.run(targets, lambda serial: self._screenshot_worker(serial, target_dir))
        self._set_status(f"Screenshot отправлен: {len(targets)}")

    def _screenshot_worker(self, serial, target_dir):
        try:
            result = self.client.run(screencap(), serial, timeout=5)
            if result.returncode == 0 and result.stdout:
                (target_dir / f"{serial}.png").write_bytes(result.stdout)
                self.logger.info(f"Screenshot сохранён: {serial}")
        except (OSError, RuntimeError, TimeoutError) as exc:
            self.logger.error(f"Screenshot {serial}: {exc}")

    def mass_restart(self):
        targets = self.get_targets()
        if not targets:
            warning("Restart", "Нет выбранных устройств.")
            return
        self.commands.run(targets, lambda serial: self.client.run(["shell", "reboot"], serial, timeout=10))
        self._set_status(f"Restart отправлен: {len(targets)}")

    def reconnect_selected(self, targets=None):
        targets = targets or self.get_targets()
        if not targets:
            warning("Reconnect", "Нет выбранных устройств.")
            return
        self.reconnect_executor.submit(lambda: [self.reconnect.reconnect(serial) for serial in targets])
        self._set_status(f"Reconnect отправлен: {len(targets)}")

    def update_card_selection(self):
        for serial, card in self.dashboard.cards.items():
            card.set_selected(serial in self.selected_devices)

    def select_all(self):
        self.selected_devices = set(self.devices); self.update_card_selection(); self._set_status(f"Выбрано всех: {len(self.selected_devices)}")

    def clear_selection(self):
        self.selected_devices.clear(); self.selected = None; self.update_card_selection(); self._set_status()

    def _set_status(self, extra=""):
        selected = f"Выбрано: {len(self.selected_devices)}\n" if self.selected_devices else ""
        self.toolbar.status.config(text=f"{selected}{extra or f'ADB ONLINE: {len(self.devices)}'}")

    def get_targets(self, force_all=False):
        if force_all or self.toolbar.target_var.get() == "ALL": return list(self.devices)
        return [serial for serial in self.selected_devices if serial in self.devices]

    def mass_keyevent(self, key):
        targets = self.get_targets()
        if not targets: warning("ADB", "Нет устройств для выполнения команды."); return
        self.logger.info(f"Команда {key} отправлена на {len(targets)} устройств")
        self.commands.run(targets, lambda serial: send_keyevent(self.client, serial, key)); self._set_status(f"{key}\nОтправлено: {len(targets)}")

    def send_text_to_selected(self):
        text = simpledialog.askstring("Ввод текста", "Текст для активного поля:", parent=self.root)
        if text is None:
            return
        targets = self.get_targets()
        if not targets:
            warning("Ввод текста", "Нет выбранных устройств.")
            return
        self.commands.run(targets, lambda serial: send_text(self.client, serial, text))
        self._set_status(f"Текст отправлен\nУстройств: {len(targets)}")

    def mass_shell(self, force_all=False):
        command = self.toolbar.command.get().strip(); targets = self.get_targets(force_all)
        if not command: return
        if not targets: warning("ADB", "Нет устройств."); return
        self.logger.info(f"Shell-команда отправлена на {len(targets)} устройств: {command}")
        self.commands.run(targets, lambda serial: run_shell(self.client, serial, command.split())); self._set_status(f"Команда отправлена\nУстройств: {len(targets)}")

    def install_apk(self):
        apk_path = filedialog.askopenfilename(
            title="Выберите APK на компьютере",
            filetypes=(("Android package", "*.apk"), ("Все файлы", "*.*")),
        )
        if not apk_path:
            return
        apk_file = Path(apk_path)
        if apk_file.suffix.lower() != ".apk" or not apk_file.is_file() or apk_file.stat().st_size == 0:
            error("APK", "Выбранный файл не является корректным APK.")
            return
        targets = self.get_targets()
        if not targets:
            warning("ADB", "Нет устройств для установки APK.")
            return
        self.logger.info(f"Начата установка {Path(apk_path).name} на {len(targets)} устройств")
        self.commands.run(targets, lambda serial: self._install_worker(serial, apk_path))
        self._set_status(f"Установка APK отправлена\nУстройств: {len(targets)}")

    def _install_worker(self, serial, apk_path):
        try:
            result = install_apk(self.client, serial, apk_path)
            output = result.stdout.decode(errors="replace").strip()
            if result.returncode == 0:
                self.logger.info(f"APK установлено на {serial}: {output or 'Success'}")
                self.root.after(0, lambda: self._set_status(f"APK установлено: {serial}"))
            else:
                details = result.stderr.decode(errors="replace").strip()
                self.logger.error(f"Ошибка установки APK на {serial}: {details or output or result.returncode}")
                self.root.after(0, lambda: error("APK", f"{serial}: {details or output or result.returncode}"))
        except Exception as exc:
            self.logger.error(f"Ошибка установки APK на {serial}: {exc}")
            self.root.after(0, lambda: error("APK", f"{serial}: {exc}"))

    def import_accounts(self):
        file_path = filedialog.askopenfilename(
            title="Выберите файл аккаунтов",
            filetypes=(("Файлы аккаунтов", "*.json *.csv *.txt *.xml"), ("Все файлы", "*.*")),
        )
        if not file_path:
            return
        targets = self.get_targets()
        if not targets:
            warning("Аккаунты", "Нет устройств для импорта файла аккаунтов.")
            return
        self.account_repository.add_import(Path(file_path), targets)
        self.logger.info(f"Начат импорт файла аккаунтов {Path(file_path).name} на {len(targets)} устройств")
        self.commands.run(targets, lambda serial: self._account_worker(serial, file_path))
        self._set_status(f"Импорт аккаунтов отправлен\nУстройств: {len(targets)}")

    def _account_worker(self, serial, file_path):
        try:
            result = push_account_file(self.client, serial, file_path)
            output = result.stdout.decode(errors="replace").strip()
            if result.returncode == 0:
                self.logger.info(f"Файл аккаунтов передан на {serial}: {Path(file_path).name}")
            else:
                details = result.stderr.decode(errors="replace").strip()
                self.logger.error(f"Ошибка импорта аккаунтов на {serial}: {details or output or result.returncode}")
        except Exception as exc:
            self.logger.error(f"Ошибка импорта аккаунтов на {serial}: {exc}")

    def _get_package_name(self):
        package_name = self.toolbar.package_name.get().strip()
        if not package_name or package_name == "com.example.app":
            warning("Приложение", "Укажите package name приложения, например com.android.settings.")
            return None
        return package_name

    def launch_app(self):
        package_name = self._get_package_name()
        targets = self.get_targets()
        if not package_name or not targets:
            if package_name and not targets:
                warning("Приложение", "Нет устройств для запуска приложения.")
            return
        self.logger.info(f"Запуск {package_name} на {len(targets)} устройств")
        self.commands.run(targets, lambda serial: self._app_worker(serial, package_name, launch_app, "Запуск"))
        self._set_status(f"Запуск приложения отправлен\nУстройств: {len(targets)}")

    def close_app(self):
        package_name = self._get_package_name()
        targets = self.get_targets()
        if not package_name or not targets:
            if package_name and not targets:
                warning("Приложение", "Нет устройств для закрытия приложения.")
            return
        self.logger.info(f"Закрытие {package_name} на {len(targets)} устройств")
        self.commands.run(targets, lambda serial: self._app_worker(serial, package_name, close_app, "Закрытие"))
        self._set_status(f"Закрытие приложения отправлено\nУстройств: {len(targets)}")

    def uninstall_app(self):
        package_name = self._get_package_name()
        targets = self.get_targets()
        if not package_name or not targets:
            if package_name and not targets:
                warning("Приложение", "Нет устройств для удаления приложения.")
            return
        self.commands.run(targets, lambda serial: self._app_worker(serial, package_name, uninstall_app, "Удаление"))
        self._set_status(f"Удаление приложения отправлено\nУстройств: {len(targets)}")

    def cleanup_app(self):
        package_name = self._get_package_name()
        targets = self.get_targets()
        if not package_name or not targets:
            if package_name and not targets:
                warning("Приложение", "Нет устройств для очистки приложения.")
            return
        self.commands.run(targets, lambda serial: self._app_worker(serial, package_name, cleanup_app, "Очистка данных"))
        self._set_status(f"Очистка данных отправлена\nУстройств: {len(targets)}")

    def show_android_logcat(self):
        targets = self.get_targets()
        if len(targets) != 1:
            warning("Logcat", "Выберите ровно одно Android-устройство.")
            return
        serial = targets[0]
        window = tk.Toplevel(self.root)
        window.title(f"DroidFleet - logcat - {serial}")
        window.geometry("1050x650")
        controls = ttk.Frame(window, padding=8)
        controls.pack(fill="x")
        ttk.Label(controls, text="Filter:").pack(side="left")
        filter_var = tk.StringVar()
        ttk.Entry(controls, textvariable=filter_var, width=35).pack(side="left", padx=5)
        ttk.Label(controls, text="Lines:").pack(side="left")
        lines_var = tk.StringVar(value="500")
        ttk.Entry(controls, textvariable=lines_var, width=8).pack(side="left", padx=5)
        text = tk.Text(window, wrap="none", background="#101010", foreground="#dddddd")
        text.pack(fill="both", expand=True, padx=8)
        status = ttk.Label(window, text=f"Device: {serial}")
        status.pack(anchor="w", padx=8, pady=4)

        def refresh():
            try:
                result = logcat(self.client, serial, int(lines_var.get()), filter_var.get())
                output = result.stdout.decode(errors="replace")
                if result.returncode != 0:
                    output = result.stderr.decode(errors="replace") or output
                text.delete("1.0", "end")
                text.insert("1.0", output or "Logcat пуст.")
                status.config(text=f"{serial}: {len(output.splitlines())} строк")
                self.logger.info(f"Logcat получен: {serial}")
            except (ValueError, OSError, RuntimeError) as exc:
                status.config(text=f"Ошибка: {exc}")
                self.logger.error(f"Ошибка logcat {serial}: {exc}")

        def export():
            path = filedialog.asksaveasfilename(
                title="Экспорт logcat",
                defaultextension=".log",
                filetypes=(("Log files", "*.log"), ("Text files", "*.txt")),
            )
            if path:
                Path(path).write_text(text.get("1.0", "end-1c"), encoding="utf-8")
                status.config(text=f"Сохранено: {path}")

        def clear():
            result = self.client.run(["logcat", "-c"], serial, timeout=15)
            status.config(text="Буфер logcat очищен" if result.returncode == 0 else "Не удалось очистить logcat")

        buttons = ttk.Frame(window, padding=8)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Обновить", command=refresh).pack(side="left")
        ttk.Button(buttons, text="Экспорт", command=export).pack(side="left", padx=5)
        ttk.Button(buttons, text="Очистить буфер", command=clear).pack(side="left")
        refresh()

    def _app_worker(self, serial, package_name, action, action_name):
        try:
            result = action(self.client, serial, package_name)
            output = result.stdout.decode(errors="replace").strip()
            if result.returncode == 0:
                self.logger.info(f"{action_name} {package_name} на {serial}: {output or 'успешно'}")
            else:
                details = result.stderr.decode(errors="replace").strip()
                self.logger.error(f"{action_name} {package_name} на {serial}: {details or output or result.returncode}")
        except Exception as exc:
            self.logger.error(f"Ошибка: {action_name.lower()} {package_name} на {serial}: {exc}")

    def preview_loop(self):
        if not self.preview.running: return
        self.preview.drain_results()
        for serial in self.devices:
            if len(self.preview.busy) >= config.PREVIEW_WORKERS: break
            self.preview.submit(serial)
        self.root.after(int(config.PREVIEW_INTERVAL * 1000), self.preview_loop)

    def update_preview(self, serial, photo):
        card = self.dashboard.cards.get(serial)
        source_size = getattr(photo, "source_size", None)
        if card and source_size:
            card.meta["source_size"] = source_size
        display_photo = ImageTk.PhotoImage(photo, master=self.root)
        self.preview_images[serial] = display_photo
        if card:
            card.screen.config(image=display_photo, text="")
        if serial == self.android_embedded_serial and self.android_embedded_label is not None:
            self.android_embedded_label.config(image=display_photo, text="")
            self.android_embedded_label.image = display_photo
        if card:
            meta = card.meta; meta["frames"] += 1; now = time.monotonic(); elapsed = now - meta.get("last_fps", now)
            if elapsed >= 1:
                meta["video_status"].config(text=f"VIDEO {meta['frames'] / elapsed:.1f} FPS", fg="#42ff42"); meta["frames"] = 0; meta["last_fps"] = now

    def preview_failed(self, serial):
        card = self.dashboard.cards.get(serial)
        if serial == self.android_embedded_serial and self.android_embedded_label is not None:
            self.android_embedded_label.config(image="", text="Не удалось получить кадр через ADB")
        if card and serial not in self.devices:
            card.screen.config(image="", text="OFFLINE")
        self.logger.warning(f"Не удалось получить preview Android: {serial}")

    def handle_device_input(self, serial, action, params):
        """Handle device input events from UI (tap, swipe, zoom)."""
        if serial not in self.devices:
            return
        record = self.device_registry.get_or_create(serial)
        record.status = "BUSY"
        card = self.dashboard.cards.get(serial)
        if card:
            card.update_device(record)
        self.input_executor.submit(self._device_input_worker, serial, action, params)

    def _device_input_worker(self, serial, action, params):
        try:
            if action == "TAP":
                device_x, device_y = normalize_to_device(params["x"], params["y"], self.client, serial)
                send_tap(self.client, serial, device_x, device_y)
            elif action == "SWIPE":
                x1, y1 = normalize_to_device(params["x1"], params["y1"], self.client, serial)
                x2, y2 = normalize_to_device(params["x2"], params["y2"], self.client, serial)
                send_swipe(self.client, serial, x1, y1, x2, y2)
            elif action in {"ZOOM_IN", "ZOOM_OUT"}:
                device_x, device_y = normalize_to_device(params["x"], params["y"], self.client, serial)
                width, _ = self.client.get_device_resolution(serial)
                send_zoom(self.client, serial, device_x, device_y, zoom_in=action == "ZOOM_IN", offset=max(60, width // 18))
            elif action == "KEY":
                send_keyevent(self.client, serial, params["key"])
            elif action == "TEXT":
                send_text(self.client, serial, params["text"])
            record = self.device_registry.get_or_create(serial)
            record.status = "ONLINE"
            self.root.after(0, lambda: self.dashboard.cards.get(serial) and self.dashboard.cards[serial].update_device(record))
            self.logger.info(f"{action} отправлен на {serial}")
        except Exception as exc:
            record = self.device_registry.get_or_create(serial)
            record.status = "ERROR"
            self.root.after(0, lambda: self.dashboard.cards.get(serial) and self.dashboard.cards[serial].update_device(record))
            self.logger.error(f"Ошибка при отправке {action} на {serial}: {exc}")
        finally:
            record = self.device_registry.get_or_create(serial)
            if record.status == "BUSY":
                record.status = "ONLINE" if serial in self.devices else "OFFLINE"
                self.root.after(0, lambda: self.dashboard.cards.get(serial) and self.dashboard.cards[serial].update_device(record))

    def open_device_scrcpy(self, serial):
        self.selected_devices = {serial}
        self.selected = serial
        self.update_card_selection()
        content = self.dashboard.open_embedded_view(f"ANDROID - {serial}")
        self.android_embedded_serial = serial
        self.android_embedded_host = tk.Frame(content, bg="black")
        self.android_embedded_host.pack(fill="both", expand=True, padx=12, pady=12)
        self.android_embedded_host.bind(
            "<Configure>",
            lambda event: self.scrcpy.resize_embedded(self.android_embedded_host.winfo_id()),
        )
        self.android_embedded_label = tk.Label(
            self.android_embedded_host,
            text="Запуск scrcpy...",
            bg="black",
            fg="white",
        )
        self.android_embedded_label.place(relx=0.5, rely=0.5, anchor="center")
        try:
            self.scrcpy.start_embedded(serial)
        except Exception as exc:
            self.android_embedded_label.config(text=f"Не удалось запустить scrcpy:\n{exc}")
            self.logger.error(f"Не удалось запустить встроенный scrcpy для {serial}: {exc}")
            return
        self.root.after(50, lambda: self._embed_scrcpy_window(serial))
        self.root.after(500, lambda: self.scrcpy.resize_embedded(self.android_embedded_host.winfo_id()) if self.android_embedded_host else None)
        self._set_status(f"Встроенный просмотр: {serial}")

    def _embed_scrcpy_window(self, serial):
        if self.android_embedded_serial != serial or not self.android_embedded_host:
            return
        try:
            self.scrcpy.embed(
                self.android_embedded_host.winfo_id(),
                "DroidFleet scrcpy - " + serial,
            )
            if self.android_embedded_label:
                self.android_embedded_label.place_forget()
            self._set_status(f"Встроенный scrcpy: {serial}")
        except RuntimeError as exc:
            if self.scrcpy.process and self.scrcpy.process.poll() is None:
                self.root.after(100, lambda: self._embed_scrcpy_window(serial))
            elif self.android_embedded_label:
                self.android_embedded_label.config(text=f"Не удалось встроить scrcpy:\n{exc}")
                self.logger.error(f"Не удалось встроить scrcpy для {serial}: {exc}")

    def embedded_android_preview_loop(self, serial):
        return

    def on_embedded_view_closed(self):
        self.scrcpy.stop()
        self.android_embedded_serial = None
        self.android_embedded_label = None
        self.android_embedded_host = None

    def start_scrcpy(self):
        if not self.selected:
            if len(self.selected_devices) == 1: self.selected = next(iter(self.selected_devices))
            else: warning("scrcpy", "Выбери одно устройство."); return
        try: self.scrcpy.start(self.selected)
        except Exception as exc: error("scrcpy", str(exc))

    def stop_scrcpy(self): self.scrcpy.stop()

    def show_logs(self):
        LogViewer(self.root, self.logger)

    def show_android_view(self):
        self.toolbar.manufacturer_var.set("Все устройства")
        self.toolbar.group_var.set("Все группы")
        self.toolbar.status_var.set("Все статусы")
        self.toolbar.search_var.set("")
        self.apply_filters()
        self.set_group_mode("Без групп")
        self._set_status("Раздел Android")

    def show_guide(self):
        window = tk.Toplevel(self.root)
        window.title("DroidFleet - Руководство / Guide")
        window.geometry("820x620")
        text = tk.Text(window, wrap="word", bg="#101923", fg="#e7f0f5", padx=18, pady=18)
        text.pack(fill="both", expand=True)
        text.insert("1.0", """РУКОВОДСТВО

Android:
ЛКМ выбирает карточку. ПКМ открывает меню действий.
В меню доступны scrcpy, переподключение, подробности, задания и группы.
Превью Android можно открыть внутри главного окна через «Открыть scrcpy».

Windows / FarmAgent:
ЛКМ выбирает карточку. Двойной ЛКМ открывает управление агентом.
ПКМ открывает меню live view, remote access, screenshot, logs, заданий и групп.
Экран FarmAgent открывается внутри главного окна Dashboard.

GUIDE

Android:
Left click selects a card. Right click opens the action menu.
The menu contains scrcpy, reconnect, details, tasks and groups.
Android preview opens inside the main window via “Open scrcpy”.

Windows / FarmAgent:
Left click selects a card. Double left click opens agent controls.
Right click opens live view, remote access, screenshot, logs, tasks and groups.
The FarmAgent screen is embedded in the main Dashboard window.
""")
        text.config(state="disabled")

    def show_windows_view(self, initial_device_id=None, initial_action=None):
        window = self.dashboard.open_embedded_view("WINDOWS AGENTS")
        window.configure(bg="#101923")
        banner = tk.Frame(window, bg="#172b3a", height=42)
        banner.pack(fill="x", padx=10, pady=(8, 0))
        banner.pack_propagate(False)
        tk.Label(
            banner, text="FARMAGENT CONTROL CENTER",
            bg="#172b3a", fg="#8ee7ff",
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left", padx=12)
        tk.Label(
            banner, text="Select a card with left click • Open actions with right click",
            bg="#172b3a", fg="#b9c8d1",
            font=("Segoe UI", 8),
        ).pack(side="right", padx=12)
        columns = ("device_id", "hostname", "windows", "ip", "cpu", "ram", "status")
        table = ttk.Treeview(window, columns=columns, show="headings")
        headings = {"device_id": "DEVICE_ID", "hostname": "HOSTNAME", "windows": "WINDOWS", "ip": "IP", "cpu": "CPU", "ram": "RAM", "status": "STATUS"}
        for column in columns:
            table.heading(column, text=headings[column])
            table.column(column, width=140, anchor="w")
        table.column("device_id", width=125)
        table.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        controls = ttk.Frame(window, padding=(10, 4))
        controls.pack(fill="x")
        ttk.Label(controls, text="Процесс:").pack(side="left")
        process_var = tk.StringVar(value="Farm Worker")
        ttk.Combobox(controls, textvariable=process_var, state="readonly", values=("Roblox", "Python Bot", "Farm Worker"), width=16).pack(side="left", padx=5)
        result_label = ttk.Label(controls, text="Выберите Windows-агент")
        result_label.pack(side="left", padx=10)

        def open_embedded_result(title):
            table.pack_forget()
            controls.pack_forget()
            viewer = tk.Frame(window, bg="black")
            viewer.pack(fill="both", expand=True)
            toolbar = tk.Frame(viewer, bg="#17232d")
            toolbar.pack(fill="x")
            close_action = {"callback": None}
            ttk.Button(
                toolbar, text="< BACK TO AGENTS",
                command=lambda: close_action["callback"]() if close_action["callback"] else close_embedded_result(viewer),
            ).pack(side="left", padx=8, pady=5)
            tk.Label(toolbar, text=title, bg="#17232d", fg="#f1f7fb", font=("Segoe UI", 10, "bold")).pack(side="left", padx=8)
            return viewer, close_action

        def close_embedded_result(viewer):
            viewer.destroy()
            table.pack(fill="both", expand=True, padx=10, pady=(10, 5))
            controls.pack(fill="x")

        def selected_id():
            selection = table.selection()
            return table.item(selection[0], "values")[0] if selection else initial_device_id

        def send_command(command):
            device_id = selected_id()
            if not device_id:
                result_label.config(text="Сначала выберите агента")
                return
            try:
                item = self.agent_server.store.queue_command(device_id, command, process_var.get())
                status = "Обновление загружается и проверяется" if command == "UPDATE" else f"{command} отправлен через Agent"
                result_label.config(text=status)
                window.after(500, lambda: wait_result(item["command_id"], device_id, command))
            except (AttributeError, ValueError) as exc:
                result_label.config(text=str(exc))

        def send_file():
            device_id = selected_id()
            if not device_id:
                result_label.config(text="Сначала выберите агента")
                return
            source = filedialog.askopenfilename(parent=window, title="Выберите файл для отправки")
            if not source:
                return
            source_path = Path(source)
            try:
                raw = source_path.read_bytes()
            except OSError as exc:
                result_label.config(text=f"Не удалось прочитать файл: {exc}")
                return
            if len(raw) > 50 * 1024 * 1024:
                result_label.config(text="Файл больше 50 МБ")
                return
            destination = simpledialog.askstring(
                "Передача файла",
                "Путь на удалённом ПК (пусто = Downloads):",
                initialvalue="",
                parent=window,
            )
            if destination is None:
                return
            params = {
                "name": source_path.name,
                "destination": destination.strip(),
                "content": base64.b64encode(raw).decode("ascii"),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            try:
                item = self.agent_server.store.queue_command(device_id, "SEND_FILE", params=params)
                result_label.config(text=f"[FILE] отправка {source_path.name} ({len(raw)} байт)...")
                window.after(500, lambda: wait_result(item["command_id"], device_id, "SEND_FILE"))
            except (AttributeError, ValueError) as exc:
                result_label.config(text=str(exc))

        def wait_result(command_id, device_id, command, attempts=0):
            if not window.winfo_exists():
                return
            result = next((item for item in reversed(self.agent_server.store.results()) if item.get("command_id") == command_id), None) if self.agent_server else None
            if result:
                if result.get("error"):
                    result_label.config(text=f"ERROR: {result['error']}")
                elif command == "SCREENSHOT":
                    encoded = self.agent_server.store.screenshot(device_id)
                    if encoded:
                        image = Image.open(io.BytesIO(base64.b64decode(encoded)))
                        image.thumbnail((900, 600))
                        viewer, _ = open_embedded_result(f"{device_id} - SCREENSHOT")
                        photo = ImageTk.PhotoImage(image)
                        label = tk.Label(viewer, image=photo, bg="black")
                        label.image = photo
                        label.pack(fill="both", expand=True, padx=10, pady=10)
                        result_label.config(text="SCREENSHOT получен")
                elif command == "GET_LOGS":
                    viewer, _ = open_embedded_result(f"{device_id} - LOGS")
                    text = tk.Text(viewer, width=110, height=25)
                    text.pack(fill="both", expand=True, padx=10, pady=10)
                    text.insert("1.0", "\n".join(result.get("logs", [])))
                    result_label.config(text="GET_LOGS получен")
                elif command == "SEND_FILE":
                    result_label.config(text=f"[FILE] передан: {result.get('path', 'готово')} ({result.get('size', 0)} байт)")
                else:
                    result_label.config(text=f"{command}: выполнено")
                return
            max_attempts = 360 if command == "UPDATE" else 20
            if attempts < max_attempts:
                window.after(500, lambda: wait_result(command_id, device_id, command, attempts + 1))
            else:
                timeout = "3 минуты" if command == "UPDATE" else "10 секунд"
                result_label.config(text=f"Agent не ответил за {timeout}")

        def start_live_view():
            device_id = selected_id()
            if not device_id:
                result_label.config(text="Сначала выберите агента")
                return
            viewer, close_action = open_embedded_result(f"{device_id} - LIVE VIEW")
            image_label = tk.Label(viewer, text="Ожидание screenshot...", bg="black", fg="white")
            image_label.pack(fill="both", expand=True)
            state = {"photo": None, "active": True}

            def close_view():
                state["active"] = False
                close_embedded_result(viewer)

            close_action["callback"] = close_view
            viewer.bind("<Destroy>", lambda event: state.update(active=False), add="+")

            def request_frame():
                if not state["active"] or not viewer.winfo_exists():
                    return
                try:
                    command = self.agent_server.store.queue_command(device_id, "SCREENSHOT")
                    viewer.after(120, lambda: receive_frame(command["command_id"]))
                except (AttributeError, ValueError):
                    close_view()

            def receive_frame(command_id, attempts=0):
                if not state["active"] or not viewer.winfo_exists():
                    return
                result = next((item for item in reversed(self.agent_server.store.results()) if item.get("command_id") == command_id), None)
                encoded = self.agent_server.store.screenshot(device_id)
                if result and result.get("error"):
                    image_label.config(text=f"FarmAgent: {result['error']}")
                    viewer.after(500, request_frame)
                    return
                if result and encoded:
                    try:
                        image = Image.open(io.BytesIO(base64.b64decode(encoded)))
                        image.thumbnail((900, 650))
                        state["photo"] = ImageTk.PhotoImage(image)
                        image_label.config(image=state["photo"], text="")
                    except (OSError, ValueError):
                        image_label.config(text="Не удалось декодировать screenshot")
                    viewer.after(max(80, int(1000 / config.AGENT_SCREENSHOT_FPS)), request_frame)
                elif attempts < 20:
                    viewer.after(250, lambda: receive_frame(command_id, attempts + 1))
                else:
                    image_label.config(text="Agent не ответил")
                    viewer.after(max(100, int(1000 / config.AGENT_SCREENSHOT_FPS)), request_frame)

            request_frame()

        def start_remote_view():
            device_id = selected_id()
            if not device_id:
                result_label.config(text="Сначала выберите агента")
                return
            viewer, close_action = open_embedded_result(f"{device_id} - REMOTE ACCESS")
            notice = tk.Label(viewer, text="VISIBLE REMOTE SUPPORT | FarmAgent console must remain open", bg="#17232d", fg="#ffd34d")
            notice.pack(fill="x")
            image_label = tk.Label(viewer, text="Ожидание экрана...", bg="black", fg="white", anchor="nw", takefocus=True)
            image_label.pack(fill="both", expand=True)
            agent = next((item for item in self.agent_server.store.list() if item.get("device_id") == device_id), {})
            screen = agent.get("screen") or {}
            state = {"photo": None, "size": (max(1, int(screen.get("width", 1))), max(1, int(screen.get("height", 1)))), "display_size": (1, 1), "active": True, "last_move": 0.0}

            def send_input(action, params):
                if self.agent_server:
                    self.agent_server.store.queue_command(device_id, action, params=params)

            def point(event):
                width, height = state["display_size"]
                source_width, source_height = state["size"]
                return {
                    "x": max(0, min(source_width - 1, int(event.x * source_width / max(1, width)))),
                    "y": max(0, min(source_height - 1, int(event.y * source_height / max(1, height)))),
                }

            def on_motion(event):
                now = time.monotonic()
                if now - state["last_move"] >= 0.05:
                    send_input("MOUSE_MOVE", point(event))
                    state["last_move"] = now

            def on_key(event):
                key = event.keysym.lower()
                aliases = {"return": "enter", "escape": "esc", "backspace": "backspace", "prior": "pageup", "next": "pagedown"}
                send_input("KEY", {"key": aliases.get(key, event.char or key)})
                return "break"

            def switch_tab(reverse=False):
                send_input("KEY", {"key": "ctrl+shift+tab" if reverse else "ctrl+tab"})

            def close_view():
                state["active"] = False
                if self.agent_server:
                    self.agent_server.store.queue_command(device_id, "STOP_STREAM")
                close_embedded_result(viewer)

            close_action["callback"] = close_view
            image_label.bind("<Motion>", on_motion)
            image_label.bind("<ButtonPress-1>", lambda event: send_input("MOUSE_DOWN", {"button": "left"}))
            image_label.bind("<ButtonRelease-1>", lambda event: send_input("MOUSE_UP", {"button": "left"}))
            viewer.bind("<Key>", on_key)
            viewer.bind("<Control-Tab>", lambda event: switch_tab())
            viewer.bind("<Control-Shift-Tab>", lambda event: switch_tab(True))
            image_label.focus_set()

            tab_bar = tk.Frame(viewer, bg="#17232d")
            tab_bar.pack(side="bottom", fill="x")
            tk.Button(tab_bar, text="Previous tab", command=lambda: switch_tab(True), bg="#25333d", fg="white", relief="flat").pack(side="left", padx=6, pady=4)
            tk.Button(tab_bar, text="Next tab", command=switch_tab, bg="#25333d", fg="white", relief="flat").pack(side="left", padx=6, pady=4)

            def refresh_frame(last_version=0):
                if not state["active"] or not viewer.winfo_exists():
                    return
                encoded, version = self.agent_server.store.screenshot_state(device_id)
                if encoded and version > last_version:
                    try:
                        image = Image.open(io.BytesIO(base64.b64decode(encoded)))
                        image.thumbnail((1050, 680))
                        state["display_size"] = image.size
                        state["photo"] = ImageTk.PhotoImage(image)
                        image_label.config(image=state["photo"], text="")
                    except (OSError, ValueError):
                        image_label.config(text="Не удалось декодировать экран")
                viewer.after(max(16, int(1000 / config.AGENT_SCREENSHOT_FPS)), lambda: refresh_frame(version))

            self.agent_server.store.queue_command(device_id, "START_STREAM")
            viewer.after(120, refresh_frame)

        for label, command in (("START", "START"), ("STOP", "STOP"), ("RESTART", "RESTART"), ("STATUS", "STATUS"), ("SCREENSHOT", "SCREENSHOT"), ("GET_LOGS", "GET_LOGS"), ("UPDATE", "UPDATE")):
            ttk.Button(controls, text=label, command=lambda value=command: send_command(value)).pack(side="left", padx=2)
        ttk.Button(controls, text="SEND FILE", command=send_file).pack(side="left", padx=2)
        ttk.Button(controls, text="LIVE VIEW", command=start_live_view).pack(side="left", padx=2)
        ttk.Button(controls, text="REMOTE ACCESS", command=start_remote_view).pack(side="left", padx=2)

        def refresh():
            if not window.winfo_exists():
                return
            for item in table.get_children():
                table.delete(item)
            agents = self.agent_server.store.list() if self.agent_server else []
            for agent in agents:
                item_id = table.insert("", "end", values=(agent.get("device_id", "--"), agent.get("hostname", "--"), agent.get("windows_version", "--"), agent.get("ip", "--"), agent.get("cpu", "--"), agent.get("ram", "--"), agent.get("status", "OFFLINE")))
                if agent.get("device_id") == initial_device_id:
                    table.selection_set(item_id)
            window.after(2000, refresh)

        refresh()
        if initial_action:
            def run_initial_action():
                if initial_action == "LIVE VIEW":
                    start_live_view()
                elif initial_action == "REMOTE ACCESS":
                    start_remote_view()
                else:
                    send_command(initial_action)
            window.after(0, run_initial_action)

    def show_groups_view(self):
        window = tk.Toplevel(self.root)
        window.title("DroidFleet - Groups")
        window.geometry("700x420")
        tk.Label(window, text="GROUPS", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        table = ttk.Treeview(window, columns=("group", "total", "online"), show="headings")
        for column, title in (("group", "GROUP"), ("total", "DEVICES"), ("online", "ONLINE")):
            table.heading(column, text=title)
            table.column(column, width=180)
        table.pack(fill="both", expand=True, padx=16, pady=6)
        def refresh():
            for item in table.get_children():
                table.delete(item)
            groups = {name: [] for name in self.device_registry.custom_groups}
            for record in self.device_registry.records.values():
                groups.setdefault(record.group, []).append(record)
            for name, records in sorted(groups.items()):
                table.insert("", "end", values=(name, len(records), sum(record.serial in self.devices for record in records)))
        def create_group():
            name = simpledialog.askstring("Create Group", "Название группы:", parent=window)
            if name:
                self.device_registry.custom_groups.add(name.strip())
                self.device_registry.save()
                refresh()
                self._update_groups()
        def open_group():
            selection = table.selection()
            if selection:
                group = table.item(selection[0], "values")[0]
                self.toolbar.group_var.set(group)
                self.apply_filters()
                window.destroy()
        def group_targets():
            selection = table.selection()
            if not selection:
                return []
            group = table.item(selection[0], "values")[0]
            return [record.serial for record in self.device_registry.records.values() if record.group == group and record.serial in self.devices]
        def group_action(action):
            targets = group_targets()
            if not targets:
                warning("Groups", "Выберите группу с online-устройствами.")
                return
            if action == "Screenshot":
                self.commands.run(targets, lambda serial: self._screenshot_worker(serial, config.DATA_DIR / "screenshots"))
            elif action == "Restart":
                self.commands.run(targets, lambda serial: self.client.run(["shell", "reboot"], serial, timeout=10))
            else:
                key = "KEYCODE_WAKEUP" if action == "Start" else "KEYCODE_POWER"
                self.commands.run(targets, lambda serial: send_keyevent(self.client, serial, key))
            self._set_status(f"{action}: {len(targets)}")
        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=16, pady=8)
        ttk.Button(buttons, text="Create Group", command=create_group).pack(side="left")
        ttk.Button(buttons, text="Open", command=open_group).pack(side="left", padx=6)
        for action in ("Start", "Stop", "Restart"):
            ttk.Button(buttons, text=action, command=lambda value=action: group_action(value)).pack(side="left", padx=2)
        refresh()

    def show_tasks_view(self):
        window = tk.Toplevel(self.root)
        window.title("DroidFleet - Tasks")
        window.geometry("760x400")
        tk.Label(window, text="TASKS", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(16, 6))
        table = ttk.Treeview(window, columns=("name", "target", "action", "status"), show="headings")
        for column in ("name", "target", "action", "status"):
            table.heading(column, text=column.upper())
            table.column(column, width=170)
        table.pack(fill="both", expand=True, padx=16, pady=8)
        def refresh():
            for item in table.get_children():
                table.delete(item)
            for task in self.tasks:
                table.insert("", "end", values=(task["name"], task["target"], task["action"], task["status"]))
        def create_task():
            name = simpledialog.askstring("New Task", "Название:", parent=window)
            target = simpledialog.askstring("New Task", "Группа:", initialvalue="Без группы", parent=window)
            action = simpledialog.askstring("New Task", "Действие (Start/Stop/Restart/Screenshot/Reconnect):", initialvalue="Screenshot", parent=window)
            if name and target and action:
                self.tasks.append({"name": name, "target": target, "action": action, "status": "SCHEDULED"})
                self.task_repository.save(self.tasks)
                refresh()
        def run_task():
            selection = table.selection()
            if not selection:
                return
            index = table.index(selection[0])
            task = self.tasks[index]
            targets = [record.serial for record in self.device_registry.records.values() if record.group == task["target"] and record.serial in self.devices]
            if task["action"].casefold() == "screenshot":
                self.commands.run(targets, lambda serial: self._screenshot_worker(serial, config.DATA_DIR / "screenshots"))
            elif task["action"].casefold() == "reconnect":
                self.reconnect_selected(targets)
            elif task["action"].casefold() == "restart":
                self.commands.run(targets, lambda serial: self.client.run(["shell", "reboot"], serial, timeout=10))
            elif task["action"].casefold() in {"start", "stop"}:
                self.mass_keyevent("KEYCODE_POWER")
            task["status"] = "RUNNING"
            self.task_repository.save(self.tasks)
            refresh()
        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=16, pady=8)
        ttk.Button(buttons, text="Create Task", command=create_task).pack(side="left")
        ttk.Button(buttons, text="Run", command=run_task).pack(side="left", padx=6)
        refresh()

    def show_settings(self):
        window = tk.Toplevel(self.root)
        window.title("DroidFleet - Settings")
        window.geometry("700x650")
        values = {"Preview FPS": str(config.PREVIEW_FPS), "Preview quality": str(config.PREVIEW_WIDTH), "Connection timeout": "5", "Scan interval": str(config.DEVICE_CHECK_INTERVAL), "Agent port": str(config.AGENT_SERVER_PORT), "Ngrok region": config.NGROK_REGION}
        tk.Label(window, text="SETTINGS", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
        language_row = ttk.Frame(window)
        language_row.pack(fill="x", padx=16, pady=4)
        ttk.Label(language_row, text="Language / Язык", width=24).pack(side="left")
        language_var = tk.StringVar(value=self.language)
        language_dropdown = ttk.Combobox(language_row, textvariable=language_var, state="readonly", values=("Русский", "English"), width=18)
        language_dropdown.pack(side="left")
        mode_row = ttk.Frame(window)
        mode_row.pack(fill="x", padx=16, pady=4)
        ttk.Label(mode_row, text="Connection mode", width=24).pack(side="left")
        mode_var = tk.StringVar(value=config.CONNECTION_MODE)
        ttk.Combobox(mode_row, textvariable=mode_var, state="readonly", values=("local", "ngrok", "external"), width=18).pack(side="left")
        android_mode_row = ttk.Frame(window)
        android_mode_row.pack(fill="x", padx=16, pady=4)
        ttk.Label(android_mode_row, text="Android ADB transport", width=24).pack(side="left")
        android_mode_var = tk.StringVar(value=config.ANDROID_CONNECTION_MODE)
        ttk.Combobox(
            android_mode_row,
            textvariable=android_mode_var,
            state="readonly",
            values=("auto", "usb", "wifi"),
            width=18,
        ).pack(side="left")
        fields = {}
        for name, value in values.items():
            row = ttk.Frame(window)
            row.pack(fill="x", padx=16, pady=4)
            ttk.Label(row, text=name, width=24).pack(side="left")
            field = ttk.Entry(row)
            field.insert(0, value)
            field.pack(side="left", fill="x", expand=True)
            fields[name] = field
        token_row = ttk.Frame(window)
        token_row.pack(fill="x", padx=16, pady=4)
        ttk.Label(token_row, text="Ngrok auth token", width=24).pack(side="left")
        token_field = ttk.Entry(token_row, show="*")
        token_field.insert(0, config.NGROK_AUTHTOKEN)
        token_field.pack(side="left", fill="x", expand=True)
        ttk.Label(
            window,
            text=(
                "FarmAgent processes (JSON). On the target PC, set the environment "
                "variable from each process's 'command' field to its full launch command."
            ),
            wraplength=760,
        ).pack(anchor="w", padx=16, pady=(12, 2))
        process_text = tk.Text(window, height=7, width=70)
        process_text.insert("1.0", json.dumps(config.PROCESS_DEFINITIONS, ensure_ascii=False, indent=2))
        process_text.pack(fill="both", expand=True, padx=16)
        def save_settings():
            try:
                self.set_language(language_var.get())
                config.PREVIEW_FPS = max(1, min(30, int(fields["Preview FPS"].get())))
                config.PREVIEW_INTERVAL = 1.0 / config.PREVIEW_FPS
                config.DEVICE_CHECK_INTERVAL = max(250, int(fields["Scan interval"].get()))
                config.CONNECTION_MODE = ConnectionProfile.from_value(mode_var.get()).config_value
                self.connection_profile = ConnectionProfile.from_value(config.CONNECTION_MODE)
                config.ANDROID_CONNECTION_MODE = android_mode_var.get()
                config.AGENT_SERVER_PORT = max(1, int(fields["Agent port"].get()))
                config.NGROK_REGION = fields["Ngrok region"].get().strip()
                config.NGROK_AUTHTOKEN = token_field.get().strip()
                definitions = json.loads(process_text.get("1.0", "end"))
                if not isinstance(definitions, dict) or not definitions:
                    raise ValueError("Process definitions must be a non-empty JSON object")
                config.PROCESS_DEFINITIONS = definitions
                config.save_user_settings()
                self.refresh_devices()
                if self.agent_server:
                    self.agent_server.store.set_process_definitions(config.PROCESS_DEFINITIONS)
                self._set_status("Настройки сохранены")
                window.destroy()
            except (ValueError, json.JSONDecodeError):
                error("Settings", "Проверьте числовые поля и JSON процессов.")
        ttk.Button(window, text="Save", command=save_settings).pack(anchor="e", padx=16, pady=14)

    def set_language(self, language):
        if language not in ("Русский", "English"):
            return
        self.language = language
        config.LANGUAGE = language
        self.toolbar.set_language(language)
        self._set_status("Язык изменён" if language == "Русский" else "Language changed")

    def on_close(self):
        if self.ngrok:
            self.ngrok.stop()
        if self.agent_server:
            self.agent_server.close()
        self.preview.close(); self.commands.close(); self.input_executor.shutdown(wait=False, cancel_futures=True); self.hardware_executor.shutdown(wait=False, cancel_futures=True); self.reconnect_executor.shutdown(wait=False, cancel_futures=True); self.monitor_executor.shutdown(wait=False, cancel_futures=True); self.stop_scrcpy(); self.root.destroy()


def main():
    root = tk.Tk()
    try: AndroidController(root)
    except Exception as exc: messagebox.showerror("Ошибка", str(exc)); return
    root.mainloop()


if __name__ == "__main__":
    main()
