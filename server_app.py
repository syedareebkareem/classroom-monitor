"""Staff-room server.

Listens for the classroom Pi, shows every reading on the dashboard,
saves readings to readings.csv, and forwards button presses as
commands (Light ON / Light OFF / Take Photo) to the Pi.

Usage:
  .venv/bin/python server_app.py                 (dashboard window)
  .venv/bin/python server_app.py --headless      (terminal, for tests)
  .venv/bin/python server_app.py --headless --send-command LED_ON
"""
import argparse
import base64
import csv
import io
import os
import queue
import threading
import time

import protocol
from net import StaffRoomServer

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_CSV = os.path.join(HERE, "readings.csv")


class AutoLight:
    """Decides Light ON/OFF from live temperature.

    ON at/above `high`, OFF at/below `low` (gap stops flicker),
    sends only on state change, at most one command per `cooldown`
    seconds. A manual button press pauses it for 60 s so the human wins.
    Pure logic (no sockets) so it is easy to test.
    """

    MANUAL_PAUSE = 60.0

    def __init__(self, high=28.0, low=26.5, cooldown=10.0):
        assert low < high, "low must be below high"
        self.high = high
        self.low = low
        self.cooldown = cooldown
        self.enabled = True
        self.state = None  # None=unknown yet, True=light should be ON
        self.last_cmd_at = 0.0
        self.paused_until = 0.0

    def note_manual(self, now):
        self.paused_until = now + self.MANUAL_PAUSE

    def update(self, temp, now):
        """Returns 'LED_ON' / 'LED_OFF' when a command should be sent."""
        if not self.enabled or now < self.paused_until:
            return None
        want = self.state
        if temp >= self.high:
            want = True
        elif temp <= self.low:
            want = False
        if self.state is None:  # first reading: adopt quietly, no command
            self.state = want if want is not None else False
            return None
        if want is None or want == self.state:
            return None
        if now - self.last_cmd_at < self.cooldown:
            return None
        self.state = want
        self.last_cmd_at = now
        return "LED_ON" if want else "LED_OFF"


def save_reading(temp, hum):
    new = not os.path.exists(LOG_CSV)
    with open(LOG_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "temp_c", "humidity"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), temp, hum])


def run_headless(host="127.0.0.1", port=12345, max_msg=6, send_command=None,
                 auto_high=28.0, auto_low=26.5, auto_cooldown=10.0, manual=False):
    auto = AutoLight(high=auto_high, low=auto_low, cooldown=auto_cooldown)
    auto.enabled = not manual
    srv = StaffRoomServer(host, port)
    srv.listen()
    print(f"[server] listening on {host}:{port} "
          f"(auto={'OFF' if manual else f'ON {auto_low}-{auto_high}C'})", flush=True)
    link, addr = srv.accept()
    print(f"[server] classroom Pi connected from {addr}", flush=True)
    link.send(protocol.hello_msg("Staff room ready. Send readings.", "server"))
    got = 0
    cmd_sent = False
    try:
        while got < max_msg:
            try:
                msg = link.recv(timeout=10.0)
            except TimeoutError:
                print("[server] waiting...", flush=True)
                continue
            if msg is None:
                print("[server] Pi hung up", flush=True)
                break
            t = msg.get("type")
            if t == "sensor":
                d = msg["data"]
                print(f"[server] reading: {d['temp_c']}C / {d['humidity']}%", flush=True)
                save_reading(d["temp_c"], d["humidity"])
                link.send(protocol.reply_msg(
                    f"Saved: {d['temp_c']}C / {d['humidity']}%"))
                got += 1
                if send_command and not cmd_sent:
                    link.send(protocol.command_msg(send_command))
                    print(f"[server] sent command: {send_command}", flush=True)
                    cmd_sent = True
                cmd = auto.update(float(d["temp_c"]), time.time())
                if cmd:
                    link.send(protocol.command_msg(cmd))
                    print(f"[server] AUTO: {d['temp_c']}C -> {cmd}", flush=True)
            elif t == "photo":
                raw = base64.b64decode(msg["data"]["bytes"])
                print(f"[server] photo received ({len(raw)} bytes)", flush=True)
                link.send(protocol.reply_msg(f"Photo shown ({len(raw)} bytes)."))
                got += 1
            else:
                link.send(protocol.reply_msg("Unknown message."))
                got += 1
    finally:
        link.close()
        srv.close()
    print(f"[server] done, handled {got} messages", flush=True)
    return got


def run_gui(host="127.0.0.1", port=12345,
            auto_high=28.0, auto_low=26.5, auto_cooldown=10.0):
    from server_ui import ServerDashboard
    from PIL import Image

    auto = AutoLight(high=auto_high, low=auto_low, cooldown=auto_cooldown)
    commands: queue.Queue = queue.Queue()
    holder: dict = {}

    def on_button(cmd):
        auto.note_manual(time.time())  # human click pauses auto for 60 s
        ui = holder.get("ui")
        if ui:
            ui.log(f"Manual override (auto paused 60s): {cmd}")
            ui.set_auto_text("AUTO: paused (manual override)")
        commands.put(cmd)

    def on_auto_toggle():
        ui = holder["ui"]
        auto.enabled = bool(ui.auto_var.get())
        ui.log(f"Auto light control {'ON' if auto.enabled else 'OFF'}")
        ui.set_auto_text(f"AUTO: {'watching' if auto.enabled else 'off'} "
                         f"({auto.low}-{auto.high} C)")

    ui = ServerDashboard(on_command=on_button, on_auto=on_auto_toggle,
                         auto_high=auto_high, auto_low=auto_low)
    holder["ui"] = ui
    ui.set_status(f"Listening on {host}:{port} ...")

    def net():
        srv = StaffRoomServer(host, port)
        try:
            srv.listen()
        except OSError as e:
            ui.set_status(f"Cannot listen: {e}")
            ui.log(f"ERROR: {e} - is an old server still running?")
            return
        ui.set_status(f"Waiting for classroom Pi on {host}:{port} ...")
        ui.log(f"Listening on {host}:{port}")
        try:
            link, addr = srv.accept()
        except Exception as e:
            ui.set_status(f"Accept failed: {e}")
            return
        ui.set_status(f"Connected to classroom Pi ({addr[0]})")
        ui.log(f"Classroom Pi connected from {addr}")
        try:
            link.send(protocol.hello_msg("Staff room ready. Send readings.", "server"))
        except Exception as e:
            ui.log(f"Send failed: {e}")
            link.close()
            return
        link.sock.settimeout(0.5)
        while True:
            try:
                while True:
                    cmd = commands.get_nowait()
                    link.send(protocol.command_msg(cmd))
                    ui.log(f"Sent command to Pi: {cmd}")
                    if cmd in ("LED_ON", "LED_OFF"):
                        ui.set_lamp(cmd == "LED_ON")
            except queue.Empty:
                pass
            except Exception as e:
                ui.log(f"Link lost while sending: {e}")
                break
            try:
                msg = link.recv()
            except TimeoutError:
                continue
            except Exception as e:
                ui.log(f"Link closed: {e}")
                break
            if msg is None:
                ui.log("Classroom Pi hung up.")
                break
            t = msg.get("type")
            if t == "sensor":
                d = msg["data"]
                ui.show_reading(d["temp_c"], d["humidity"])
                ui.log(f"Reading: {d['temp_c']} C / {d['humidity']} % (saved)")
                save_reading(d["temp_c"], d["humidity"])
                try:
                    link.send(protocol.reply_msg(
                        f"Saved: {d['temp_c']}C / {d['humidity']}%"))
                except Exception:
                    break
                cmd = auto.update(float(d["temp_c"]), time.time())
                if cmd:
                    try:
                        link.send(protocol.command_msg(cmd))
                    except Exception:
                        break
                    ui.log(f"AUTO: {d['temp_c']} C -> {cmd}")
                    ui.set_auto_text("AUTO: cooling (light ON)" if cmd == "LED_ON"
                                     else "AUTO: idle (light OFF)")
                    ui.set_lamp(cmd == "LED_ON")
            elif t == "photo":
                try:
                    raw = base64.b64decode(msg["data"]["bytes"])
                    ui.show_photo(Image.open(io.BytesIO(raw)).convert("RGB"))
                    ui.log(f"Classroom photo shown ({len(raw)} bytes)")
                except Exception as e:
                    ui.log(f"Bad photo data: {e}")
                try:
                    link.send(protocol.reply_msg("Photo is on the dashboard."))
                except Exception:
                    break
            else:
                try:
                    link.send(protocol.reply_msg("Unknown message."))
                except Exception:
                    break
        link.close()
        srv.close()
        ui.set_status("Pi disconnected. Restart both apps for a new session.")

    threading.Thread(target=net, daemon=True).start()
    ui.mainloop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=12345)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--max-msg", type=int, default=6)
    ap.add_argument("--send-command", default=None,
                    choices=["LED_ON", "LED_OFF", "TAKE_PHOTO"])
    ap.add_argument("--auto-high", type=float, default=28.0)
    ap.add_argument("--auto-low", type=float, default=26.5)
    ap.add_argument("--auto-cooldown", type=float, default=10.0)
    ap.add_argument("--manual", action="store_true",
                    help="disable automatic light control")
    a = ap.parse_args()
    if a.headless:
        run_headless(a.host, a.port, a.max_msg, a.send_command,
                     a.auto_high, a.auto_low, a.auto_cooldown, a.manual)
    else:
        run_gui(a.host, a.port, a.auto_high, a.auto_low, a.auto_cooldown)
