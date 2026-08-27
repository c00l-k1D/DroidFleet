import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config
from app.fleet_logging import FleetLogger
from app.adb.client import AdbClient
from app.adb.monitor import DeviceMonitor
from app.adb.reconnect import ReconnectService
from app.actions.batch import BatchExecutor
from app.actions.input import send_keyevent
from app.actions.apps import install_apk, run_shell
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
        root.title("Android USB Fleet Controller")
        root.geometry("1450x900")
        root.minsize(1100, 700)
        self.client = AdbClient()
        self.scrcpy = ScrcpyStream(ScrcpyStream.find(Path(__file__).resolve().parents[1]))
        self.devices = []
        self.hardware_info = {}
        self.group_filter = "Все устройства"
        self.selected = None
        self.selected_devices = set()
        self.preview_images = {}
        self.preview = PreviewService(root, self.client, self.update_preview, self.preview_failed, config.PREVIEW_WIDTH, config.PREVIEW_HEIGHT, config.PREVIEW_WORKERS)
        self.commands = BatchExecutor(config.COMMAND_WORKERS)
        self.hardware_executor = ThreadPoolExecutor(max_workers=config.PREVIEW_WORKERS)
        self.reconnect_executor = ThreadPoolExecutor(max_workers=2)
        self.reconnect = ReconnectService(self.client, self.logger)
        self.monitor = DeviceMonitor(self.client, self._on_devices_changed)
        left = tk.Frame(root); left.pack(side="left", fill="y", padx=10, pady=10)
        self.toolbar = Toolbar(left, self)
        self.dashboard = Dashboard(root, self)
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
        try:
            self.monitor.refresh()
        except Exception as exc:
            self.logger.error(f"Ошибка обновления устройств: {exc}")

    def _on_devices_changed(self, devices):
        old = set(self.devices); current = set(devices); self.devices = devices
        for serial in old - current:
            self.logger.warning(f"Устройство отключилось: {serial}")
            self.dashboard.remove(serial); self.preview_images.pop(serial, None); self.hardware_info.pop(serial, None); self.selected_devices.discard(serial)
            self.reconnect_executor.submit(self.reconnect.reconnect, serial)
        for serial in current - old:
            self.logger.info(f"Устройство подключено: {serial}")
            self.dashboard.add(serial)
        if self.selected not in current: self.selected = None
        self.toolbar.count.config(text=f"ADB ONLINE: {len(devices)}")
        self.update_card_selection()
        for serial in devices:
            self.hardware_executor.submit(self._load_hardware, serial)
        self._set_status()

    def _load_hardware(self, serial):
        try:
            info = self.client.hardware_info(serial)
            self.root.after(0, lambda: self._apply_hardware(serial, info))
        except Exception:
            pass

    def _apply_hardware(self, serial, info):
        card = self.dashboard.cards.get(serial)
        if card and serial in self.devices:
            self.hardware_info[serial] = info
            card.update_hardware(info)
            self._update_groups()

    def _update_groups(self):
        groups = set()
        for info in self.hardware_info.values():
            if info.manufacturer != "--":
                groups.add(info.manufacturer)
            if info.manufacturer != "--" and info.model != "--":
                groups.add(f"{info.manufacturer} {info.model}")
        self.toolbar.set_groups(groups)

    def set_group_filter(self, group):
        self.group_filter = group
        self.dashboard.set_filter(self._matches_group)

    def _matches_group(self, serial):
        if self.group_filter == "Все устройства":
            return True
        info = self.hardware_info.get(serial)
        if not info:
            return False
        return self.group_filter in (info.manufacturer, f"{info.manufacturer} {info.model}")

    def toggle_device_selection(self, serial):
        if serial in self.selected_devices: self.selected_devices.remove(serial)
        else: self.selected_devices.add(serial)
        self.selected = serial; self.update_card_selection(); self._set_status(f"Последнее: {serial}")

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
            else:
                details = result.stderr.decode(errors="replace").strip()
                self.logger.error(f"Ошибка установки APK на {serial}: {details or output or result.returncode}")
        except Exception as exc:
            self.logger.error(f"Ошибка установки APK на {serial}: {exc}")

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

    def on_close(self):
        self.preview.close(); self.commands.close(); self.hardware_executor.shutdown(wait=False, cancel_futures=True); self.reconnect_executor.shutdown(wait=False, cancel_futures=True); self.stop_scrcpy(); self.root.destroy()


def main():
    root = tk.Tk()
    try: AndroidController(root)
    except Exception as exc: messagebox.showerror("Ошибка", str(exc)); return
    root.mainloop()


if __name__ == "__main__":
    main()
