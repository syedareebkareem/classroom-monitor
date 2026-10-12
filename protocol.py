"""Message protocol for the classroom monitor.

The Pi node and the staff-room server talk over one persistent TCP
connection. Every message is one JSON object followed by a newline,
so the receiver can split the byte stream into whole messages.
"""
import json

VALID_TYPES = ("sensor", "photo", "command", "reply", "hello")


def encode(msg: dict) -> bytes:
    assert msg.get("type") in VALID_TYPES, f"bad type: {msg.get('type')}"
    return (json.dumps(msg) + "\n").encode("utf-8")


def decode_line(line: str) -> dict:
    msg = json.loads(line)
    assert msg.get("type") in VALID_TYPES, f"bad type: {msg.get('type')}"
    return msg


class LineBuffer:
    """Collects recv() bytes and yields complete newline-ended lines."""

    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes):
        self.buf += data

    def pop_lines(self):
        lines = []
        while b"\n" in self.buf:
            raw, self.buf = self.buf.split(b"\n", 1)
            if raw.strip():
                lines.append(raw.decode("utf-8"))
        return lines


def sensor_msg(temp_c: float, humidity: float) -> dict:
    return {"type": "sensor", "from": "pi",
            "data": {"temp_c": temp_c, "humidity": humidity}}


def photo_msg(png_b64: str) -> dict:
    return {"type": "photo", "from": "pi",
            "data": {"format": "png_b64", "bytes": png_b64}}


def command_msg(cmd: str) -> dict:
    assert cmd in ("LED_ON", "LED_OFF", "TAKE_PHOTO"), cmd
    return {"type": "command", "from": "server", "data": {"cmd": cmd}}


def reply_msg(text: str) -> dict:
    return {"type": "reply", "from": "server", "data": {"text": text}}


def hello_msg(text: str, frm: str) -> dict:
    return {"type": "hello", "from": frm, "data": {"text": text}}
