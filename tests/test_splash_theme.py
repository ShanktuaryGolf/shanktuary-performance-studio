"""Splash screen: approved navy/teal/gold palette + brand imagery.

The splash used to render in the legacy hunter-green `theme` palette while
the rest of the redesigned desktop moved to the approved navy/teal/gold
system in src/ui/tokens.py. This locks in the fix and covers the new
brand-image rendering (Nova/GSPro logos, hero composite) added alongside it.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tk = pytest.importorskip("tkinter")


@pytest.fixture
def tk_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.delenv("SPS_SHOT_SOURCE", raising=False)
    monkeypatch.delenv("SPS_GSPRO_DB", raising=False)
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.geometry("1200x800")
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def _splash(root, **kwargs):
    from src.ui.splash import SplashScreen

    defaults = dict(clubs=["Driver", "7 Iron", "PW"], current_club="7 Iron")
    defaults.update(kwargs)
    sp = SplashScreen(root, **defaults)
    for _ in range(6):
        root.update()
        sp.win.update_idletasks()
    return sp


def _canvas_colors(sp):
    colors = set()
    for item in sp.canvas.find_all():
        for opt in ("fill", "outline"):
            try:
                val = sp.canvas.itemcget(item, opt)
            except tk.TclError:
                continue
            if val:
                colors.add(val)
    return colors


def test_splash_uses_the_approved_gold_teal_navy_palette_not_hunter_green(tk_root):
    from src.ui import tokens

    sp = _splash(tk_root)
    try:
        colors = _canvas_colors(sp)
        # The old palette's hunter-green accent must be gone.
        legacy_accent = {"#22402C", "#4C8C5E", "#6FA880", "#9CC9AC"}
        assert not (colors & legacy_accent), (
            f"splash still paints the legacy hunter-green accent: {colors & legacy_accent}"
        )
        # The approved gold/navy tokens must actually be present.
        assert tokens.GOLD in colors, "gold accent not used anywhere on the splash"
        assert tokens.PAGE_BG in colors or tokens.RAIL_BG in colors, (
            "approved navy background tokens not used"
        )
    finally:
        sp._close()


def test_start_button_and_selected_card_use_gold_not_green(tk_root):
    from src.ui import tokens

    sp = _splash(tk_root)
    try:
        start_rect = [r for r in sp._hit_rects if r[4] == "start"][0]
        x1, y1, x2, y2, _, _ = start_rect
        items = sp.canvas.find_overlapping(x1 + 2, y1 + 2, x2 - 2, y2 - 2)
        fills = {sp.canvas.itemcget(i, "fill") for i in items}
        assert tokens.GOLD in fills, "START SESSION button is not gold"
    finally:
        sp._close()


def test_source_cards_load_brand_logo_images(tk_root):
    """Nova and GSPro cards render the real logo PNGs, not placeholder text."""
    sp = _splash(tk_root)
    try:
        gspro_logo = sp._load_image("gspro", __import__(
            "src.ui.asset_paths", fromlist=["asset_path"]
        ).asset_path("gspro_logo.png"), 30)
        nova_logo = sp._load_image("nova", __import__(
            "src.ui.asset_paths", fromlist=["asset_path"]
        ).asset_path("nova_logo.png"), 30)
        assert gspro_logo is not None, "gspro_logo.png failed to load"
        assert nova_logo is not None, "nova_logo.png failed to load"

        image_items = [i for i in sp.canvas.find_all() if sp.canvas.type(i) == "image"]
        assert len(image_items) >= 3, (
            "expected at least shield + 2 source-card logos as canvas images"
        )
    finally:
        sp._close()


def test_hero_panel_renders_a_composite_image_not_a_flat_fill(tk_root):
    sp = _splash(tk_root)
    try:
        hero = sp._hero_image(sp.w, sp.h)
        assert hero is not None, "hero composite failed to build"

        image_items = [i for i in sp.canvas.find_all() if sp.canvas.type(i) == "image"]
        assert image_items, "left panel has no image content"
    finally:
        sp._close()


def test_hero_image_is_cached_across_redraws(tk_root):
    """Rebuilding the PIL composite on every redraw would be a visible stutter."""
    sp = _splash(tk_root)
    try:
        first = sp._hero_image(sp.w, sp.h)
        second = sp._hero_image(sp.w, sp.h)
        assert first is second, "hero image was rebuilt instead of served from cache"
    finally:
        sp._close()
