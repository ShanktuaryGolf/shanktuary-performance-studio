"""Quad-view layout: masks and chips must be sized to their content.

Three reported clipping bugs, all the same root cause — a hardcoded pixel
size that no longer matched the text it was meant to hold:

1. Sidebar shot-card values ("06:24 PM") sat 24px from the card edge and
   read as clipped against the border.
2. The Q2 cleanup mask was a fixed 175x77 block, far wider and taller than
   the "DYNAMIC LOFT"/"ATTACK ANGLE" labels it clears. It reached into the
   bottom-left quadrant and erased the top of the ball-flight arc, so the
   trajectory looked cut off mid-curve.
3. The "DIRECTION ESTIMATE" chip reserved 116*fs (~214px) for ~258px of
   text, so the centred label spilled ~22px past each end of its own badge
   — colliding with "IMPACT LOCATION" and hanging outside the box.
"""

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")

REAL_HISTORY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "shanktuary_session_history.json",
)


@pytest.fixture
def quad(tmp_path, monkeypatch):
    """Quad view rendered from a COPY of the real history (never the original)."""
    import shanktuary_performance_studio as studio

    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    hist = tmp_path / "history.json"
    if os.path.exists(REAL_HISTORY):
        shutil.copy2(REAL_HISTORY, hist)
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(hist))

    from src.ui import ShanktuaryDesktopApp

    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("1915x1111")
    app = ShanktuaryDesktopApp(root)

    shots = app.session_shots
    if not shots:
        pytest.skip("no shots available to render the quad view")
    app.selected_shot_index = len(shots) - 1
    app.current_shot = shots[-1]
    app.view_mode = 1
    app.draw_screen()
    root.update()

    yield root, app
    try:
        root.destroy()
    except tk.TclError:
        pass


def _text_item(canvas, wanted, contains=False):
    for item in canvas.find_all():
        if canvas.type(item) != "text":
            continue
        text = canvas.itemcget(item, "text")
        if (wanted in text) if contains else (text == wanted):
            return item, canvas.bbox(item), text
    return None, None, None


def test_impact_caption_and_estimate_chip_do_not_touch(quad):
    _root, app = quad
    c = app.canvas

    _ci, cap_bb, _ct = _text_item(c, "IMPACT LOCATION")
    assert cap_bb, "IMPACT LOCATION was not drawn"

    chip = None
    for item in c.find_all():
        if c.type(item) != "text":
            continue
        text = c.itemcget(item, "text")
        if "ESTIMATE" in text and text != "IMPACT LOCATION":
            chip = (item, c.bbox(item), text)
    assert chip, "no state chip was drawn"

    gap = chip[1][0] - cap_bb[2]
    assert gap >= 8, (
        f"{chip[2]!r} starts {gap}px after IMPACT LOCATION — they collide"
    )


def test_the_estimate_chip_box_contains_its_own_label(quad):
    """The badge must wrap the text, not be overflowed by it."""
    _root, app = quad
    c = app.canvas

    chip = None
    for item in c.find_all():
        if c.type(item) != "text":
            continue
        text = c.itemcget(item, "text")
        if "ESTIMATE" in text and text != "IMPACT LOCATION":
            chip = (item, c.bbox(item), text)
    assert chip, "no state chip"
    _item, (tx1, ty1, tx2, ty2), label = chip

    # Find the chip's own background rect (the one straddling the label).
    best = None
    for item in c.find_all():
        if c.type(item) != "rectangle":
            continue
        co = c.coords(item)
        if len(co) != 4:
            continue
        rx1, ry1, rx2, ry2 = co
        if rx1 <= tx1 + 4 and rx2 >= tx2 - 4 and ry1 <= ty1 + 6 and ry2 >= ty2 - 6:
            width = rx2 - rx1
            if best is None or width < best[0]:
                best = (width, co)

    assert best, (
        f"the {label!r} chip has no background box wide enough to hold it "
        f"(text spans {tx1}..{tx2})"
    )


def test_q2_mask_does_not_erase_the_trajectory_arc(quad):
    """The ball-flight arc must not be painted over after it is drawn."""
    _root, app = quad
    c = app.canvas
    order = list(c.find_all())

    traj = None
    for item in order:
        if c.type(item) != "line":
            continue
        coords = c.coords(item)
        # The arc is a long multi-point gold polyline in the lower half.
        if len(coords) >= 20 and c.itemcget(item, "fill").upper() in (
                "#E3BC70", "#D4A24F"):
            ys = coords[1::2]
            if min(ys) > 600:
                traj = item
                break
    if traj is None:
        pytest.skip("no trajectory arc in this render")

    tb = c.bbox(traj)
    idx = order.index(traj)
    covering = []
    for item in order[idx + 1:]:
        if c.type(item) != "rectangle":
            continue
        bb = c.bbox(item)
        if not bb:
            continue
        if bb[0] < tb[2] and bb[2] > tb[0] and bb[1] < tb[3] and bb[3] > tb[1]:
            covering.append((bb, c.itemcget(item, "fill")))

    assert not covering, (
        f"rectangles painted over the trajectory arc {tb}: {covering}"
    )


def test_shot_card_values_clear_the_card_edge(quad):
    """Card values need real padding, not 4px of breathing room."""
    _root, app = quad
    c = app.canvas

    cards = getattr(app, "design_shot_card_rects", [])
    if not cards:
        pytest.skip("no shot cards rendered")
    card_right = cards[0][2]

    checked = 0
    for item in c.find_all():
        if c.type(item) != "text":
            continue
        text = c.itemcget(item, "text")
        if not (text.endswith(" PM") or text.endswith(" AM")):
            continue
        bb = c.bbox(item)
        if not bb or bb[0] > 320:
            continue
        # Only the selected card's right-aligned value column.
        if bb[2] < card_right - 60:
            continue
        checked += 1
        margin = card_right - bb[2]
        # card_right is the OUTER hit rect; the visible card body is inset a
        # few px inside it, so this margin is a slight over-estimate of what
        # the eye sees. 19px looked crowded against the border; >=22 reads
        # as deliberate padding.
        assert margin >= 22, (
            f"{text!r} sits {margin}px from the card edge — reads as clipped"
        )
    if not checked:
        pytest.skip("no right-aligned time value on screen")
