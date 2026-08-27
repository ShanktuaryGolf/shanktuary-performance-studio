"""Tools menu: floor-projection entries must exist AND be wired.

Guards the dead-button class of bug -- a row rendered into the menu whose
action key no action handler matches, so clicking it does nothing.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "shanktuary_performance_studio.py"


def _source():
    return APP.read_text()


def test_floor_projection_offers_both_surfaces():
    """/divot and /tiles are separate windows, so both need menu entries."""
    src = _source()
    section = re.search(
        r'\("FLOOR PROJECTION", \[(.*?)\]\),', src, re.S)
    assert section, "FLOOR PROJECTION section not found in the tools menu"
    body = section.group(1)

    assert "open_tiles" in body, (
        "the tools menu offers no way to open /tiles, so the metric-tile "
        "projector surface is unreachable from the app"
    )
    assert "open_divot" in body
    assert "/tiles" in body, "no /tiles URL shown in the floor projection section"


def test_every_tools_menu_action_is_handled():
    """A menu row with no matching handler renders but does nothing."""
    src = _source()

    # Action keys rendered into the menu.
    sections = re.search(
        r"sections = \[(.*?)\n        \]", src, re.S)
    assert sections, "tools menu sections block not found"
    rendered = set(re.findall(r'\("([a-z0-9_]+)", "', sections.group(1)))
    assert rendered, "no action keys parsed from the tools menu"

    # Action keys the click dispatcher compares against.
    handler = re.search(
        r"if self\.show_tools_menu:(.*?)\n            self\.show_tools_menu = False",
        src, re.S)
    assert handler, "tools menu click handler not found"
    handled = set(re.findall(r'action == "([a-z0-9_]+)"', handler.group(1)))

    missing = rendered - handled
    assert not missing, (
        f"tools menu rows with no handler (clicking them does nothing): "
        f"{sorted(missing)}"
    )


def test_tiles_and_divot_open_different_urls():
    """Both entries must not point at the same surface."""
    src = _source()
    m = re.search(
        r"if self\.show_tools_menu:(.*?)\n            self\.show_tools_menu = False",
        src, re.S)
    assert m, "tools menu click handler not found"
    handler = m.group(1)

    def url_for(action):
        m = re.search(
            rf'action == "{action}":\s*\n\s*(?:self\.copy_to_clipboard|webbrowser\.open)'
            rf'\(f"http://localhost:\{{obs_server\.OBS_PORT\}}([^"]*)"\)',
            handler)
        return m.group(1) if m else None

    assert url_for("open_divot") == "/divot"
    assert url_for("open_tiles") == "/tiles", (
        "open_tiles does not open /tiles -- the two projector surfaces would "
        "show the same thing"
    )
    assert url_for("copy_tiles_url") == "/tiles"


def test_menu_panel_height_is_derived_not_hardcoded():
    """A hand-summed box_h drifts out of sync and clips the last row.

    That is exactly what happened: the constant said 624 while the layout
    walk ended at 630, so Open Setup hung 6px past the border.
    """
    src = _source()
    fn = re.search(r"def draw_tools_flyout_menu\(self, w, h\):(.*?)\n    def ",
                   src, re.S)
    assert fn, "draw_tools_flyout_menu not found"
    body = fn.group(1)

    assert "box_h = (" not in body, (
        "panel height is a hand-summed constant again; it will drift out of "
        "sync with the layout walk the next time a row is added"
    )
    assert "y2 = sb[3] + pad_bottom" in body, (
        "panel must wrap the last element actually drawn"
    )
    assert "self.canvas.coords(panel" in body, (
        "panel must be created first and resized in place, so it keeps its "
        "stacking position behind this menu's content"
    )

    # Strip comments -- the rationale for avoiding tag_lower is documented
    # in one, and matching that would defeat the check.
    code = "\n".join(re.sub(r"#.*$", "", ln) for ln in body.splitlines())
    assert "tag_lower" not in code, (
        "tag_lower moves the panel to the bottom of the WHOLE canvas display "
        "list, putting it behind the app background -- the menu renders "
        "transparent"
    )

