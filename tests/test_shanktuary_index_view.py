"""The standalone desktop Shanktuary Index view: nav registration and the
three response states (available, insufficient coverage, no history at all),
rendered on a real Tk canvas the same way test_board_assign_modal_layout.py
checks the board-assignment modal.
"""
import sys

import pytest

sys.path.insert(0, "/home/sean/sps")

tk = pytest.importorskip("tkinter")


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.geometry("1900x980")
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def _shot(bs, carry, club="7 Iron"):
    return {
        "club": club,
        "total_spin_rpm": 6500.0,
        "vertical_launch_angle_degrees": 18.0,
        "spin_axis_degrees": 1.0,
        "open_golf_coach": {
            "us_customary_units": {"ball_speed_mph": bs, "carry_distance_yards": carry}
        },
    }


def _texts(canvas):
    out = []
    for item in canvas.find_all():
        if canvas.type(item) != "text":
            continue
        bb = canvas.bbox(item)
        if bb:
            out.append((canvas.itemcget(item, "text"), bb))
    return out


def _render(tk_root, sessions, is_left_handed=False, w=1900, h=980):
    import shanktuary_performance_studio as studio

    canvas = tk.Canvas(tk_root, width=w, height=h)
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.canvas = canvas
    app.root = tk_root
    app.sessions = sessions
    app.is_left_handed = is_left_handed

    canvas.delete("all")
    studio.ShanktuaryApp.draw_shanktuary_index_viewport(app, w, h)
    tk_root.update_idletasks()
    return canvas


# --- nav registration --------------------------------------------------------

def test_index_is_registered_in_nav_items():
    import theme

    ids = {mode_id: label for mode_id, label, _tooltip in theme.NAV_ITEMS}
    assert 11 in ids
    assert ids[11] == "Index"


def test_production_app_navigates_to_mode_11_runtime(tk_root, tmp_path, monkeypatch):
    """Calling set_mode(11) on ShanktuaryApp executes draw_screen() and paints the Index view."""
    import shanktuary_performance_studio as studio

    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))

    app = studio.ShanktuaryApp(tk_root)
    tk_root.update_idletasks()

    assert 11 in app.mode_pill_rects
    r = app.mode_pill_rects[11]
    assert r is not None

    app.set_mode(11)
    assert app.view_mode == 11

    texts = [t for t, _bb in _texts(app.canvas)]
    assert any("SHANKTUARY INDEX" in t for t in texts)
    assert any("OVERALL SCORE" in t for t in texts)


def test_hardened_tier_label_boundary(tk_root):
    """_draw_index_score_pane handles both enum and string tier values without raising."""
    import shanktuary_performance_studio as studio
    from src.analytics.index import IndexTier

    canvas = tk.Canvas(tk_root, width=600, height=400)
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.canvas = canvas
    app.root = tk_root

    # 1. Enum tier
    canvas.delete("all")
    app._draw_index_score_pane(0, 0, 300, 300, {
        "status": "available",
        "score": 75.2,
        "tier": IndexTier.FULL_SPREAD,
    })
    texts = [t for t, _bb in _texts(canvas)]
    assert any("FULL-SPREAD" in t for t in texts)

    # 2. String tier (e.g. from JSON payload)
    canvas.delete("all")
    app._draw_index_score_pane(0, 0, 300, 300, {
        "status": "available",
        "score": 68.0,
        "tier": "Index",
    })
    texts = [t for t, _bb in _texts(canvas)]
    assert any("INDEX" in t for t in texts)

    canvas.destroy()


# --- available state ----------------------------------------------------------

def test_available_state_shows_score_and_established_club_count(tk_root):
    shots = (
        [_shot(bs=110.0, carry=250.0, club="Driver") for _ in range(35)]
        + [_shot(bs=95.0, carry=150.0, club="7 Iron") for _ in range(35)]
        + [_shot(bs=90.0, carry=100.0, club="PW") for _ in range(35)]
    )
    canvas = _render(tk_root, [{"shots": shots}])
    texts = [t for t, _bb in _texts(canvas)]

    assert any("3 Established Clubs" in t for t in texts)
    assert any(t == "INDEX" for t in texts)  # tier badge
    assert any("Driver" in t for t in texts)  # per-club row
    canvas.destroy()


# --- insufficient coverage state ----------------------------------------------

def test_insufficient_coverage_shows_the_explicit_reason(tk_root):
    shots = [_shot(bs=110.0, carry=250.0, club="Driver") for _ in range(35)]
    canvas = _render(tk_root, [{"shots": shots}])
    texts = [t for t, _bb in _texts(canvas)]

    assert any("at least 3 established clubs" in t for t in texts)
    canvas.destroy()


# --- missing / empty history state --------------------------------------------

def test_no_session_history_does_not_crash_and_shows_a_reason(tk_root):
    canvas = _render(tk_root, [])
    texts = [t for t, _bb in _texts(canvas)]

    assert texts, "empty-history view painted no text at all"
    assert any("0 Established Clubs" in t for t in texts)
    canvas.destroy()


def test_sessions_with_no_shots_key_does_not_crash(tk_root):
    canvas = _render(tk_root, [{"id": "empty_session"}])
    texts = [t for t, _bb in _texts(canvas)]
    assert texts
    canvas.destroy()


# --- read-only: no state/rect mutation ----------------------------------------

def test_view_does_not_write_any_app_attributes(tk_root):
    """The view is read-only -- it must not create hit-rect lists or other
    mutable state the way the interactive My Bag view does."""
    import shanktuary_performance_studio as studio

    canvas = tk.Canvas(tk_root, width=800, height=600)
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.canvas = canvas
    app.root = tk_root
    app.sessions = []
    app.is_left_handed = False

    before = set(vars(app))
    studio.ShanktuaryApp.draw_shanktuary_index_viewport(app, 800, 600)
    after = set(vars(app))
    assert after == before
    canvas.destroy()


# --- desktop subclass integration -------------------------------------------
#
# theme.NAV_ITEMS is not what actually renders in the shipped app:
# ShanktuaryDesktopApp.draw_nav_rail() paints it first, then
# shell_redesign_v13.paint_nav() (reached via the v14/v17 delegation chain)
# repaints the rail from its own hardcoded per-section mode list and
# OVERWRITES app.mode_pill_rects/design_mode_rects with only what it knows
# about. Mode 11 was invisible and unclickable in the real shell until it
# was also added there -- these two tests pin that it stays registered.

def test_desktop_subclass_has_palette_wrapped_index_viewport():
    """ShanktuaryDesktopApp must wrap draw_shanktuary_index_viewport with legacy_palette."""
    import inspect

    from src.ui.desktop import ShanktuaryDesktopApp

    src = inspect.getsource(ShanktuaryDesktopApp.draw_shanktuary_index_viewport)
    assert "legacy_palette.draw_production_page" in src
    assert "draw_shanktuary_index_viewport" in src


def test_desktop_subclass_registers_and_navigates_mode_11(tk_root, tmp_path, monkeypatch):
    """Clicking mode 11 on the redesigned nav rail must switch view_mode to 11 and render."""
    import shanktuary_performance_studio as studio
    from src.ui.desktop import ShanktuaryDesktopApp

    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))

    app = ShanktuaryDesktopApp(tk_root)
    tk_root.update_idletasks()

    # Verify mode 11 is in design_mode_rects
    assert 11 in app.design_mode_rects
    rect = app.design_mode_rects[11]
    assert rect is not None

    # Simulate mouse click on the Index nav item
    click_x = (rect[0] + rect[2]) // 2
    click_y = (rect[1] + rect[3]) // 2
    event = type("Event", (), {"x": click_x, "y": click_y})()

    app.handle_mouse_press(event)
    assert app.view_mode == 11

    # Verify that draw_screen rendered the Index viewport elements
    texts = [t for t, _bb in _texts(app.canvas)]
    assert any("SHANKTUARY INDEX" in t for t in texts)
    assert any("OVERALL SCORE" in t for t in texts)


def test_nav_icon_scorecard_draws(tk_root):
    """The Index nav item must render the scorecard line icon onto canvas."""
    import shell_redesign as icons

    canvas = tk.Canvas(tk_root, width=100, height=100)
    canvas.delete("all")
    icons._draw_nav_icon(canvas, "Index", 32, 32, "#FFFFFF")
    items = canvas.find_all()
    assert len(items) >= 4  # outer card, center fold, rows, pencil
    canvas.destroy()

