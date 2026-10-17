"""Setup page: pressure SOURCE picker (Wii Balance Boards / open-fp plates).

Drives the shipped ShanktuaryDesktopApp canvas. Everything that persists is
isolated: session history, shot source, and the pressure calibration file
(set_pressure_source saves; the real ~/.shanktuary file must never change).
"""
import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")


def _closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    monkeypatch.delenv("SPS_OPENFP_URL", raising=False)
    import obs_server
    import shanktuary_performance_studio as studio

    monkeypatch.setattr(obs_server, "CALIBRATION_FILE", str(tmp_path / "cal.json"))
    hist = tmp_path / "hist.json"
    hist.write_text("{}")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(hist))

    # A fresh manager reading the (empty) temp calibration: Wii boards,
    # single mode. The module-global one is restored afterwards.
    pm = obs_server.PressureManager()
    pm.openfp_url = f"http://127.0.0.1:{_closed_port()}"  # refused at once
    monkeypatch.setattr(obs_server, "pressure_manager", pm)

    from src.ui import ShanktuaryDesktopApp

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("1915x1111")
    application = ShanktuaryDesktopApp(root)
    application.view_mode = 10
    application.draw_screen()
    root.update()

    yield root, application, pm, tmp_path

    pm.running = False
    if pm.backend is not None:
        pm.backend.close()
    try:
        root.destroy()
    except tk.TclError:
        pass


def _texts(app):
    c = app.canvas
    return [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]


def _click(root, app, rect):
    ev = tk.Event()
    ev.x, ev.y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    app.handle_mouse_press(ev)
    for _ in range(3):
        root.update()


def _source_rect(app, key):
    hits = [r for r in app.setup_pressure_source_rects if r[4] == key]
    assert hits, f"no {key!r} pill on Setup: {app.setup_pressure_source_rects}"
    return hits[0]


def test_picker_offers_both_sources_and_defaults_to_wii_boards(app):
    root, application, pm, _ = app
    assert {r[4] for r in application.setup_pressure_source_rects} == {"wbb", "openfp"}
    texts = _texts(application)
    assert "BALANCE BOARDS" in texts and "MODE" in texts
    assert "PLATES" not in texts


def test_clicking_openfp_switches_source_shows_plates_panel_and_persists(app):
    root, application, pm, tmp_path = app
    _click(root, application, _source_rect(application, "openfp"))

    assert pm.pressure_source == "openfp"
    assert pm.backend.__class__.__name__ == "OpenFpBackend"
    application.draw_screen()
    root.update()
    texts = _texts(application)
    assert "FORCE PLATES" in texts and "PLATES" in texts
    # Wii-only controls are gone and their hit rects cannot fire.
    assert "MODE" not in texts and "PAIRING" not in texts
    assert application.setup_mode_1_rect is None
    assert application.setup_pair_rect is None
    assert application.setup_wizard_rect is None
    # Not connected (port refused): say so, show no fabricated weight.
    assert "searching…" in texts
    assert texts.count("—") >= 2, "per-foot weight must read '—' while not streaming"
    import json
    saved = json.loads((tmp_path / "cal.json").read_text())
    assert saved["pressure_source"] == "openfp"

    _click(root, application, _source_rect(application, "wbb"))
    assert pm.pressure_source == "wbb"
    application.draw_screen()
    root.update()
    assert "MODE" in _texts(application)


def test_change_address_uses_the_prompt_and_rejects_garbage(app, monkeypatch):
    root, application, pm, _ = app
    _click(root, application, _source_rect(application, "openfp"))
    application.draw_screen()
    root.update()

    port = _closed_port()
    monkeypatch.setattr(application, "_prompt_openfp_url",
                        lambda current: f"127.0.0.1:{port}")
    _click(root, application, application.setup_openfp_url_rect)
    assert pm.openfp_url == f"127.0.0.1:{port}"
    assert (pm.backend.host, pm.backend.port) == ("127.0.0.1", port)

    application.draw_screen()
    root.update()
    monkeypatch.setattr(application, "_prompt_openfp_url", lambda current: "http://")
    _click(root, application, application.setup_openfp_url_rect)
    assert pm.openfp_url == f"127.0.0.1:{port}", "a bad address replaced a good one"
    assert "Invalid address" in (application.copy_feedback or "")

    # Cancelled dialog: nothing changes.
    application.draw_screen()
    root.update()
    monkeypatch.setattr(application, "_prompt_openfp_url", lambda current: None)
    _click(root, application, application.setup_openfp_url_rect)
    assert pm.openfp_url == f"127.0.0.1:{port}"


def test_dashboard_button_opens_the_board_in_a_browser(app, monkeypatch):
    root, application, pm, _ = app
    _click(root, application, _source_rect(application, "openfp"))
    application.draw_screen()
    root.update()
    import shanktuary_performance_studio as studio
    opened = []
    monkeypatch.setattr(studio.webbrowser, "open", lambda url: opened.append(url))
    _click(root, application, application.setup_openfp_dash_rect)
    host, port = pm.backend.host, pm.backend.port
    assert opened == [f"http://{host}:{port}/"]


def test_guided_setup_skips_board_assignment_for_openfp(app):
    root, application, pm, _ = app
    pm.board_mode = "dual"          # left over from a Wii-board setup
    pm.set_pressure_source("openfp")
    application.start_guided_setup()
    assert "assign" not in application.setup_flow_steps
    application.show_board_assign_modal = False

    pm.set_pressure_source("wbb")
    application.start_guided_setup()
    assert application.setup_flow_steps[0] == "assign"
    application.show_board_assign_modal = False
