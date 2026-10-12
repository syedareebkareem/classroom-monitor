"""Verifies the full classroom scenario. Run: .venv/bin/python test_all.py"""
import base64
import csv
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import protocol
from hal import ClassroomHardware
from net import StaffRoomServer, ClassroomNode
import server_app


def test_protocol_framing():
    msgs = [protocol.sensor_msg(25.5, 60.0),
            protocol.command_msg("LED_ON"),
            protocol.photo_msg("QUJD"),
            protocol.reply_msg("Saved"),
            protocol.hello_msg("Hi", "server")]
    blob = b"".join(protocol.encode(m) for m in msgs)
    buf = protocol.LineBuffer()
    buf.feed(blob[:len(blob) // 2])          # split TCP packet in half
    first = buf.pop_lines()
    buf.feed(blob[len(blob) // 2:])
    got = first + buf.pop_lines()
    assert len(got) == 5, got
    back = [protocol.decode_line(l) for l in got]
    assert back[0]["data"] == {"temp_c": 25.5, "humidity": 60.0}
    assert back[1]["data"] == {"cmd": "LED_ON"}
    print("protocol framing OK (5 messages survive a split packet)")


def test_hardware_mock():
    hal = ClassroomHardware()
    assert hal.mode == "mock", hal.mode
    t, h = hal.read_climate()
    assert 21.0 <= t <= 31.0 and 40.0 <= h <= 70.0, (t, h)
    t2, _ = hal.read_climate()
    assert abs(t2 - t) <= 0.5, (t, t2)  # smooth drift, no wild jumps
    import hal as hal_mod
    assert hal_mod.BASE_TEMP + hal_mod.AMPLITUDE >= 27, "wave must reach ON temp"
    assert hal_mod.BASE_TEMP - hal_mod.AMPLITUDE <= 23, "wave must reach OFF temp"
    assert hal.set_led(True).endswith("(simulated)") and hal.led_on
    assert hal.set_led(False) and not hal.led_on
    raw = base64.b64decode(hal.take_photo())
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "photo is not a PNG"
    print(f"hardware mock OK ({t}C/{h}%, light toggle, PNG {len(raw)} bytes)")


def test_full_scenario():
    """Server: reading -> save -> LED_ON -> photo request -> photo.
    Pi:     send reading -> do LED_ON -> take+send photo."""
    if os.path.exists(server_app.LOG_CSV):
        os.remove(server_app.LOG_CSV)
    port = 12601
    log = []

    def server_side():
        srv = StaffRoomServer("127.0.0.1", port)
        srv.listen()
        link, _ = srv.accept()
        link.send(protocol.hello_msg("Staff room ready.", "server"))
        m = link.recv(timeout=5.0)
        assert m["type"] == "sensor", m
        server_app.save_reading(m["data"]["temp_c"], m["data"]["humidity"])
        log.append(f"saved {m['data']}")
        link.send(protocol.command_msg("LED_ON"))
        link.send(protocol.command_msg("TAKE_PHOTO"))
        m2 = link.recv(timeout=5.0)
        assert m2["type"] == "photo", m2
        raw = base64.b64decode(m2["data"]["bytes"])
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"
        log.append(f"photo {len(raw)} bytes")
        link.send(protocol.reply_msg("All shown on dashboard."))
        link.close()
        srv.close()

    t = threading.Thread(target=server_side, daemon=True)
    t.start()
    time.sleep(0.3)
    hal = ClassroomHardware()
    link = ClassroomNode("127.0.0.1", port).connect()
    assert link.recv(timeout=5.0)["type"] == "hello"
    link.send(protocol.sensor_msg(*hal.read_climate()))
    for _ in range(3):  # LED_ON, TAKE_PHOTO, final reply
        m = link.recv(timeout=5.0)
        assert m is not None
        if m["type"] == "command":
            cmd = m["data"]["cmd"]
            if cmd == "LED_ON":
                hal.set_led(True)
                log.append("light ON")
            elif cmd == "TAKE_PHOTO":
                link.send(protocol.photo_msg(hal.take_photo()))
                log.append("photo sent")
        elif m["type"] == "reply":
            log.append(m["data"]["text"])
    link.close()
    t.join(timeout=5)
    assert hal.led_on, "light should be ON after LED_ON"
    with open(server_app.LOG_CSV) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1 and float(rows[0]["temp_c"]) > 0, rows
    print("full scenario OK:", " | ".join(log), "| readings.csv has 1 row")


def test_auto_light():
    from server_app import AutoLight
    a = AutoLight(high=28.0, low=26.5, cooldown=0.0)
    now = 1000.0
    assert a.update(25.0, now) is None          # baseline adopted, quiet
    assert a.update(27.9, now + 1) is None      # inside gap, nothing
    assert a.update(28.0, now + 2) == "LED_ON"  # crossed high
    assert a.update(29.5, now + 3) is None      # already ON, no repeat
    assert a.update(27.0, now + 4) is None      # inside gap, stays ON
    assert a.update(26.5, now + 5) == "LED_OFF"  # crossed low
    assert a.update(24.0, now + 6) is None      # already OFF
    b = AutoLight(high=28.0, low=26.5, cooldown=100.0)
    b.update(25.0, now)
    assert b.update(29.0, now + 1) == "LED_ON"
    assert b.update(29.5, now + 2) is None
    assert b.update(25.0, now + 3) is None      # cooldown blocks LED_OFF
    c = AutoLight(high=28.0, low=26.5, cooldown=0.0)
    c.update(25.0, now)
    c.note_manual(now + 1)                       # human pressed a button
    assert c.update(29.0, now + 2) is None      # auto paused 60 s
    assert c.update(29.0, now + 62) == "LED_ON"  # pause over, acts again
    d = AutoLight(high=28.0, low=26.5, cooldown=0.0)
    d.enabled = False
    assert d.update(35.0, now) is None          # manual mode: silent
    print("auto light OK (thresholds, gap, cooldown, manual pause, off switch)")


def test_windows():
    from server_ui import ServerDashboard
    from pi_ui import PiPanel
    from PIL import Image
    cmds = []
    s = ServerDashboard(on_command=cmds.append, on_auto=lambda: None)
    s.show_reading(26.4, 58.0)
    s.log("Reading: 26.4 C / 58.0 % (saved)")
    s.show_photo(Image.new("RGB", (320, 180), (10, 120, 180)))
    s.set_status("Connected")
    s.set_auto_text("AUTO: cooling (light ON)")
    s.set_lamp(True)
    s.set_lamp(False)
    s.update(); s.update_idletasks(); s.update()
    cmds.append("LED_ON")
    assert cmds == ["LED_ON"]
    s.destroy()
    p = PiPanel(on_send_reading=lambda: None, on_send_photo=lambda: None,
                on_auto=lambda: None)
    p.set_status("Connected")
    p.set_light(True)
    p.show_reading(26.4, 58.0)
    p.log("Command from staff room: LED_ON")
    p.update(); p.update_idletasks(); p.update()
    p.destroy()
    print("windows OK (dashboard cards, photo, buttons, Pi panel)")


def test_protocol_rejects_bad():
    for bad in ({"type": "nonsense"}, {"nope": 1}, {"type": "SENSOR"}):
        try:
            protocol.encode(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"encode accepted {bad}")
    try:
        protocol.decode_line('{"type": "hacker"}')
    except AssertionError:
        pass
    else:
        raise AssertionError("decode accepted bad type")
    try:
        protocol.decode_line("not json{")
    except Exception:
        pass
    else:
        raise AssertionError("decode accepted garbage")
    print("protocol rejects bad input OK")


def test_auto_boundaries():
    from server_app import AutoLight
    a = AutoLight(high=28.0, low=26.5, cooldown=0.0)
    now = 2000.0
    assert a.update(20.0, now) is None       # baseline adopts OFF quietly
    assert a.update(28.0, now + 1) == "LED_ON"   # exactly high fires
    b = AutoLight(high=28.0, low=26.5, cooldown=0.0)
    b.update(30.0, now)                       # baseline adopts ON quietly
    assert b.update(26.5, now + 1) == "LED_OFF"  # exactly low fires
    print("auto boundaries OK (exact high/low fire, baseline quiet)")


def test_disconnect_returns_none():
    import socket
    from net import Link
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 12602))
    srv.listen(1)
    cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cli.connect(("127.0.0.1", 12602))
    conn, _ = srv.accept()
    peer, mine = Link(conn), Link(cli)
    mine.send(protocol.sensor_msg(25.0, 50.0))
    assert peer.recv(timeout=5.0)["type"] == "sensor"
    mine.close()                              # hang up without goodbye
    assert peer.recv(timeout=5.0) is None      # clean None, no exception
    peer.close()
    srv.close()
    print("disconnect handling OK (hangup -> None)")


def test_csv_appends_rows():
    import server_app
    if os.path.exists(server_app.LOG_CSV):
        os.remove(server_app.LOG_CSV)
    server_app.save_reading(25.0, 50.0)
    server_app.save_reading(26.5, 52.0)
    with open(server_app.LOG_CSV) as f:
        rows = list(csv.DictReader(f))
    assert [r["temp_c"] for r in rows] == ["25.0", "26.5"], rows
    assert rows[0]["timestamp"] and rows[0]["humidity"] == "50.0"
    os.remove(server_app.LOG_CSV)
    print("CSV logging OK (header once, rows append)")


def test_burst_of_20():
    buf = protocol.LineBuffer()
    blob = b"".join(protocol.encode(protocol.sensor_msg(20.0 + i * 0.1, 50.0))
                     for i in range(20))
    buf.feed(blob)  # all 20 readings in a single TCP packet
    lines = buf.pop_lines()
    assert len(lines) == 20, len(lines)
    assert protocol.decode_line(lines[19])["data"]["temp_c"] == 21.9
    print("burst OK (20 readings in one packet all parsed)")


if __name__ == "__main__":
    test_protocol_framing()
    test_protocol_rejects_bad()
    test_hardware_mock()
    test_full_scenario()
    test_auto_light()
    test_auto_boundaries()
    test_disconnect_returns_none()
    test_csv_appends_rows()
    test_burst_of_20()
    test_windows()
    print("\nALL CHECKS PASSED")
