import tkinter as tk
from tkinter import ttk


class LogViewer:
    def __init__(self, parent, logger):
        self.logger = logger
        self.window = tk.Toplevel(parent)
        self.window.title("Логи DroidFleet")
        self.window.geometry("900x500")
        self.window.minsize(600, 300)
        self.text = tk.Text(self.window, wrap="none", state="disabled", background="#101010", foreground="#dddddd")
        self.text.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(self.window, orient="vertical", command=self.text.yview)
        scrollbar.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scrollbar.set)
        ttk.Button(self.window, text="Обновить", command=self.refresh).pack(side="bottom", fill="x", padx=6, pady=6)
        self.refresh()

    def refresh(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", self.logger.text() or "Логов пока нет.")
        self.text.configure(state="disabled")
        self.text.see("end")
