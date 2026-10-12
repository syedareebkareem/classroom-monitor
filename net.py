"""TCP plumbing. Both sides speak the JSON protocol from protocol.py
over one persistent connection (WiFi/Ethernet, or localhost for demo).
"""
import socket
import protocol

CHUNK = 65536


class Link:
    """One open TCP connection with JSON message framing."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._rx = protocol.LineBuffer()

    def send(self, msg: dict):
        self.sock.sendall(protocol.encode(msg))

    def recv(self, timeout=None):
        if timeout is not None:
            self.sock.settimeout(timeout)
        while True:
            lines = self._rx.pop_lines()
            if lines:
                return protocol.decode_line(lines[0])
            chunk = self.sock.recv(CHUNK)
            if not chunk:
                return None  # other side hung up
            self._rx.feed(chunk)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class StaffRoomServer:
    """Listens for the classroom Pi and accepts its connection."""

    def __init__(self, host="127.0.0.1", port=12345):
        self.host = host
        self.port = port
        self._sock = None

    def listen(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(1)

    def accept(self):
        conn, addr = self._sock.accept()
        conn.settimeout(30.0)
        return Link(conn), addr

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass


class ClassroomNode:
    """The Pi side: dials the staff-room server."""

    def __init__(self, host="127.0.0.1", port=12345):
        self.host = host
        self.port = port

    def connect(self) -> Link:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect((self.host, self.port))
        return Link(sock)
