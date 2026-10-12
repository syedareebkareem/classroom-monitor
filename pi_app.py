"""Classroom Pi node.

Connects to the staff-room server, sends fake climate readings and
camera photos, and carries out incoming commands (classroom light
ON/OFF, take a photo) using hal.py. Laptop = simulated devices,
real Raspberry Pi = real devices, same file.

Usage:
  .venv/bin/python pi_app.py                        (panel window)
  .venv/bin/python pi_app.py --headless --count 3   (terminal, for tests)
"""
import argparse
import queue
import threading
import time

import protocol
from net import ClassroomNode
from hal import ClassroomHardware


def execute_command(hal: ClassroomHardware, link, cmd: str, log):
    if cmd == "LED_ON":
        result = hal.set_led(True)
        log(result)
        return result
    if cmd == "LED_OFF":
        result = hal.set_led(False)
        log(result)
        return result
    if cmd == "TAKE_PHOTO":
        log("Staff room asked for a photo - capturing...")
        b64 = hal.take_photo()
        link.send(protocol.photo_msg(b64))
        log(f"Photo sent ({len(b64)} characters)")
        return "photo sent"
    log(f"Unknown command: {cmd}")
    return "unknown"


def run_headless(host="127.0.0.1", port=12345, count=3, interval=0.5):
    hal = ClassroomHardware()
    print(f"[pi] devices: {hal.mode} (mock = simulated)", flush=True)
    link = ClassroomNode(host, port).connect()
    print(f"[pi] connected to staff room {host}:{port}", flush=True)
    try:
        hello = link.recv(timeout=10.0)
        print(f"[pi] server says: {hello['data']['text']}", flush=True)
    except Exception as e:
        print(f"[pi] no greeting: {e}", flush=True)
    sent = 0
    try:
        for _ in range(count):
            t, h = hal.read_climate()
            link.send(protocol.sensor_msg(t, h))
            print(f"[pi] sent reading: {t}C / {h}%", flush=True)
            sent += 1
            try:
                rsp = link.recv(timeout=5.0)
            except TimeoutError:
                print("[pi] no reply, continuing", flush=True)
                continue
            if rsp is None:
                print("[pi] server hung up", flush=True)
                break
            if rsp["type"] == "reply":
                print(f"[pi] server: {rsp['data']['text']}", flush=True)
            elif rsp["type"] == "command":
                cmd = rsp["data"]["cmd"]
                print(f"[pi] command from staff room: {cmd}", flush=True)
                execute_command(hal, link, cmd, print)
                try:  # command may be followed by the reading's reply
                    extra = link.recv(timeout=5.0)
                    if extra is not None and extra["type"] == "reply":
                        print(f"[pi] server: {extra['data']['text']}", flush=True)
                    elif extra is not None and extra["type"] == "command":
                        execute_command(hal, link, extra["data"]["cmd"], print)
                except TimeoutError:
                    pass
            time.sleep(interval)
    finally:
        link.close()
    print(f"[pi] done, readings sent={sent}, light={'ON' if hal.led_on else 'OFF'}",
          flush=True)
    return sent


def run_gui(host="127.0.0.1", port=12345):
    from pi_ui import PiPanel
    hal = ClassroomHardware()
    outbox: queue.Queue = queue.Queue()
    auto = {"on": True, "every": 5.0, "last": 0.0}
    holder: dict = {}

    def send_reading():
        t, h = hal.read_climate()
        ui = holder.get("ui")
        if ui:
            ui.show_reading(t, h)
            ui.log(f"Sending reading: {t} C / {h} %")
        outbox.put(protocol.sensor_msg(t, h))

    def send_photo():
        ui = holder.get("ui")
        if ui:
            ui.log("Capturing classroom photo...")
        b64 = hal.take_photo()
        if ui:
            ui.log(f"Sending photo ({len(b64)} characters)")
        outbox.put(protocol.photo_msg(b64))

    def toggle_auto():
        auto["on"] = holder["ui"].auto_var.get()
        holder["ui"].log(f"Auto-send {'ON' if auto['on'] else 'OFF'}")

    ui = PiPanel(on_send_reading=send_reading, on_send_photo=send_photo,
                 on_auto=toggle_auto)
    holder["ui"] = ui
    ui.log(f"Devices: {hal.mode} (simulated on laptop)")

    def net():
        try:
            link = ClassroomNode(host, port).connect()
        except Exception as e:
            ui.set_status(f"Cannot reach staff room: {e}")
            ui.log(f"ERROR: {e} - start the server first, then restart me.")
            return
        ui.set_status(f"Connected to staff room ({host}:{port})")
        ui.log(f"Connected to staff room at {host}:{port}")
        try:
            hello = link.recv(timeout=10.0)
            ui.log(f"Staff room: {hello['data']['text']}")
        except Exception as e:
            ui.log(f"No greeting: {e}")
        link.sock.settimeout(0.5)
        auto["last"] = time.time()
        while True:
            try:
                while True:
                    link.send(outbox.get_nowait())
            except queue.Empty:
                pass
            except Exception as e:
                ui.log(f"Link lost while sending: {e}")
                break
            if auto["on"] and time.time() - auto["last"] >= auto["every"]:
                auto["last"] = time.time()
                t, h = hal.read_climate()
                try:
                    link.send(protocol.sensor_msg(t, h))
                except Exception as e:
                    ui.log(f"Link lost while sending: {e}")
                    break
                ui.show_reading(t, h)
                ui.log(f"Auto reading: {t} C / {h} %")
            try:
                msg = link.recv()
            except TimeoutError:
                continue
            except Exception as e:
                ui.log(f"Link closed: {e}")
                break
            if msg is None:
                ui.log("Staff room hung up.")
                break
            if msg["type"] == "command":
                cmd = msg["data"]["cmd"]
                ui.log(f"Command from staff room: {cmd}")
                try:
                    result = execute_command(hal, link, cmd, ui.log)
                except Exception as e:
                    ui.log(f"Link lost during command: {e}")
                    break
                if cmd in ("LED_ON", "LED_OFF"):
                    ui.set_light(hal.led_on)
            elif msg["type"] == "reply":
                ui.log(f"Staff room: {msg['data']['text']}")
            elif msg["type"] == "hello":
                ui.log(f"Staff room: {msg['data']['text']}")
        link.close()
        ui.set_status("Disconnected. Restart both apps for a new session.")

    threading.Thread(target=net, daemon=True).start()
    ui.mainloop()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=12345)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--interval", type=float, default=0.5)
    a = ap.parse_args()
    if a.headless:
        run_headless(a.host, a.port, a.count, a.interval)
    else:
        run_gui(a.host, a.port)
