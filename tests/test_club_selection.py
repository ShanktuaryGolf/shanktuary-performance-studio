"""SHA-53 round-trip tests: range club selection -> server -> desktop app.

Covers the SHA-49 bug fix:
- POST /api/club (in-bag) -> 200, obs_state.selected_club updated, live WS
  client receives the {"type": "club", "club": ...} broadcast frame.
- POST /api/club (unknown / malformed) -> 400, no state change, no listener
  call, no WS broadcast.
- GET /api/club reflects state; WS init payload carries "club".
- Bag fixture injected via a temp SESSION_LOG_PATH (no machine-state dep).

WS frames are asserted with tests/fixtures/mini_ws_client.py — a stdlib-only
client, so no test dependency beyond the standard library.
"""

import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import importlib.util

import obs_server
from obs_server import obs_state


def _load_mini_ws_client():
    path = Path(__file__).parent / "fixtures" / "mini_ws_client.py"
    spec = importlib.util.spec_from_file_location("mini_ws_client", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MiniWSClient = _load_mini_ws_client().MiniWSClient

REPO = Path(__file__).parent.parent


@pytest.fixture()
def club_server(tmp_path, monkeypatch):
    """OBS server on a free port with a bag fixture written to a temp history."""
    history = tmp_path / "shanktuary_session_history.json"
    history.write_text(json.dumps({
        "bag": [
            {"name": "QA Driver", "category": "wood"},
            {"name": "QA 7 Iron", "category": "iron"},
        ],
        "is_left_handed": False,
        "sessions": [],
    }))
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", history)
    monkeypatch.setattr(obs_state, "selected_club", None)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    t = threading.Thread(target=obs_server.start_obs_server, args=(port,), daemon=True)
    t.start()
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.fail("OBS server did not come up")

    yield port
    obs_state.club_listeners.clear()
    obs_state.selected_club = None


def _post(port, payload):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://localhost:{port}/api/club", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _connect_ws(port, want_init=True):
    ws = MiniWSClient("localhost", port, timeout=5)
    init = None
    if want_init:
        init = ws.recv_json(timeout=5)
    return ws, init


def _drain_until(ws, pred, timeout=5.0):
    """Read WS frames until pred(frame) or timeout. Returns matching frame."""
    end = time.time() + timeout
    while time.time() < end:
        remaining = max(0.1, end - time.time())
        try:
            frame = ws.recv_json(timeout=remaining)
        except (socket.timeout, TimeoutError, ConnectionError):
            return None
        if pred(frame):
            return frame
    return None


def test_club_roundtrip_ws_broadcast_and_listeners(club_server):
    port = club_server
    heard = []
    obs_state.club_listeners.append(lambda c: heard.append(c))

    ws, init = _connect_ws(port)
    assert "club" in init, f"init missing club key: {init}"
    assert init["club"] is None  # nothing selected yet

    status, payload = _post(port, {"club": "QA 7 Iron"})
    assert status == 200, payload
    assert payload == {"status": "ok", "club": "QA 7 Iron"}

    assert obs_state.selected_club == "QA 7 Iron"
    assert heard == ["QA 7 Iron"]  # exactly one listener notify

    frame = _drain_until(ws, lambda f: f.get("type") == "club")
    assert frame is not None, "no club WS broadcast frame received"
    assert frame == {"type": "club", "club": "QA 7 Iron"}
    ws.close()


def test_init_carries_selected_club_for_late_joiners(club_server):
    port = club_server
    assert _post(port, {"club": "QA Driver"})[0] == 200
    ws, init = _connect_ws(port)
    assert init["club"] == "QA Driver"
    ws.close()


def test_get_club_reflects_state(club_server):
    port = club_server
    with urllib.request.urlopen(f"http://localhost:{port}/api/club", timeout=5) as r:
        assert json.loads(r.read()) == {"club": None}
    assert _post(port, {"club": "QA Driver"})[0] == 200
    with urllib.request.urlopen(f"http://localhost:{port}/api/club", timeout=5) as r:
        assert json.loads(r.read()) == {"club": "QA Driver"}


def test_unknown_club_rejected_no_side_effects(club_server):
    port = club_server
    heard = []
    obs_state.club_listeners.append(lambda c: heard.append(c))
    ws, _ = _connect_ws(port)

    status, payload = _post(port, {"club": "QA Putter"})
    assert status == 400
    assert payload == {"status": "error", "message": "club not in bag"}
    assert obs_state.selected_club is None
    assert heard == []

    # Sanity: a valid POST still broadcasts, proving the WS link was live
    # during the rejected POST above (so silence there was meaningful).
    status2, _ = _post(port, {"club": "QA Driver"})
    assert status2 == 200
    frame = _drain_until(ws, lambda f: f.get("type") == "club")
    assert frame == {"type": "club", "club": "QA Driver"}
    ws.close()


@pytest.mark.parametrize("bad", [
    {"club": 123},
    {"club": "   "},
    {"club": ""},
    {"wrong": "x"},
    {},
    b"not json",
    b"[1,2,3]",
    b'"just a string"',
])
def test_malformed_payloads_rejected(club_server, bad):
    port = club_server
    heard = []
    obs_state.club_listeners.append(lambda c: heard.append(c))
    status, payload = _post(port, bad)
    assert status == 400, (bad, payload)
    assert payload.get("status") == "error"
    assert obs_state.selected_club is None
    assert heard == []


def test_whitespace_is_trimmed(club_server):
    port = club_server
    status, payload = _post(port, {"club": "  QA 7 Iron  "})
    assert status == 200, payload
    assert obs_state.selected_club == "QA 7 Iron"


def test_documented_ws_types_include_club():
    """AGENTS.md documents `club` among the WS message types."""
    agents_md = (REPO / "AGENTS.md").read_text()
    assert "`init`, `shot`, `pressure`, `shot_pressure`, `layout_update`, `club`" in agents_md
