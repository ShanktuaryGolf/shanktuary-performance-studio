"""Raw HTTP regression tests for unread-body request injection."""

import http.client
import socket
import threading
from types import SimpleNamespace

import pytest

import obs_server


@pytest.fixture
def framing_server(monkeypatch):
    calls = []
    monkeypatch.setattr(
        obs_server, "pressure_manager",
        SimpleNamespace(tare=lambda: calls.append("tare") or True),
    )
    server = obs_server.ThreadedHTTPServer(
        ("127.0.0.1", 0), obs_server.OBSHTTPRequestHandler,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(method="POST", path="/api/pressure/tare", headers=(), body=b""):
    lines = [f"{method} {path} HTTP/1.1", "Host: localhost", *headers, "", ""]
    return "\r\n".join(lines).encode("ascii") + body


def exchange(address, payload, *, finish_body=False):
    with socket.create_connection(address, timeout=2) as sock:
        sock.sendall(payload)
        if finish_body:
            sock.shutdown(socket.SHUT_WR)
        response = bytearray()
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                return bytes(response)
            response.extend(chunk)


@pytest.mark.parametrize("origin_header", [
    "Origin: https://attacker.example", "Sec-Fetch-Site: cross-site",
])
def test_cross_origin_body_cannot_execute_as_next_request(framing_server, origin_header):
    address, calls = framing_server
    injected = request(headers=["Content-Length: 0", "Connection: close"])
    response = exchange(address, request(
        headers=[origin_header, f"Content-Length: {len(injected)}"], body=injected,
    ))
    assert response.startswith(b"HTTP/1.1 403")
    assert b"Connection: close\r\n" in response
    assert response.count(b"HTTP/1.1 ") == 1
    assert calls == []


@pytest.mark.parametrize("headers, status", [
    (["Content-Length: nope"], 400),
    (["Content-Length: -1"], 400),
    (["Content-Length: +1"], 400),
    (["Content-Length: 0, 0"], 400),
    (["Content-Length: 0", "Content-Length: 0"], 400),
    (["Content-Length: 0", "Content-Length: 100"], 400),
    (["Content-Length: 1048577"], 413),
    (["Transfer-Encoding: chunked"], 400),
    (["Transfer-Encoding: identity", "Content-Length: 0"], 400),
])
def test_invalid_framing_closes_without_executing_body(framing_server, headers, status):
    address, calls = framing_server
    injected = request(headers=["Connection: close", "Content-Length: 0"])
    response = exchange(address, request(headers=headers, body=injected))
    assert response.startswith(f"HTTP/1.1 {status}".encode())
    assert b"Connection: close\r\n" in response
    assert response.count(b"HTTP/1.1 ") == 1
    assert calls == []


def test_truncated_body_does_not_execute_action(framing_server):
    address, calls = framing_server
    response = exchange(address, request(headers=["Content-Length: 20"], body=b"{}"),
                        finish_body=True)
    assert response.startswith(b"HTTP/1.1 400")
    assert b"Connection: close\r\n" in response
    assert calls == []


def test_bodyless_action_consumes_body_before_next_request(framing_server):
    address, calls = framing_server
    injected = request(headers=["Content-Length: 0"])
    payload = request(headers=[f"Content-Length: {len(injected)}"], body=injected)
    payload += request(method="GET", path="/api/club", headers=["Connection: close"])
    response = exchange(address, payload)
    assert response.count(b"HTTP/1.1 200") == 2
    assert calls == ["tare"]


def test_get_body_is_rejected_without_executing_embedded_post(framing_server):
    address, calls = framing_server
    injected = request(headers=["Content-Length: 0", "Connection: close"])
    response = exchange(address, request(
        method="GET", path="/api/club",
        headers=[f"Content-Length: {len(injected)}"], body=injected,
    ))
    assert response.startswith(b"HTTP/1.1 400")
    assert b"Connection: close\r\n" in response
    assert response.count(b"HTTP/1.1 ") == 1
    assert calls == []


@pytest.mark.parametrize("headers", [{}, {"Origin": "http://localhost", "Host": "localhost"}])
def test_valid_requests_reuse_keepalive_connection(framing_server, headers):
    address, calls = framing_server
    conn = http.client.HTTPConnection(*address, timeout=2)
    try:
        conn.request("POST", "/api/pressure/tare", body=b"{}", headers=headers)
        response = conn.getresponse()
        assert response.status == 200
        response.read()
        first_socket = conn.sock
        conn.request("POST", "/api/pressure/tare", body=b"{}", headers=headers)
        response = conn.getresponse()
        assert response.status == 200
        response.read()
        assert conn.sock is first_socket
        assert calls == ["tare", "tare"]
    finally:
        conn.close()
