"""Classroom Pi window.

Shows link status, classroom light state, last sent reading, an event
log, buttons to push a reading or a photo, and an auto-send switch.
"""
import customtkinter as ctk
import tkinter as tk

BG = "#F5F5F5"
INK = "#111111"
CARD = "#FFFFFF"
RED = "#E60023"


class PiPanel(ctk.CTk):
    def __init__(self, on_send_reading, on_send_photo, on_auto):
        super().__init__()
        self.title("Classroom Pi Node")
        self.geometry("430x640")
        self.on_send_reading = on_send_reading
        self.on_send_photo = on_send_photo

        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")
        self.configure(bg_color=BG)
        self.grid_columnconfigure(0, weight=1)

        self.status = ctk.CTkLabel(self, text="Connecting...",
                                   font=("Arial", 14), text_color=INK)
        self.status.grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")

        top = ctk.CTkFrame(self, fg_color=CARD)
        top.grid(row=1, column=0, padx=12, pady=6, sticky="ew")
        top.grid_columnconfigure((0, 1, 2), weight=1)
        # Visible lamp: plain Tk canvas circle (no CustomTkinter redraw race).
        self.bulb = tk.Canvas(top, width=64, height=64, highlightthickness=0,
                              bg=CARD)
        self.bulb.grid(row=0, column=0, padx=(10, 0), pady=10)
        self._bulb_glow = self.bulb.create_oval(4, 4, 60, 60, fill="",
                                                outline="", width=0)
        self._bulb_glass = self.bulb.create_oval(12, 12, 52, 52,
                                                 fill="#555555", outline="#333333",
                                                 width=2)
        self.led_lbl = ctk.CTkLabel(top, text="Light: OFF",
                                    font=("Arial", 20, "bold"), text_color="#888888")
        self.led_lbl.grid(row=0, column=1, padx=5, pady=10)
        self.reading_lbl = ctk.CTkLabel(top, text="--.- C / --.- %",
                                        font=("Arial", 16), text_color=INK)
        self.reading_lbl.grid(row=0, column=2, padx=10, pady=10)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=2, column=0, padx=12, pady=6, sticky="ew")
        btns.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btns, text="Send Reading", fg_color=RED,
                      command=self.on_send_reading).grid(row=0, column=0,
                                                        padx=4, sticky="ew")
        ctk.CTkButton(btns, text="Send Photo",
                      command=self.on_send_photo).grid(row=0, column=1,
                                                      padx=4, sticky="ew")

        self.auto_var = tk.BooleanVar(value=True)
        self.auto_sw = ctk.CTkSwitch(self, text="Auto-send reading every 5s",
                                     variable=self.auto_var, command=on_auto)
        self.auto_sw.grid(row=3, column=0, padx=12, pady=2, sticky="w")

        self.logbox = ctk.CTkTextbox(self, height=300, fg_color=CARD,
                                     text_color=INK, font=("Arial", 13))
        self.logbox.grid(row=4, column=0, padx=12, pady=(6, 12), sticky="nsew")
        self.grid_rowconfigure(4, weight=1)
        self.logbox.configure(state="disabled")

    def set_status(self, text):
        self.after(0, lambda: self.status.configure(text=text))

    def set_light(self, on):
        def _do():
            try:
                self.led_lbl.configure(text=f"Light: {'ON' if on else 'OFF'}",
                                       text_color=RED if on else "#888888")
                self.bulb.itemconfig(
                    self._bulb_glass,
                    fill="#FFD34D" if on else "#555555")
                self.bulb.itemconfig(
                    self._bulb_glow,
                    outline="#FFD34D" if on else "", width=6 if on else 0)
            except tk.TclError:
                pass
        self.after(0, _do)

    def show_reading(self, temp, hum):
        self.after(0, lambda: self.reading_lbl.configure(
            text=f"{temp} C / {hum} %"))

    def log(self, text):
        def _do():
            try:
                self.logbox.configure(state="normal")
                self.logbox.insert("end", text + "\n")
                self.logbox.configure(state="disabled")
                self.logbox.see("end")
            except tk.TclError:
                pass
        self.after(0, _do)

    def report_callback_exception(self, exc, val, tb):
        try:
            import _tkinter
            if isinstance(val, _tkinter.TclError) and "invalid command name" in str(val):
                return
        except Exception:
            pass
        super().report_callback_exception(exc, val, tb)
