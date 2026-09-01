"""Eleventh-pass shell: approved Shanktuary PNG branding only.

Navigation, Recent Shots, controls, and hit targets remain owned by v10/v9.
This pass replaces all code-drawn brand glyphs/wordmarks with approved image
assets so the header and packaged app use the exact brand artwork.
"""

from __future__ import annotations

from PIL import Image, ImageTk

import shell_redesign_v9 as v9
import shell_redesign_v10 as v10
import theme
from src.ui.asset_paths import asset_path

BLUE = v10.BLUE
BLUE_LINE = v10.BLUE_LINE
BLUE_TEXT = v10.BLUE_TEXT
ORANGE = v10.ORANGE
GOOD = v9.GOOD

# Shared resolver handles both the repository root and PyInstaller's _MEIPASS
# data directory. Do not derive these paths from this legacy module's __file__:
# PyInstaller flattens modules differently from a source checkout.
SHIELD_PATH = asset_path("shanktuary_shield.png")
WORDMARK_PATH = asset_path("shanktuary_wordmark.png")
LOCKUP_PATH = asset_path("shanktuary_lockup.png")


def _load_brand_image(app, attr, path, target_h):
    """Load an approved transparent PNG once at the exact display height."""
    key_attr = f"{attr}_key"
    key = (path, int(target_h))
    if getattr(app, key_attr, None) == key:
        return getattr(app, attr)

    try:
        im = Image.open(path).convert("RGBA")
        ratio = target_h / max(1, im.height)
        target_w = max(1, round(im.width * ratio))
        im = im.resize((target_w, int(target_h)), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(im)
    except Exception:
        photo = None

    setattr(app, attr, photo)
    setattr(app, key_attr, key)
    return photo


def paint_nav(app, h):
    return v10.paint_nav(app, h)


def paint_sidebar(app, w, h):
    return v10.paint_sidebar(app, w, h)


def paint_top_header(app, w, h, offset_x=0):
    c = app.canvas
    hh = 52

    # Preserve the accepted textured equipment header, but none of v9's
    # generated logo/wordmark artwork.
    c.create_image(0, 0, image=v9._brand_surface(app, w, hh), anchor="nw")

    # Exact approved art. Keep shield and wordmark as separate PNGs so each can
    # be sized cleanly in the shallow header without distorting the lockup.
    shield = _load_brand_image(app, "_brand_shield_v11_img", SHIELD_PATH, 43)
    wordmark = _load_brand_image(app, "_brand_wordmark_v11_img", WORDMARK_PATH, 39)
    if shield is not None:
        c.create_image(10, 4, image=shield, anchor="nw")
    if wordmark is not None:
        c.create_image(58, 7, image=wordmark, anchor="nw")

    # Utility cluster is unchanged from the accepted shell.
    right = w - 10
    y1, y2 = 7, 45
    fs_w, tools_w, dex_w, club_w, gap = 38, 86, 58, 112, 7

    app.fullscreen_btn_rect = (right - fs_w, y1, right, y2)
    right -= fs_w + gap
    app.tools_btn_rect = (right - tools_w, y1, right, y2)
    right -= tools_w + gap
    app.dexterity_btn_rect = (right - dex_w, y1, right, y2)
    right -= dex_w + gap
    app.club_btn_rect = (right - club_w, y1, right, y2)

    club_rect = app.club_btn_rect
    status_x = club_rect[0] - 82
    c.create_oval(status_x, 23, status_x + 8, 31, fill=GOOD, outline="")
    c.create_text(status_x + 14, 27, text="Ready", fill=theme.TEXT_2,
                  font=(v9.v4._font(), 9, "bold"), anchor="w")

    v9._utility_button(c, app.club_btn_rect,
                       f"{getattr(app, 'current_club', 'Club')}  ▼",
                       bool(getattr(app, "show_club_menu", False)))
    hand = "LH" if getattr(app, "is_left_handed", False) else "RH"
    v9._utility_button(c, app.dexterity_btn_rect, hand)
    v9._utility_button(c, app.tools_btn_rect, "Tools  ▼",
                       bool(getattr(app, "show_tools_menu", False)))
    v9._utility_button(c, app.fullscreen_btn_rect, "⛶")

    # Preserve deterministic design-owned hit targets.
    app.design_club_btn_rect = tuple(app.club_btn_rect) if app.club_btn_rect else None
    app.design_dexterity_btn_rect = tuple(app.dexterity_btn_rect) if app.dexterity_btn_rect else None
    app.design_tools_btn_rect = tuple(app.tools_btn_rect) if app.tools_btn_rect else None
    app.design_fullscreen_btn_rect = tuple(app.fullscreen_btn_rect) if app.fullscreen_btn_rect else None
