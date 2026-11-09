"""Shared visual assets; decorative scenery never represents telemetry."""

import tkinter as tk
from collections import OrderedDict

from PIL import Image, ImageOps, ImageTk

from .asset_paths import asset_path


def range_landscape(canvas, x0, y0, x1, y1, sky_crop=0.0):
    real = getattr(canvas, "_canvas", canvas)
    if not isinstance(real, tk.Canvas):
        return False
    width, height = max(1, round(x1 - x0)), max(1, round(y1 - y0))
    cache = getattr(real, "_concept_scene_cache", None)
    if cache is None:
        cache = OrderedDict()
        real._concept_scene_cache = cache
    key = (width, height, sky_crop)
    photo = cache.get(key)
    if photo is None:
        try:
            with Image.open(asset_path("studio_range_landscape.png")) as source:
                photo = ImageTk.PhotoImage(
                    source.crop((0, int(source.height * sky_crop), source.width, source.height)).resize((width, height), Image.Resampling.LANCZOS), master=real
                )
        except OSError:
            return False
        cache[key] = photo
        while len(cache) > 8:
            cache.popitem(last=False)
    canvas.create_image(x0, y0, image=photo, anchor="nw")
    return True


def graphite_contact_pixels(pixels):
    """Apply a display-only steel finish without changing the contact sprite.

    This is a UI appearance filter, not alternate physical club artwork. The
    original alpha, dimensions, grooves and every geometric control point stay
    fixed. A dark middle tone and bright upper highlights retain the source's
    steel rim rather than flattening the whole face into a dark silhouette.
    """
    graphite = ImageOps.colorize(
        pixels.convert("L"),
        black="#0E1C23",
        mid="#314650",
        white="#DFE9EC",
        midpoint=180,
    ).convert("RGBA")
    graphite.putalpha(pixels.getchannel("A"))
    return graphite


def visible_contact_art(app, image, dark=False):
    """Trim transparent padding for layout while retaining virtual face origin.

    The pressure/contact coordinate model remains tied to the original sprite;
    returned offsets place the cropped pixels at precisely the same location.
    """
    key = (str(image), bool(dark))
    cache = getattr(app, "_concept_contact_cache", None)
    if cache is None:
        cache = OrderedDict()
        app._concept_contact_cache = cache
    if key not in cache:
        pixels = ImageTk.getimage(image).convert("RGBA")
        box = pixels.getchannel("A").getbbox() or (0, 0, pixels.width, pixels.height)
        if dark:
            pixels = graphite_contact_pixels(pixels)
        trimmed = ImageTk.PhotoImage(pixels.crop(box), master=app.root)
        cache[key] = (trimmed, box[0] - pixels.width / 2, box[1] - pixels.height / 2)
        while len(cache) > 16:
            cache.popitem(last=False)
    return cache[key]


def club_face_kind(club):
    """Choose a schematic family without changing the selected shot's club."""
    import re

    name = str(club or "").strip().lower()
    compact = re.sub(r"[\s_-]+", "", name)
    if "putter" in name or compact in {"pt", "putt", "p"}:
        return "putter"
    if ("driver" in name or "wood" in name or "hybrid" in name
            or compact in {"dr", "d"} or re.fullmatch(r"\d+[wh]", compact)):
        return "driver"
    return "iron"


def club_face_layout(club, rect, left_handed=False):
    """Fit the approved artwork and retain the existing mm-coordinate contract.

    The origins/scales below locate a generic *schematic* face, not a calibrated
    model of the user's equipment. The stored heel/high millimetres, input
    limits and handedness convention remain owned by FaceGeometry. Only their
    presentation transform changes; drawing and click conversion stay inverse.
    """
    from src.analytics.strike import (
        FACE_PX_PER_MM,
        FACE_SWEET_DX,
        FACE_SWEET_DY,
        FaceGeometry,
    )

    kind = club_face_kind(club)
    # Source artwork is 1536 x 1024. Origins lie in its grooved hitting area.
    origin_x, origin_y, source_px_per_mm = {
        "iron": (650, 610, 12),
        "driver": (700, 565, 16),
        "putter": (770, 760, 7),
    }[kind]
    x0, y0, x1, y1 = rect
    pixel_h = max(1, int(min(max(1, y1 - y0), max(1, x1 - x0) / 1.5)))
    pixel_w = int(pixel_h * 1.5)
    left = (x0 + x1 - pixel_w) / 2
    top = (y0 + y1 - pixel_h) / 2
    scale = pixel_h / 1024
    sx = left + ((1536 - origin_x) if left_handed else origin_x) / 1536 * pixel_w
    sy = top + origin_y * scale
    size = source_px_per_mm * scale / FACE_PX_PER_MM
    sign = 1 if left_handed else -1
    geometry = FaceGeometry(sx - FACE_SWEET_DX * size * sign,
                            sy + FACE_SWEET_DY * size, size, left_handed)
    return asset_path(f"studio_{kind}_face.png"), (left, top, left + pixel_w, top + pixel_h), geometry
