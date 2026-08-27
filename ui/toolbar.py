import tkinter as tk
from tkinter import ttk
from app.adb.commands import KEY_HOME, KEY_BACK, KEY_RECENTS, KEY_POWER


class Toolbar:
    def __init__(self, parent, controller):
        self.controller = controller
        self.target_var = tk.StringVar(value="SELECTED")
        ttk.Label(parent, text="ANDROID FLEET", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self.count = ttk.Label(parent, text="0 устройств")
        self.count.pack(anchor="w", pady=(2, 10))
        ttk.Button(parent, text="Обновить устройства", command=controller.refresh_devices).pack(fill="x", pady=2)
        ttk.Separator(parent).pack(fill="x", pady=10)
        ttk.Label(parent, text="Массовое управление", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Radiobutton(parent, text="Выбранные", variable=self.target_var, value="SELECTED").pack(anchor="w")
        ttk.Radiobutton(parent, text="Все устройства", variable=self.target_var, value="ALL").pack(anchor="w")
        ttk.Button(parent, text="Выбрать все", command=controller.select_all).pack(fill="x", pady=(6, 2))
        ttk.Button(parent, text="Снять выбор", command=controller.clear_selection).pack(fill="x", pady=2)
        ttk.Label(parent, text="Фильтр устройств").pack(anchor="w", pady=(8, 0))
        self.group_var = tk.StringVar(value="Все устройства")
        self.group_filter = ttk.Combobox(parent, textvariable=self.group_var, state="readonly", values=("Все устройства",))
        self.group_filter.pack(fill="x", pady=2)
        self.group_filter.bind("<<ComboboxSelected>>", lambda event: controller.set_group_filter(self.group_var.get()))
        ttk.Separator(parent).pack(fill="x", pady=10)
        ttk.Label(parent, text="Команды", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        for label, key in (("HOME", KEY_HOME), ("BACK", KEY_BACK), ("RECENTS", KEY_RECENTS), ("POWER", KEY_POWER)):
            ttk.Button(parent, text=label, command=lambda value=key: controller.mass_keyevent(value)).pack(fill="x", pady=2)
        ttk.Separator(parent).pack(fill="x", pady=10)
        ttk.Label(parent, text="ADB shell", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.command = ttk.Entry(parent)
        self.command.pack(fill="x", pady=4)
        self.command.insert(0, "getprop ro.product.model")
        ttk.Button(parent, text="Выполнить на выбранных", command=controller.mass_shell).pack(fill="x", pady=2)
        ttk.Button(parent, text="Выполнить на ВСЕХ", command=lambda: controller.mass_shell(True)).pack(fill="x", pady=2)
        ttk.Button(parent, text="Массовая установка APK", command=controller.install_apk).pack(fill="x", pady=2)
        ttk.Separator(parent).pack(fill="x", pady=10)
        ttk.Button(parent, text="Открыть scrcpy", command=controller.start_scrcpy).pack(fill="x", pady=2)
        ttk.Button(parent, text="Закрыть scrcpy", command=controller.stop_scrcpy).pack(fill="x", pady=2)
        ttk.Button(parent, text="Показать логи", command=controller.show_logs).pack(fill="x", pady=2)
        ttk.Separator(parent).pack(fill="x", pady=10)
        self.status = ttk.Label(parent, text="Нет выбранного устройства", wraplength=220)
        self.status.pack(anchor="w", pady=5)

    def set_groups(self, groups):
        current = self.group_var.get()
        values = ("Все устройства", *sorted(groups, key=str.casefold))
        self.group_filter.configure(values=values)
        self.group_var.set(current if current in values else "Все устройства")
