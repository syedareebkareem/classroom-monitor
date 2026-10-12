"""Staff-room dashboard window.

Big temperature/humidity cards, event log, latest classroom photo,
and three command buttons. All update methods are thread-safe: the
network thread calls them from a worker thread and they hop onto the
main thread with `after`.
"""
import customtkinter as ctk
import tkinter as tk

BG = "#18191A"
PANEL = "#242526"
TEXT = "#F5F6F7"
RED = "#E60023"


class ServerDashboard(ctk.CTk):
    def __init__(self, on_command, on_auto=None, auto_high=28.0, auto_low=26.5):
        super().__init__()
        self.title("Staff Room - Classroom Monitor")
        self.geometry("620x740")
        self.on_command = on_command

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self.configure(bg_color=BG)
        self.grid_columnconfigure(0, weight=1)

        self.status = ctk.CTkLabel(self, text="Starting...",
                                   font=("Arial", 14), text_color=TEXT)
        self.status.grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")

        cards = ctk.CTkFrame(self, fg_color=PANEL)
        cards.grid(row=1, column=0, padx=12, pady=6, sticky="ew")
        cards.grid_columnconfigure((0, 1), weight=1)
        self.temp_lbl = ctk.CTkLabel(cards, text="--.- C",
                                     font=("Arial", 32, "bold"), text_color=TEXT)
        self.temp_lbl.grid(row=0, column=0, padx=10, pady=8)
        ctk.CTkLabel(cards, text="Classroom temperature", font=("Arial", 12),
                     text_color="gray").grid(row=1, column=0, pady=(0, 8))
        self.hum_lbl = ctk.CTkLabel(cards, text="--.- %",
                                    font=("Arial", 32, "bold"), text_color=TEXT)
        self.hum_lbl.grid(row=0, column=1, padx=10, pady=8)
        ctk.CTkLabel(cards, text="Classroom humidity", font=("Arial", 12),
                     text_color="gray").grid(row=1, column=1, pady=(0, 8))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=2, column=0, padx=12, pady=6, sticky="ew")
        btns.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkButton(btns, text="Light ON", fg_color=RED,
                      command=lambda: self.on_command("LED_ON")).grid(
                          row=0, column=0, padx=4, sticky="ew")
        ctk.CTkButton(btns, text="Light OFF", fg_color="#555555",
                      command=lambda: self.on_command("LED_OFF")).grid(
                          row=0, column=1, padx=4, sticky="ew")
        ctk.CTkButton(btns, text="Take Photo",
                      command=lambda: self.on_command("TAKE_PHOTO")).grid(
                          row=0, column=2, padx=4, sticky="ew")

        self.photo_lbl = ctk.CTkLabel(self, text="No classroom photo yet",
                                      text_color="gray", font=("Arial", 13))
        self.photo_lbl.grid(row=3, column=0, padx=12, pady=6)
        self._photo_ref = None

        auto_row = ctk.CTkFrame(self, fg_color="transparent")
        auto_row.grid(row=4, column=0, padx=12, pady=2, sticky="ew")
        self.auto_var = tk.BooleanVar(value=True)
        self.auto_sw = ctk.CTkSwitch(
            auto_row, text=f"Auto light ({auto_low}-{auto_high} C)",
            variable=self.auto_var,
            command=on_auto if on_auto else (lambda: None))
        self.auto_sw.grid(row=0, column=0, sticky="w")
        self.auto_lbl = ctk.CTkLabel(auto_row, text="AUTO: watching",
                                     font=("Arial", 12), text_color="gray")
        self.auto_lbl.grid(row=0, column=1, padx=12, sticky="e")
        self.lamp = tk.Canvas(auto_row, width=22, height=22,
                              highlightthickness=0, bg=BG)
        self.lamp.grid(row=0, column=2, padx=(0, 4))
        self._lamp_dot = self.lamp.create_oval(3, 3, 19, 19,
                                               fill="#555555", outline="#333333")
        auto_row.grid_columnconfigure(1, weight=1)
        self.threshold_lbl = ctk.CTkLabel(
            self, text=f"Light turns ON at {auto_high} C or hotter, "
                       f"OFF at {auto_low} C or colder",
            font=("Arial", 12), text_color="gray")
        self.threshold_lbl.grid(row=5, column=0, padx=12, pady=(0, 2), sticky="w")

        self.logbox = ctk.CTkTextbox(self, height=200, fg_color=PANEL,
                                     text_color=TEXT, font=("Arial", 13))
        self.logbox.grid(row=6, column=0, padx=12, pady=(6, 12), sticky="nsew")
        self.grid_rowconfigure(6, weight=1)
        self.logbox.configure(state="disabled")

    def set_status(self, text):
        self.after(0, lambda: self.status.configure(text=text))

    def set_auto_text(self, text):
        self.after(0, lambda: self.auto_lbl.configure(text=text))

    def set_lamp(self, on):
        """Mirror of the classroom light as the server last commanded it."""
        def _do():
            try:
                self.lamp.itemconfig(self._lamp_dot,
                                     fill="#FFD34D" if on else "#555555")
            except tk.TclError:
                pass
        self.after(0, _do)

    def show_reading(self, temp, hum):
        self.after(0, lambda: (self.temp_lbl.configure(text=f"{temp} C"),
                               self.hum_lbl.configure(text=f"{hum} %")))

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

    def show_photo(self, pil_image):
        def _do():
            try:
                img = ctk.CTkImage(light_image=pil_image, dark_image=pil_image,
                                   size=(320, 180))
                self._photo_ref = img
                self.photo_lbl.configure(image=img, text="")
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
