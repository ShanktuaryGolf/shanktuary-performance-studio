"""The Setup (mode 10) page must agree with the tools menu about connection.

Reported as "Setup says Nova offline / Not connected but the tools menu shows
Nova online". Root cause: draw_setup_viewport() read self.nova_connected, an
attribute that is only set when a SHOT arrives — not a link flag. So on a live
link with no shots yet, Setup said "Not connected" while the tools menu (which
reads nova_status) correctly showed it online.

Also: a user who never wants the splash screen still needs a way to switch the
shot source from Nova to GSPro. The SHOT SOURCE card exposes Nova/GSPro/Both
buttons that persist via apply_shot_source().
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    import shanktuary_performance_studio as studio

    # Isolate session history so the test never touches the user's real data.
    hist = tmp_path / "hist.json"
    if os.path.exists("/home/sean/sps/shanktuary_session_history.json"):
        import shutil
        shutil.copy2(
            "/home/sean/sps/shanktuary_session_history.json", str(hist)
        )
    else:
        hist.write_text("{}")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(hist))

    from src.ui import ShanktuaryDesktopApp

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("1915x1111")

    nova_before = dict(studio.nova_status)
    gspro_before = dict(studio.gspro_status)
    studio.nova_status.update({"connected": False, "host": ""})
    studio.gspro_status.clear()

    application = ShanktuaryDesktopApp(root)
    root.update()

    yield root, application, studio

    try:
        root.destroy()
    except tk.TclError:
        pass
    studio.nova_status.clear()
    studio.nova_status.update(nova_before)
    studio.gspro_status.clear()
    studio.gspro_status.update(gspro_before)


def _texts(app):
    c = app.canvas
    return [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]


def test_setup_shows_connected_when_nova_link_is_up_but_no_shot_arrived(app):
    """The reported bug: live link, zero shots -> Setup said 'Not connected'."""
    root, application, studio = app
    # Nova IS connected but no shot has arrived yet. The stale attribute the
    # page used to read is therefore False — exactly the contradictory state.
    studio.nova_status.update({"connected": True, "host": "192.168.40.249:2920"})
    application.nova_connected = False

    application.view_mode = 10
    application.draw_screen()
    for _ in range(5):
        root.update()

    texts = _texts(application)
    assert "Nova connected" in texts, (
        f"Setup should say 'Nova connected' on a live link; got: {texts}"
    )
    # The old wrong strings must be gone.
    assert "Not connected" not in texts, "stale 'Not connected' still shown"
    assert "Nova offline" not in texts, "stale 'Nova offline' still shown"


def test_setup_shows_offline_when_nova_link_is_down(app):
    root, application, studio = app
    studio.nova_status.update({"connected": False, "host": ""})
    application.view_mode = 10
    application.draw_screen()
    for _ in range(5):
        root.update()

    texts = _texts(application)
    assert "Nova offline" in texts or "Not connected" in texts


def test_setup_exposes_gspro_switcher(app):
    """A user who skips the splash can still pick GSPro from Setup."""
    root, application, studio = app
    application.view_mode = 10
    application.draw_screen()
    for _ in range(5):
        root.update()

    keys = [r[4] for r in application.setup_source_btn_rects]
    assert "nova" in keys and "gspro" in keys and "both" in keys, (
        f"SHOT SOURCE card must offer nova/gspro/both; got {keys}"
    )


def test_clicking_gspro_on_setup_persists_the_switch(app):
    root, application, studio = app
    from src.gspro import settings as gspro_settings

    application.view_mode = 10
    application.draw_screen()
    for _ in range(5):
        root.update()

    rect = [r for r in application.setup_source_btn_rects if r[4] == "gspro"]
    assert rect, "no GSPro button to click"
    gx0, gy0, gx1, gy1, _ = rect[0]

    ev = tk.Event()
    ev.x, ev.y = (gx0 + gx1) // 2, (gy0 + gy1) // 2
    application.handle_mouse_press(ev)
    for _ in range(5):
        root.update()

    assert gspro_settings.effective_source() == "gspro", (
        "clicking GSPro on Setup did not persist the source switch"
    )
    # The card should now present GSPro as the device.
    texts = _texts(application)
    assert "GSPro" in texts
