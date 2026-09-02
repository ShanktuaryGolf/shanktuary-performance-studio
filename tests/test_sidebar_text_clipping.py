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
    """The bold session label inside the sidebar session button."""
    for item in reversed(canvas.find_all()):
        if canvas.type(item) != "text":
            continue
        bbox = canvas.bbox(item)
        if not bbox:
            continue
        if (70 <= bbox[0] <= 95 and 70 <= bbox[1] <= 100
                and "bold" in canvas.itemcget(item, "font")):
            return item, bbox
    return None, None


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
    assert shown == name, f"label shows {shown!r}, expected the full {name!r}"

    covering = _covering(application.canvas, item, bbox)
    assert not covering, f"label is painted over by {covering}"


def test_a_long_session_name_ellipsizes_instead_of_running_under_controls(app):
    root, application = app
    long_name = "A Very Long Session Name That Should Ellipsize"
    application.get_active_session()["name"] = long_name
    application.draw_screen()
    root.update()

    item, bbox = _session_label(application.canvas)
    shown = application.canvas.itemcget(item, "text")
    assert shown.endswith("…"), f"long name was not ellipsized: {shown!r}"
    assert shown != long_name
    assert not _covering(application.canvas, item, bbox)


def test_no_clipped_wordmark_behind_the_header(app):
    """The v4 sidebar wordmark sat under the 52px header and showed a sliver."""
    root, application = app
    application.draw_screen()
    root.update()

    canvas = application.canvas
    for item in canvas.find_all():
        if canvas.type(item) != "text":
            continue
        text = canvas.itemcget(item, "text")
        if text not in ("PERFORMANCE GOLF", "SHANKTUARY"):
            continue
        bbox = canvas.bbox(item)
        if not bbox or bbox[0] > 300:
            continue          # header brand lives further right; fine
        # Anything in the sidebar column that starts above the 52px header
        # boundary is the stale wordmark showing through.
        assert bbox[1] >= 52, (
            f"{text!r} at y={bbox[1]} is clipped by the 52px header"
        )


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


def test_session_button_uses_the_sidebar_palette_not_the_old_grey(app):
    """The repaint must use the sidebar's own colour family.

    Filling this button with theme.SURFACE_2 (#1D2127, a grey from the older
    dark theme) against the redesigned blue-teal sidebar (#091B24) rendered
    as a black box. Assert the fill stays in the sidebar's family: close to
    the surrounding background, and never a neutral grey.
    """
    root, application = app
    application.get_active_session()["name"] = "Session 1 - 7 Iron"
    application.draw_screen()
    root.update()

    canvas = application.canvas
    rect = application.sidebar_session_btn_rect

    fills = []
    for item in canvas.find_all():
        if canvas.type(item) != "rectangle":
            continue
        if [int(v) for v in canvas.coords(item)] == [int(v) for v in rect]:
            fill = canvas.itemcget(item, "fill")
            if fill:
                fills.append(fill)
    assert fills, "session button face is never painted"

    fill = fills[-1]
    r = int(fill[1:3], 16)
    g = int(fill[3:5], 16)
    b = int(fill[5:7], 16)

    # The sidebar palette is blue-teal: blue clearly exceeds red. A neutral
    # grey (r ~= g ~= b) is the bug.
    assert b > r + 6, (
        f"session button fill {fill} is not a sidebar blue-teal "
        f"(r={r} g={g} b={b}) — this renders as a black/grey box"
    )

