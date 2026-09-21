"""The Setup page's Pair Board button must actually pair, from the GUI.

Users reported that the PIN shown in Settings would not paste into the Windows
Bluetooth prompt. The real problem is that pasting a PIN can never work for
most adapters: the PIN is six raw binary bytes and the Windows PIN field is a
text control that rejects control characters and re-encodes non-ASCII. The
fix is for the app to pair natively -- so the GUI must expose that, in the
redesigned desktop app the user actually runs, not only in a CLI script.

These tests drive the real ShanktuaryDesktopApp and synthesize real clicks.
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

    # Never let a GUI test touch the user's real shot history.
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


def _open_setup(root, application):
    application.view_mode = 10
    application.draw_screen()
    for _ in range(5):
        root.update()


def _click(root, application, rect):
    ev = tk.Event()
    ev.x, ev.y = int((rect[0] + rect[2]) // 2), int((rect[1] + rect[3]) // 2)
    application.handle_mouse_press(ev)
    for _ in range(5):
        root.update()


def test_setup_page_has_a_pairing_button(app):
    """The whole fix is worthless if it is only reachable from a CLI script."""
    root, application, _ = app
    _open_setup(root, application)

    rect = getattr(application, "setup_pair_rect", None)
    assert rect, "Setup page exposes no pairing button"
    assert rect[2] > rect[0] and rect[3] > rect[1], f"degenerate button rect {rect}"


def test_pair_button_is_labelled_for_native_pairing_when_available(app, monkeypatch):
    """On Windows the button must say what it does -- it pairs, it no longer
    just scans and tells the user to go type a PIN elsewhere."""
    root, application, _ = app
    monkeypatch.setattr(
        "src.hardware.pressure.native_pairing_available", lambda: True,
        raising=False,
    )
    _open_setup(root, application)

    assert "Pair Board" in _texts(application), (
        "native pairing is available but the button does not offer it"
    )


def test_clicking_pair_opens_the_guided_prompt(app, monkeypatch):
    """The click must reach the pairing flow through the redesigned shell's
    hit testing -- ShanktuaryDesktopApp overrides handle_mouse_press, so a
    handler that only works on the production class is not enough.

    Pairing itself is no longer fired straight from this button: it opens the
    guided prompt, because a one-shot call narrated only to a console is
    invisible in a --windowed build (and could never reach a second board).
    """
    root, application, _ = app
    import src.hardware.pressure as pressure

    monkeypatch.setattr(pressure, "native_pairing_available", lambda: True)

    _open_setup(root, application)
    rect = getattr(application, "setup_pair_rect", None)
    assert rect, "no pairing button to click"

    _click(root, application, rect)

    assert application.show_pairing_modal, (
        "Pair Board did not open the guided pairing prompt"
    )
    assert application.pairing_flow is not None


def test_pairing_unavailable_is_reported_in_the_gui(app, monkeypatch):
    """A --windowed build has no console. A dead end that only print()s is
    invisible -- which is how the original 'Pair' button looked dead.

    (Failures *during* pairing are shown on the guided prompt itself; see
    tests/test_pairing_modal.py.)
    """
    root, application, _ = app
    import src.hardware.pressure as pressure

    monkeypatch.setattr(pressure, "native_pairing_available", lambda: False)

    _open_setup(root, application)
    _click(root, application, application.setup_pair_rect)

    assert not application.show_pairing_modal, (
        "opened a guided prompt that cannot pair anything"
    )
    assert application.copy_feedback, "no GUI feedback when pairing is unavailable"
    assert "Windows" in str(application.copy_feedback)


def test_untypeable_pin_is_flagged_rather_than_offered_for_pasting(app, monkeypatch):
    """The reported adapter 00:E0:4C:00:00:01 yields PIN bytes 01 00 00 4C E0 00.
    Telling the user to paste that is an instruction that cannot succeed."""
    root, application, _ = app
    import src.hardware.pressure.bluetooth_windows as btw

    monkeypatch.setattr(btw, "get_host_bluetooth_mac", lambda: "00E04C000001")
    _open_setup(root, application)

    texts = " ".join(_texts(application))
    assert "Windows cannot accept these bytes" in texts, (
        f"untypeable PIN was not flagged in the GUI; got: {texts[:400]}"
    )


def test_ascii_pin_is_still_offered_for_pasting(app, monkeypatch):
    """The lucky case must keep working -- the PIN card is a real fallback,
    not dead weight."""
    root, application, _ = app
    import src.hardware.pressure.bluetooth_windows as btw

    # Reverses to printable ASCII 'ABCDEF'.
    monkeypatch.setattr(btw, "get_host_bluetooth_mac", lambda: "464544434241")
    _open_setup(root, application)

    texts = " ".join(_texts(application))
    assert "Plain ASCII" in texts, (
        f"typeable PIN should be offered for pasting; got: {texts[:400]}"
    )


def test_copy_pin_warns_instead_of_pasting_a_truncated_pin(app, monkeypatch):
    """Windows clipboard text ends at the first NUL, so this PIN pastes as a
    single character. The GUI must say so rather than appear to succeed."""
    root, application, _ = app
    import src.hardware.pressure.bluetooth_windows as btw

    monkeypatch.setattr(btw, "get_host_bluetooth_mac", lambda: "00E04C000001")
    _open_setup(root, application)

    rect = getattr(application, "setup_pin_copy_rect", None)
    assert rect, "no Copy PIN button on the Setup page"
    _click(root, application, rect)

    feedback = str(application.copy_feedback or "")
    assert "cannot" in feedback.lower() or "Pair Board" in feedback, (
        f"Copy PIN silently pasted a truncated PIN; feedback was {feedback!r}"
    )


def test_repeated_clicks_do_not_stack_pairing_attempts(app, monkeypatch):
    """Each confirm starts a ~10s Bluetooth inquiry on a worker thread. A real
    run showed an impatient user stacking seven of them on one radio, which
    produced interleaved, contradictory log output as they fought each other.

    The guard now lives in the flow, and the modal additionally hides its
    action button while searching -- so there is nothing to double-click.
    """
    import threading
    import time

    root, application, _ = app
    import src.hardware.pressure as pressure
    from src.hardware.pressure.pairing_flow import PairingFlow

    started = []
    release = threading.Event()

    def _slow_pair(**kwargs):
        started.append(1)
        release.wait(timeout=5)
        return {"success": True, "message": "paired", "address": "001E35AABBCC",
                "radio_address": "38FC983BB4DC", "method": "callback",
                "boards_seen": 1}

    monkeypatch.setattr(pressure, "native_pairing_available", lambda: True)
    monkeypatch.setattr(
        "src.hardware.pressure.pairing_flow.make_pairing_flow",
        lambda target_count=1: PairingFlow(target_count=target_count,
                                           pair_fn=_slow_pair),
    )

    _open_setup(root, application)
    _click(root, application, application.setup_pair_rect)
    assert application.show_pairing_modal

    # Hammer the action button: the first click confirms SYNC, the rest must
    # not launch more searches.
    rect = application.pairing_action_rect
    assert rect
    for _ in range(5):
        _click(root, application, rect)
        time.sleep(0.02)

    for _ in range(20):
        if started:
            break
        time.sleep(0.05)
        root.update()

    assert len(started) == 1, (
        f"{len(started)} concurrent pairing attempts were started"
    )

    release.set()
    for _ in range(40):
        if application.pairing_flow.status()["phase"] == "done":
            break
        time.sleep(0.05)
        root.update()

    assert application.pairing_flow.status()["phase"] == "done", (
        "flow never completed; the prompt would be stuck"
    )
