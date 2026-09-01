"""Thirteenth-pass Shot view: page-local gold + teal palette only.

This does NOT change the shared theme or any other workspace. The Shot page
uses antique gold/bronze for current-shot and brand emphasis, while muted teal
handles analytical geometry, chart lines, and technical annotations.
"""

import overview_redesign_v4 as v4
import overview_redesign_v5 as v5
import overview_redesign_v7 as v7
import overview_redesign_v8 as v8
import overview_redesign_v9 as v9
import overview_redesign_v10 as v10
import overview_redesign_v11 as v11
import overview_redesign_v12 as v12
import theme

# Page-local palette. Intentionally more restrained than the old electric blue
# and orange treatment.
GOLD = "#C49A55"
GOLD_LIGHT = "#DFC07A"
BRONZE = "#956C35"
TEAL = "#2F7880"
TEAL_LINE = "#5B9CA2"
TEAL_TEXT = "#82B7BB"


def _apply_palette():
    # Earliest shared helpers / ribbon.
    v4.BLUE = GOLD
    v4.BLUE_LINE = TEAL_LINE
    v4.BLUE_TEXT = TEAL_TEXT
    v4.ORANGE = GOLD
    v4.SESSION_DOT = v4._mix(theme.TEXT_3, TEAL, .15)
    v4.RIBBON = v4._mix(theme.SURFACE, GOLD, .020)

    # Trend helpers still used by the accepted Session section.
    v5.BLUE = GOLD
    v5.BLUE_LINE = TEAL_LINE
    v5.BLUE_TEXT = TEAL_TEXT
    v5.ORANGE = GOLD
    v5.GOLD = GOLD_LIGHT

    # Main accepted Shot composition.
    v7.BLUE = GOLD
    v7.BLUE_LINE = TEAL_LINE
    v7.BLUE_TEXT = TEAL_TEXT
    v7.ORANGE = GOLD
    v7.GOLD = GOLD_LIGHT
    v7.SESSION_DOT = v7._mix(theme.TEXT_3, TEAL, .16)
    v7.ELLIPSE = v7._mix(TEAL_LINE, theme.BG, .36)
    v7.NEUTRAL_POINT = v7._mix(theme.TEXT_2, TEAL, .08)

    # Material/session pass and confidence ellipse.
    v8.BLUE = GOLD
    v8.BLUE_LINE = TEAL_LINE
    v8.BLUE_TEXT = TEAL_TEXT
    v8.ORANGE = GOLD
    v8.GOLD = GOLD_LIGHT
    v8.SESSION_DOT = v7.SESSION_DOT

    # Readability/polish layers copy color constants at import time, so update
    # them explicitly rather than touching theme.py globally.
    v9.BLUE_LINE = TEAL_LINE
    v9.BLUE_TEXT = TEAL_TEXT
    v9.ORANGE = GOLD
    v9.SESSION_DOT = v7.SESSION_DOT

    v10.BLUE_LINE = TEAL_LINE
    v10.BLUE_TEXT = TEAL_TEXT
    v10.ORANGE = GOLD
    v10.NEUTRAL_POINT = v7.NEUTRAL_POINT

    v11.BLUE_LINE = TEAL_LINE
    v11.BLUE_TEXT = TEAL_TEXT
    v11.ORANGE = GOLD

    v12.BLUE_LINE = TEAL_LINE
    v12.BLUE_TEXT = TEAL_TEXT
    v12.ORANGE = GOLD
    v12.NEUTRAL_POINT = v7.NEUTRAL_POINT


def draw_overview(*args, **kwargs):
    _apply_palette()
    return v12.draw_overview(*args, **kwargs)
