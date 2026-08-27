import tkinter as tk
from .device_card import DeviceCard


class Dashboard:
    def __init__(self, root, controller):
        self.controller = controller
        right = tk.Frame(root); right.pack(side="right", fill="both", expand=True)
        self.canvas = tk.Canvas(right, background="#101010", highlightthickness=0)
        scrollbar = tk.Scrollbar(right, orient="vertical", command=self.canvas.yview); scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scrollbar.set); self.canvas.pack(side="left", fill="both", expand=True)
        self.frame = tk.Frame(self.canvas, bg="#101010"); self.window = self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.frame.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: (self.canvas.itemconfigure(self.window, width=event.width), self.rebuild()))
        self.canvas.bind_all("<MouseWheel>", lambda event: self.canvas.yview_scroll(int(-event.delta / 120), "units"))
        self.cards = {}
        self.filter_callback = None

    def add(self, serial):
        self.cards[serial] = DeviceCard(self.frame, serial, self.controller.toggle_device_selection, self.controller.open_device_scrcpy)
        self.rebuild()

    def remove(self, serial):
        card = self.cards.pop(serial, None)
        if card: card.frame.destroy()

    def rebuild(self):
        columns = max(1, max(self.canvas.winfo_width(), 800) // 205)
        visible_cards = [card for card in self.cards.values() if not self.filter_callback or self.filter_callback(card.serial)]
        for card in self.cards.values():
            if card not in visible_cards:
                card.frame.grid_remove()
        for index, card in enumerate(visible_cards):
            card.frame.grid(row=index // columns, column=index % columns, padx=5, pady=5, sticky="n")

    def set_filter(self, callback):
        self.filter_callback = callback
        self.rebuild()
