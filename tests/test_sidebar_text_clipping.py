"""Sidebar text must not be clipped by later paint passes.

Two bugs from the layered renderer stack (production -> v4 -> v13 -> v14 ->
v17, each painting over the last):

1. A v4-era sidebar wordmark drew "SHANKTUARY / PERFORMANCE GOLF" at y=19/43.
   The 52px top header is painted over that area, so only the clipped bottom
   sliver of "PERFORMANCE GOLF" showed under the logo.

2. The session label was painted by v4, then v13 repainted a stale "+"
   button on top of it and v14 wiped a rectangle over the same row — eating
   the tail, so "Session 1 - 7 Iron" rendered as "Session 1 - 7 Iro".

The fix is ordering: the label is painted LAST, after every covering pass.
These tests assert the rendered result rather than the drawing calls.
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

    # Redirect session persistence to a throwaway file. Without this, a test
    # that clicks "+" writes new sessions into the USER'S real
    # shanktuary_session_history.json — which is exactly how six junk
    # "Session N - 7 Iron" entries with 0 shots ended up in it.
    import shanktuary_performance_studio as studio

    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))

    from src.ui import ShanktuaryDesktopApp

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("1916x1200")
    application = ShanktuaryDesktopApp(root)
    root.update()
    yield root, application
    try:
        root.destroy()
    except tk.TclError:
        pass


def _session_label(canvas):
    """The current session label lives in the expanded workspace header."""
    items = canvas.find_withtag("session-label")
    return (items[0], canvas.bbox(items[0])) if items else (None, None)


def _covering(canvas, item, bbox):
    """Items painted AFTER `item` that overlap its bbox."""
    order = list(canvas.find_all())
    idx = order.index(item)
    out = []
    for other in order[idx + 1:]:
        try:
            other_box = canvas.bbox(other)
        except tk.TclError:
            continue
        if not other_box:
            continue
        if (other_box[0] < bbox[2] and other_box[2] > bbox[0]
                and other_box[1] < bbox[3] and other_box[3] > bbox[1]):
            out.append((canvas.type(other), other_box))
    return out


@pytest.mark.parametrize("name", [
    "Session 1 - 7 Iron",
    "Session 12 - Driver",
    "S 3 - PW",
])
def test_session_label_is_not_clipped_by_later_passes(app, name):
    root, application = app
    application.get_active_session()["name"] = name
    application.draw_screen()
    root.update()

    item, bbox = _session_label(application.canvas)
    assert item is not None, "no session label was drawn"

    shown = application.canvas.itemcget(item, "text")
    assert shown == "Session: " + name, f"label shows {shown!r}, expected the full {name!r}"

    covering = _covering(application.canvas, item, bbox)
    assert not covering, f"label is painted over by {covering}"


def test_a_long_session_name_ellipsizes_instead_of_running_under_controls(app):
    root, application = app
    long_name = "A Very Long Session Name That Should Ellipsize " * 4
    application.get_active_session()["name"] = long_name
    application.draw_screen()
    root.update()

    item, bbox = _session_label(application.canvas)
    shown = application.canvas.itemcget(item, "text")
    assert shown.endswith("…"), f"long name was not ellipsized: {shown!r}"
    assert shown != long_name
    assert not _covering(application.canvas, item, bbox)


def test_no_clipped_wordmark_behind_the_header(app):
    root, application = app
    application.draw_screen()
    root.update()
    canvas = application.canvas
    brand = [item for item in canvas.find_all() if canvas.type(item) == "text"
             and canvas.itemcget(item, "text") == "SHANKTUARY"]
    assert len(brand) == 1
    box = canvas.bbox(brand[0])
    assert 0 <= box[0] < box[2] <= 260
    assert not _covering(canvas, brand[0], box)


def test_new_session_button_survives_and_stays_clear_of_the_label(app):
    """Removing the duplicate + must not break the real one."""
    root, application = app
    application.get_active_session()["name"] = "Session 1 - 7 Iron"
    application.draw_screen()
    root.update()

    rect = application.sidebar_new_sess_btn_rect
    assert rect, "new-session button rect is missing"

    _item, bbox = _session_label(application.canvas)
    assert rect[0] > bbox[2], (
        f"+ button at x={rect[0]} overlaps the label ending at x={bbox[2]}"
    )

    before = len(application.sessions)

    class _Evt:
        pass

    evt = _Evt()
    evt.x = (rect[0] + rect[2]) // 2
    evt.y = (rect[1] + rect[3]) // 2
    application.handle_mouse_press(evt)
    root.update()

    assert len(application.sessions) == before + 1, "+ button no longer works"


def test_session_picker_has_no_legacy_grey_slab(app):
    root, application = app
    application.draw_screen()
    root.update()
    canvas = application.canvas
    rect = application.sidebar_session_btn_rect
    item, box = _session_label(canvas)
    assert item is not None and rect
    assert rect[0] <= box[0] and box[2] <= rect[2]
    # The concept picker is a transparent header label, not the retired card.
    for other in canvas.find_all():
        if canvas.type(other) == "rectangle" and canvas.coords(other) == list(rect):
            assert canvas.itemcget(other, "fill").lower() not in ("#1d2127", "#16191e")
