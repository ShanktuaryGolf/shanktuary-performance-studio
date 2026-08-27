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


def test_rotate_control_lives_in_the_toolbar(overlay):
    """A rotate button on the widget rotates with it -- unusable at 180."""
    assert "spsRotateSelected" in overlay
    assert "spsSelectWidget" in overlay
    assert 'id="rotateLeftBtn"' in overlay
    assert 'id="rotateRightBtn"' in overlay
    assert "spsInstallRotateControls" not in overlay, (
        "the per-widget rotate cluster is back; it rotates with the widget"
    )

    # The control must sit inside the fixed edit toolbar, not a widget.
    toolbar = re.search(
        r'<div class="edit-toolbar">(.*?)</div>\s*<!-- All 5 Visual Widgets -->',
        overlay,
        re.S,
    )
    assert toolbar, "edit toolbar block not found"
    assert 'id="rotateLeftBtn"' in toolbar.group(1), (
        "rotate control is not in the edit toolbar"
    )


# --- virtual divot ---------------------------------------------------------

def test_divot_is_not_the_old_polygon(overlay):
    """The 6-point polygon read as an abstract shape, not a hole."""
    assert "const w = 36, h = 120;" not in overlay, (
        "the old 6-point divot polygon is back"
    )
    assert "function spsDivotOutline" in overlay
    assert "function spsDivotEnv" in overlay


def test_divot_is_blunt_at_both_ends(overlay):
    """Two pointed ends on a long thin shape is the anatomical read.

    A real iron divot does not taper to a point at the ball -- the club is
    already in the ground -- so both ends must keep real width.
    """
    env = re.search(r"function spsDivotEnv\(t\) \{(.*?)\n    \}", overlay, re.S)
    assert env, "spsDivotEnv not found"
    body = env.group(1)
    assert "0.78 + 0.22" in body, (
        "entry no longer starts blunt; it will taper to a point"
    )
    assert "1.0 - 0.18" in body, "exit no longer stays blunt"


def test_divot_has_no_mirror_line(overlay):
    """Lateral curve + unequal banks are what break the symmetry."""
    out = re.search(r"function spsDivotOutline\(.*?\n    \}", overlay, re.S)
    assert out, "spsDivotOutline not found"
    body = out.group(0)
    assert "drift" in body, "lateral curve removed -- shape becomes symmetric"
    assert "1.08" in body and "0.80" in body, (
        "the two banks are equal again, restoring the mirror line"
    )


def test_divot_aspect_stays_broad(overlay):
    """Long and thin reads anatomical; real divots are ~2:1."""
    mL = re.search(r"SPS_DIVOT_L = (\d+)", overlay)
    mW = re.search(r"SPS_DIVOT_W = (\d+)", overlay)
    assert mL and mW, "divot dimension constants not found"
    L, W = int(mL.group(1)), int(mW.group(1))
    assert 1.3 <= L / W <= 2.4, (
        f"divot aspect {L/W:.2f}:1 is outside the 1.3-2.4 range; too thin "
        "reads as an almond, too wide stops reading as a divot"
    )


def test_divot_shape_is_not_scaled_by_measurements(overlay):
    """Nova measures club path only -- not divot depth, length or width.

    Sizing the divot by ball speed or launch angle would present an
    invented measurement as if observed.
    """
    fn = re.search(r"function drawDivot\(shot\) \{(.*?)\n    \}\n", overlay, re.S)
    assert fn, "drawDivot not found"
    body = fn.group(1)
    for forbidden in ("ball_speed", "total_spin", "vertical_launch",
                      "carry_distance", "smash"):
        assert forbidden not in body, (
            f"divot geometry is keyed off {forbidden}; the Nova does not "
            "measure divot size, so this invents data"
        )
    assert "SPS_DIVOT_L" in body and "SPS_DIVOT_W" in body, (
        "divot dimensions must come from the constants, not per-shot values"
    )


def test_divot_scale_is_derived_from_measured_extent(overlay):
    """The divot is drawn FORWARD of the ball, not centred on it.

    So it occupies one half of the canvas. Scaling it with the guides'
    centred divisor (min/220) ran it off the widget by ~60px at 250px.
    Scale must come from the measured extent instead.
    """
    fn = re.search(r"function drawDivot\(shot\) \{(.*?)\n    \}\n", overlay, re.S)
    assert fn, "drawDivot not found"
    body = fn.group(1)

    assert "function spsDivotExtent" in overlay, (
        "the measured-extent helper is gone; a fixed divisor will overflow "
        "the widget as soon as the shape changes"
    )
    assert "spsDivotExtent()" in body, (
        "drawDivot no longer derives its scale from the measured extent"
    )
    # The divot transform must not reuse the guides' centred scale.
    divot_block = body.split("ctx.rotate(rad);")[1]
    assert "ctx.scale(scale, scale)" not in divot_block, (
        "divot is using the guides' centred scale again -- it assumes the "
        "shape straddles the origin and will overflow"
    )


def test_divot_extent_covers_fringe_and_debris(overlay):
    """Extent must include the overhanging parts, not just the outline.

    Fringe tufts and forward-thrown debris reach past the rim; measuring
    only the outline would still clip them.
    """
    ext = re.search(r"function spsDivotExtent\(\) \{(.*?)\n    \}", overlay, re.S)
    assert ext, "spsDivotExtent not found"
    body = ext.group(1)
    assert "spsDivotOutline" in body, "extent ignores the outline"
    assert "1.6 + 3.6 * t" in body, "extent ignores the fringe tufts"
    assert "- t * 40" in body, "extent ignores the forward debris spray"


def test_divot_edge_is_deterministic(overlay):
    """A random edge would crawl between frames on a projector."""
    assert "Math.random" not in overlay.split("function drawDivot")[1][:6000], (
        "divot uses Math.random; the edge will crawl every repaint"
    )
    assert "function spsDivotNoise" in overlay


def test_projector_roles_are_distinct(overlay):
    """/divot and /tiles are separate windows aimed at separate surfaces."""
    assert "SPS_PROJECTOR_ROLE" in overlay
    assert "function spsRoleAllowsWidget" in overlay

    role = re.search(r"const SPS_PROJECTOR_ROLE = \(\(\) => \{(.*?)\}\)\(\);",
                     overlay, re.S)
    assert role, "projector role resolver not found"
    body = role.group(1)
    assert "'/divot'" in body and "return 'divot'" in body
    assert "'/tiles'" in body and "return 'tiles'" in body
    assert "'/projector'" in body, "/projector must stay an alias for setups"


def test_role_gate_survives_the_layout_fetch(overlay):
    """The scattered-tiles bug: applyLayoutConfig re-showed everything.

    The role must be consulted where display is decided, not applied once
    at startup -- the layout fetch resolves later and would overwrite it.
    """
    apply_fn = re.search(
        r"function applyLayoutConfig\(\) \{(.*?)\n    \}", overlay, re.S)
    assert apply_fn, "applyLayoutConfig not found"
    assert "spsRoleAllowsWidget" in apply_fn.group(1), (
        "applyLayoutConfig ignores the projector role, so /divot and /tiles "
        "will both show whatever the saved layout left visible"
    )


def test_role_gate_does_not_rewrite_saved_visibility(overlay):
    """Viewing /tiles must not persist the divot as hidden."""
    apply_fn = re.search(
        r"function applyLayoutConfig\(\) \{(.*?)\n    \}", overlay, re.S)
    assert apply_fn, "applyLayoutConfig not found"
    body = apply_fn.group(1)
    assert "const isVis = cfg.visible !== false;" in body, (
        "data-visible must reflect the user's saved intent, not the role"
    )
    assert "showHere" in body, "role gate must be a separate display decision"
