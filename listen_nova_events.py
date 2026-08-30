#!/usr/bin/env python3
import base64
import json
import os
import socket
import struct
import sys
import time

TARGET_HOST = "192.168.40.249"
TARGET_PORT = 2920

def make_ws_frame(data, opcode=1):
    payload = data.encode("utf-8") if isinstance(data, str) else data
    length = len(payload)
    header = bytearray([0x80 | (opcode & 0x0F)])
    mask_key = os.urandom(4)
    if length <= 125:
        header.append(0x80 | length)
    elif length <= 65535:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask_key)
    masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return bytes(header + masked)

def read_ws_frame(s):
    head = s.recv(2)
    if not head or len(head) < 2:
        return None, None
    b1, b2 = head[0], head[1]
    opcode = b1 & 0x0F
    has_mask = (b2 & 0x80) != 0
    payload_len = b2 & 0x7F
    if payload_len == 126:
        payload_len = struct.unpack("!H", s.recv(2))[0]
    elif payload_len == 127:
        payload_len = struct.unpack("!Q", s.recv(8))[0]
    mask_key = s.recv(4) if has_mask else None
    raw = b""
    while len(raw) < payload_len:
        chunk = s.recv(payload_len - len(raw))
        if not chunk:
            break
        raw += chunk
    if has_mask:
        raw = bytes(b ^ mask_key[i % 4] for i, b in enumerate(raw))
    return opcode, raw

def main():
    print(f"[*] Connecting to OpenLaunch Nova at ws://{TARGET_HOST}:{TARGET_PORT}...")
    try:
        s = socket.create_connection((TARGET_HOST, TARGET_PORT), timeout=5)
    except Exception as e:
        print(f"[!] Failed to connect: {e}")
        sys.exit(1)

    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {TARGET_HOST}:{TARGET_PORT}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    s.sendall(req.encode())

    # Read HTTP handshake response
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = s.recv(1024)
        if not chunk:
            break
        buf += chunk

    if b"101 Switching Protocols" not in buf:
        print("[!] WebSocket handshake failed. Response:")
        print(buf.decode("utf-8", errors="replace"))
        sys.exit(1)

    print("[+] WebSocket connection established!")
    print("[*] Listening for events (touch bar gestures, radar, telemetry)...")
    print("[*] Try swiping, tapping, or gesturing near the touch bar / radar sensor.")
    print("[*] Press Ctrl+C to exit.\n" + "=" * 60)

    s.settimeout(1.0)
    try:
        while True:
            try:
                opcode, data = read_ws_frame(s)
                if data:
                    text = data.decode("utf-8", errors="replace")
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        parsed = json.loads(text)
                        formatted = json.dumps(parsed, indent=2)
                        print(f"[{timestamp}] Event received:\n{formatted}\n{'-'*40}")
                    except json.JSONDecodeError:
                        print(f"[{timestamp}] Raw frame (opcode {opcode}): {text}")
            except socket.timeout:
                pass
    except KeyboardInterrupt:
        print("\n[*] Stopping listener.")
    finally:
        s.close()

if __name__ == "__main__":
    main()
