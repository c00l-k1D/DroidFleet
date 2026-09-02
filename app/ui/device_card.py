import tkinter as tk


class DeviceCard:
    def __init__(self, parent, serial, on_select, on_open, on_device_input=None):
        self.serial = serial
        self.on_device_input = on_device_input
        self.compact = False
        self.record = None
        self.frame = tk.Frame(parent, bg="#181818", bd=2, relief="solid")
        self.frame.configure(width=210, height=430)
        self.frame.pack_propagate(False)
        header = tk.Frame(self.frame, bg="#181818"); header.pack(fill="x")
        self.title = tk.Label(header, text=serial[:20] + ("..." if len(serial) > 20 else ""), bg="#181818", fg="#eeeeee", font=("Segoe UI", 9, "bold"), anchor="w"); self.title.pack(side="left", padx=6, pady=4)
        indicator = tk.Label(header, text="●", bg="#181818", fg="#42ff42", font=("Segoe UI", 11, "bold")); indicator.pack(side="right", padx=6)
        self.screen = tk.Label(self.frame, bg="#000000", fg="#777777", text="VIDEO...", font=("Segoe UI", 9), width=180, height=300); self.screen.pack(padx=5, pady=(0, 5))
        self.hardware = tk.Label(self.frame, text="Model: --\nAndroid --\nBattery --     CPU --\nRAM --", bg="#181818", fg="#cccccc", justify="left", anchor="w", font=("Segoe UI", 8)); self.hardware.pack(fill="x", padx=6, pady=(0, 5))
        footer = tk.Frame(self.frame, bg="#181818"); footer.pack(fill="x")
        adb_status = tk.Label(footer, text="ADB ONLINE", bg="#181818", fg="#42ff42", font=("Segoe UI", 8, "bold")); adb_status.pack(side="left", padx=6, pady=3)
        video_status = tk.Label(footer, text="VIDEO --", bg="#181818", fg="#888888", font=("Segoe UI", 8)); video_status.pack(side="right", padx=6)
        self.meta = {"indicator": indicator, "adb_status": adb_status, "video_status": video_status, "frames": 0}
        for widget in (self.frame, header, self.title, indicator, self.hardware, footer, adb_status, video_status):
            widget.bind("<Button-1>", lambda event: on_select(self.serial))
            widget.bind("<Double-Button-1>", lambda event: on_open(self.serial))
        
        # Bind screen interactions (click, drag, wheel)
        self.screen.bind("<Button-1>", self._on_screen_click)
        self.screen.bind("<B1-Motion>", self._on_screen_drag)
        self.screen.bind("<ButtonRelease-1>", self._on_screen_release)
        self.screen.bind("<MouseWheel>", self._on_screen_wheel)
        
        # Dragging state
        self._drag_start = None

    def _on_screen_click(self, event):
        """Handle screen click - record start position."""
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
        
        # Get widget size for normalization (0-1000)
        width = self.screen.winfo_width()
        height = self.screen.winfo_height()
        
        if width > 1 and height > 1:
            # Normalize to 0-1000 range
            norm_x_start = int((x_start / width) * 1000)
            norm_y_start = int((y_start / height) * 1000)
            norm_x_end = int((x_end / width) * 1000)
            norm_y_end = int((y_end / height) * 1000)
            
            if distance > 20:  # Swipe threshold
                self.on_device_input(self.serial, "SWIPE", {
                    "x1": norm_x_start,
                    "y1": norm_y_start,
                    "x2": norm_x_end,
                    "y2": norm_y_end,
                })
            else:  # Tap
                norm_x = int((x_start / width) * 1000)
                norm_y = int((y_start / height) * 1000)
                self.on_device_input(self.serial, "TAP", {"x": norm_x, "y": norm_y})

    def _on_screen_wheel(self, event):
        """Handle mouse wheel - send zoom in/out."""
        if not self.on_device_input:
            return
        
        # Get widget size for normalization
        width = self.screen.winfo_width()
        height = self.screen.winfo_height()
        
        if width > 1 and height > 1:
            norm_x = int((event.x / width) * 1000)
            norm_y = int((event.y / height) * 1000)
            action = "ZOOM_IN" if event.delta > 0 else "ZOOM_OUT"
            self.on_device_input(self.serial, action, {"x": norm_x, "y": norm_y})

    def update_hardware(self, info):
        self.hardware.config(text=(f"Model: {info.model}\nOS: {info.android_version}\n"
                                   f"Battery: {info.battery}\nCPU: {info.cpu}\nRAM: {info.ram}\n"
                                   f"Temperature: {info.temperature}\nIP: {info.ip}"))

    def update_device(self, record):
        self.record = record
        colors = {"ONLINE": "#42ff42", "BUSY": "#ffd34d", "OFFLINE": "#ff5c5c", "ERROR": "#ff9f43"}
        status = str(record.status).upper()
        self.title.config(text=record.display_name[:24] + ("..." if len(record.display_name) > 24 else ""))
        self.meta["indicator"].config(text="●", fg=colors.get(status, "#ff9f43"))
        self.meta["adb_status"].config(text=status, fg=colors.get(status, "#ff9f43"))
        if self.compact:
            self.hardware.config(text=f"{record.model}    Android {record.os}    Battery {record.battery}    CPU {record.cpu}    RAM {record.ram}")
        else:
            self.hardware.config(text=(f"{record.model}\nAndroid {record.os}\n"
                                       f"Battery {record.battery}     CPU {record.cpu}\nRAM {record.ram}"))

    def set_view_mode(self, mode):
        compact = mode == "LIST"
        if compact == self.compact:
            return
        self.compact = compact
        if compact:
            self.screen.pack_forget()
            self.frame.configure(width=900, height=86)
        else:
            self.screen.pack(padx=5, pady=(0, 5), after=self.title.master)
            self.frame.configure(width=210, height=430)
        if self.record:
            self.update_device(self.record)

    def set_selected(self, selected):
        color = "#175ea8" if selected else "#181818"
        self.frame.config(bg=color, bd=3 if selected else 2)
        for child in self.frame.winfo_children():
            if child != self.screen:
                child.config(bg=color)
                for item in child.winfo_children():
                    if item != self.screen:
                        item.config(bg=color)
