"""Run the real entry point; optionally test a frozen executable instead.

SPS_SMOKE_EXECUTABLE=/absolute/path/to/executable pytest -q tests/test_packaged_startup.py
Run under Xvfb on headless Linux. The executable may also be an AppImage with
APPIMAGE_EXTRACT_AND_RUN=1. These tests never import Pillow's native Tk helpers.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolate_parent_process(tmp_path, monkeypatch):
    monkeypatch.setenv("SPS_UI_PREVIEW", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "settings.json"))


def test_desktop_startup(tmp_path):
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        pytest.skip("GUI smoke test requires DISPLAY (run with xvfb-run)")
    executable = os.environ.get("SPS_SMOKE_EXECUTABLE")
    command = [executable] if executable else [sys.executable, str(ROOT / "shanktuary_app.py")]
    env = os.environ.copy()
    for key in ("HOME", "USERPROFILE", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "LOCALAPPDATA"):
        directory = tmp_path / key.lower()
        directory.mkdir()
        env[key] = str(directory)
    # The CLI flag must disable hardware before imports, even without preview.
    env.pop("SPS_UI_PREVIEW", None)
    env["SPS_SHOT_SOURCE_FILE"] = str(tmp_path / "shot-source.json")
    env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    result = subprocess.run(
        command + ["--smoke-test"], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SPS_SMOKE_TEST_OK: desktop and sidebar rendered" in output, output
    assert "Traceback" not in output, output
    assert "[preview] Pressure hardware disabled" in output, output
    assert "Balance board not connected" not in output, output


def test_smoke_flag_uses_bounded_render_check(monkeypatch):
    import shanktuary_app

    calls = []
    monkeypatch.setattr(shanktuary_app, "smoke_test", lambda: calls.append("render"))

    def unexpected_thread(*args, **kwargs):
        raise AssertionError("Smoke mode must not start connection workers")

    monkeypatch.setattr(shanktuary_app.threading, "Thread", unexpected_thread)
    monkeypatch.setattr(shanktuary_app.studio.obs_server, "launch_obs_server_thread", unexpected_thread)
    shanktuary_app.main(["--smoke-test"])
    assert calls == ["render"]


def test_smoke_mode_does_not_allow_interactive_splash():
    import shanktuary_app

    with pytest.raises(SystemExit):
        shanktuary_app.parse_args(["--smoke-test", "--splash"])
