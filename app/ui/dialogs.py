from tkinter import messagebox


def warning(title: str, text: str):
    messagebox.showwarning(title, text)


def error(title: str, text: str):
    messagebox.showerror(title, text)
