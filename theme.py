"""Shared/legacy theme tokens for Shanktuary Performance Studio.

This module remains the compatibility source for production renderers and the
browser/OBS surfaces that already consume these names.  The redesigned desktop
UI has a separate, intentional navy/teal/gold design system in
``src/ui/tokens.py``; see ``DESIGN_SYSTEM.md`` before styling new desktop work.

Do not globally replace these compatibility values just to recolor the desktop.
The desktop adapter applies its palette at the UI boundary so browser assets and
older production renderers can migrate deliberately without surprise regressions.

The legacy rules below still apply to code that consumes this module directly:

* ONE neutral ramp (BG -> SURFACE -> HAIRLINE -> TEXT*) builds structure.
* ONE compatibility accent (hunter green) marks identity and active state.
* SEMANTIC colours (WARN / DANGER / ESTIMATE) are reserved for meaning and
  must never be used decoratively.
"""

# --- neutral ramp ---------------------------------------------------------
BG        = "#0E1013"   # app background
RAIL      = "#121418"   # nav rail, slightly lifted from BG
SURFACE   = "#16191E"   # cards / panels
SURFACE_2 = "#1D2127"   # hover, selected row, secondary fill
HAIRLINE  = "#252A32"   # 1px separators -- never full boxes

TEXT      = "#F2F4F7"   # primary values            15.9:1
TEXT_2    = "#9BA3AF"   # labels, secondary copy     7.2:1
TEXT_3    = "#646C79"   # units, captions, disabled  3.5:1

# --- brand accent: hunter green scale ------------------------------------
ACCENT_DEEP = "#22402C"  # 1.9:1  pressed states, chip backgrounds
ACCENT      = "#4C8C5E"  # 4.7:1  fills, bars, active nav
ACCENT_LINE = "#6FA880"  # 6.4:1  strokes, dots, 1px marks
ACCENT_TEXT = "#9CC9AC"  # 9.1:1  numbers and labels on dark

# --- semantic -------------------------------------------------------------
WARN   = "#F5A524"   # estimates, low-confidence, caution
DANGER = "#F04438"   # errors, extreme miss
GUIDE  = "#3A424E"   # dashed reference/target lines

# Values the Nova cannot measure render in TEXT_3 with a "--" placeholder.
# See compute_smash_confidence(): a clamped OpenGolfCoach estimate carries no
# information, so it must not be styled like a measurement.
MUTED = TEXT_3

# --- layout ---------------------------------------------------------------
RAIL_W = 64          # left icon rail, always visible


# --- typography -------------------------------------------------------------
# Tk resolves unknown families silently, and "Helvetica" is NOT installed on
# most Linux systems -- it falls back to Nimbus Sans, a narrow URW clone that
# reads as monospace-ish at small sizes and is why the UI looked like terminal
# output. Resolve a real UI face once, at import, and use it everywhere.
def _resolve_ui_font():
    try:
        import tkinter.font as tkfont
        fams = set(tkfont.families())
    except Exception:
        return "Helvetica"
    for cand in ("Inter", "Noto Sans", "DejaVu Sans", "Liberation Sans",
                 "Cantarell", "Segoe UI", "Helvetica Neue", "Arial"):
        if cand in fams:
            return cand
    return "Helvetica"


_UI_FONT = None


def ui_font():
    """Family name for all UI text. Resolved lazily -- needs a live Tk root."""
    global _UI_FONT
    if _UI_FONT is None:
        _UI_FONT = _resolve_ui_font()
    return _UI_FONT
NAV_ITEM_H = 56      # per nav entry
CORNER = 10          # standard corner radius

# view_mode -> (rail label, tooltip).
# NOTE: mode 0 is the floor divot projector (entered via Tools, not the rail)
# and mode 5 is Big Numbers. Overview is mode 9 to avoid colliding with either.
NAV_ITEMS = [
    (9, "Overview", "Shot summary and session trends"),
    (1, "Quad",     "Four-panel club and ball geometry"),
    (2, "Range",    "3D driving range"),
    (3, "Disp",     "Dispersion and covariance"),
    (4, "Table",    "Shot table"),
    (5, "Nums",     "Big numbers"),
    (6, "Bag",      "My Bag and club specs"),
    (7, "Fit",      "Club fitting comparison"),
    (8, "Lab",      "Swing lab / pressure"),
    (11, "Index",   "Shanktuary Index score"),
]


# Browser Studio redesign. Scoped separately from compatibility desktop tokens.
BROWSER_STUDIO = {
    "bg": "#031723", "surface": "#062D35", "surface-2": "#0B454B",
    "hairline": "#4D8088", "text": "#F4F8FA", "text-2": "#CBDBE0",
    "text-3": "#92AFB7", "accent-deep": "#075D5C", "accent": "#00D6BC",
    "accent-line": "#24F1D7", "accent-text": "#8CF7E9", "gold": "#FFD16A",
    "guide": "#46757D", "warn": "#FFD16A", "danger": "#F27575",
}

# Explicit overlay presets. The projector always keeps inverted polarity.
BROWSER_OVERLAY_THEMES = {
    "broadcast-dark": {"bg": "#091119", "surface": "#15212B", "surface-2": "#22343E", "hairline": "#66808A", "text": "#F4F8FA", "text-2": "#C6D3D9", "text-3": "#9AADB5"},
    "clean-light": {"bg": "#E4F0F4", "surface": "#F2F8FA", "surface-2": "#D1E6EB", "hairline": "#5D8792", "text": "#092630", "text-2": "#244D59", "text-3": "#426A75", "accent": "#007E78", "accent-line": "#008D83", "accent-text": "#006F67"},
}
