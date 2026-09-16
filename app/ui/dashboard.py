import tkinter as tk
from .device_card import DeviceCard
from .agent_card import AgentCard


class Dashboard:
    def __init__(self, root, controller):
        self.controller = controller
        right = tk.Frame(root, bg="#0b1117"); right.pack(side="right", fill="both", expand=True, padx=(14, 14), pady=12)
        self.right = right
        self.embedded_view = None
        heading = tk.Frame(right, bg="#0b1117", height=42)
        heading.pack(fill="x")
        heading.pack_propagate(False)
        tk.Label(heading, text="FARM DEVICES", bg="#0b1117", fg="#f1f7fb", font=("Segoe UI", 14, "bold")).pack(side="left", padx=8)
        self.summary = tk.Label(heading, text="0 online", bg="#0b1117", fg="#8da1b2", font=("Segoe UI", 9))
        self.summary.pack(side="right", padx=8)
        self.view_mode = "GRID"
        self.list_button = tk.Button(heading, text="LIST", command=lambda: self.set_view_mode("LIST"), bg="#172532", fg="#a9bac6", activebackground="#246c70", activeforeground="#ffffff", relief="flat", padx=12, pady=5)
        self.list_button.pack(side="right", padx=(2, 0))
        self.grid_button = tk.Button(heading, text="GRID", command=lambda: self.set_view_mode("GRID"), bg="#246c70", fg="#ffffff", activebackground="#2f8580", activeforeground="#ffffff", relief="flat", padx=12, pady=5)
        self.grid_button.pack(side="right", padx=(2, 0))
        self.canvas = tk.Canvas(right, background="#0f171e", highlightthickness=0)
        scrollbar = tk.Scrollbar(right, orient="vertical", command=self.canvas.yview); scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scrollbar.set); self.canvas.pack(side="left", fill="both", expand=True)
        self.frame = tk.Frame(self.canvas, bg="#101010"); self.window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.frame.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: (self.canvas.itemconfigure(self.window, width=event.width), self.rebuild()))
        self.canvas.bind_all("<MouseWheel>", lambda event: self.canvas.yview_scroll(int(-event.delta / 120), "units"))
        self.cards = {}
        self.agent_cards = {}
        self.filter_callback = None
        self.group_callback = None
        self.group_headers = {}
        self.empty_state = tk.Label(self.frame, text="Нет подключённых устройств\n\nПодключите телефон по USB и нажмите\n«Обновить список устройств».", bg="#101010", fg="#9aa6b2", font=("Segoe UI", 12), justify="center")
        self.empty_state.grid(row=0, column=0, padx=40, pady=80)
        self._update_summary()

    def open_embedded_view(self, title):
        self.canvas.pack_forget()
        if self.embedded_view is not None:
            self.embedded_view.destroy()
        view = tk.Frame(self.right, bg="#101010")
        view.pack(side="top", fill="both", expand=True)
        header = tk.Frame(view, bg="#172532")
        header.pack(fill="x")
        tk.Button(
            header, text="< BACK TO DEVICES",
            command=self.close_embedded_view,
            bg="#246c70", fg="#ffffff", relief="flat",
            padx=10, pady=5,
        ).pack(side="left", padx=8, pady=6)
        tk.Label(
            header, text=title, bg="#172532", fg="#f1f7fb",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=8)
        content = tk.Frame(view, bg="#101010")
        content.pack(fill="both", expand=True)
        self.embedded_view = view
        return content

    def close_embedded_view(self):
        if self.embedded_view is not None:
            self.embedded_view.destroy()
            self.embedded_view = None
        if hasattr(self.controller, "on_embedded_view_closed"):
            self.controller.on_embedded_view_closed()
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rebuild()

    def add(self, serial):
        self.cards[serial] = DeviceCard(
            self.frame, serial, 
            self.controller.toggle_device_selection, 
            None,
            self.controller.handle_device_input if hasattr(self.controller, 'handle_device_input') else None,
            connection_label=self.controller.android_connection_label(serial),
            on_context_menu=self.controller.show_android_context_menu,
        )
        self.empty_state.grid_remove()
        self._update_summary()
        self.rebuild()

    def add_agent(self, record):
        device_id = str(record.get("device_id", "")).strip()
        if not device_id:
            return
        card = self.agent_cards.get(device_id)
        if card is None:
            card = AgentCard(
                self.frame,
                record,
                self.controller.show_windows_view,
                self.controller.connection_profile.label,
                self.controller.show_windows_context_menu,
                self.controller.toggle_agent_selection,
            )
            self.agent_cards[device_id] = card
        else:
            card.update(record)
        self.empty_state.grid_remove()
        self._update_summary()
        self.rebuild()

    def remove_agent(self, device_id):
        card = self.agent_cards.pop(device_id, None)
        if card:
            card.frame.destroy()
        if not self.agent_cards and "WINDOWS AGENTS" in self.group_headers:
            self.group_headers.pop("WINDOWS AGENTS").destroy()
        self.rebuild()

    def remove(self, serial):
        card = self.cards.pop(serial, None)
        if card: card.frame.destroy()
        for group, header in list(self.group_headers.items()):
            if group == "WINDOWS AGENTS":
                continue
            if not any(self.group_callback and self.group_callback(item.serial) == group for item in self.cards.values()):
                header.destroy()
                del self.group_headers[group]
        if not self.cards and not self.agent_cards:
            self.empty_state.grid(row=0, column=0, padx=40, pady=80)
        self._update_summary()

    def _update_summary(self):
        online = sum(1 for serial in self.cards if serial in self.controller.devices)
        agent_online = sum(1 for card in self.agent_cards.values() if card.record.get("status") == "ONLINE")
        total = len(self.cards) + len(self.agent_cards)
        self.summary.config(text=f"{online + agent_online} online / {total} total")

    def rebuild(self):
        columns = 1 if self.view_mode == "LIST" else max(1, max(self.canvas.winfo_width(), 800) // 260)
        for card in self.cards.values():
            card.set_view_mode(self.view_mode)
        for card in self.agent_cards.values():
            card.set_view_mode(self.view_mode)
            card.set_selected(str(card.record.get("device_id", "")) in self.controller.selected_agents)
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
        if self.agent_cards:
            header = self.group_headers.get("WINDOWS AGENTS")
            if header is None:
                header = tk.Label(self.frame, text="WINDOWS AGENTS", bg="#101010", fg="#4ec6ff", font=("Segoe UI", 10, "bold"), anchor="w")
                self.group_headers["WINDOWS AGENTS"] = header
            header.grid(row=row, column=0, columnspan=columns, padx=8, pady=(16, 2), sticky="ew")
            row += 1
            for index, card in enumerate(self.agent_cards.values()):
                card.frame.grid(row=row, column=index % columns, padx=5, pady=5, sticky="n")
                if index % columns == columns - 1:
                    row += 1

    def set_filter(self, callback):
        self.filter_callback = callback
        self.rebuild()

    def set_grouping(self, callback):
        self.group_callback = callback
        self.rebuild()

    def set_view_mode(self, mode):
        self.view_mode = mode
        active = {"bg": "#246c70", "fg": "#ffffff"}
        inactive = {"bg": "#172532", "fg": "#a9bac6"}
        self.grid_button.config(**(active if mode == "GRID" else inactive))
        self.list_button.config(**(active if mode == "LIST" else inactive))
        self.rebuild()
