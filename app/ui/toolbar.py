import tkinter as tk
from tkinter import ttk
from app.adb.commands import KEY_HOME, KEY_BACK, KEY_RECENTS, KEY_POWER


class Toolbar:
    def __init__(self, parent, controller):
        self.controller = controller
        scroll_canvas = tk.Canvas(parent, width=260, highlightthickness=0, background="#f4f6f8")
        scroll_bar = ttk.Scrollbar(parent, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scroll_bar.set)
        scroll_bar.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)
        content = ttk.Frame(scroll_canvas, padding=(8, 8, 12, 8))
        content_window = scroll_canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda event: scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>", lambda event: scroll_canvas.itemconfigure(content_window, width=event.width))
        scroll_canvas.bind_all("<MouseWheel>", lambda event: scroll_canvas.yview_scroll(int(-event.delta / 120), "units"))
        parent = content
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="DEVICES", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(parent, text="Навигация", foreground="#607080").pack(anchor="w", pady=(0, 5))
        navigation = ttk.Frame(parent)
        navigation.pack(fill="x", pady=(0, 8))
        self.navigation_buttons = {}
        navigation_commands = (("Android", controller.show_android_view), ("Windows", controller.show_windows_view), ("Groups", controller.show_groups_view), ("Tasks", controller.show_tasks_view), ("Logs", controller.show_logs), ("Settings", controller.show_settings))
        for label, command in navigation_commands:
            button = ttk.Button(navigation, text=label, command=command)
            button.pack(fill="x", pady=1)
            self.navigation_buttons[label] = button
        self.count = ttk.Label(parent, text="0 устройств")
        self.count.pack(anchor="w", pady=(2, 10))
        ttk.Button(parent, text="Обновить список устройств", command=controller.refresh_devices).pack(fill="x", pady=2)
        selection = ttk.LabelFrame(parent, text="Кому отправлять команды", padding=8)
        selection.pack(fill="x", pady=(12, 4))
        self.target_var = tk.StringVar(value="SELECTED")
        ttk.Label(selection, text="Сначала выберите карточки устройств ниже.", foreground="#607080", wraplength=230).pack(anchor="w", pady=(0, 4))
        ttk.Radiobutton(selection, text="Только выбранные", variable=self.target_var, value="SELECTED").pack(anchor="w")
        ttk.Radiobutton(selection, text="Все подключённые", variable=self.target_var, value="ALL").pack(anchor="w")
        ttk.Button(selection, text="Выбрать все карточки", command=controller.select_all).pack(fill="x", pady=(6, 2))
        ttk.Button(selection, text="Снять выбор", command=controller.clear_selection).pack(fill="x", pady=2)
        filters = ttk.LabelFrame(parent, text="FILTER", padding=8)
        filters.pack(fill="x", pady=(8, 4))
        ttk.Label(filters, text="Производитель").pack(anchor="w")
        self.manufacturer_var = tk.StringVar(value="Все устройства")
        self.manufacturer_filter = ttk.Combobox(filters, textvariable=self.manufacturer_var, state="readonly", values=("Все устройства",))
        self.manufacturer_filter.pack(fill="x", pady=2)
        self.manufacturer_filter.bind("<<ComboboxSelected>>", lambda event: controller.apply_filters())
        ttk.Label(filters, text="Группа").pack(anchor="w")
        self.group_var = tk.StringVar(value="Все группы")
        self.group_filter = ttk.Combobox(filters, textvariable=self.group_var, state="readonly", values=("Все группы",))
        self.group_filter.pack(fill="x", pady=2)
        self.group_filter.bind("<<ComboboxSelected>>", lambda event: controller.apply_filters())
        ttk.Label(filters, text="Статус").pack(anchor="w")
        self.status_var = tk.StringVar(value="Все статусы")
        self.status_filter = ttk.Combobox(filters, textvariable=self.status_var, state="readonly", values=("Все статусы", "ONLINE", "BUSY", "OFFLINE", "ERROR"))
        self.status_filter.pack(fill="x", pady=2)
        self.status_filter.bind("<<ComboboxSelected>>", lambda event: controller.apply_filters())
        ttk.Label(filters, text="Поиск").pack(anchor="w")
        self.search_var = tk.StringVar()
        ttk.Entry(filters, textvariable=self.search_var).pack(fill="x", pady=2)
        self.search_var.trace_add("write", lambda *_: controller.apply_filters())
        ttk.Label(parent, text="Группировать карточки").pack(anchor="w", pady=(6, 0))
        self.group_mode_var = tk.StringVar(value="Без групп")
        self.group_mode = ttk.Combobox(parent, textvariable=self.group_mode_var, state="readonly", values=("Без групп", "Производитель", "Модель"))
        self.group_mode.pack(fill="x", pady=2)
        self.group_mode.bind("<<ComboboxSelected>>", lambda event: controller.set_group_mode(self.group_mode_var.get()))
        quick = ttk.LabelFrame(parent, text="QUICK ACTIONS", padding=8)
        quick.pack(fill="x", pady=(8, 4))
        self.quick_buttons = {}
        quick_commands = (("Screenshot", controller.capture_selected_screenshots), ("Restart", controller.mass_restart), ("Reconnect ADB", controller.reconnect_selected), ("HOME", lambda: controller.mass_keyevent(KEY_HOME)), ("BACK", lambda: controller.mass_keyevent(KEY_BACK)), ("RECENTS", lambda: controller.mass_keyevent(KEY_RECENTS)), ("POWER", lambda: controller.mass_keyevent(KEY_POWER)))
        for label, command in quick_commands:
            button = ttk.Button(quick, text=label, command=command)
            button.pack(fill="x", pady=1)
            self.quick_buttons[label] = button
        shell = ttk.LabelFrame(parent, text="ADB-команда", padding=8)
        shell.pack(fill="x", pady=(8, 4))
        self.command = ttk.Entry(shell)
        self.command.pack(fill="x", pady=4)
        self.command.insert(0, "getprop ro.product.model")
        ttk.Button(shell, text="Выполнить на выбранных", command=controller.mass_shell).pack(fill="x", pady=2)
        ttk.Button(shell, text="Выполнить на всех", command=lambda: controller.mass_shell(True)).pack(fill="x", pady=2)
        apps = ttk.LabelFrame(parent, text="Приложения", padding=8)
        apps.pack(fill="x", pady=(8, 4))
        ttk.Label(apps, text="Установите APK или укажите package name уже установленного приложения.", foreground="#607080", wraplength=230).pack(anchor="w", pady=(0, 4))
        ttk.Button(apps, text="Выбрать APK и установить", command=controller.install_apk).pack(fill="x", pady=2)
        self.package_name = ttk.Entry(apps)
        self.package_name.insert(0, "com.example.app")
        self.package_name.pack(fill="x", pady=(6, 2))
        ttk.Label(apps, text="Пример: com.android.settings", foreground="#607080").pack(anchor="w")
        ttk.Button(apps, text="Запустить приложение", command=controller.launch_app).pack(fill="x", pady=(5, 2))
        ttk.Button(apps, text="Закрыть приложение", command=controller.close_app).pack(fill="x", pady=2)
        ttk.Button(apps, text="Импортировать файл аккаунтов", command=controller.import_accounts).pack(fill="x", pady=(6, 2))
        ttk.Label(apps, text="Файл будет передан в Download/DroidFleet/accounts.", foreground="#607080", wraplength=230).pack(anchor="w")
        media = ttk.LabelFrame(parent, text="Экран устройства", padding=8)
        media.pack(fill="x", pady=(8, 4))
        ttk.Button(media, text="Открыть scrcpy", command=controller.start_scrcpy).pack(fill="x", pady=2)
        ttk.Button(media, text="Закрыть scrcpy", command=controller.stop_scrcpy).pack(fill="x", pady=2)
        self.status = ttk.Label(parent, text="Нет выбранного устройства", wraplength=220)
        self.status.pack(anchor="w", pady=5)

    def set_language(self, language):
        russian = language == "Русский"
        navigation = {"Android": "Android", "Windows": "Windows", "Groups": "Группы", "Tasks": "Задания", "Logs": "Журнал", "Settings": "Настройки"}
        quick = {"Screenshot": "Скриншот", "Restart": "Перезапуск", "Reconnect ADB": "Переподключить ADB", "HOME": "ГЛАВНЫЙ ЭКРАН", "BACK": "НАЗАД", "RECENTS": "ПОСЛЕДНИЕ", "POWER": "ПИТАНИЕ"}
        if not russian:
            navigation = {key: key for key in navigation}
            quick = {key: key for key in quick}
        for key, button in self.navigation_buttons.items():
            button.config(text=navigation[key])
        for key, button in self.quick_buttons.items():
            button.config(text=quick[key])

    def set_groups(self, groups):
        current = self.group_var.get()
        values = ("Все группы", *sorted(groups, key=str.casefold))
        self.group_filter.configure(values=values)
        self.group_var.set(current if current in values else "Все группы")

    def set_manufacturers(self, manufacturers):
        current = self.manufacturer_var.get()
        values = ("Все устройства", *sorted(manufacturers, key=str.casefold))
        self.manufacturer_filter.configure(values=values)
        self.manufacturer_var.set(current if current in values else "Все устройства")

