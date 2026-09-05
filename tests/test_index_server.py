import json
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent.resolve()))
import obs_server
from obs_server import obs_state, start_obs_server
from src.analytics.index import ConfidenceTier, bag_index_summary


@pytest.fixture(scope="module")
def server():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    t = threading.Thread(target=start_obs_server, args=(port,), daemon=True)
    t.start()

    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://localhost:{port}/", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    else:
        pytest.fail(f"OBS server did not come up on port {port}")

    yield port


def _sample_shot(bs=90.0, vla=18.0, spin=6500.0, axis=1.0, club="7 Iron", excluded=False):
    return {
        "club": club,
        "excluded": excluded,
        "total_spin_rpm": spin,
        "vertical_launch_angle_degrees": vla,
        "spin_axis_degrees": axis,
        "open_golf_coach": {
            "us_customary_units": {"ball_speed_mph": bs}
        },
    }


def test_index_missing_history_file(server, monkeypatch, tmp_path):
    missing_path = tmp_path / "nonexistent.json"
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", missing_path)

    url = f"http://localhost:{server}/api/index"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        assert "application/json" in response.headers.get("Content-Type", "")
        data = json.loads(response.read().decode("utf-8"))
        assert data == {}


def test_index_empty_history(server, monkeypatch, tmp_path):
    empty_path = tmp_path / "empty_history.json"
    empty_path.write_text(json.dumps({"sessions": []}))
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", empty_path)

    url = f"http://localhost:{server}/api/index"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        data = json.loads(response.read().decode("utf-8"))
        assert data == {}


def test_index_corrupt_history_file(server, monkeypatch, tmp_path):
    corrupt_path = tmp_path / "corrupt.json"
    corrupt_path.write_text("{invalid json truncated")
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", corrupt_path)

    url = f"http://localhost:{server}/api/index"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        data = json.loads(response.read().decode("utf-8"))
        assert data == {}


def test_index_with_shots_matches_bag_index_summary(server, monkeypatch, tmp_path):
    shots = [
        _sample_shot(bs=90.0, vla=18.0, spin=6500.0, axis=1.0, club="7 Iron"),
        _sample_shot(bs=92.0, vla=18.5, spin=6400.0, axis=1.2, club="7 Iron"),
        _sample_shot(bs=160.0, vla=11.0, spin=2800.0, axis=0.5, club="Driver"),
        _sample_shot(bs=162.0, vla=11.5, spin=2750.0, axis=0.2, club="Driver"),
    ]
    payload = {
        "sessions": [
            {
                "id": "sess_1",
                "name": "Test Session",
                "shots": shots,
            }
        ],
        "is_left_handed": False,
    }
    history_file = tmp_path / "session_history.json"
    history_file.write_text(json.dumps(payload))
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", history_file)

    expected = bag_index_summary(shots, is_left_handed=False)

    url = f"http://localhost:{server}/api/index"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        assert "application/json" in response.headers.get("Content-Type", "")
        data = json.loads(response.read().decode("utf-8"))

        assert "7 Iron" in data
        assert "Driver" in data
        assert "composite" in data["7 Iron"]
        assert "composite" in data["Driver"]
        assert data["7 Iron"]["composite"]["score"] == pytest.approx(
            expected["7 Iron"]["composite"]["score"], abs=0.01
        )
        assert data["7 Iron"]["efficiency"]["count"] == 2
        assert data["7 Iron"]["efficiency"]["confidence"] == int(ConfidenceTier.UNRATED)


def test_index_respects_is_left_handed(server, monkeypatch, tmp_path):
    shots = [
        _sample_shot(axis=5.0, club="7 Iron"),
        _sample_shot(axis=5.0, club="7 Iron"),
    ]
    rh_payload = {"sessions": [{"shots": shots}], "is_left_handed": False}
    lh_payload = {"sessions": [{"shots": shots}], "is_left_handed": True}

    history_file = tmp_path / "session_history.json"

    history_file.write_text(json.dumps(rh_payload))
    monkeypatch.setattr(obs_server, "SESSION_LOG_PATH", history_file)
    with urllib.request.urlopen(f"http://localhost:{server}/api/index") as resp:
        rh_data = json.loads(resp.read().decode("utf-8"))

    history_file.write_text(json.dumps(lh_payload))
    with urllib.request.urlopen(f"http://localhost:{server}/api/index") as resp:
        lh_data = json.loads(resp.read().decode("utf-8"))

    expected_rh = bag_index_summary(shots, is_left_handed=False)
    expected_lh = bag_index_summary(shots, is_left_handed=True)
    assert rh_data["7 Iron"]["shape"]["score"] == pytest.approx(
        expected_rh["7 Iron"]["shape"]["score"], abs=0.01
    )
    assert lh_data["7 Iron"]["shape"]["score"] == pytest.approx(
        expected_lh["7 Iron"]["shape"]["score"], abs=0.01
    )
