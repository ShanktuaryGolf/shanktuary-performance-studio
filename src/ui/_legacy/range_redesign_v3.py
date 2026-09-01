"""Final Range simplification: continuous dark-green field below the metrics.

Keeps v2's perspective grid, shot flights, landing dispersion, metrics, and
WebGPU action. It removes the twilight-sky/mountain scene entirely so the area
between the metric ribbon and the range corridor simply uses the same dark
range-green material as the rough edges.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageOps, ImageTk

import range_redesign_v2 as v2


TOP_GREEN = "#081A15"
BOTTOM_GREEN = v2.GROUND
FAIRWAY = v2.FAIRWAY
TEAL = v2.TEAL_LINE


def _rgb(col):
    return tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))


def _green_scene(app, w, h, horizon_rel):
    """One continuous green range surface with a slightly raised center lane."""
    key = (int(w), int(h), int(horizon_rel), "range-v3-green")
    if getattr(app, "_range_v3_bg_key", None) == key:
        return app._range_v3_bg_img

    iw, ih = max(1, int(w)), max(1, int(h))
    horizon = max(80, min(ih - 120, int(horizon_rel)))
    img = Image.new("RGB", (iw, ih), _rgb(TOP_GREEN))
    d = ImageDraw.Draw(img, "RGBA")

    # Very restrained vertical material shift. The entire viewport remains
    # green; there is deliberately no separate sky band or horizon scenery.
    ta, tb = _rgb(TOP_GREEN), _rgb(BOTTOM_GREEN)
    for y in range(0, ih, 3):
        t = y / max(1, ih - 1)
        col = tuple(round(ta[i] + (tb[i] - ta[i]) * t) for i in range(3))
        d.rectangle((0, y, iw, min(ih, y + 3)), fill=col)

    # Preserve the perspective center corridor only below the existing v2
    # horizon. Above it, the same rough-green material simply continues up to
    # the metric ribbon, which is the requested simplification.
    cx = iw / 2
    far_half = iw * .17
    near_half = iw * .54
    d.polygon(
        [
            (cx - far_half, horizon),
            (cx + far_half, horizon),
            (cx + near_half, ih),
            (cx - near_half, ih),
        ],
        fill=_rgb(FAIRWAY) + (255,),
    )

    # A few near-invisible range-surface contours on the rough keep the field
    # from becoming a dead rectangle without reintroducing scenic clutter.
    for side in (-1, 1):
        for band in range(6):
            yy = horizon + 58 + band * max(30, (ih - horizon) / 8)
            if yy >= ih:
                continue
            if side < 0:
                pts = [(0, yy + 5), (iw * .11, yy), (iw * .22, yy + 4), (cx - far_half - 18, yy + 1)]
            else:
                pts = [(cx + far_half + 18, yy + 1), (iw * .78, yy + 4), (iw * .89, yy), (iw, yy + 5)]
            d.line(pts, fill=(88, 183, 180, 9), width=1)

    try:
        noise = Image.effect_noise((iw, ih), 8).convert("L")
        noise_col = ImageOps.colorize(noise, black="#06100D", white="#153129")
        img = Image.blend(img, noise_col, .012)
    except Exception:
        pass

    photo = ImageTk.PhotoImage(img)
    app._range_v3_bg_img = photo
    app._range_v3_bg_key = key
    return photo


def draw_range(*args, **kwargs):
    """Run the accepted v2 Range geometry over the simplified green field."""
    original = v2._scene_background
    v2._scene_background = _green_scene
    try:
        return v2.draw_range(*args, **kwargs)
    finally:
        v2._scene_background = original
