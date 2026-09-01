"""Approved desktop design tokens for Shanktuary Performance Studio.

This is the public palette API for the redesigned Tk desktop.  Legacy renderer
modules still carry a few literal values internally, but new desktop work should
import roles from here instead of inventing colors.
"""

# Brand / emphasis
GOLD = "#D4A24F"
GOLD_LIGHT = "#E3BC70"
BRONZE = "#A7793A"

# Analytical / technical
TEAL = "#32979A"
TEAL_LINE = "#58B7B4"
TEAL_TEXT = "#78C4C1"
TEAL_SOFT = "#698E96"

# Structure
PAGE_BG = "#0A2029"
RAIL_BG = "#081923"
SIDEBAR_BG = "#091B24"
SURFACE = "#0D2731"
SURFACE_2 = "#15333D"
ACTIVE_BG = "#18313A"
SECTION_BG = "#173B42"
HAIRLINE = "#2A4C55"
GUIDE = "#456D76"

# Typography
TEXT = "#F3F6FA"
TEXT_2 = "#B3BEC2"
TEXT_3 = "#70868C"

# Semantic only
SUCCESS = "#39A879"
DANGER = "#E34A4A"

# Persistent shell geometry
NAV_RAIL_W = 64
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
