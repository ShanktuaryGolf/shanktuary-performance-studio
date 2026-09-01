"""The Quad view's impact panel must not paint over its own labels.

Reported as "the picture of the iron on the bottom right is blocking text".

Three separate faults were behind it:

1. The redesign hid production's clubface with an opaque rectangle sized from
   its own (larger) image, which erased the panel header and both disclaimer
   lines. Trimming the cover to spare them left a sliver of the old clubhead
   visible instead -- the cover-and-repaint approach cannot win. Production's
   face asset is now suppressed for the duration of the render, so there is
   nothing to cover.

2. The face was sized from quadrant height alone, so it reached back across
   the VERTICAL / HORIZONTAL readouts and down over the footer. It is now
   budgeted against the free space in both axes.

3. The "DIRECTION ESTIMATE" badge used a hardcoded 118px offset and sat on top
   of "IMPACT LOCATION". Production measures the caption at the same spot and
   documents why; the redesign now does too.

These are rendering assertions -- they drive the real app and read canvas
geometry, because occlusion is invisible to a unit test on the helpers.
"""
import pytest


def _quad_app():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("no display")
    root.geometry("1600x950")
    from src.ui.desktop import ShanktuaryDesktopApp

    app = ShanktuaryDesktopApp(root)
    app.view_mode = 1  # Quad
    app.draw_screen()
    root.update_idletasks()
    return root, app


# A shape this large is the panel background or a full-quadrant wash, not a
# decorative graphic. Panels are painted before their own labels, so counting
# them produces a false positive on every string in the panel.
_PANEL_FILL_W = 500
_PANEL_FILL_H = 320


def _panel_items(app):
    """(kind, z, bbox, text) for the bottom-right quadrant only."""
    ids = list(app.canvas.find_all())
    out = []
    for item in ids:
        box = app.canvas.bbox(item)
        if not box or box[0] < 900 or box[1] < 500:
            continue
        kind = app.canvas.type(item)
        text = app.canvas.itemcget(item, "text") if kind == "text" else ""
        out.append((kind, ids.index(item), box, text))
    return out


def _occluders(items):
    """Graphics that could plausibly hide a label -- backgrounds excluded."""
    out = []
    for kind, z, b, _ in items:
        if kind not in ("rectangle", "image"):
            continue
        if (b[2] - b[0]) >= _PANEL_FILL_W and (b[3] - b[1]) >= _PANEL_FILL_H:
            continue  # panel background
        out.append((z, b))
    return out


def test_only_one_clubface_is_drawn():
    """Production's face plus the redesign's is what forced the opaque cover
    in the first place. Suppressing the asset should leave exactly one."""
    root, app = _quad_app()
    try:
        faces = [b for kind, _, b, _ in _panel_items(app)
                 if kind == "image" and (b[2] - b[0]) > 150]
        assert len(faces) == 1, f"expected 1 clubface, found {len(faces)}: {faces}"
    finally:
        root.destroy()


def test_the_clubface_clears_the_readout_column():
    """VERTICAL / HORIZONTAL values sit left of the graphic; the face must not
    reach back over them."""
    root, app = _quad_app()
    try:
        items = _panel_items(app)
        faces = [b for kind, _, b, _ in items
                 if kind == "image" and (b[2] - b[0]) > 150]
        assert faces, "no clubface image in the panel"
        face_left = min(b[0] for b in faces)

        readout = [(b, t) for kind, _, b, t in items
                   if kind == "text" and t and b[0] < 1100 and 560 < b[1] < 800]
        assert readout, "impact readout labels not found"

        clashes = [f"{t[:24]!r} ends x{b[2]} but face starts x{face_left}"
                   for b, t in readout if b[2] > face_left]
        assert not clashes, "clubface overlaps the readout: " + "; ".join(clashes)
    finally:
        root.destroy()


def test_the_footer_disclaimer_is_never_covered():
    """'Nova measures ball flight, not face contact' is an honesty label about
    estimated data. Decoration must never be what hides it."""
    root, app = _quad_app()
    try:
        items = _panel_items(app)
        footer = [(z, b) for kind, z, b, t in items
                  if kind == "text" and "Nova measures" in t]
        assert footer, "the Nova disclaimer is missing from the Quad view"

        for tz, tb in footer:
            for z, cb in _occluders(items):
                if z <= tz:
                    continue
                ox = min(tb[2], cb[2]) - max(tb[0], cb[0])
                oy = min(tb[3], cb[3]) - max(tb[1], cb[1])
                assert not (ox > 40 and oy > 8), f"disclaimer covered by {cb}"
    finally:
        root.destroy()


def test_the_estimate_badge_does_not_sit_on_the_caption():
    """A hardcoded offset put "DIRECTION ESTIMATE" on top of "IMPACT
    LOCATION". The badge must be placed from the measured caption width."""
    root, app = _quad_app()
    try:
        items = _panel_items(app)
        caption = next((b for kind, _, b, t in items
                        if kind == "text" and t == "IMPACT LOCATION"), None)
        badge = next((b for kind, _, b, t in items
                      if kind == "text" and "ESTIMATE" in t and t != "IMPACT LOCATION"),
                     None)
        if caption is None or badge is None:
            pytest.skip("panel state does not show a caption/badge pair")
        assert badge[0] >= caption[2], (
            f"badge starts x{badge[0]} but caption runs to x{caption[2]}"
        )
    finally:
        root.destroy()


# Production draws its own badge and readout, then the redesign paints its
# replacement on top. Those two are intentionally superseded; every other
# label must survive.
_SUPERSEDED = {"ESTIMATE", "DIR EST"}


def test_no_panel_label_is_substantially_covered():
    """Catch-all: nothing drawn later may bury a label in this panel."""
    root, app = _quad_app()
    try:
        items = _panel_items(app)
        texts = [(z, b, t) for kind, z, b, t in items
                 if kind == "text" and t and t.strip() not in _SUPERSEDED]
        covers = _occluders(items)

        buried = []
        for tz, tb, label in texts:
            for cz, cb in covers:
                if cz <= tz:
                    continue
                ox = min(tb[2], cb[2]) - max(tb[0], cb[0])
                oy = min(tb[3], cb[3]) - max(tb[1], cb[1])
                if ox > (tb[2] - tb[0]) * 0.5 and oy > (tb[3] - tb[1]) * 0.5:
                    buried.append(f"{label[:28]!r} under {cb}")
        assert not buried, "panel text is covered: " + "; ".join(buried)
    finally:
        root.destroy()
