"""The splash must actually appear on screen.

Regression test for a launch-blocking bug: the splash was created as a
transient child of a WITHDRAWN root. The window manager never maps such a
window, so it was 1x1 and invisible — yet grab_set() and wait_window() both
succeeded, leaving the app hung on a modal nobody could see. It looked
exactly like "I launched the app and nothing happened".

Rendering the canvas to PostScript (how the splash was originally checked)
works fine on an unmapped window, which is why drawing tests missed this.
These assert real window mapping instead.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")


@pytest.fixture
def tk_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.delenv("SPS_SHOT_SOURCE", raising=False)
    monkeypatch.delenv("SPS_GSPRO_DB", raising=False)
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("900x600")
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def _splash(root):
    from src.ui.splash import SplashScreen

    sp = SplashScreen(root, clubs=["Driver", "7 Iron", "PW"], current_club="7 Iron")
    for _ in range(6):
        root.update()
        sp.win.update_idletasks()
    return sp


def test_splash_window_is_actually_mapped_and_sized(tk_root):
    """The bug: window existed but was never mapped, at 1x1."""
    sp = _splash(tk_root)
    try:
        assert sp.win.winfo_ismapped(), "splash window was never mapped on screen"
        assert sp.win.winfo_viewable(), "splash window is not viewable"
        assert sp.win.winfo_width() > 200, f"splash collapsed to {sp.win.winfo_width()}px"
        assert sp.win.winfo_height() > 200, f"splash collapsed to {sp.win.winfo_height()}px"
    finally:
        sp._close()


def test_splash_is_visible_even_when_the_root_is_withdrawn(tk_root):
    """The exact failing launch path: root withdrawn before the splash.

    Even if a caller withdraws the root, the splash must still be visible
    rather than silently hanging the app.
    """
    tk_root.withdraw()
    sp = _splash(tk_root)
    try:
        assert sp.win.winfo_ismapped(), (
            "splash is invisible when the root is withdrawn — this hangs the app"
        )
        assert sp.win.winfo_width() > 200
    finally:
        sp._close()


def test_the_empty_root_stays_hidden_behind_the_splash(tk_root):
    """The grey root window must not cover the splash.

    Second bug in this area: hiding the root made the splash invisible, so
    the root was left mapped — which put a blank grey window on top of the
    splash instead. The working combination is a WITHDRAWN root plus an
    explicit deiconify() on the splash, which maps it regardless of the
    master's state. This asserts both halves at once.
    """
    tk_root.withdraw()
    sp = _splash(tk_root)
    try:
        assert sp.win.winfo_ismapped(), "splash must be visible under a withdrawn root"
        assert not tk_root.winfo_viewable(), (
            "the empty root window is showing and will cover the splash"
        )
    finally:
        sp._close()


def test_every_club_in_a_full_bag_is_reachable_and_selectable(tk_root):
    """A 15-club bag must be fully clickable.

    The dropdown originally rendered self.clubs[:9], silently hiding the
    wedges and putter — a user simply could not pick their SW. Two columns
    fit the whole bag; this walks every entry and checks the click maps to
    the right club (a column-index bug would select the wrong one).
    """
    from src.ui.splash import SplashScreen

    bag = ["Driver", "3 Wood", "5 Wood", "3 Hybrid", "4 Iron", "5 Iron",
           "6 Iron", "7 Iron", "8 Iron", "9 Iron", "PW", "GW", "SW", "LW",
           "Putter"]
    sp = SplashScreen(tk_root, clubs=bag, current_club="7 Iron")
    try:
        for target in bag:
            sp._club_menu_open = True
            sp._draw()
            hits = [r for r in sp._hit_rects if r[4] == "club" and r[5] == target]
            assert hits, f"{target} has no hit target — it is unreachable"

            x1, y1, x2, y2, _, _ = hits[0]

            class _Evt:
                pass

            evt = _Evt()
            evt.x = (x1 + x2) // 2
            evt.y = (y1 + y2) // 2
            sp._on_click(evt)
            assert sp.current_club == target, (
                f"clicking {target} selected {sp.current_club}"
            )
    finally:
        sp._close()


def test_club_subtitle_reports_only_real_bag_data(tk_root):
    """Gear text must come from the bag, never be invented."""
    from src.ui.splash import SplashScreen

    specs = {
        "7 Iron": {"brand": "Callaway", "model": "Paradym X", "loft_deg": 27.5},
        "Mystery Club": {},
    }
    sp = SplashScreen(tk_root, clubs=["7 Iron", "Mystery Club"],
                      current_club="7 Iron", club_specs=specs)
    try:
        assert sp._club_subtitle("7 Iron") == "Callaway Paradym X  ·  27.5°"
        # No specs -> no subtitle, rather than a placeholder model name.
        assert sp._club_subtitle("Mystery Club") == ""
        assert sp._club_subtitle("Not In Bag") == ""
    finally:
        sp._close()


def test_the_every_launch_toggle_persists_and_controls_the_splash(tk_root):
    """The "show every launch" checkbox must round-trip and take effect.

    Nova connects ~0.5s AFTER launch, so a user who wants to confirm their
    monitor is live before a session needs the setup screen every time.
    """
    import importlib
    import json

    from src.gspro import settings as gspro_settings
    from src.ui import splash as splash_mod
    from src.ui.splash import SplashScreen

    def click(sp, action):
        hits = [r for r in sp._hit_rects if r[4] == action]
        assert hits, f"no hit target for {action!r}"
        x1, y1, x2, y2, _, _ = hits[0]

        class _Evt:
            pass

        evt = _Evt()
        evt.x = (x1 + x2) // 2
        evt.y = (y1 + y2) // 2
        sp._on_click(evt)

    sp = SplashScreen(tk_root, clubs=["7 Iron"], current_club="7 Iron")
    tk_root.update()
    assert sp.always_show is False, "should default to off"
    click(sp, "always")
    assert sp.always_show is True
    click(sp, "start")

    path = os.environ["SPS_SHOT_SOURCE_FILE"]
    assert json.loads(open(path).read())["always_show_splash"] is True

    importlib.reload(gspro_settings)
    importlib.reload(splash_mod)
    assert splash_mod.should_show_splash() is True, (
        "ticked, but the splash would not reappear"
    )

    # Untick -> back to onboarding-only behaviour.
    sp2 = SplashScreen(tk_root, clubs=["7 Iron"], current_club="7 Iron")
    tk_root.update()
    assert sp2.always_show is True, "checkbox state was not remembered"
    click(sp2, "always")
    click(sp2, "start")

    importlib.reload(gspro_settings)
    importlib.reload(splash_mod)
    assert splash_mod.should_show_splash() is False


def test_nova_card_reports_live_connection_state(tk_root):
    """The Nova card must show real status, not a hopeful default."""
    import shanktuary_performance_studio as studio
    from src.ui.splash import SplashScreen

    original = dict(studio.nova_status)
    try:
        studio.nova_status.update({"connected": False, "host": ""})
        sp = SplashScreen(tk_root, clubs=["7 Iron"], current_club="7 Iron")
        tk_root.update()

        def texts():
            return [sp.canvas.itemcget(i, "text")
                    for i in sp.canvas.find_all()
                    if sp.canvas.type(i) == "text"]

        assert any("searching" in t for t in texts()), "no searching state shown"

        studio.nova_status.update({"connected": True, "host": "10.0.0.5:2920"})
        sp._poll_status()
        tk_root.update()
        assert any("10.0.0.5:2920" in t for t in texts()), (
            "card did not go live when Nova connected"
        )
        sp._close()
    finally:
        studio.nova_status.clear()
        studio.nova_status.update(original)


def test_run_does_not_block_when_the_window_cannot_be_shown(tk_root):
    """If the splash truly cannot display, run() must return, not hang."""
    from src.ui.splash import SplashScreen

    sp = SplashScreen(tk_root, clubs=["7 Iron"], current_club="7 Iron")
    sp.win.withdraw()          # force the un-showable state
    tk_root.update_idletasks()
    assert sp.run() is None, "run() should fall through instead of blocking"


def test_start_button_persists_the_choice_and_closes(tk_root):
    """Clicking START SESSION must record the source and release the grab."""
    from src.gspro import settings as gspro_settings

    sp = _splash(tk_root)
    try:
        sp.source = "gspro"
        start = [r for r in sp._hit_rects if r[4] == "start"]
        assert start, "no START SESSION hit target was registered"
        x1, y1, x2, y2, _, _ = start[0]

        class _Evt:
            pass

        evt = _Evt()
        evt.x = (x1 + x2) // 2
        evt.y = (y1 + y2) // 2
        sp._on_click(evt)
    finally:
        try:
            sp._close()
        except Exception:
            pass

    assert sp.result is not None and sp.result["source"] == "gspro"
    assert gspro_settings.load_settings(refresh=True)["source"] == "gspro"
    assert gspro_settings.load_settings()["onboarded"] is True
