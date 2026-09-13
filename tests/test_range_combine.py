"""Combine lives on the range: a game-mode card starts/ends a run through the
server, the desktop app (owner of session history and shot stamping) applies
it, and the range reads live progress + history from GET /api/combine.
"""
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import obs_server
from obs_server import obs_state

REPO = Path(__file__).resolve().parent.parent
RANGE_HTML = (REPO / "assets" / "range" / "index.html").read_text(encoding="utf-8")
WS_JS = (REPO / "assets" / "range" / "js" / "websocket.js").read_text(encoding="utf-8")
STUDIO = (REPO / "shanktuary_performance_studio.py").read_text(encoding="utf-8")


def _shot(club, station=None, bs=40.0):
    s = {"club": club, "ball_speed_meters_per_second": bs, "vertical_launch_angle_degrees": 18.0,
         "total_spin_rpm": 6000, "spin_axis_degrees": 0.0, "timestamp_ns": id(object()),
         "open_golf_coach": {"us_customary_units": {"ball_speed_mph": bs / 0.44704}}}
    if station:
        s["combine_station"] = station
    return s


@pytest.fixture()
def server(tmp_path, monkeypatch):
    history = tmp_path / "shanktuary_session_history.json"
    history.write_text(json.dumps({
        "bag": [{"name": "PW"}, {"name": "7 Iron"}, {"name": "4 Hybrid"}],
        "is_left_handed": False,
        "sessions": [{"id": "sess_1", "name": "S", "shots": []}],
    }))
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", history)
    import shanktuary_performance_studio as studio
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(history))
    monkeypatch.setattr(obs_state, "combine_run", None)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    threading.Thread(target=obs_server.start_obs_server, args=(port,), daemon=True).start()
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.fail("OBS server did not come up")
    yield port, history
    obs_state.combine_listeners.clear()
    obs_state.combine_run = None


def _get(port):
    with urllib.request.urlopen(f"http://localhost:{port}/api/combine", timeout=5) as r:
        return r.status, json.loads(r.read())


def _post(port, payload):
    req = urllib.request.Request(f"http://localhost:{port}/api/combine", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# --- server -------------------------------------------------------------------------

def test_get_combine_reports_protocol_history_and_no_run(server):
    port, _ = server
    status, body = _get(port)
    assert status == 200
    assert body["active"] is False and body["run"] is None
    assert [s["club"] for s in body["protocol"]["stations"]] == ["PW", "7 Iron", "4 Hybrid"]
    assert body["history"] is None


def test_post_start_builds_a_run_from_the_bag_and_notifies_the_desktop(server):
    port, _ = server
    heard = []
    obs_state.combine_listeners.append(lambda run: heard.append(run))
    status, body = _post(port, {"action": "start"})
    assert status == 200 and body["active"] is True
    assert [s["role"] for s in body["run"]["stations"]] == ["short", "mid", "long"]
    assert body["run"]["session_id"] == "sess_1"
    assert heard == [body["run"]]
    status, body = _post(port, {"action": "end"})
    assert status == 200 and body["active"] is False and body["run"] is None
    assert heard[-1] is None


def test_post_start_with_a_thin_bag_is_refused_with_the_reason(server):
    port, history = server
    data = json.loads(history.read_text()); data["bag"] = [{"name": "7 Iron"}]
    history.write_text(json.dumps(data))
    status, body = _post(port, {"action": "start"})
    assert status == 400 and "need" in body["message"].lower()
    assert obs_state.combine_run is None


def test_get_combine_scores_the_live_run_from_saved_shots(server):
    port, history = server
    assert _post(port, {"action": "start"})[0] == 200
    data = json.loads(history.read_text())
    data["sessions"][0]["shots"] = [_shot("PW", "short") for _ in range(7)] + [_shot("7 Iron", "mid") for _ in range(10)]
    history.write_text(json.dumps(data))
    _, body = _get(port)
    st = {s["role"]: s for s in body["result"]["stations"]}
    assert st["short"]["counted"] == 7 and st["mid"]["complete"] and st["long"]["counted"] == 0
    assert body["result"]["status"] == "in_progress"


def test_bad_actions_are_rejected(server):
    port, _ = server
    assert _post(port, {"action": "dance"})[0] == 400
    assert _post(port, {"nope": 1})[0] == 400


# --- desktop app applies the range's decision ----------------------------------------

def test_desktop_applies_a_range_started_run_on_the_tk_thread():
    body = STUDIO[STUDIO.index("    def poll_queue(self):"):STUDIO.index("    def apply_range_club(")]
    assert "apply_range_combine" in body, "poll_queue must drain the combine queue like the club queue"
    assert "combine_listeners.append" in STUDIO


def test_apply_range_combine_sets_and_clears_the_run(tmp_path, monkeypatch):
    import shanktuary_performance_studio as studio
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "h.json"))
    a = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    a.sessions = [{"id": "sess_1", "name": "S", "shots": []}]; a.active_session_index = 0
    a.bag = [{"name": "PW"}, {"name": "7 Iron"}]; a.clubs = list(studio.DEFAULT_CLUBS)
    a.is_left_handed = False; a.balls = []; a.current_ball = None; a.current_club = "7 Iron"
    a.combine_run = None; a.copy_feedback = ""
    run = {"stations": [{"role": "short", "club": "PW"}, {"role": "mid", "club": "7 Iron"}], "session_id": "sess_1"}
    a.apply_range_combine(run)
    assert a.combine_run == run
    assert a._stamp_equipment({"club": "7 Iron"})["combine_station"] == "mid"
    a.apply_range_combine(None)
    assert a.combine_run is None


def test_tools_menu_no_longer_carries_the_combine_row():
    assert "toggle_combine" not in STUDIO


# --- range UI -------------------------------------------------------------------------

def _drawer():
    start = RANGE_HTML.index('id="game-modes-drawer"')
    end = RANGE_HTML.index("Settings drawer", start)
    return RANGE_HTML[start:end]


def test_combine_is_a_game_mode_card():
    d = _drawer()
    assert 'data-mode="combine"' in d and "Combine" in d and 'id="tag-combine"' in d


def test_game_modes_are_laid_out_as_a_3x3_grid():
    d = _drawer()
    assert len(re.findall(r'class="game-mode-card', d)) == 9
    assert 'id="game-mode-grid"' in d
    css = RANGE_HTML[RANGE_HTML.index("#game-mode-grid {"):]
    css = css[:css.index("}")]
    assert "grid-template-columns: repeat(3" in css


def test_combine_mode_is_wired_to_the_server_and_hud():
    assert "fetch('/api/combine'" in WS_JS
    assert "mode === 'combine'" in WS_JS
    assert 'id="combine-scorecard"' in RANGE_HTML
