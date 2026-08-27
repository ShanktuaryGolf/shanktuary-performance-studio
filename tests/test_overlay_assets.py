"""Overlay asset guarantees.

Two classes of regression these lock down:

1. Data honesty. The overlay is the surface other people see on stream, and
   it used to display four fabricated values as if measured -- attack angle
   and dynamic loft derived from vertical launch angle, apex from carry, and
   a hardcoded 1.23 smash fallback (the OGC clamp constant).

2. Shared theming. The browser assets carried their own palette, which is
   how the app reached 195 distinct colours before the redesign.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
OVERLAY = REPO / "assets" / "overlay.html"
CONFIG = REPO / "assets" / "config.html"
THEME_CSS = REPO / "assets" / "theme.css"


@pytest.fixture(scope="module")
def overlay():
    return OVERLAY.read_text()


# --- data honesty ----------------------------------------------------------

FABRICATIONS = {
    "smash falls back to the OGC clamp constant": r"smash_factor\s*\|\|\s*1\.2",
    "attack angle derived from launch angle": r"\*\s*0\.3\s*-\s*4\.5",
    "dynamic loft derived from launch angle": r"\*\s*0\.85\)",
    "apex derived from carry": r"0\.42\s*\*\s*3\.0",
    "closure rate synthesised": r"1800\s*\+\s*Math\.abs",
    "club speed guessed from ball speed": r"ball_speed_mph\s*/\s*1\.35",
    "descent angle defaults to a tour figure": r"descent_angle_degrees\s*\|\|\s*46",
}


@pytest.mark.parametrize("desc,pattern", sorted(FABRICATIONS.items()))
def test_no_fabricated_values(overlay, desc, pattern):
    assert not re.search(pattern, overlay), (
        f"overlay.html reintroduced a fabricated value: {desc}. "
        "The Nova measures five ball parameters; anything else is derived "
        "by OpenGolfCoach or not measured at all."
    )


def test_smash_clamp_constants_match_the_app(overlay):
    """The JS clamp detector must agree with the Python one."""
    import sys
    sys.path.insert(0, str(REPO))
    import shanktuary_performance_studio as app

    for js_name, py_val in (
        ("SPS_SMASH_FLOOR", app.OGC_SMASH_AT_COR_FLOOR),
        ("SPS_SMASH_CEILING", app.OGC_SMASH_AT_COR_CEILING),
    ):
        m = re.search(rf"const {js_name}\s*=\s*([0-9.]+)", overlay)
        assert m, f"{js_name} missing from overlay.html"
        assert abs(float(m.group(1)) - py_val) < 1e-12, (
            f"{js_name} has drifted from {py_val}"
        )


def test_suppression_helper_exists(overlay):
    assert "function spsSetMetric" in overlay
    assert "function spsSmashClamped" in overlay


def test_estimate_chip_on_face_impact(overlay):
    """Strike location is inferred, and must say so on stream."""
    assert "est-chip" in overlay
    assert "ESTIMATE" in overlay


# --- shared theming --------------------------------------------------------

def test_theme_css_is_generated_from_theme_py():
    import sys
    sys.path.insert(0, str(REPO))
    import theme

    css = THEME_CSS.read_text()
    root = re.search(r":root\s*\{([^}]*)\}", css)
    assert root, "theme.css has no :root block"
    block = root.group(1)

    for css_name, attr in (
        ("bg", "BG"), ("surface", "SURFACE"), ("text", "TEXT"),
        ("accent", "ACCENT"), ("warn", "WARN"), ("danger", "DANGER"),
    ):
        m = re.search(rf"--{css_name}:\s*(#[0-9A-Fa-f]{{6}})", block)
        assert m, f"--{css_name} missing from theme.css"
        assert m.group(1).upper() == getattr(theme, attr).upper(), (
            f"--{css_name} is stale; run scripts/gen_theme_css.py"
        )


def test_projector_polarity_is_inverted():
    """A projector adds light, so the card must be bright and text dark."""
    css = THEME_CSS.read_text()
    m = re.search(r"body\.mode-projector\s*\{([^}]*)\}", css)
    assert m, "theme.css has no projector override block"
    block = m.group(1)
    surface = re.search(r"--surface:\s*(#[0-9A-Fa-f]{6})", block).group(1)
    text = re.search(r"--text:\s*(#[0-9A-Fa-f]{6})", block).group(1)

    def luminance(hex_colour):
        h = hex_colour.lstrip("#")
        vals = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            vals.append(c / 12.92 if c <= 0.03928
                        else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]

    assert luminance(surface) > luminance(text), (
        "projector mode must invert: the card is the bright element"
    )


@pytest.mark.parametrize("path", [OVERLAY, CONFIG])
def test_browser_assets_use_shared_tokens(path):
    src = path.read_text()
    assert "/assets/theme.css" in src, f"{path.name} does not import theme.css"

    literals = set(re.findall(r"#[0-9A-Fa-f]{6}", src))
    # #000000 is legitimate: projector backdrop means "emit no light here".
    literals.discard("#000000")
    assert not literals, (
        f"{path.name} carries its own colours: {sorted(literals)}. "
        "Use var(--token) so the browser side cannot drift from theme.py."
    )


# --- projector + rotation --------------------------------------------------

def test_projector_does_not_hide_widgets(overlay):
    """?edit=true exists so a user can place cards on their floor."""
    assert ".widget:not(#w_divot)" not in overlay, (
        "projector mode is hiding every widget again, which defeats the "
        "layout editor"
    )


def test_rotation_round_trips(overlay):
    assert "function spsSetRotation" in overlay
    assert "data-rotation" in overlay
    assert "rotation: rot" in overlay, "rotation is not saved into the layout"
    assert "cfg.rotation || 0" in overlay, (
        "rotation must default to 0 so layouts saved before it existed "
        "still load"
    )
