"""Approved desktop design tokens for Shanktuary Performance Studio.

This is the public palette API for the redesigned Tk desktop.  Legacy renderer
modules still carry a few literal values internally, but new desktop work should
import roles from here instead of inventing colors.
"""

# Brand / emphasis
GOLD = "#F6CE69"
GOLD_LIGHT = "#FFDF85"
BRONZE = "#A7793A"

# Analytical / technical
TEAL = "#00BFAE"
TEAL_LINE = "#13DFCA"
TEAL_TEXT = "#91E9DF"
TEAL_SOFT = "#698E96"

# Structure
PAGE_BG = "#041823"
RAIL_BG = "#03151F"
SIDEBAR_BG = "#061E28"
SURFACE = "#04232D"
SURFACE_2 = "#0B4148"
ACTIVE_BG = "#075750"
SECTION_BG = "#073B42"
HAIRLINE = "#37616B"
GUIDE = "#456D76"

# Typography
TEXT = "#F3F6FA"
TEXT_2 = "#B3BEC2"
TEXT_3 = "#70868C"

# Semantic only
SUCCESS = "#39A879"
DANGER = "#E34A4A"

# Persistent shell geometry
NAV_RAIL_W = 272
COLLAPSED_GUTTER_W = 28


def role_for(name: str) -> str:
    """Return the design role for a common element name (documentation helper)."""
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    if key in {"current", "selected", "active", "hero", "primary", "action"}:
        return "gold"
    if key in {"analysis", "technical", "geometry", "path", "guide", "chart"}:
        return "teal"
    if key in {"success", "ready", "positive"}:
        return "success"
    if key in {"danger", "error", "negative"}:
        return "danger"
    if key in {"secondary", "context", "muted", "unit", "caption"}:
        return "slate"
    return "structure"
