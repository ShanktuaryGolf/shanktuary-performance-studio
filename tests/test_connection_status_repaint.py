"""The UI must repaint when hardware connection state changes.

Reported as "the Nova shows as disconnected in settings". It was not
disconnected — Nova connects ~0.5s AFTER the first paint, and poll_queue()
only called draw_screen() when a SHOT arrived. So the window kept showing
whatever it painted at startup: permanently stale "disconnected" text on a
perfectly working link.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    import shanktuary_performance_studio as studio
    from src.ui import ShanktuaryDesktopApp

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("1400x850")

    nova_before = dict(studio.nova_status)
    gspro_before = dict(studio.gspro_status)
    studio.nova_status.update({"connected": False, "host": ""})

    application = ShanktuaryDesktopApp(root)
    root.update()

    counter = {"n": 0}
    original = application.draw_screen

    def counting(*a, **k):
        counter["n"] += 1
        return original(*a, **k)

    application.draw_screen = counting
    application.poll_queue()          # start the 100ms poll chain
    root.update()
    counter["n"] = 0

    yield root, application, counter, studio

    try:
        root.destroy()
    except tk.TclError:
        pass
    studio.nova_status.clear()
    studio.nova_status.update(nova_before)
    studio.gspro_status.clear()
    studio.gspro_status.update(gspro_before)


def _spin(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def test_ui_repaints_when_nova_connects(app):
    """The reported bug: connection happened, UI never noticed."""
    root, _application, counter, studio = app
    studio.nova_status.update({"connected": True, "host": "192.168.40.249:2920"})
    _spin(root, 1.5)
    assert counter["n"] >= 1, (
        "UI did not repaint when Nova connected — status stays stale"
    )


def test_ui_repaints_when_nova_drops(app):
    root, _application, counter, studio = app
    studio.nova_status.update({"connected": True, "host": "192.168.40.249:2920"})
    _spin(root, 1.0)
    counter["n"] = 0
    studio.nova_status.update({"connected": False, "host": ""})
    _spin(root, 1.0)
    assert counter["n"] >= 1, "UI did not repaint when Nova dropped"


def test_ui_repaints_when_gspro_connects(app):
    root, _application, counter, studio = app
    studio.gspro_status.update(
        {"enabled": True, "connected": True, "db_found": True}
    )
    _spin(root, 1.0)
    assert counter["n"] >= 1, "UI did not repaint when GSPro connected"


def test_a_steady_connection_does_not_cause_continuous_redraws(app):
    """Repaint on CHANGE only — not 10x a second forever."""
    root, _application, counter, studio = app
    studio.nova_status.update({"connected": True, "host": "192.168.40.249:2920"})
    _spin(root, 1.0)
    counter["n"] = 0
    _spin(root, 2.0)
    assert counter["n"] == 0, (
        f"redrew {counter['n']}x with nothing changing — wasteful repaint loop"
    )
