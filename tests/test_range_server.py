import urllib.request
import threading
import time
import pytest
import sys
from pathlib import Path

# Add parent directory to path to import obs_server
sys.path.append(str(Path(__file__).parent.parent.resolve()))
from obs_server import start_obs_server, OBS_PORT

@pytest.fixture(scope="module")
def server():
    t = threading.Thread(target=start_obs_server, daemon=True)
    t.start()
    time.sleep(1) # Allow server to bind and start
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
        
        body = response.read().decode("utf-8")
        assert "initRenderer" in body
