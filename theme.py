"""Central design tokens for Shanktuary Performance Studio.

Why this exists
---------------
The desktop UI grew to 195 distinct hex literals across ~734 usages. Colour
stopped carrying meaning: cyan marked "offline" in one panel and "spin axis"
in another, so nothing stood out because everything did.

This module is the single source of truth. The rules:

* ONE neutral ramp (BG -> SURFACE -> HAIRLINE -> TEXT*) builds structure.
* ONE brand accent (hunter green) marks identity and active state.
* SEMANTIC colours (WARN / DANGER / ESTIMATE) are reserved for meaning and
  must never be used decoratively.

Hunter green needs a scale, not a single value. A true hunter (#355E3B) is
only 2.55:1 against BG, which is unreadable for text or thin strokes. The
deep tones carry large fills; the light tints carry text and 1px lines.
Contrast ratios below are measured against BG (#0E1013).
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
NAV_ITEM_H = 56      # per nav entry
CORNER = 10          # standard corner radius

# view_mode -> (rail label, tooltip). Mode 0 is the new Overview.
NAV_ITEMS = [
    (0, "Overview", "Shot summary and session trends"),
    (1, "Quad",     "Four-panel club and ball geometry"),
    (2, "Range",    "3D driving range"),
    (3, "Disp",     "Dispersion and covariance"),
    (4, "Table",    "Shot table"),
    (5, "Nums",     "Big numbers"),
    (6, "Bag",      "My Bag and club specs"),
    (7, "Fit",      "Club fitting comparison"),
    (8, "Lab",      "Swing lab / pressure"),
]
