"""Layout guard for the full-screen board-assignment prompt.

The wizard is read from across a room while the user is standing on a board,
so the one thing that must never happen is text landing on top of other text.

The bug this locks in: the layout advanced by the FONT'S POINT SIZE as if it
were a pixel height. A 52pt headline reserved 52px for a ~70px line, so
"Both boards assigned" was painted straight through its own subtitle, and the
"kg" unit ran through the weight it belonged to.
"""
import sys

import pytest

sys.path.insert(0, "/home/sean/sps")

tk = pytest.importorskip("tkinter")


class _FakeWiz:
    threshold = 5.0

    def __init__(self, phase, wa, wb):
        self._st = {"phase": phase, "board_a_weight": wa,
                    "board_b_weight": wb, "message": ""}
        self.board_a, self.board_b = "A", "B"
        self.left_board = "A" if phase == "complete" else None
        self.right_board = "B" if phase == "complete" else None

    def get_status(self):
        return self._st


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


@pytest.fixture
def restore_pressure_manager():
    """The modal reads obs_server.pressure_manager, a module global.

    Swapping in a stub without putting the real one back leaves every later
    test in the session talking to a fake manager -- which silently broke the
    Setup page's SHOT SOURCE buttons when the full suite ran in one process.
    """
    import obs_server
    sentinel = object()
    original = getattr(obs_server, "pressure_manager", sentinel)
    yield obs_server
    if original is sentinel:
        try:
            del obs_server.pressure_manager
        except AttributeError:
            pass
    else:
        obs_server.pressure_manager = original


@pytest.mark.parametrize("phase,wa,wb", [
    ("waiting_left", 0.0, 0.0),
    ("waiting_right", 34.0, 0.0),
    ("complete", 10.0, 2.0),
])
@pytest.mark.parametrize("size", [(1900, 970), (1280, 720), (1100, 720)])
def test_no_text_overlaps_or_clips(tk_root, restore_pressure_manager,
                                   phase, wa, wb, size):
    import shanktuary_performance_studio as studio

    obs_server = restore_pressure_manager
    w, h = size

    canvas = tk.Canvas(tk_root, width=w, height=h)
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.canvas = canvas
    app.root = tk_root
    obs_server.pressure_manager = type(
        "PM", (), {"assignment_wizard": _FakeWiz(phase, wa, wb)})()

    canvas.delete("all")
    studio.ShanktuaryApp.draw_board_assign_modal(app, w, h)
    tk_root.update_idletasks()

    texts = []
    for item in canvas.find_all():
        if canvas.type(item) != "text":
            continue
        bb = canvas.bbox(item)
        if bb:
            texts.append((canvas.itemcget(item, "text"), bb))

    assert texts, "modal painted no text at all"

    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            (t1, a), (t2, b) = texts[i], texts[j]
            overlap = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
            assert not overlap, (
                f"{phase} @ {w}x{h}: {t1!r} {a} overlaps {t2!r} {b}"
            )

    for text, bb in texts:
        assert bb[1] >= 0 and bb[3] <= h and bb[0] >= 0 and bb[2] <= w, (
            f"{phase} @ {w}x{h}: {text!r} {bb} falls outside the window"
        )

    canvas.destroy()
