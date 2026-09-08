"""Minimal stdlib-only WebSocket client for tests.

Speaks just enough of RFC 6455 to handshake with obs_server and read the
unmasked server->client text frames it broadcasts. No external deps.
"""

import base64
import hashlib
import json
import os
import socket


class MiniWSClient:
    def __init__(self, host, port, timeout=5.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET /ws HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("handshake failed: connection closed")
            resp += chunk
        head, _, rest = resp.partition(b"\r\n\r\n")
        head_text = head.decode("latin-1")
        if "101" not in head_text.split("\r\n")[0]:
            raise ConnectionError(f"handshake rejected: {head_text.splitlines()[0]}")
        # Verify the accept key per RFC 6455.
        guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        expected = base64.b64encode(
            hashlib.sha1((key + guid).encode()).digest()
        ).decode()
        accept = ""
        for line in head_text.split("\r\n"):
            if line.lower().startswith("sec-websocket-accept:"):
                accept = line.split(":", 1)[1].strip()
        if accept != expected:
            raise ConnectionError("bad Sec-WebSocket-Accept")
        self._buf = bytearray(rest)

    def _recv_exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("connection closed")
            self._buf.extend(chunk)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def recv_frame(self):
        """Return (fin, opcode, payload) of the next server frame."""
        b1, b2 = self._recv_exact(2)
        fin = bool(b1 & 0x80)
        opcode = b1 & 0x0F
        masked = bool(b2 & 0x80)
        length = b2 & 0x7F
        if length == 126:
            length = int.from_bytes(self._recv_exact(2), "big")
        elif length == 127:
            length = int.from_bytes(self._recv_exact(8), "big")
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length)
        if mask:
            payload = bytes(p ^ mask[i % 4] for i, p in enumerate(payload))
        return fin, opcode, payload

    def recv_json(self, timeout=5.0):
        """Next text frame as JSON, skipping ping/close frames. Blocking on socket timeout."""
        self.sock.settimeout(timeout)
        while True:
            fin, opcode, payload = self.recv_frame()
            if opcode == 0x8:  # close
                raise ConnectionError("server closed connection")
            if opcode == 0x9:  # ping — ignore
                continue
            if opcode in (0x1, 0x2):
                return json.loads(payload.decode("utf-8"))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
