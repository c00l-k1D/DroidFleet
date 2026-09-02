import sys
import time
import base64
import io
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageTk

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config
from app.accounts.repository import AccountRepository
from app.agent_server import AgentServer, AgentStore
from app.devices.registry import DeviceRegistry
from app.fleet_logging import FleetLogger
from app.adb.client import AdbClient
from app.adb.monitor import DeviceMonitor
from app.adb.reconnect import ReconnectService
from app.actions.batch import BatchExecutor
from app.actions.input import send_keyevent, send_tap, send_swipe, send_zoom
from app.adb.commands import screencap
from app.actions.coordinates import normalize_to_device
from app.actions.apps import close_app, install_apk, launch_app, push_account_file, run_shell
from app.ui.dashboard import Dashboard
from app.ui.dialogs import error, warning
from app.ui.toolbar import Toolbar
from app.ui.log_viewer import LogViewer
from app.video.preview import PreviewService
from app.video.stream import ScrcpyStream


class AndroidController:
    def __init__(self, root):
        self.root = root
        self.logger = FleetLogger()
        self.account_repository = AccountRepository(config.ACCOUNTS_FILE)
        self.device_registry = DeviceRegistry(config.DEVICES_FILE)
        root.title("DroidFleet")
        root.geometry("1450x900")
        root.minsize(1100, 700)
        self.client = AdbClient()
        self.scrcpy = ScrcpyStream(ScrcpyStream.find(Path(__file__).resolve().parents[1]))
        self.devices = []
        self.hardware_info = {}
        self.group_filter = "Все устройства"
        self.group_mode = "Без групп"
        self.selected = None
        self.selected_devices = set()
        self.preview_images = {}
        self.preview = PreviewService(root, self.client, self.update_preview, self.preview_failed, config.PREVIEW_WIDTH, config.PREVIEW_HEIGHT, config.PREVIEW_WORKERS)
        self.commands = BatchExecutor(config.COMMAND_WORKERS)
        self.hardware_executor = ThreadPoolExecutor(max_workers=config.PREVIEW_WORKERS)
        self.reconnect_executor = ThreadPoolExecutor(max_workers=2)
        self.monitor_executor = ThreadPoolExecutor(max_workers=1)
        self._monitor_busy = False
        self._last_hardware_refresh = {}
        self.tasks = []
        self.language = config.LANGUAGE if config.LANGUAGE in ("Русский", "English") else "Русский"
        self.reconnect = ReconnectService(self.client, self.logger)
        self.monitor = DeviceMonitor(self.client, self._on_devices_changed)
        self.agent_server = None
        root.configure(bg="#0b1117")
        header = tk.Frame(root, bg="#101923", height=58)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="DROIDFLEET", bg="#101923", fg="#f1f7fb", font=("Segoe UI", 16, "bold")).pack(side="left", padx=20)
        self.server_status = tk.Label(header, text="● SERVER STARTING", bg="#101923", fg="#ffd34d", font=("Segoe UI", 10, "bold"))
        self.server_status.pack(side="right", padx=20)
        try:
            self.agent_server = AgentServer((config.AGENT_SERVER_HOST, config.AGENT_SERVER_PORT), AgentStore(config.AGENT_STALE_AFTER))
            self.agent_server.start_background()
            self.server_status.config(text="● SERVER OK", fg="#51d88a")
        except OSError as exc:
            self.logger.error(f"Не удалось запустить сервер агентов: {exc}")
            self.server_status.config(text="● SERVER ERROR", fg="#ff9f43")
        workspace = tk.Frame(root, bg="#0b1117")
        workspace.pack(side="top", fill="both", expand=True)
        left = tk.Frame(workspace, bg="#f4f6f8"); left.pack(side="left", fill="y", padx=(10, 0), pady=10)
        self.toolbar = Toolbar(left, self)
        self.toolbar.set_language(self.language)
        self.dashboard = Dashboard(workspace, self)
        self.refresh_devices()
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

    def _refresh_devices_worker(self):
        try:
            devices = self.client.devices()
            self.root.after(0, lambda: self._on_devices_changed(devices))
        except Exception as exc:
            self.logger.error(f"Ошибка обновления устройств: {exc}")
        finally:
            self._monitor_busy = False

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
            record.battery = info.battery
            record.cpu = info.cpu
            record.ram = info.ram
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
        self.show_device_details(serial)
        self._set_status(f"Последнее: {serial}")

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
        details.config(text=(f"General\nName       {record.display_name}\nID         {record.device_id}\nType       {record.device_type}\nModel      {record.model}\nOS         {record.os}\nIP         {record.ip}\n\nSystem\nBattery    {record.battery}\nCPU        {record.cpu}\nRAM        {record.ram}\nTemperature {record.temperature}\nLast Seen  {record.last_seen}\n\nOrganization\nGroup      {record.group}\nTags       {', '.join(record.tags) or '--'}"))
        editor = tk.Frame(body)
        editor.pack(fill="x", pady=14)
        name_var, group_var, tags_var = tk.StringVar(value=record.name), tk.StringVar(value=record.group), tk.StringVar(value=", ".join(record.tags))
        for label, variable in (("Name", name_var), ("Group", group_var), ("Tags", tags_var)):
            tk.Label(editor, text=label).pack(anchor="w")
            tk.Entry(editor, textvariable=variable).pack(fill="x", pady=(0, 4))
        def save():
            record.name = name_var.get().strip()
            record.group = group_var.get().strip() or "Без группы"
            record.tags = [tag.strip() for tag in tags_var.get().split(",") if tag.strip()]
            self.device_registry.save()
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
        for serial in self.devices:
            if len(self.preview.busy) >= config.PREVIEW_WORKERS: break
            self.preview.submit(serial)
        self.root.after(int(config.PREVIEW_INTERVAL * 1000), self.preview_loop)

    def update_preview(self, serial, photo):
        card = self.dashboard.cards.get(serial)
        if not card: return
        self.preview_images[serial] = photo; card.screen.config(image=photo, text="")
        meta = card.meta; meta["frames"] += 1; now = time.monotonic(); elapsed = now - meta.get("last_fps", now)
        if elapsed >= 1:
            meta["video_status"].config(text=f"VIDEO {meta['frames'] / elapsed:.1f} FPS", fg="#42ff42"); meta["frames"] = 0; meta["last_fps"] = now

    def preview_failed(self, serial):
        card = self.dashboard.cards.get(serial)
        if card and serial not in self.devices: card.screen.config(image="", text="OFFLINE")

    def handle_device_input(self, serial, action, params):
        """Handle device input events from UI (tap, swipe, zoom)."""
        if serial not in self.devices:
            return
        record = self.device_registry.get_or_create(serial)
        record.status = "BUSY"
        card = self.dashboard.cards.get(serial)
        if card:
            card.update_device(record)
        self.commands.run([serial], lambda target: self._device_input_worker(target, action, params))

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
            record = self.device_registry.get_or_create(serial)
            record.status = "ONLINE"
            self.root.after(0, lambda: self.dashboard.cards.get(serial) and self.dashboard.cards[serial].update_device(record))
            self.logger.info(f"{action} отправлен на {serial}")
        except Exception as exc:
            record = self.device_registry.get_or_create(serial)
            record.status = "ERROR"
            self.root.after(0, lambda: self.dashboard.cards.get(serial) and self.dashboard.cards[serial].update_device(record))
            self.logger.error(f"Ошибка при отправке {action} на {serial}: {exc}")

    def open_device_scrcpy(self, serial):
        self.selected_devices = {serial}; self.selected = serial; self.update_card_selection(); self.start_scrcpy()

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

    def show_windows_view(self):
        window = tk.Toplevel(self.root)
        window.title("DroidFleet - Windows")
        window.geometry("1100x500")
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

        def selected_id():
            selection = table.selection()
            return table.item(selection[0], "values")[0] if selection else None

        def send_command(command):
            device_id = selected_id()
            if not device_id:
                result_label.config(text="Сначала выберите агента")
                return
            try:
                item = self.agent_server.store.queue_command(device_id, command, process_var.get())
                result_label.config(text=f"{command} отправлен через Agent")
                window.after(500, lambda: wait_result(item["command_id"], device_id, command))
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
                        viewer = tk.Toplevel(window)
                        viewer.title(f"DroidFleet - {device_id} screen")
                        photo = ImageTk.PhotoImage(image)
                        label = tk.Label(viewer, image=photo, bg="black")
                        label.image = photo
                        label.pack()
                        result_label.config(text="SCREENSHOT получен")
                elif command == "GET_LOGS":
                    viewer = tk.Toplevel(window)
                    viewer.title(f"DroidFleet - {device_id} logs")
                    text = tk.Text(viewer, width=110, height=25)
                    text.pack(fill="both", expand=True)
                    text.insert("1.0", "\n".join(result.get("logs", [])))
                    result_label.config(text="GET_LOGS получен")
                else:
                    result_label.config(text=f"{command}: выполнено")
                return
            if attempts < 20:
                window.after(500, lambda: wait_result(command_id, device_id, command, attempts + 1))
            else:
                result_label.config(text="Agent не ответил за 10 секунд")

        def start_live_view():
            device_id = selected_id()
            if not device_id:
                result_label.config(text="Сначала выберите агента")
                return
            viewer = tk.Toplevel(window)
            viewer.title(f"DroidFleet - {device_id} live view")
            image_label = tk.Label(viewer, text="Ожидание screenshot...", bg="black", fg="white")
            image_label.pack(fill="both", expand=True)
            state = {"photo": None, "active": True}

            def close_view():
                state["active"] = False
                viewer.destroy()

            viewer.protocol("WM_DELETE_WINDOW", close_view)

            def request_frame():
                if not state["active"] or not viewer.winfo_exists():
                    return
                try:
                    command = self.agent_server.store.queue_command(device_id, "SCREENSHOT")
                    viewer.after(350, lambda: receive_frame(command["command_id"]))
                except (AttributeError, ValueError):
                    close_view()

            def receive_frame(command_id, attempts=0):
                if not state["active"] or not viewer.winfo_exists():
                    return
                result = next((item for item in reversed(self.agent_server.store.results()) if item.get("command_id") == command_id), None)
                encoded = self.agent_server.store.screenshot(device_id)
                if result and encoded:
                    try:
                        image = Image.open(io.BytesIO(base64.b64decode(encoded)))
                        image.thumbnail((900, 650))
                        state["photo"] = ImageTk.PhotoImage(image)
                        image_label.config(image=state["photo"], text="")
                    except (OSError, ValueError):
                        image_label.config(text="Не удалось декодировать screenshot")
                    viewer.after(max(100, int(1000 / config.AGENT_SCREENSHOT_FPS)), request_frame)
                elif attempts < 20:
                    viewer.after(250, lambda: receive_frame(command_id, attempts + 1))
                else:
                    image_label.config(text="Agent не ответил")
                    viewer.after(max(100, int(1000 / config.AGENT_SCREENSHOT_FPS)), request_frame)

            request_frame()

        for label, command in (("START", "START"), ("STOP", "STOP"), ("RESTART", "RESTART"), ("STATUS", "STATUS"), ("SCREENSHOT", "SCREENSHOT"), ("GET_LOGS", "GET_LOGS")):
            ttk.Button(controls, text=label, command=lambda value=command: send_command(value)).pack(side="left", padx=2)
        ttk.Button(controls, text="LIVE VIEW", command=start_live_view).pack(side="left", padx=2)

        def refresh():
            if not window.winfo_exists():
                return
            for item in table.get_children():
                table.delete(item)
            agents = self.agent_server.store.list() if self.agent_server else []
            for agent in agents:
                table.insert("", "end", values=(agent.get("device_id", "--"), agent.get("hostname", "--"), agent.get("windows_version", "--"), agent.get("ip", "--"), agent.get("cpu", "--"), agent.get("ram", "--"), agent.get("status", "OFFLINE")))
            window.after(2000, refresh)

        refresh()

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
            refresh()
        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=16, pady=8)
        ttk.Button(buttons, text="Create Task", command=create_task).pack(side="left")
        ttk.Button(buttons, text="Run", command=run_task).pack(side="left", padx=6)
        refresh()

    def show_settings(self):
        window = tk.Toplevel(self.root)
        window.title("DroidFleet - Settings")
        window.geometry("620x420")
        values = {"Preview FPS": str(config.PREVIEW_FPS), "Preview quality": str(config.PREVIEW_WIDTH), "Connection timeout": "5", "Scan interval": str(config.DEVICE_CHECK_INTERVAL), "Agent port": str(config.AGENT_SERVER_PORT)}
        tk.Label(window, text="SETTINGS", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
        language_row = ttk.Frame(window)
        language_row.pack(fill="x", padx=16, pady=4)
        ttk.Label(language_row, text="Language / Язык", width=24).pack(side="left")
        language_var = tk.StringVar(value=self.language)
        language_dropdown = ttk.Combobox(language_row, textvariable=language_var, state="readonly", values=("Русский", "English"), width=18)
        language_dropdown.pack(side="left")
        fields = {}
        for name, value in values.items():
            row = ttk.Frame(window)
            row.pack(fill="x", padx=16, pady=4)
            ttk.Label(row, text=name, width=24).pack(side="left")
            field = ttk.Entry(row)
            field.insert(0, value)
            field.pack(side="left", fill="x", expand=True)
            fields[name] = field
        def save_settings():
            try:
                self.set_language(language_var.get())
                config.PREVIEW_FPS = max(1, min(30, int(fields["Preview FPS"].get())))
                config.PREVIEW_INTERVAL = 1.0 / config.PREVIEW_FPS
                config.DEVICE_CHECK_INTERVAL = max(250, int(fields["Scan interval"].get()))
                self._set_status("Настройки сохранены")
                window.destroy()
            except ValueError:
                error("Settings", "Числовые настройки заполнены неверно.")
        ttk.Button(window, text="Save", command=save_settings).pack(anchor="e", padx=16, pady=14)

    def set_language(self, language):
        if language not in ("Русский", "English"):
            return
        self.language = language
        config.LANGUAGE = language
        self.toolbar.set_language(language)
        self._set_status("Язык изменён" if language == "Русский" else "Language changed")

    def on_close(self):
        if self.agent_server:
            self.agent_server.close()
        self.preview.close(); self.commands.close(); self.hardware_executor.shutdown(wait=False, cancel_futures=True); self.reconnect_executor.shutdown(wait=False, cancel_futures=True); self.monitor_executor.shutdown(wait=False, cancel_futures=True); self.stop_scrcpy(); self.root.destroy()


def main():
    root = tk.Tk()
    try: AndroidController(root)
    except Exception as exc: messagebox.showerror("Ошибка", str(exc)); return
    root.mainloop()


if __name__ == "__main__":
    main()
