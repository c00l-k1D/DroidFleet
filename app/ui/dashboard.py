import tkinter as tk
from .device_card import DeviceCard


class Dashboard:
    def __init__(self, root, controller):
        self.controller = controller
        right = tk.Frame(root, bg="#0b1117"); right.pack(side="right", fill="both", expand=True, padx=(10, 10), pady=10)
        heading = tk.Frame(right, bg="#0b1117", height=42)
        heading.pack(fill="x")
        heading.pack_propagate(False)
        tk.Label(heading, text="FARM DEVICES", bg="#0b1117", fg="#f1f7fb", font=("Segoe UI", 14, "bold")).pack(side="left", padx=8)
        self.summary = tk.Label(heading, text="0 online", bg="#0b1117", fg="#8da1b2", font=("Segoe UI", 9))
        self.summary.pack(side="right", padx=8)
        self.view_mode = "GRID"
        tk.Button(heading, text="LIST", command=lambda: self.set_view_mode("LIST"), bg="#1b2935", fg="#dce8ef", relief="flat").pack(side="right", padx=(2, 0))
        tk.Button(heading, text="GRID", command=lambda: self.set_view_mode("GRID"), bg="#1b2935", fg="#dce8ef", relief="flat").pack(side="right", padx=(2, 0))
        self.canvas = tk.Canvas(right, background="#101010", highlightthickness=0)
        scrollbar = tk.Scrollbar(right, orient="vertical", command=self.canvas.yview); scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scrollbar.set); self.canvas.pack(side="left", fill="both", expand=True)
        self.frame = tk.Frame(self.canvas, bg="#101010"); self.window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.frame.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: (self.canvas.itemconfigure(self.window, width=event.width), self.rebuild()))
        self.canvas.bind_all("<MouseWheel>", lambda event: self.canvas.yview_scroll(int(-event.delta / 120), "units"))
        self.cards = {}
        self.filter_callback = None
        self.group_callback = None
        self.group_headers = {}
        self.empty_state = tk.Label(self.frame, text="Нет подключённых устройств\n\nПодключите телефон по USB и нажмите\n«Обновить список устройств».", bg="#101010", fg="#9aa6b2", font=("Segoe UI", 12), justify="center")
        self.empty_state.grid(row=0, column=0, padx=40, pady=80)
        self._update_summary()

    def add(self, serial):
        self.cards[serial] = DeviceCard(
            self.frame, serial, 
            self.controller.toggle_device_selection, 
            self.controller.open_device_scrcpy,
            self.controller.handle_device_input if hasattr(self.controller, 'handle_device_input') else None
        )
        self.empty_state.grid_remove()
        self._update_summary()
        self.rebuild()

    def remove(self, serial):
        card = self.cards.pop(serial, None)
        if card: card.frame.destroy()
        for group, header in list(self.group_headers.items()):
            if not any(self.group_callback and self.group_callback(item.serial) == group for item in self.cards.values()):
                header.destroy()
                del self.group_headers[group]
        if not self.cards:
            self.empty_state.grid(row=0, column=0, padx=40, pady=80)
        self._update_summary()

    def _update_summary(self):
        online = sum(1 for serial in self.cards if serial in self.controller.devices)
        self.summary.config(text=f"{online} online / {len(self.cards)} total")

    def rebuild(self):
        columns = 1 if self.view_mode == "LIST" else max(1, max(self.canvas.winfo_width(), 800) // 205)
        for card in self.cards.values():
            card.set_view_mode(self.view_mode)
        visible_cards = [card for card in self.cards.values() if not self.filter_callback or self.filter_callback(card.serial)]
        if visible_cards:
            self.empty_state.grid_remove()
        elif self.cards:
            self.empty_state.config(text="В этой группе устройств пока нет карточек.")
            self.empty_state.grid(row=0, column=0, padx=40, pady=80)
        for card in self.cards.values():
            if card not in visible_cards:
                card.frame.grid_remove()
        for header in self.group_headers.values():
            header.grid_remove()
        row = 0
        if self.group_callback:
            visible_cards.sort(key=lambda card: (self.group_callback(card.serial) or "Не определено", card.serial.casefold()))
        current_group = None
        for index, card in enumerate(visible_cards):
            group = self.group_callback(card.serial) if self.group_callback else None
            if group != current_group:
                if group:
                    header = self.group_headers.get(group)
                    if header is None:
                        header = tk.Label(self.frame, text=group, bg="#101010", fg="#138a80", font=("Segoe UI", 10, "bold"), anchor="w")
                        self.group_headers[group] = header
                    header.grid(row=row, column=0, columnspan=columns, padx=8, pady=(12, 2), sticky="ew")
                    row += 1
                current_group = group
            card.frame.grid(row=row, column=index % columns, padx=5, pady=5, sticky="n")
            if index % columns == columns - 1:
                row += 1
        if visible_cards and len(visible_cards) % columns:
            row += 1

    def set_filter(self, callback):
        self.filter_callback = callback
        self.rebuild()

    def set_grouping(self, callback):
        self.group_callback = callback
        self.rebuild()

    def set_view_mode(self, mode):
        self.view_mode = mode
        self.rebuild()
