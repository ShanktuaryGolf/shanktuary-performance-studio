"""Club page palette pass matching the accepted Shot v15 direction.

This stays page-local. It keeps the accepted Club-page hierarchy/credibility
polish from v1, but moves the workspace onto the richer navy + teal undertone
material and assigns color roles consistently:

- antique gold = primary/current/estimated emphasis
- brighter teal = analytical geometry and delivery cues
- cool navy = page material
- semantic red remains reserved for danger
"""

from contextlib import contextmanager

import club_redesign_v1 as v1
import overview_redesign_v14 as shot_v14
import theme

GOLD = shot_v14.GOLD
GOLD_LIGHT = shot_v14.GOLD_LIGHT
BRONZE = shot_v14.BRONZE
TEAL = shot_v14.TEAL
TEAL_LINE = shot_v14.TEAL_LINE
TEAL_TEXT = shot_v14.TEAL_TEXT

# Club-local material. Slightly flatter than Shot because the four-quadrant
# instrumentation already provides strong spatial structure.
CLUB_BG = "#091B24"
CLUB_SURFACE = "#0E2631"
CLUB_SURFACE_2 = "#17343F"
CLUB_HAIRLINE = "#35515B"
CLUB_GUIDE = "#496F78"
CLUB_TEXT = "#F0F2EF"
CLUB_TEXT_2 = "#B5C1C5"
CLUB_TEXT_3 = "#7B929A"


@contextmanager
def _club_theme(accent_text=GOLD_LIGHT):
    """Temporarily apply the Club palette without changing other pages."""
    names = (
        "BG", "SURFACE", "SURFACE_2", "HAIRLINE",
        "TEXT", "TEXT_2", "TEXT_3",
        "ACCENT_DEEP", "ACCENT", "ACCENT_LINE", "ACCENT_TEXT",
        "WARN", "GUIDE", "MUTED",
    )
    old = {name: getattr(theme, name) for name in names}
    try:
        theme.BG = CLUB_BG
        theme.SURFACE = CLUB_SURFACE
        theme.SURFACE_2 = CLUB_SURFACE_2
        theme.HAIRLINE = CLUB_HAIRLINE
        theme.TEXT = CLUB_TEXT
        theme.TEXT_2 = CLUB_TEXT_2
        theme.TEXT_3 = CLUB_TEXT_3

        theme.ACCENT_DEEP = "#3A2B19"
        theme.ACCENT = GOLD
        # Geometry/path/spin axes use the teal family rather than gold.
        theme.ACCENT_LINE = TEAL_LINE
        theme.ACCENT_TEXT = accent_text
        theme.WARN = GOLD
        theme.GUIDE = CLUB_GUIDE
        theme.MUTED = CLUB_TEXT_3
        yield
    finally:
        for name, value in old.items():
            setattr(theme, name, value)


def draw_top_metric_toolbar(app, *args, **kwargs):
    """Gold hero metric in the ribbon, over the lighter navy material."""
    with _club_theme(accent_text=GOLD_LIGHT):
        return v1.draw_top_metric_toolbar(app, *args, **kwargs)


def draw_4_quadrant_studio(app, production_draw, *args, **kwargs):
    """Draw production quadrants under the page-local palette, then v1 polish."""
    # Production owns the diagrams and base quadrant layout. Giving it the
    # page-local theme recolors those primitives without altering shared tokens.
    with _club_theme(accent_text=GOLD_LIGHT):
        result = production_draw(*args, **kwargs)

    # The polish layer's interpretation text, spin labels, and measured states
    # are analytical cues, so they use teal. Estimated state remains gold via
    # theme.WARN and the clubface/hero emphasis remains controlled by production.
    with _club_theme(accent_text=TEAL_TEXT):
        v1.polish_club_page(app, *args, **kwargs)

    return result
