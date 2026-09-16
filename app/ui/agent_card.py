import tkinter as tk


class AgentCard:
    def __init__(self, parent, record, on_open, connection_label="SELF-HOST", on_context_menu=None, on_select=None):
        self.parent = parent
        self.record = {}
        self.connection_label = connection_label
        self.on_select = on_select
        self.frame = tk.Frame(parent, bg="#25333d", bd=1, relief="solid", highlightthickness=1, highlightbackground="#3b5361")
        self.frame.configure(width=250, height=220)
        self.frame.pack_propagate(False)
        header = tk.Frame(self.frame, bg="#25333d")
        header.pack(fill="x")
        self.title = tk.Label(header, bg="#25333d", fg="#f1f7fb", font=("Segoe UI", 9, "bold"), anchor="w")
        self.title.pack(side="left", padx=8, pady=6)
        self.indicator = tk.Label(header, text="●", bg="#25333d", fg="#42ff42", font=("Segoe UI", 11, "bold"))
        self.indicator.pack(side="right", padx=8)
        self.details = tk.Label(self.frame, bg="#25333d", fg="#b9c8d1", justify="left", anchor="w", font=("Segoe UI", 8), wraplength=232)
        self.details.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.status = tk.Label(self.frame, bg="#25333d", fg="#42ff42", font=("Segoe UI", 8, "bold"), anchor="w")
        self.status.pack(fill="x", padx=8, pady=5)
        for widget in (self.frame, header, self.title, self.indicator, self.details, self.status):
            widget.bind("<Button-1>", lambda event: self.on_select and self.on_select(self.record.get("device_id", "")))
            widget.bind("<Double-Button-1>", lambda event: on_open(self.record.get("device_id", "")))
            widget.bind("<Button-3>", lambda event: on_context_menu and on_context_menu(self.record.get("device_id", ""), event))
        self.update(record)

    def update(self, record):
        self.record = dict(record)
        state = str(record.get("status", "OFFLINE")).upper()
        colors = {"ONLINE": "#42ff42", "UPDATING": "#62c8ff", "BUSY": "#ffd34d", "OFFLINE": "#ff5c5c", "ERROR": "#ff9f43"}
        color = colors.get(state, "#ff9f43")
        platform_name = str(record.get("platform") or "Windows")
        self.title.config(text=str(record.get("hostname") or record.get("device_id") or platform_name)[:24])
        self.indicator.config(fg=color)
        android_devices = record.get("android_devices") or []
        android_label = self._android_label(android_devices)
        if self.frame.winfo_height() <= 100:
            details = (
                f"ID: {record.get('device_id', '--')} | OS: {record.get('os_version') or record.get('windows_version', '--')}\n"
                f"CPU: {record.get('cpu', '--')} | RAM: {record.get('ram', '--')} | "
                f"IP: {record.get('ip', '--')} | Ping: {self._ping_label(record.get('ping_ms'))} | Android: {android_label} | {self.connection_label}"
            )
        else:
            details = (
                f"ID: {record.get('device_id', '--')}\n"
                f"OS: {record.get('os_version') or record.get('windows_version', '--')}\n"
                f"CPU: {record.get('cpu', '--')}\n"
                f"RAM: {record.get('ram', '--')}\n"
                f"IP: {record.get('ip', '--')}\n"
                f"Ping: {self._ping_label(record.get('ping_ms'))}\n"
                f"Android devices: {android_label}\n"
                f"Screen: {self._screen_label(record.get('screen'))}\n"
                f"Agent: {record.get('agent_version', '--')} ({len(record.get('capabilities', []))} capabilities)\n"
                f"Connection: {self.connection_label}"
            )
        self.details.config(text=details)
        self.status.config(text=f"{platform_name.upper()} FARM AGENT  {state}", fg=color)

    @staticmethod
    def _screen_label(screen):
        if not isinstance(screen, dict):
            return "unknown"
        if screen.get("available"):
            return f"{screen.get('width', '?')}x{screen.get('height', '?')}"
        return "unavailable"

    @staticmethod
    def _ping_label(value):
        if value is None or value == "--":
            return "--"
        try:
            return f"{float(value):.0f} ms"
        except (TypeError, ValueError):
            return "--"

    @staticmethod
    def _android_label(devices):
        if not isinstance(devices, list):
            return "0"
        online = [item for item in devices if isinstance(item, dict) and item.get("status") == "device"]
        if not online:
            return "0"
        names = [str(item.get("model") or item.get("serial", "?")) for item in online[:3]]
        suffix = f" +{len(online) - 3}" if len(online) > 3 else ""
        return f"{len(online)} ({', '.join(names)}{suffix})"

    def set_view_mode(self, mode):
        compact = mode == "LIST"
        self.frame.configure(width=900 if compact else 250, height=66 if compact else 220)
        if compact:
            self.details.config(anchor="w")
        self.update(self.record)

    def set_selected(self, selected):
        color = "#31505a" if selected else "#25333d"
        self.frame.config(bg=color, bd=3 if selected else 2)
        for child in self.frame.winfo_children():
            child.config(bg=color)
            for item in child.winfo_children():
                item.config(bg=color)
