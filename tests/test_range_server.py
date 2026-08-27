import urllib.request
import urllib.error
import threading
import time
import socket
import pytest
import sys
import json
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.resolve()))
from obs_server import start_obs_server, obs_state

@pytest.fixture(scope="module")
def server():
    # Bind a free port rather than the default. If the desktop app is already
    # running it owns 9321, and the test would silently exercise whatever
    # code that process was started with instead of the working tree.
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

def test_range_route(server):
    url = f"http://localhost:{server}/range"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        content_type = response.headers.get("Content-Type", "")
        assert "text/html" in content_type
        
        body = response.read().decode("utf-8")
        assert "3D Driving Range" in body
        # HUD elements are namespaced hud-* ids (e.g. hud-pressure-phase)
        assert 'id="hud-' in body

def test_range_static_js(server):
    url = f"http://localhost:{server}/range/js/main.js"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        content_type = response.headers.get("Content-Type", "")
        assert "application/javascript" in content_type or "text/javascript" in content_type

def test_projector_surface_routes(server):
    """/divot and /tiles are separate windows aimed at separate surfaces.

    Both serve overlay.html; the page branches on pathname to decide which
    widgets it draws. /projector stays an alias of /divot for existing setups.
    """
    for path in ("/divot", "/tiles", "/projector"):
        url = f"http://localhost:{server}{path}"
        with urllib.request.urlopen(urllib.request.Request(url)) as response:
            assert response.status == 200, f"{path} did not serve"
            assert "text/html" in response.headers.get("Content-Type", "")
            body = response.read().decode("utf-8")
            assert "SPS_PROJECTOR_ROLE" in body, (
                f"{path} served a page with no projector role resolver"
            )


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


def _get_status(port, path):
    url = f"http://localhost:{port}{path}"
    try:
        with urllib.request.urlopen(url) as response:
            return response.status
    except urllib.error.HTTPError as e:
        return e.code


def test_static_traversal_blocked(server):
    # Path traversal must never escape the assets directory
    # (server binds 0.0.0.0 — this is LAN-reachable).
    assert _get_status(server, "/assets/%2e%2e/obs_server.py") in (400, 403, 404)
    assert _get_status(server, "/range/%2e%2e/%2e%2e/obs_server.py") in (400, 403, 404)
    assert _get_status(server, "/assets/%2e%2e%2f%2e%2e%2fetc%2fpasswd") in (400, 403, 404)


def test_static_legit_asset_still_served(server):
    assert _get_status(server, "/assets/overlay.html") == 200
    assert _get_status(server, "/range/js/main.js") == 200
