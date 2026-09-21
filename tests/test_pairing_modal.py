"""The guided pairing prompt must be usable without a console.

Reported: with one board already paired, trying to pair both removed the
working board and never paired the second -- and none of that was visible,
because the narration went to a console a --windowed build does not have.

These drive the real redesigned desktop app and synthesize real clicks.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

BOARD_1 = "001E35AAAAAA"
BOARD_2 = "001E35BBBBBB"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    import shanktuary_performance_studio as studio

    hist = tmp_path / "hist.json"
    hist.write_text("{}")
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(hist))

    from src.ui import ShanktuaryDesktopApp

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("1915x1111")
    application = ShanktuaryDesktopApp(root)
    root.update()

    yield root, application, studio

    try:
        root.destroy()
    except tk.TclError:
        pass


def _texts(application):
    c = application.canvas
    return [c.itemcget(i, "text") for i in c.find_all() if c.type(i) == "text"]


def _click(root, application, rect):
    ev = tk.Event()
    ev.x, ev.y = int((rect[0] + rect[2]) // 2), int((rect[1] + rect[3]) // 2)
    application.handle_mouse_press(ev)
    for _ in range(5):
        root.update()


def _pump(root, application, until, timeout=4.0):
    end = time.time() + timeout
    while time.time() < end:
        if until():
            return True
        time.sleep(0.02)
        root.update()
        application.draw_screen()
    return False


def _install_flow(application, target_count, boards, monkeypatch):
    """Give the app a flow wired to a fake pairer (no Bluetooth)."""
    from src.hardware.pressure.pairing_flow import PairingFlow

    state = {"calls": []}

    def _pair(discovery_timeout_mult=8, exclude_addresses=None, log=print):
        excluded = list(exclude_addresses or [])
        state["calls"].append(excluded)
        remaining = [b for b in boards if b not in excluded]
        if not remaining:
            return {"success": False,
                    "message": "Only the board you already paired answered."}
        return {"success": True, "message": "paired", "address": remaining[0],
                "radio_address": "38FC983BB4DC", "method": "callback",
                "boards_seen": len(remaining)}

    application.pairing_flow = PairingFlow(target_count=target_count,
                                           pair_fn=_pair)
    application.pairing_flow.start()
    application.show_pairing_modal = True
    application.draw_screen()
    return state


class TestPromptIsVisible:
    def test_single_board_prompt_names_the_sync_button(self, app, monkeypatch):
        root, application, _ = app
        _install_flow(application, 1, [BOARD_1], monkeypatch)

        blob = " ".join(_texts(application))
        assert "SYNC" in blob
        assert "battery" in blob.lower(), (
            "prompt should say where the SYNC button is"
        )
        assert application.pairing_action_rect, "no action button drawn"

    def test_two_board_prompt_says_which_board(self, app, monkeypatch):
        root, application, _ = app
        _install_flow(application, 2, [BOARD_1, BOARD_2], monkeypatch)

        blob = " ".join(_texts(application))
        assert "FIRST" in blob, f"user is not told which board; got {blob[:300]}"
        assert "First board" in blob and "Second board" in blob, (
            "two-board flow should show a step rail"
        )


class TestTwoBoardWalkthrough:
    def test_full_two_board_run_pairs_both(self, app, monkeypatch):
        root, application, _ = app
        state = _install_flow(application, 2, [BOARD_1, BOARD_2], monkeypatch)
        flow = application.pairing_flow

        _click(root, application, application.pairing_action_rect)
        assert _pump(root, application,
                     lambda: flow.status()["phase"] == "step_ok"), \
            f"stuck in {flow.status()['phase']}"

        blob = " ".join(_texts(application))
        assert "First board paired" in blob

        _click(root, application, application.pairing_action_rect)  # Next board
        assert flow.status()["phase"] == "prompt"
        assert "SECOND" in " ".join(_texts(application))

        _click(root, application, application.pairing_action_rect)  # I pressed SYNC
        assert _pump(root, application,
                     lambda: flow.status()["phase"] == "done"), \
            f"stuck in {flow.status()['phase']}"

        addrs = [p["address"] for p in flow.paired]
        assert addrs == [BOARD_1, BOARD_2], f"paired same board twice: {addrs}"
        assert BOARD_1 in state["calls"][1], (
            "second search did not exclude the first board"
        )
        assert "Both boards paired" in " ".join(_texts(application))

    def test_failure_is_shown_on_screen_with_a_retry(self, app, monkeypatch):
        root, application, _ = app
        # No boards available -> the pair call fails.
        _install_flow(application, 1, [], monkeypatch)
        flow = application.pairing_flow

        _click(root, application, application.pairing_action_rect)
        assert _pump(root, application,
                     lambda: flow.status()["phase"] == "failed")

        blob = " ".join(_texts(application))
        assert "That didn't work" in blob
        assert "Try again" in blob, "no retry offered after a failure"


class TestModalBehaviour:
    def test_modal_swallows_stray_clicks(self, app, monkeypatch):
        """A full-screen prompt that leaks clicks lets users change settings
        blind."""
        root, application, _ = app
        _install_flow(application, 1, [BOARD_1], monkeypatch)
        before = application.view_mode

        ev = tk.Event()
        ev.x, ev.y = 5, 5          # nav rail territory
        application.handle_mouse_press(ev)
        root.update()

        assert application.view_mode == before, "click fell through the modal"
        assert application.show_pairing_modal

    def test_cancel_closes_the_prompt(self, app, monkeypatch):
        root, application, _ = app
        _install_flow(application, 1, [BOARD_1], monkeypatch)
        assert application.pairing_cancel_rect
        _click(root, application, application.pairing_cancel_rect)
        assert not application.show_pairing_modal

    def test_no_action_button_while_searching(self, app, monkeypatch):
        """Nothing to click during the inquiry -- offering a button there is
        how people start a second search on top of the first."""
        import threading

        from src.hardware.pressure.pairing_flow import PairingFlow

        root, application, _ = app
        release = threading.Event()

        def _slow(**kw):
            release.wait(timeout=3)
            return {"success": True, "address": BOARD_1, "message": "ok",
                    "method": "callback"}

        application.pairing_flow = PairingFlow(target_count=1, pair_fn=_slow)
        application.pairing_flow.start()
        application.show_pairing_modal = True
        application.draw_screen()

        _click(root, application, application.pairing_action_rect)
        _pump(root, application,
              lambda: application.pairing_flow.status()["busy"], timeout=2)

        application.draw_screen()
        assert application.pairing_action_rect is None
        assert "Working" in " ".join(_texts(application))
        release.set()


class TestClickFeedback:
    """Reported: 'I can't tell that I actually clicked it.'

    Canvas rectangles are not widgets -- no hover, no press state. Confirming
    SYNC then starts a ~10s inquiry, so with no immediate visual change the
    click reads as ignored.
    """

    def test_button_paints_a_pressed_state_on_click(self, app, monkeypatch):
        import threading

        from src.hardware.pressure.pairing_flow import PairingFlow

        root, application, _ = app
        release = threading.Event()
        seen = {}

        def _slow(**kw):
            # Sample the pressed state from inside the click, before the
            # 140ms release timer can clear it.
            seen["pressed"] = getattr(application, "pairing_pressed", None)
            release.wait(timeout=3)
            return {"success": True, "address": BOARD_1, "message": "ok",
                    "method": "callback"}

        application.pairing_flow = PairingFlow(target_count=1, pair_fn=_slow)
        application.pairing_flow.start()
        application.show_pairing_modal = True
        application.draw_screen()

        rect = application.pairing_action_rect
        ev = tk.Event()
        ev.x, ev.y = int((rect[0] + rect[2]) // 2), int((rect[1] + rect[3]) // 2)
        application.handle_mouse_press(ev)

        _pump(root, application, lambda: "pressed" in seen, timeout=2)
        assert seen.get("pressed") == "action", (
            "no pressed state was painted; the click is invisible to the user"
        )
        release.set()

    def test_pressed_state_clears_itself(self, app, monkeypatch):
        """A button stuck in its pressed colour is its own bug."""
        root, application, _ = app
        _install_flow(application, 1, [BOARD_1], monkeypatch)

        application._flash_pairing_button("action")
        assert application.pairing_pressed == "action"

        assert _pump(root, application,
                     lambda: application.pairing_pressed is None, timeout=2), \
            "pressed state never cleared"

    def test_searching_screen_shows_elapsed_time(self, app, monkeypatch):
        """'It felt like nothing was happening' -- a static screen for ~10s
        reads as frozen, so show a counter that visibly climbs."""
        import threading

        from src.hardware.pressure.pairing_flow import PairingFlow

        root, application, _ = app
        release = threading.Event()

        def _slow(**kw):
            release.wait(timeout=3)
            return {"success": True, "address": BOARD_1, "message": "ok",
                    "method": "callback"}

        application.pairing_flow = PairingFlow(target_count=1, pair_fn=_slow)
        application.pairing_flow.start()
        application.show_pairing_modal = True
        application.draw_screen()

        _click(root, application, application.pairing_action_rect)
        _pump(root, application,
              lambda: application.pairing_flow.status()["busy"], timeout=2)
        application.draw_screen()

        blob = " ".join(_texts(application))
        assert "Working" in blob
        assert "(0s)" in blob or "s)" in blob, (
            f"no elapsed counter during the search; got {blob[:300]}"
        )
        assert "20 seconds" in blob, "user is not told how long this takes"
        release.set()


class TestConsoleOutput:
    def test_pairing_progress_still_reaches_the_console(self, capfd):
        """Reported: 'I looked at the console and saw nothing.'

        The flow routes the library's log= into its own handler to build the
        on-screen line. That handler swallowed every line, so a developer
        debugging a real failure got total silence. Both audiences matter.
        """
        from src.hardware.pressure.pairing_flow import PairingFlow

        def _pair(discovery_timeout_mult=8, exclude_addresses=None, log=print):
            log("[i] Scanning for a Wii Balance Board")
            log("[i] Found Nintendo RVL-WBC-01 at 001E35AAAAAA")
            return {"success": True, "address": BOARD_1, "message": "ok",
                    "method": "callback"}

        flow = PairingFlow(target_count=1, pair_fn=_pair)
        flow.start()
        flow.confirm_sync_pressed()
        for _ in range(200):
            if flow.status()["phase"] == "done":
                break
            time.sleep(0.01)

        out = capfd.readouterr().out
        assert "Scanning for" in out, f"library output never printed: {out!r}"
        assert "Found Nintendo" in out
        assert "Paired" in out, "outcome was not logged"

    def test_failure_reason_reaches_the_console(self, capfd):
        from src.hardware.pressure.pairing_flow import PairingFlow

        flow = PairingFlow(
            target_count=1,
            pair_fn=lambda **kw: {"success": False,
                                  "message": "No balance board answered."})
        flow.start()
        flow.confirm_sync_pressed()
        for _ in range(200):
            if flow.status()["phase"] == "failed":
                break
            time.sleep(0.01)

        out = capfd.readouterr().out
        assert "No balance board answered" in out, (
            f"failure reason never printed: {out!r}"
        )


class TestSetupEntryPoint:
    def test_modal_click_is_not_stolen_by_the_redesigned_shell(self, app,
                                                               monkeypatch):
        """Guard: the shell must defer to the production handler while the
        pairing modal is up.

        ShanktuaryDesktopApp tests its OWN hit rects before delegating, and
        the modal covers the whole window. Today the action button happens to
        sit where no design rect lives, so the click falls through -- but any
        new centred rect would silently swallow it. The board-assign modal
        already delegates for this reason; pairing now does too.
        """
        root, application, _ = app
        _install_flow(application, 1, [BOARD_1], monkeypatch)
        flow = application.pairing_flow

        rect = application.pairing_action_rect
        assert rect, "no action button drawn"

        # Go through the REAL bound handler, which is the redesigned shell's.
        ev = tk.Event()
        ev.x, ev.y = int((rect[0] + rect[2]) // 2), int((rect[1] + rect[3]) // 2)
        application.handle_mouse_press(ev)
        for _ in range(5):
            root.update()

        assert flow.status()["phase"] != "prompt", (
            "the click never reached the pairing flow — still waiting at the "
            "prompt, which is the reported 'nothing happens' symptom"
        )

    def test_pair_button_opens_the_guided_flow(self, app, monkeypatch):
        root, application, _ = app
        import src.hardware.pressure as pressure

        monkeypatch.setattr(pressure, "native_pairing_available", lambda: True)
        monkeypatch.setattr(
            "src.hardware.pressure.pairing_flow.make_pairing_flow",
            lambda target_count=1: __import__(
                "src.hardware.pressure.pairing_flow", fromlist=["PairingFlow"]
            ).PairingFlow(target_count=target_count,
                          pair_fn=lambda **kw: {"success": True,
                                                "address": BOARD_1,
                                                "message": "ok",
                                                "method": "callback"}),
        )

        application.view_mode = 10
        application.draw_screen()
        for _ in range(5):
            root.update()

        rect = application.setup_pair_rect
        assert rect, "no Pair button on the Setup page"
        _click(root, application, rect)

        assert application.show_pairing_modal, (
            "Pair button did not open the guided prompt"
        )

    def test_dual_mode_asks_for_two_boards(self, app, monkeypatch):
        """The reported case: the user wants both boards paired."""
        root, application, studio = app
        import src.hardware.pressure as pressure

        monkeypatch.setattr(pressure, "native_pairing_available", lambda: True)
        pm = getattr(studio.obs_server, "pressure_manager", None)
        if pm is None:
            pytest.skip("no pressure manager")
        monkeypatch.setattr(pm, "board_mode", "dual", raising=False)

        captured = {}

        def _fake_make(target_count=1):
            captured["n"] = target_count
            from src.hardware.pressure.pairing_flow import PairingFlow
            return PairingFlow(target_count=target_count,
                               pair_fn=lambda **kw: {"success": True,
                                                     "address": BOARD_1,
                                                     "message": "ok",
                                                     "method": "callback"})

        monkeypatch.setattr(
            "src.hardware.pressure.pairing_flow.make_pairing_flow", _fake_make)

        application.start_pairing_flow()
        assert captured.get("n") == 2, (
            "dual-plate setup should walk the user through both boards"
        )
