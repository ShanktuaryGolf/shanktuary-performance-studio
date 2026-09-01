"""Table palette pass matching the accepted Shot / shell direction.

Keeps v1's dense table composition exactly as-is, but gives the page its own
richer navy + teal-undertone material and new gold/teal color roles.
"""

from contextlib import contextmanager

import overview_redesign_v8 as shot_v8
import overview_redesign_v14 as shot_v14
import table_redesign_v1 as v1
import theme

GOLD = shot_v14.GOLD
GOLD_LIGHT = shot_v14.GOLD_LIGHT
TEAL = shot_v14.TEAL
TEAL_LINE = shot_v14.TEAL_LINE
TEAL_TEXT = shot_v14.TEAL_TEXT

PAGE_BG = "#091B24"
SURFACE = "#0E2631"
SURFACE_2 = "#17343F"
HAIRLINE = "#35515B"
TEXT = "#F0F2EF"
TEXT_2 = "#B5C1C5"
TEXT_3 = "#7B929A"
GUIDE = "#496F78"


@contextmanager
def _table_theme():
    names = (
        "BG", "SURFACE", "SURFACE_2", "HAIRLINE",
        "TEXT", "TEXT_2", "TEXT_3",
        "ACCENT_DEEP", "ACCENT", "ACCENT_LINE", "ACCENT_TEXT",
        "WARN", "GUIDE", "MUTED",
    )
    old = {name: getattr(theme, name) for name in names}
    try:
        theme.BG = PAGE_BG
        theme.SURFACE = SURFACE
        theme.SURFACE_2 = SURFACE_2
        theme.HAIRLINE = HAIRLINE
        theme.TEXT = TEXT
        theme.TEXT_2 = TEXT_2
        theme.TEXT_3 = TEXT_3
        theme.ACCENT_DEEP = "#3A2B19"
        theme.ACCENT = GOLD
        theme.ACCENT_LINE = TEAL_LINE
        theme.ACCENT_TEXT = GOLD_LIGHT
        theme.WARN = GOLD
        theme.GUIDE = GUIDE
        theme.MUTED = TEXT_3
        yield
    finally:
        for name, value in old.items():
            setattr(theme, name, value)


def _background(app, avail_w, h, offset_x=0):
    """Use the same navy/teal material family as Shot without adding clutter."""
    img = shot_v8._material_image(
        app, "table_v2_bg", avail_w, max(1, h - 52),
        top="#0D2732", bottom="#07151E",
        left="#0A2933", right="#091923",
        mottle=.045, fibers=.018, grain=.014, seed=221,
    )
    app.canvas.create_image(offset_x, 52, image=img, anchor="nw")


def draw_shot_table_viewport(app, avail_w, h, offset_x=0):
    with _table_theme():
        _background(app, avail_w, h, offset_x=offset_x)
        return v1.draw_shot_table_viewport(app, avail_w, h, offset_x=offset_x)
