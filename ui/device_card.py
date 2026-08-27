import tkinter as tk


class DeviceCard:
    def __init__(self, parent, serial, on_select, on_open):
        self.serial = serial
        self.frame = tk.Frame(parent, bg="#181818", bd=2, relief="solid")
        header = tk.Frame(self.frame, bg="#181818"); header.pack(fill="x")
        title = tk.Label(header, text=serial[:20] + ("..." if len(serial) > 20 else ""), bg="#181818", fg="#eeeeee", font=("Segoe UI", 9, "bold"), anchor="w"); title.pack(side="left", padx=6, pady=4)
        indicator = tk.Label(header, text="●", bg="#181818", fg="#42ff42", font=("Segoe UI", 11, "bold")); indicator.pack(side="right", padx=6)
        self.screen = tk.Label(self.frame, bg="#000000", fg="#777777", text="VIDEO...", font=("Segoe UI", 9), width=22, height=18); self.screen.pack(padx=5, pady=(0, 5))
        self.hardware = tk.Label(self.frame, text="Производитель: --\nМодель: --\nЭкран: --\nAndroid: --\nАкб: --   Температура: --", bg="#181818", fg="#cccccc", justify="left", anchor="w", font=("Segoe UI", 8)); self.hardware.pack(fill="x", padx=6, pady=(0, 5))
        footer = tk.Frame(self.frame, bg="#181818"); footer.pack(fill="x")
        adb_status = tk.Label(footer, text="ADB ONLINE", bg="#181818", fg="#42ff42", font=("Segoe UI", 8, "bold")); adb_status.pack(side="left", padx=6, pady=3)
        video_status = tk.Label(footer, text="VIDEO --", bg="#181818", fg="#888888", font=("Segoe UI", 8)); video_status.pack(side="right", padx=6)
        self.meta = {"indicator": indicator, "adb_status": adb_status, "video_status": video_status, "frames": 0}
        for widget in (self.frame, header, title, indicator, self.screen, self.hardware, footer, adb_status, video_status):
            widget.bind("<Button-1>", lambda event: on_select(self.serial))
            widget.bind("<Double-Button-1>", lambda event: on_open(self.serial))

    def update_hardware(self, info):
        self.hardware.config(text=(f"Производитель: {info.manufacturer}\n"
                       f"Модель: {info.model}\n"
                                   f"Экран: {info.screen}\n"
                                   f"Android: {info.android_version}\n"
                                   f"Акб: {info.battery}   Температура: {info.temperature}"))

    def set_selected(self, selected):
        color = "#175ea8" if selected else "#181818"
        self.frame.config(bg=color, bd=3 if selected else 2)
        for child in self.frame.winfo_children():
            if child != self.screen:
                child.config(bg=color)
                for item in child.winfo_children():
                    if item != self.screen:
                        item.config(bg=color)
