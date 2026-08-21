import urllib.request
import threading
import time
import pytest
import sys
import json
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.resolve()))
from obs_server import start_obs_server, OBS_PORT, obs_state

@pytest.fixture(scope="module")
def server():
    t = threading.Thread(target=start_obs_server, daemon=True)
    t.start()
    time.sleep(1)
    yield

def test_range_route(server):
    url = f"http://localhost:{OBS_PORT}/range"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        content_type = response.headers.get("Content-Type", "")
        assert "text/html" in content_type
        
        body = response.read().decode("utf-8")
        assert "3D Driving Range" in body
        assert "id=\"hud\"" in body

def test_range_static_js(server):
    url = f"http://localhost:{OBS_PORT}/range/js/main.js"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        content_type = response.headers.get("Content-Type", "")
        assert "application/javascript" in content_type or "text/javascript" in content_type

def test_push_native_nova_shot(server):
    # Exact native JSON payload from OpenLaunch Nova + OpenGolfCoach
    native_nova_shot = {
        "type": "shot",
        "shot_number": 64,
        "ball_speed_meters_per_second": 26.75376892089844,
        "vertical_launch_angle_degrees": 22.26587677001953,
        "horizontal_launch_angle_degrees": -4.231376647949219,
        "total_spin_rpm": 2788.01513671875,
        "spin_axis_degrees": -6.941661357879639,
        "open_golf_coach": {
            "us_customary_units": {
                "ball_speed_mph": 59.846476593431866,
                "carry_distance_yards": 51.68079468377285,
                "offline_distance_yards": -4.76143564815784
            }
        }
    }
    obs_state.push_shot(native_nova_shot)
    assert obs_state.latest_shot == native_nova_shot
