"""The approved full-width labeled navigation and studio header."""

import math
from functools import lru_cache

import theme

from . import tokens as T

RAIL = 272
HEADER = 176
TITLES = {
    13: "Session history",
    14: "Tools & outputs",
    12: "Session overview",
    9: "Shot analysis",
    1: "Club analysis",
    4: "Session table",
    5: "Numbers",
    2: "Range",
    3: "Dispersion",
    6: "My bag",
    7: "Club fitting",
    8: "Swing lab",
    11: "Shanktuary Index",
    10: "Studio setup",
    0: "Floor projection",
}
GROUPS = [
    (
        "SESSION",
        [(12, "Overview"), (1, "Club"), (4, "Table"), (5, "Numbers")],
    ),
    ("PRACTICE", [(2, "Range"), (11, "Index")]),
    ("TOOLS", [(3, "Dispersion"), (6, "Bag"), (7, "Fit"), (8, "Lab"), (10, "Setup")]),
]


def _brand_mark_pixels(scale=1):
    """Resample the approved mockup's ribbon directly at device resolution."""
    from PIL import Image, ImageOps

    from .asset_paths import asset_path

    with Image.open(asset_path("studio_brand_mark.png")) as source:
        pixels = source.convert("RGBA")
    bounds = pixels.getchannel("A").getbbox()
    if bounds:
        pixels = pixels.crop(bounds)
    return ImageOps.contain(pixels, (max(1, round(43 * scale)), max(1, round(64 * scale))),
                            Image.Resampling.LANCZOS)


def paint_brand_mark(canvas):
    """Keep the small gold mark antialiased at 100–200% UI scaling.

    This image is sized from its high-resolution source for each display scale,
    rather than enlarging the 43px preview through ScaledCanvas a second time.
    """
    import tkinter as tk

    from PIL import ImageTk

    real = getattr(canvas, "_canvas", canvas)
    if not isinstance(real, tk.Canvas):
        return None  # Recorder canvases have no Tcl image interpreter.
    scale = getattr(real, "ui_scale", 1)
    cache = getattr(real, "_concept_brand_cache", None)
    if cache is None:
        cache = real._concept_brand_cache = {}
    if scale not in cache:
        cache[scale] = ImageTk.PhotoImage(_brand_mark_pixels(scale), master=real)
    # Bypass only ScaledCanvas's image upsampling; coordinates still use its
    # exact scale, and normal canvas bbox/hit geometry remains unchanged.
    options = {"image": cache[scale], "anchor": "center", "tags": "studio-brand-mark"}
    if hasattr(real, "create_device_image"):
        return real.create_device_image(44 * scale, 60 * scale, **options)
    return tk.Canvas._create(real, "image", (44 * scale, 60 * scale), options)


def text(c, x, y, value, size=12, color=T.TEXT, bold=False, anchor="w", **kw):
    return c.create_text(
        x,
        y,
        text=value,
        fill=color,
        font=(theme.ui_font(), size, "bold" if bold else "normal"),
        anchor=anchor,
        **kw,
    )


def veil(c, w, h):
    """Smooth modal dimming rather than a visible stipple/checker pattern."""
    import tkinter as tk
    real = getattr(c, "_canvas", c)
    if not isinstance(real, tk.Canvas):
        return c.create_rectangle(0, 0, w, h, fill=T.PAGE_BG, outline="", stipple="gray75")
    from PIL import Image, ImageTk
    key = (max(1, round(w)), max(1, round(h)))
    cached = getattr(real, "_concept_veil", None)
    if cached is None or cached[0] != key:
        photo = ImageTk.PhotoImage(Image.new("RGBA", key, (3, 20, 30, 205)), master=real)
        real._concept_veil = (key, photo)
    return c.create_image(0, 0, image=real._concept_veil[1], anchor="nw")


def panel(
    c, x0, y0, x1, y1, fill=T.SURFACE, outline=T.HAIRLINE, r=12, width=1, **kwargs
):
    """Softly lit rounded material, with a vector outline for crisp scaling."""
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    raster = False
    real = getattr(c, "_canvas", c)
    # Recorder canvases and headless tests use the same vector fallback.
    import tkinter as tk

    if isinstance(real, tk.Canvas) and fill and x1 > x0 and y1 > y0:
        from collections import OrderedDict

        from PIL import Image, ImageDraw, ImageTk

        key = (round(x1 - x0), round(y1 - y0), fill, round(r), outline, width)
        cache = getattr(real, "_concept_material_cache", None)
        if cache is None:
            cache = OrderedDict()
            real._concept_material_cache = cache
        photo = cache.get(key)
        if photo is None:
            iw, ih = max(1, key[0]), max(1, key[1])
            rgb = (
                tuple(int(fill[i : i + 2], 16) for i in (1, 3, 5))
                if fill.startswith("#") and len(fill) == 7
                else (6, 35, 44)
            )
            # Small material tile is upsampled once, avoiding per-frame work.
            tile = Image.new("RGB", (32, 32))
            pixels = []
            for yy in range(32):
                for xx in range(32):
                    lift = max(0, 1 - yy / 31) * max(0.15, 1 - xx / 42) * 0.20
                    pixels.append(
                        tuple(
                            round(v + (target - v) * lift)
                            for v, target in zip(rgb, (15, 89, 91))
                        )
                    )
            tile.putdata(pixels)
            material = tile.resize((iw * 2, ih * 2), Image.Resampling.BILINEAR).convert("RGBA")
            mask = Image.new("L", (iw * 2, ih * 2), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (1, 1, iw * 2 - 2, ih * 2 - 2), radius=max(0, r * 2), fill=255
            )
            material.putalpha(mask)
            if outline:
                ImageDraw.Draw(material).rounded_rectangle(
                    (1, 1, iw * 2 - 2, ih * 2 - 2), radius=max(0, r * 2),
                    outline=outline, width=max(1, round(width * 2)),
                )
            material = material.resize((iw, ih), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(material, master=real)
            cache[key] = photo
            while len(cache) > 128:
                cache.popitem(last=False)
        # ScaledCanvas retains the image for this frame through its image API.
        c.create_image(x0, y0, image=photo, anchor="nw")
        raster = True
    points = []
    for cx, cy, start in ((x0+r, y0+r, 180), (x1-r, y0+r, 270),
                          (x1-r, y1-r, 0), (x0+r, y1-r, 90)):
        for step in range(9):
            angle = math.radians(start + step * 90 / 8)
            points.extend((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return c.create_polygon(
        *points, smooth=False, fill="" if raster else fill,
        outline="" if raster else outline, width=width, **kwargs,
    )


def icon(c, kind, x, y, color=T.TEXT):
    line = lambda *p: c.create_line(*p, fill=color, width=1.6)
    if kind == 12:
        line(x - 4, y - 1, x + 8, y - 13, x + 21, y - 1)
        line(x - 1, y - 3, x - 1, y + 12, x + 18, y + 12, x + 18, y - 3)
        line(x + 5, y + 12, x + 5, y + 3, x + 11, y + 3, x + 11, y + 12)
    elif kind == 9:
        for i, h in enumerate((8, 15, 23)):
            c.create_rectangle(
                x + i * 7, y + 11 - h, x + i * 7 + 3, y + 11, fill=color, outline=""
            )
    elif kind == 4:
        c.create_rectangle(x - 2, y - 10, x + 20, y + 12, outline=color, width=1.4)
        for d in (0, 7):
            line(x - 2, y + d, x + 20, y + d)
        line(x + 5, y - 10, x + 5, y + 12)
    elif kind == 5:
        text(c, x + 8, y, "Σ", 26, color, anchor="center")
    elif kind in (3, 11):
        for r in (11, 7, 2):
            c.create_oval(x + 8 - r, y - r, x + 8 + r, y + r, outline=color, width=1.4)
    elif kind == 2:
        line(x + 2, y + 12, x + 2, y - 13)
        line(x + 2, y - 13, x + 19, y - 7, x + 2, y - 2)
        line(x - 3, y + 12, x + 9, y + 12)
    elif kind == 1:
        line(x - 1, y + 7, x + 10, y + 11, x + 20, y - 14)
        line(x - 1, y + 7, x - 2, y + 1, x + 10, y + 5)
    elif kind == 7:
        for j, dx in enumerate((4, 13, 7)):
            yy = y - 10 + j * 10
            line(x - 3, yy, x + 22, yy)
            c.create_oval(
                x + dx - 2, yy - 3, x + dx + 3, yy + 3, fill=T.RAIL_BG, outline=color
            )
    elif kind == 8:
        line(x + 3, y - 12, x + 13, y - 12)
        line(
            x + 5,
            y - 12,
            x + 5,
            y - 4,
            x - 2,
            y + 10,
            x + 20,
            y + 10,
            x + 11,
            y - 4,
            x + 11,
            y - 12,
        )
    elif kind == 6:
        line(x, y - 1, x + 16, y - 1, x + 16, y + 12, x, y + 12, x, y - 1)
        line(x + 4, y - 1, x + 4, y - 13, x + 9, y - 16)
        line(x + 10, y - 1, x + 12, y - 12, x + 17, y - 14)
    else:
        c.create_oval(x - 3, y - 12, x + 21, y + 12, outline=color, width=1.6)
        c.create_oval(x + 4, y - 5, x + 14, y + 5, outline=color, width=1.6)


@lru_cache(maxsize=16)
def _header_contours(w):
    """The same immutable header geometry, calculated once per viewport width."""
    contours = []
    for band in range(13):
        pts = []
        for step in range(161):
            angle = math.tau * step / 160
            radius_x, radius_y = 130 + band * 40, 34 + band * 13
            xx = radius_x * math.cos(angle)
            yy = radius_y * math.sin(angle) * (1 + 0.20 * math.sin(angle * 3))
            x = w * 0.67 + xx * 0.94 - yy * 0.34
            y = 25 + xx * 0.34 + yy * 0.94
            pts.extend((x, y))
        contours.append(tuple(pts))
    return tuple(contours)


def paint(app, w, h):
    c = app.canvas
    c.create_rectangle(0, 0, RAIL, h, fill=T.RAIL_BG, outline="")
    c.create_line(RAIL, 0, RAIL, h, fill=T.HAIRLINE)
    c.create_rectangle(RAIL, 0, w, 176, fill=T.PAGE_BG, outline="")
    # Organic contour lines echo the approved topographic header artwork.
    for pts in _header_contours(w):
        c.create_line(*pts, fill="#102E3B", smooth=True, width=0.65)
    paint_brand_mark(c)
    text(c, 68, 44, "SHANKTUARY", 18, bold=True)
    text(c, 69, 74, "PERFORMANCE STUDIO", 8, T.TEXT_2)
    app.concept_actions = []
    y = 139
    row = max(36, min(47, (h - 340) / 12))
    app.design_mode_rects = {}
    for heading, items in GROUPS:
        text(c, 26, y, heading, 12, T.TEXT_2)
        c.create_line(112, y, 255, y, fill=T.HAIRLINE)
        y += 40
        for mode, label in items:
            rect = (16, y - 18, 258, y + row - 21)
            active = app.view_mode == mode
            if active:
                panel(c, *rect, fill=T.ACTIVE_BG, outline=T.TEAL_LINE, r=10)
            icon(c, mode, 36, y + 1, T.TEAL_LINE if active else T.TEXT_2)
            text(c, 90, y + 1, label, 15, T.TEXT, active)
            app.design_mode_rects[mode] = rect
            y += row
        y += 13
    c.create_line(20, h - 96, 240, h - 96, fill=T.HAIRLINE)
    panel(c, 18, h - 79, 242, h - 39, fill=T.RAIL_BG, outline=T.HAIRLINE, r=8)
    text(c, 35, h - 59, "Tools & display", 11, T.TEXT_2)
    app.design_tools_btn_rect = (18, h - 79, 242, h - 39)
    app.concept_actions.append((app.design_tools_btn_rect, "tools"))
    text(c, 26, h - 21, "LOCAL PERFORMANCE STUDIO", 8, T.TEXT_3)
    title = TITLES.get(app.view_mode, "Performance studio")
    if app.view_mode == 10 and (getattr(app, "concept_setup_page", "overview") == "details"
                               or getattr(app, "show_board_assign_modal", False)):
        title = "Board setup & calibration"
    text(c, RAIL + 29, 48, title, 32, bold=True)
    session = app.get_active_session()
    name = session.get("name", "Session")
    app.sidebar_session_btn_rect = (RAIL + 22, 73, min(w - 390, RAIL + 680), 110)
    label = f"Session: {name}"
    available = app.sidebar_session_btn_rect[2] - (RAIL + 29) - 12
    while label and app._text_width(label, (theme.ui_font(), 16)) > available:
        label = label[:-2] + "…" if not label.endswith("…") else label[:-2] + "…"
    text(c, RAIL + 29, 91, label, 16, T.TEXT_2, tags="session-label")
    app.concept_actions.append((app.sidebar_session_btn_rect, "sessions"))
    right = w - 22
    panel(c, right - 180, 65, right, 112, fill=T.SURFACE, outline=T.TEXT_2)
    text(c, right - 90, 88, "New Session", 14, bold=True, anchor="center")
    app.sidebar_new_sess_btn_rect = (right - 180, 65, right, 112)
    app.concept_actions.append((app.sidebar_new_sess_btn_rect, "new"))
    panel(c, right - 370, 65, right - 194, 112, fill=T.SURFACE, outline=T.TEXT_2)
    text(c, right - 282, 88, app.current_club + "  ▾", 14, bold=True, anchor="center")
    app.design_club_btn_rect = (right - 370, 65, right - 194, 112)
    app.concept_actions.append((app.design_club_btn_rect, "club"))
    text(c, right, 24, "LOCAL STUDIO", 9, T.TEAL_TEXT, anchor="e")
    panel(c, RAIL + 22, 128, w - 22, 168, fill="#06252F", outline=T.HAIRLINE, r=9)
    import shanktuary_performance_studio as studio

    status = studio.connection_setup_controller().snapshot()
    state = status.get("state", "idle")
    name = status.get("source") or "Shot source"
    source = {
        "pureplay": "PurePlay",
        "open_connect": "Open Connect",
        "gspro": "GSPro",
        "nova": "Nova",
        "cgp": "CGP",
    }.get(name, name)
    ready = state == "ready"
    board_live = callable(getattr(app, "board_is_streaming", None)) and app.board_is_streaming()
    pm = getattr(studio.obs_server, "pressure_manager", None)
    board_label = "Demo" if board_live and getattr(pm, "is_simulator", False) else "Local" if board_live else "Not connected"
    for dot_x, active in ((RAIL + 39, board_live), (RAIL + 470, ready)):
        c.create_oval(dot_x, 141, dot_x + 14, 155,
                      fill=T.TEAL_LINE if active else T.TEXT_3, outline="")
    text(c, RAIL + 65, 148, f"Boards  ·  {board_label}", 12, T.TEXT_2)
    c.create_line(RAIL + 440, 137, RAIL + 440, 159, fill=T.HAIRLINE)
    message = status.get("message") or ("Ready" if ready else "Not connected")
    source_text = f"{source}  ·  {message}"
    available_source = max(120, w - (RAIL + 496) - 240)
    while len(source_text) > 1 and app._text_width(source_text, (theme.ui_font(), 12)) > available_source:
        source_text = source_text[:-2] + "…" if source_text.endswith("…") else source_text[:-1] + "…"
    text(c, RAIL + 496, 148, source_text, 12, T.TEXT_2)
    text(
        c,
        w - 38,
        148,
        f"{len(app.session_shots)} shots  ·  "
        + ("Left handed" if app.is_left_handed else "Right handed"),
        9,
        T.TEXT_2,
        anchor="e",
    )
    app.concept_actions.append(((w - 225, 128, w - 22, 168), "hand"))
