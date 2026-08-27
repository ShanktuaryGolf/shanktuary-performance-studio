#!/usr/bin/env python3
"""Generate assets/theme.css from theme.py.

The browser assets used to carry their own palette -- 22 distinct hex
literals in overlay.html, 13 in config.html, none of them shared with the
desktop app. That is how the app ended up with 195 colours before the
redesign, and the browser side was on track to repeat it.

This makes theme.py the single source of truth: run the script after
changing a token and both surfaces follow.

    python3 scripts/gen_theme_css.py

The generated file is committed, so a fresh checkout (or a PyInstaller
build, which only bundles assets/) does not need to run this first.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import theme  # noqa: E402

# (css-var-name, theme.py attribute). Order controls the output order.
TOKENS = [
    ("bg",          "BG"),
    ("surface",     "SURFACE"),
    ("surface-2",   "SURFACE_2"),
    ("hairline",    "HAIRLINE"),
    ("text",        "TEXT"),
    ("text-2",      "TEXT_2"),
    ("text-3",      "TEXT_3"),
    ("accent-deep", "ACCENT_DEEP"),
    ("accent",      "ACCENT"),
    ("accent-line", "ACCENT_LINE"),
    ("accent-text", "ACCENT_TEXT"),
    ("warn",        "WARN"),
    ("danger",      "DANGER"),
    ("guide",       "GUIDE"),
]

HEADER = """/* GENERATED FILE -- do not edit by hand.
 *
 * Source: theme.py  ->  scripts/gen_theme_css.py
 * Regenerate with:  python3 scripts/gen_theme_css.py
 *
 * Shared design tokens for the browser surfaces (overlay, configurator,
 * floor projector). Mirrors the desktop app so both look like one product.
 */

:root {
"""

# Projector polarity switch.
#
# A projector ADDS light to a surface -- it cannot project black, because
# black is simply the absence of light (i.e. whatever the mat already looks
# like). A dark card therefore projects as almost nothing, leaving floating
# text on the turf with no card behind it.
#
# The fix is to invert rather than brighten: the CARD becomes the bright
# element and the text becomes dark, so the projector puts light exactly
# where the card is. Same token NAMES, different values, so every widget
# inverts for free and anything added later inherits both modes.
#
# Measured contrast:
#   screen    #F2F4F7 on #16191E  = 15.99:1
#   projector #0E1013 on #F2F4F7  = 17.29:1
PROJECTOR = """}

/* Floor projector: inverted polarity. See scripts/gen_theme_css.py for why. */
body.mode-projector {
  --bg:          #000000;
  --surface:     #F2F4F7;
  --surface-2:   #E4E7EC;
  --hairline:    #C4CAD3;
  --text:        #0E1013;
  --text-2:      #3A424E;
  --text-3:      #646C79;
  --accent-deep: #C9DDD0;
  --accent:      #2F6640;
  --accent-line: #22402C;
  --accent-text: #1B3322;
  --warn:        #8A5A00;
  --danger:      #A11C11;
  --guide:       #9BA3AF;
}
"""

FOOTER = """
/* Typography. The desktop app resolves a real UI face at runtime because
 * Tk silently falls back to Nimbus Sans when asked for "Helvetica"; the
 * browser can just list a stack. */
:root {
  --ui-font: Inter, 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto,
             'Helvetica Neue', Arial, sans-serif;
}
"""


def main():
    lines = [HEADER]
    for css_name, attr in TOKENS:
        val = getattr(theme, attr, None)
        if val is None:
            raise SystemExit(f"theme.py has no attribute {attr!r}")
        lines.append(f"  --{css_name}:{'':<{max(1, 14 - len(css_name))}}{val};\n")
    lines.append(PROJECTOR)
    lines.append(FOOTER)

    out = REPO / "assets" / "theme.css"
    out.write_text("".join(lines))
    print(f"wrote {out} ({len(TOKENS)} tokens + projector overrides)")


if __name__ == "__main__":
    main()
