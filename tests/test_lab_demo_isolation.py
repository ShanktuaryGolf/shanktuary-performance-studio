"""Check harness isolation in a fresh process before production imports occur."""
import subprocess
import sys
from pathlib import Path


def test_harness_import_disables_workers_and_redirects_user_paths(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    code = '''
import os, runpy, threading
from pathlib import Path
original_home = os.environ.get("HOME")
harness = runpy.run_path("scripts/demo_lab.py", run_name="lab_demo_import_test")
state = harness["STATE"]
import obs_server
import shanktuary_performance_studio as studio
assert os.environ["SPS_UI_PREVIEW"] == "1"
assert os.environ["SPS_DISABLE_LEGACY_MIGRATION"] == "1"
assert obs_server.pressure_manager.backend is None
assert not any(t.name == "pressure-worker" for t in threading.enumerate())
assert Path(studio.SESSION_LOG_PATH).is_relative_to(state)
assert obs_server.CONFIG_DIR.is_relative_to(state)
for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME",
            "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "SPS_SHOT_SOURCE_FILE"):
    assert Path(os.environ[key]).is_relative_to(state), key
assert os.environ["HOME"] != original_home
assert not list(state.rglob("shanktuary_session_history.json"))
print("isolated")
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=repo,
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "isolated" in result.stdout
