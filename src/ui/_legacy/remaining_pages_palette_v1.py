"""Page-local palette pass for the remaining production views.

Applies the accepted navy + teal + antique-gold system to Range, Dispersion,
Bag, Fit, Lab, and Setup without changing the global theme module or the
already-polished Shot/Club/Table/Numbers pages.
"""

from contextlib import contextmanager

import dispersion_redesign_v1 as dispersion
import theme

GOLD = "#D4A24F"
GOLD_LIGHT = "#E3BC70"
TEAL = "#32979A"
TEAL_LINE = "#58B7B4"
TEAL_TEXT = "#78C4C1"
TEAL_SOFT = "#698E96"

PAGE_BG = "#0A2029"
RAIL_BG = "#0B1B24"
SURFACE = "#0D2731"
SURFACE_2 = "#15333D"
HAIRLINE = "#2A4C55"
TEXT = "#F3F6FA"
TEXT_2 = "#B3BEC2"
TEXT_3 = "#70868C"
ACCENT_DEEP = "#173B42"
GUIDE = "#456D76"
GOOD = "#39A879"
DANGER = "#E34A4A"

# Catch old literal palette values that bypass theme.py inside production views.
_LITERAL_MAP = {
    "#0b0f16": PAGE_BG,
    "#0e1420": RAIL_BG,
    "#111923": SURFACE,
    "#182334": SURFACE_2,
    "#253247": HAIRLINE,
    "#f3f6fa": TEXT,
    "#a6b0be": TEXT_2,
    "#657286": TEXT_3,
    "#112a4e": ACCENT_DEEP,
    "#1e6cff": GOLD,
    "#40a3ff": TEAL_LINE,
    "#78baff": TEAL_TEXT,
    "#f47a32": GOLD,
    "#c89a4a": GOLD,
    "#34445b": GUIDE,
    # A few older electric-blue/orange literals used in legacy views.
    "#00bfff": TEAL_LINE,
    "#0096ff": TEAL_LINE,
    "#00a3ff": TEAL_LINE,
    "#1e90ff": TEAL_LINE,
    "#4a90e2": TEAL_LINE,
    "#ff7a00": GOLD,
    "#ff8c00": GOLD,
    "#e76f25": GOLD,
}

_THEME_VALUES = {
    "BG": PAGE_BG,
    "RAIL": RAIL_BG,
    "SURFACE": SURFACE,
    "SURFACE_2": SURFACE_2,
    "HAIRLINE": HAIRLINE,
    "TEXT": TEXT,
    "TEXT_2": TEXT_2,
    "TEXT_3": TEXT_3,
    "ACCENT_DEEP": ACCENT_DEEP,
    "ACCENT": GOLD,
    "ACCENT_LINE": TEAL_LINE,
    "ACCENT_TEXT": TEAL_TEXT,
    "GOOD": GOOD,
    "WARN": GOLD,
    "DANGER": DANGER,
    "GOLD": GOLD,
    "GUIDE": GUIDE,
    "MUTED": TEXT_3,
}

_MISSING = object()


def _map_color(value):
    if not isinstance(value, str):
        return value
    return _LITERAL_MAP.get(value.lower(), value)


@contextmanager
def _page_palette(app):
    # The production compatibility theme intentionally does not expose every
    # token used by older design-sandbox renderers (notably GOOD and GOLD).
    # Treat missing attributes as temporary adapter-owned tokens instead of
    # crashing before a Tools page can render.
    saved_theme = {
        name: getattr(theme, name, _MISSING)
        for name in _THEME_VALUES
    }
    for name, value in _THEME_VALUES.items():
        setattr(theme, name, value)

    c = app.canvas
    method_names = (
        "create_rectangle", "create_text", "create_line", "create_oval",
        "create_polygon", "create_arc",
    )
    saved_methods = {}
    for name in method_names:
        original = getattr(c, name)
        saved_methods[name] = original

        def wrapped(*args, __orig=original, **kwargs):
            for key in ("fill", "outline", "activefill", "activeoutline"):
                if key in kwargs:
                    kwargs[key] = _map_color(kwargs[key])
            return __orig(*args, **kwargs)

        setattr(c, name, wrapped)

    try:
        yield
    finally:
        for name, original in saved_methods.items():
            setattr(c, name, original)
        for name, value in saved_theme.items():
            if value is _MISSING:
                try:
                    delattr(theme, name)
                except AttributeError:
                    pass
            else:
                setattr(theme, name, value)


def draw_production_page(app, draw_fn, *args, **kwargs):
    """Run one legacy production view through the accepted page-local palette."""
    with _page_palette(app):
        return draw_fn(*args, **kwargs)


def draw_dispersion_and_gapping(app, avail_w, h, offset_x=0):
    """Retheme the dedicated Dispersion redesign without changing its layout."""
    old = (
        dispersion.BLUE, dispersion.BLUE_TEXT, dispersion.ORANGE,
        dispersion.GRID, dispersion.MUTED, dispersion.SOFT,
    )
    dispersion.BLUE = TEAL_LINE
    dispersion.BLUE_TEXT = TEAL_TEXT
    dispersion.ORANGE = GOLD
    dispersion.GRID = GUIDE
    dispersion.MUTED = TEXT_3
    dispersion.SOFT = HAIRLINE
    try:
        with _page_palette(app):
            return dispersion.draw_dispersion_and_gapping(
                app, avail_w, h, offset_x=offset_x
            )
    finally:
        (
            dispersion.BLUE, dispersion.BLUE_TEXT, dispersion.ORANGE,
            dispersion.GRID, dispersion.MUTED, dispersion.SOFT,
        ) = old
