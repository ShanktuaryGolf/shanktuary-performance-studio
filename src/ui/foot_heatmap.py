"""Estimated foot-shaped load display, never a plantar-pressure measurement.

The source frame has four displayed board zones in kg: TL, TR, BL, BR. A
displayed side contributes only two values, front and back. The silhouette is
illustrative; its color is a longitudinal interpolation of those two values,
with no lateral field, anatomical split, extra sensors or inferred contact.
Both sides use the largest valid zone in the frame as the color-scale maximum.
Loads below 1 kg remain neutral so small unloaded-board noise cannot become
the hottest color. This is a display threshold, not a change to sensor data.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageTk

import theme

from . import tokens as T

_LEVELS = 128
_PHOTO_CACHE_SIZE = 24
_MAX_IMAGE_HEIGHT = 512
_MIN_DISPLAY_LOAD_KG = 1.0


@dataclass(frozen=True)
class SideLoads:
    front: float | None
    back: float | None
    maximum: float
    share: float | None
    total: float | None

    @property
    def available(self):
        return self.front is not None and self.back is not None

    @property
    def low_load(self):
        return self.available and self.total is not None and self.total < _MIN_DISPLAY_LOAD_KG


def _measured(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def read_side_loads(latest, is_left=True):
    """Read the frame without changing it or deriving absent raw measurements."""
    frame = latest if isinstance(latest, dict) else {}
    raw = frame.get("raw_cells")
    values = (
        tuple(_measured(value) for value in raw)
        if isinstance(raw, (list, tuple)) and len(raw) == 4
        else (None,) * 4
    )
    front, back = (values[0], values[2]) if is_left else (values[1], values[3])
    share = _measured(frame.get("pct_left" if is_left else "pct_right"))
    if share is not None and share > 100:
        share = None
    maximum = max((value for value in values if value is not None), default=0.0)
    total = _measured(frame.get("total_kg"))
    if total is None and all(value is not None for value in values):
        total = sum(values)
    return SideLoads(front, back, maximum, share, total)


def _levels(loads):
    if not loads.available:
        return None, None
    if loads.low_load or loads.maximum == 0:
        return 0, 0
    return tuple(round(value / loads.maximum * _LEVELS) for value in (loads.front, loads.back))


@lru_cache(maxsize=16)
def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _color(level):
    """A continuous relative-load ramp; zero stays an unheated navy."""
    stops = ((0.0, T.SURFACE_2), (0.45, T.TEAL), (0.75, T.TEAL_TEXT), (1.0, T.GOLD))
    level = max(0.0, min(1.0, level))
    for (lo, first), (hi, second) in zip(stops, stops[1:]):
        if level <= hi:
            fraction = (level - lo) / (hi - lo)
            return tuple(round(a + (b - a) * fraction) for a, b in zip(_rgb(first), _rgb(second)))
    return _rgb(T.GOLD)


@lru_cache(maxsize=2)
def _components(is_left):
    """Generic silhouette outlines. Geometry never responds to sensor values."""
    start = (0.74, 0.23)
    curves = (
        ((0.92, 0.32), (0.85, 0.44), (0.71, 0.50)),
        ((0.53, 0.58), (0.57, 0.68), (0.66, 0.78)),
        ((0.78, 0.99), (0.41, 1.03), (0.31, 0.93)),
        ((0.16, 0.82), (0.18, 0.66), (0.16, 0.52)),
        ((0.12, 0.36), (0.21, 0.23), (0.38, 0.20)),
        ((0.50, 0.18), (0.63, 0.19), start),
    )
    body = [start]
    for control_a, control_b, end in curves:
        for step in range(1, 17):
            t = step / 16
            body.append(tuple(
                (1 - t) ** 3 * start[i] + 3 * (1 - t) ** 2 * t * control_a[i]
                + 3 * (1 - t) * t ** 2 * control_b[i] + t ** 3 * end[i]
                for i in (0, 1)
            ))
        start = end
    # These are outlines, not individual toe sensors or colored hotspots.
    ellipses = (
        (0.64, 0.015, 0.88, 0.215),
        (0.47, 0.02, 0.625, 0.17),
        (0.315, 0.065, 0.455, 0.20),
        (0.19, 0.125, 0.315, 0.245),
        (0.095, 0.205, 0.205, 0.31),
    )
    components = [body]
    for x0, y0, x1, y1 in ellipses:
        components.append([
            ((x0 + x1) / 2 + (x1 - x0) / 2 * math.cos(i * math.tau / 32),
             (y0 + y1) / 2 + (y1 - y0) / 2 * math.sin(i * math.tau / 32))
            for i in range(32)
        ])
    return tuple(tuple((x if is_left else 1 - x, y) for x, y in points) for points in components)


@lru_cache(maxsize=16)
def _masks(width, height, is_left):
    scale = 3
    mask = Image.new("L", (width * scale, height * scale), 0)
    draw = ImageDraw.Draw(mask)
    for points in _components(True):
        draw.polygon([(x * (width * scale - 1), y * (height * scale - 1)) for x, y in points], fill=255)
    mask = mask.resize((width, height), Image.Resampling.LANCZOS)
    # Transposing the raster guarantees an exact left/right mirror at any size.
    if not is_left:
        mask = mask.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    edge = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(3)))
    return mask, edge


def _foot_pixels(width, height, is_left, front_level, back_level):
    """Render in O(height) drawing calls with cached, antialiased geometry."""
    mask, edge = _masks(width, height, is_left)
    pixels = Image.new("RGBA", (width, height), T.SURFACE)
    if front_level is not None and back_level is not None:
        draw = ImageDraw.Draw(pixels)
        for row in range(height):
            t = row / max(1, height - 1)
            level = ((1 - t) * front_level + t * back_level) / _LEVELS
            draw.line((0, row, width - 1, row), fill=_color(level))
    # A quiet rim makes the unloaded/unavailable silhouette recognizable.
    rim = Image.new("RGBA", pixels.size, T.TEAL_SOFT)
    pixels = Image.composite(rim, pixels, edge.point(lambda value: round(value * 0.45)))
    pixels.putalpha(mask)
    return pixels


def _clip_y(points, boundary, keep_above):
    output = []
    previous = points[-1]
    previous_inside = previous[1] >= boundary if keep_above else previous[1] <= boundary
    for current in points:
        inside = current[1] >= boundary if keep_above else current[1] <= boundary
        if inside != previous_inside:
            fraction = (boundary - previous[1]) / (current[1] - previous[1])
            output.append((previous[0] + (current[0] - previous[0]) * fraction, boundary))
        if inside:
            output.append(current)
        previous, previous_inside = current, inside
    return output


def _vector_foot(canvas, x0, y0, width, height, is_left, front, back):
    """Bounded recorder/headless fallback with the same longitudinal field."""
    components = _components(is_left)
    for points in components:
        coords = [v for x, y in points for v in (x0 + x * width, y0 + y * height)]
        canvas.create_polygon(*coords, fill=T.SURFACE, outline="", tags="estimated-foot-shape")
    if front is not None and back is not None:
        bands = 40
        for band in range(bands):
            lo, hi = band / bands, (band + 1) / bands
            t = (lo + hi) / 2
            color = "#%02x%02x%02x" % _color(((1 - t) * front + t * back) / _LEVELS)
            for points in components:
                clipped = _clip_y(points, lo, True)
                if clipped:
                    clipped = _clip_y(clipped, hi, False)
                if len(clipped) >= 3:
                    canvas.create_polygon(
                        *[v for x, y in clipped for v in (x0 + x * width, y0 + y * height)],
                        fill=color, outline="", tags="estimated-foot-gradient",
                    )
    for points in components:
        canvas.create_polygon(
            *[v for x, y in points for v in (x0 + x * width, y0 + y * height)],
            fill="", outline=T.TEAL_SOFT, width=0.7, tags="estimated-foot-outline",
        )


def _draw_foot(canvas, x0, y0, width, height, is_left, loads):
    levels = _levels(loads)
    real = getattr(canvas, "_canvas", canvas)
    if not isinstance(real, tk.Canvas):
        _vector_foot(canvas, x0, y0, width, height, is_left, *levels)
        return
    width, height = max(1, round(width)), max(1, round(height))
    scale = getattr(real, "ui_scale", 1.0)
    key = (width, height, bool(is_left), *levels, scale)
    cache = getattr(real, "_estimated_foot_cache", None)
    if cache is None:
        cache = real._estimated_foot_cache = OrderedDict()
    photo = cache.get(key)
    if photo is None:
        pixels = _foot_pixels(width, height, is_left, *levels)
        if scale != 1:
            # Same logical raster and same resize as ScaledCanvas, but upload
            # once instead of Tk upload -> readback -> resize -> second upload.
            pixels = pixels.resize((max(1, round(width * scale)), max(1, round(height * scale))))
        photo = ImageTk.PhotoImage(pixels, master=real)
        photo._sps_device_scale = scale
        cache[key] = photo
        while len(cache) > _PHOTO_CACHE_SIZE:
            cache.popitem(last=False)
    else:
        cache.move_to_end(key)
    # Coordinates still follow ViewportCanvas and ScaledCanvas. The marker
    # prevents a second image resize while cached/retained owners keep it alive.
    canvas.create_image(x0, y0, anchor="nw", image=photo, tags="estimated-foot-image")


def _label(canvas, x, y, value, size, color, width, bold=False):
    """Fit width only, retaining a readable logical-pixel font floor."""
    item = canvas.create_text(
        x, y, text=value, fill=color,
        font=(theme.ui_font(), -size, "bold" if bold else "normal"),
        anchor="center", tags="estimated-foot-label",
    )
    box = canvas.bbox(item)
    real = getattr(canvas, "_canvas", canvas)
    scale = getattr(real, "ui_scale", 1.0)
    while box and size > 9 and box[2] - box[0] > width:
        size -= 1
        canvas.itemconfigure(item, font=(theme.ui_font(), -max(1, round(size * scale)),
                                         "bold" if bold else "normal"))
        box = canvas.bbox(item)
    return item


def _text_height(canvas, item, fallback):
    box = canvas.bbox(item)
    return box[3] - box[1] if box else fallback


def _place_text_top(canvas, item, top, fallback):
    box = canvas.bbox(item)
    if box:
        x, y = canvas.coords(item)
        canvas.coords(item, x, y + top - box[1])
        return canvas.bbox(item)[3]
    return top + fallback


def _kg(value):
    if value is None:
        return "--"
    return f"{value:.1f} kg" if value < 100000 else f"{value:.3g} kg"


def draw_estimated_foot_heatmap(app, x1, y1, w, h, is_left=True, latest=None):
    """Illustrate measured zones with readable, measured text groups.

    Short cards omit the duplicated subtitle; the enclosing Lab pane already
    says estimated. Raw values and the not-plantar-pressure notice remain.
    """
    if w < 140 or h < 150:
        return
    canvas = app.canvas
    loads = read_side_loads(latest, is_left)
    compact = w < 200 or h < 260
    cx, y2 = x1 + w / 2, y1 + h
    side = "LEFT" if is_left else "RIGHT"
    role = "LEAD" if is_left != bool(getattr(app, "is_left_handed", False)) else "TRAIL"
    role_item = _label(canvas, cx, y1 + 12, f"{role} SIDE ({side})",
                       11 if compact else 12, T.TEXT_2, w - 10)
    header_end = _place_text_top(canvas, role_item, y1 + 4, 18)
    if not compact:
        title = _label(canvas, cx, y1 + 34, "Estimated foot load", 13,
                       T.TEXT, w - 10, bold=True)
        header_end = _place_text_top(canvas, title, header_end + 3, 20)
    top = header_end + 5

    status = ("Per-cell data unavailable" if not loads.available else
              ("No load detected" if loads.total == 0 else "Low load · under 1 kg")
              if loads.low_load else " ")
    share = f"Share of load: {loads.share:.0f}%" if loads.share is not None else "Share of load: --"
    status_item = _label(canvas, cx, y2 - 48, status, 9, T.TEXT_2, w - 8)
    share_item = _label(canvas, cx, y2 - 29, share, 10 if compact else 11, T.TEXT_2, w - 10)
    notice_item = _label(canvas, cx, y2 - 10, "Not plantar pressure", 9, T.TEXT_2, w - 10)
    cursor = y2 - 4
    for item, fallback in ((notice_item, 14), (share_item, 16), (status_item, 14)):
        height = _text_height(canvas, item, fallback)
        _place_text_top(canvas, item, cursor - height, fallback)
        cursor -= height + 3
    bottom = cursor - 2
    area_h = max(1, bottom - top)

    foot_h = min(area_h, _MAX_IMAGE_HEIGHT, (w * 0.49 - 8) / .63)
    foot_w = foot_h * .63
    _draw_foot(canvas, x1 + w * .25 - foot_w / 2, top + (area_h - foot_h) / 2,
               foot_w, foot_h, is_left, loads)

    raw_x, raw_width = x1 + w * .755, w * .45 - 6
    pair_gap, inner_gap = (4, 2) if compact else (8, 4)
    pair_h = (area_h - pair_gap) / 2
    for index, (name, value) in enumerate((
        ("Front (TL)" if is_left else "Front (TR)", loads.front),
        ("Back (BL)" if is_left else "Back (BR)", loads.back),
    )):
        pair_top = top + index * (pair_h + pair_gap)
        label = _label(canvas, raw_x, pair_top + pair_h * .25, name,
                       9 if compact else 11, T.TEXT_2, raw_width)
        amount_size = 13 if compact else 19
        amount = _label(canvas, raw_x, pair_top + pair_h * .7, _kg(value),
                        amount_size, T.TEXT if value is not None else T.TEXT_3,
                        raw_width, bold=True)
        label_box, amount_box = canvas.bbox(label), canvas.bbox(amount)
        if label_box and amount_box:
            real = getattr(canvas, "_canvas", canvas)
            scale = getattr(real, "ui_scale", 1.0)
            while (amount_size > 11 and label_box[3] - label_box[1] + inner_gap
                   + amount_box[3] - amount_box[1] > pair_h - 2):
                amount_size -= 1
                canvas.itemconfigure(amount, font=(theme.ui_font(),
                    -max(1, round(amount_size * scale)), "bold"))
                amount_box = canvas.bbox(amount)
            used_h = label_box[3] - label_box[1] + inner_gap + amount_box[3] - amount_box[1]
            group_top = pair_top + (pair_h - used_h) / 2
            label_end = _place_text_top(canvas, label, group_top, 14)
            _place_text_top(canvas, amount, label_end + inner_gap, 18)
