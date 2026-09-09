import tkinter as tk


class DeviceCard:
    def __init__(self, parent, serial, on_select, on_open=None, on_device_input=None, connection_label="SELF-HOST", on_context_menu=None):
        self.serial = serial
        self.on_device_input = on_device_input
        self.connection_label = connection_label
        self.compact = False
        self.record = None
        self.frame = tk.Frame(parent, bg="#17232d", bd=1, relief="solid", highlightthickness=1, highlightbackground="#263947")
        self.frame.configure(width=250, height=430)
        self.frame.pack_propagate(False)
        header = tk.Frame(self.frame, bg="#17232d"); header.pack(fill="x")
        self.title = tk.Label(header, text=serial[:20] + ("..." if len(serial) > 20 else ""), bg="#17232d", fg="#f1f7fb", font=("Segoe UI", 9, "bold"), anchor="w"); self.title.pack(side="left", padx=8, pady=6)
        indicator = tk.Label(header, text="●", bg="#17232d", fg="#42ff42", font=("Segoe UI", 11, "bold")); indicator.pack(side="right", padx=8)
        self.screen = tk.Label(self.frame, bg="#000000", fg="#777777", text="VIDEO...", font=("Segoe UI", 9), width=220, height=300, takefocus=True); self.screen.pack(padx=5, pady=(0, 5))
        self.hardware = tk.Label(self.frame, text=f"Model: --\nAndroid --\nBattery --     CPU --\nRAM --\nConnection: {self.connection_label}", bg="#17232d", fg="#b9c8d1", justify="left", anchor="w", font=("Segoe UI", 8)); self.hardware.pack(fill="x", padx=8, pady=(0, 6))
        footer = tk.Frame(self.frame, bg="#17232d"); footer.pack(fill="x")
        adb_status = tk.Label(footer, text="ADB ONLINE", bg="#17232d", fg="#42ff42", font=("Segoe UI", 8, "bold")); adb_status.pack(side="left", padx=8, pady=5)
        video_status = tk.Label(footer, text="VIDEO --", bg="#17232d", fg="#8295a2", font=("Segoe UI", 8)); video_status.pack(side="right", padx=8)
        self.meta = {"indicator": indicator, "adb_status": adb_status, "video_status": video_status, "frames": 0, "source_size": (1, 1)}
        widgets = (self.frame, header, self.title, indicator, self.hardware, footer, adb_status, video_status, self.screen)
        for widget in widgets:
            widget.bind("<Button-1>", lambda event: on_select(self.serial))
            widget.bind("<Button-3>", lambda event: on_context_menu and on_context_menu(self.serial, event))
        
        # Bind screen interactions (click, drag, wheel)
        self.screen.bind("<Button-1>", self._on_screen_click)
        self.screen.bind("<B1-Motion>", self._on_screen_drag)
        self.screen.bind("<ButtonRelease-1>", self._on_screen_release)
        self.screen.bind("<MouseWheel>", self._on_screen_wheel)
        self.screen.bind("<Key>", self._on_key)
        
        # Dragging state
        self._drag_start = None

    def _on_screen_click(self, event):
        """Handle screen click - record start position."""
        self.screen.focus_set()
        if self.on_device_input:
            self._drag_start = (event.x, event.y)

    def _on_screen_drag(self, event):
        """Handle screen drag - track movement."""
        # Could be used for visual feedback, but main logic is in release
        pass

    def _on_screen_release(self, event):
        """Handle screen release - send tap or swipe to device."""
        if not self.on_device_input or not self._drag_start:
            return
        
        x_start, y_start = self._drag_start
        x_end, y_end = event.x, event.y
        self._drag_start = None
        
        # Calculate movement distance
        dx = x_end - x_start
        dy = y_end - y_start
        distance = max(abs(dx), abs(dy))
        
        start = self._screen_coordinates(x_start, y_start)
        end = self._screen_coordinates(x_end, y_end)
        if start and end:
            norm_x_start, norm_y_start = start
            norm_x_end, norm_y_end = end
            # Normalize to 0-1000 range
            if distance > 20:  # Swipe threshold
                self.on_device_input(self.serial, "SWIPE", {
                    "x1": norm_x_start,
                    "y1": norm_y_start,
                    "x2": norm_x_end,
                    "y2": norm_y_end,
                })
            else:  # Tap
                norm_x, norm_y = start
                self.on_device_input(self.serial, "TAP", {"x": norm_x, "y": norm_y})

    def _screen_coordinates(self, x, y):
        width = self.screen.winfo_width()
        height = self.screen.winfo_height()
        source_width, source_height = self.meta["source_size"]
        if width <= 1 or height <= 1 or source_width <= 1 or source_height <= 1:
            return None
        source_ratio = source_width / source_height
        canvas_ratio = width / height
        if source_ratio >= canvas_ratio:
            image_width = width
            image_height = max(1, int(width / source_ratio))
        else:
            image_height = height
            image_width = max(1, int(height * source_ratio))
        left = (width - image_width) / 2
        top = (height - image_height) / 2
        if x < left or y < top or x >= left + image_width or y >= top + image_height:
            return None
        norm_x = int((x - left) * 1000 / image_width)
        norm_y = int((y - top) * 1000 / image_height)
        return max(0, min(999, norm_x)), max(0, min(999, norm_y))

    def _on_screen_wheel(self, event):
        """Handle mouse wheel - send zoom in/out."""
        if not self.on_device_input:
            return
        
        coordinates = self._screen_coordinates(event.x, event.y)
        if coordinates:
            norm_x, norm_y = coordinates
            action = "ZOOM_IN" if event.delta > 0 else "ZOOM_OUT"
            self.on_device_input(self.serial, action, {"x": norm_x, "y": norm_y})

    def _on_key(self, event):
        if not self.on_device_input:
            return
        special_keys = {
            "Return": "KEYCODE_ENTER", "BackSpace": "KEYCODE_DEL", "Tab": "KEYCODE_TAB",
            "Escape": "KEYCODE_ESCAPE", "Left": "KEYCODE_DPAD_LEFT", "Right": "KEYCODE_DPAD_RIGHT",
            "Up": "KEYCODE_DPAD_UP", "Down": "KEYCODE_DPAD_DOWN", "Home": "KEYCODE_MOVE_HOME",
            "End": "KEYCODE_MOVE_END", "Delete": "KEYCODE_FORWARD_DEL",
        }
        key = special_keys.get(event.keysym)
        if key:
            self.on_device_input(self.serial, "KEY", {"key": key})
        elif event.char and event.char.isprintable():
            self.on_device_input(self.serial, "TEXT", {"text": event.char})
        else:
            return
        return "break"

    def update_hardware(self, info):
        try:
            width, height = str(info.screen).lower().split("x", 1)
            self.meta["source_size"] = (max(1, int(width)), max(1, int(height)))
        except (TypeError, ValueError):
            pass
        self.hardware.config(text=(f"Model: {info.model}\nOS: {info.android_version}\n"
                                   f"SDK: {info.sdk}  Battery: {info.battery}\n"
                                   f"CPU: {info.cpu}\nRAM: {info.ram}  Storage: {info.storage}\n"
                                   f"Temperature: {info.temperature}\nResolution: {info.screen}\nIP: {info.ip}"))

    def update_device(self, record):
        self.record = record
        colors = {"ONLINE": "#42ff42", "BUSY": "#ffd34d", "OFFLINE": "#ff5c5c", "ERROR": "#ff9f43"}
        status = str(record.status).upper()
        self.title.config(text=record.display_name[:24] + ("..." if len(record.display_name) > 24 else ""))
        self.meta["indicator"].config(text="●", fg=colors.get(status, "#ff9f43"))
        self.meta["adb_status"].config(text=status, fg=colors.get(status, "#ff9f43"))
        if self.compact:
            self.hardware.config(text=(
                f"{record.model} | Android {record.os} | Battery {record.battery} | "
                f"RAM {record.ram}\n{self.connection_label} | {status}"
            ))
        else:
            self.hardware.config(text=(f"{record.model}\nAndroid {record.os}\n"
                                       f"SDK {record.sdk}  Battery {record.battery}\n"
                                       f"CPU {record.cpu}  RAM {record.ram}\nStorage {record.storage}\n"
                                       f"Connection: {self.connection_label}"))

    def set_view_mode(self, mode):
        compact = mode == "LIST"
        if compact == self.compact:
            return
        self.compact = compact
        if compact:
            self.screen.pack_forget()
            self.frame.configure(width=900, height=66)
        else:
            self.screen.pack(padx=5, pady=(0, 5), after=self.title.master)
            self.frame.configure(width=250, height=430)
        if self.record:
            self.update_device(self.record)

    def set_selected(self, selected):
        color = "#214f59" if selected else "#17232d"
        self.frame.config(bg=color, bd=3 if selected else 2)
        for child in self.frame.winfo_children():
            if child != self.screen:
                child.config(bg=color)
                for item in child.winfo_children():
                    if item != self.screen:
                        item.config(bg=color)
