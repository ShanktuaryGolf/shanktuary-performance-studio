"""One logical-pixel coordinate system for the canvas desktop (not OBS).

Legacy painters and their hit rectangles remain in 96-DPI design coordinates.
Only this boundary converts to display pixels; point fonts cannot independently
follow the desktop's font DPI and collide with fixed geometry.
"""
from __future__ import annotations

import copy
import json
import math
import os
import tempfile
import tkinter as tk
import tkinter.font as tkfont
from collections import OrderedDict
from pathlib import Path

from PIL import ImageTk

from user_data import get_data_dir

CHOICES = ("Auto", "100%", "125%", "150%", "175%", "200%")
BASE_DPI = 96


def settings_path():
    return get_data_dir() / "desktop_display.json"


def load_choice(path=None):
    try:
        value = json.loads(Path(path or settings_path()).read_text())["ui_scale"]
        return value if value in CHOICES else "Auto"
    except (OSError, ValueError, KeyError, TypeError):
        return "Auto"


def save_choice(value, path=None):
    if value not in CHOICES:
        raise ValueError("Unsupported UI scale")
    path = Path(path or settings_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".display-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as out:
            json.dump({"ui_scale": value}, out)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def resolve_scale(choice, dpi):
    if choice != "Auto" and choice in CHOICES:
        return int(choice[:-1]) / 100
    if not math.isfinite(dpi) or dpi <= 0:
        dpi = BASE_DPI
    return max(1.0, min(3.0, round(dpi / BASE_DPI * 4) / 4))


def configure_root(root):
    """Initialize once before onboarding, retaining the unmodified display DPI."""
    if not hasattr(root, "_sps_original_dpi"):
        root._sps_original_dpi = float(root.winfo_fpixels("1i"))
    choice = load_choice()
    scale = resolve_scale(choice, root._sps_original_dpi)
    root._sps_ui_scale = scale
    root.tk.call("tk", "scaling", BASE_DPI / 72 * scale)
    return choice, scale


def logical_font(master=None, **kwargs):
    """Font metrics in design pixels, independent of Tk's native-dialog DPI."""
    size = kwargs.pop("size", 10)
    kwargs["size"] = -max(1, round(size * BASE_DPI / 72)) if size > 0 else size
    return tkfont.Font(root=master, **kwargs)


class ScaledCanvas(tk.Canvas):
    """Scale primitives, raster assets, measured boxes, and pointer input once."""
    def __init__(self, master, *, scale=1.0, minimum_size=(1100, 900), **kwargs):
        self.ui_scale = scale
        self.minimum_size = minimum_size
        self._scaled_images = OrderedDict()
        self._frame_images = []
        super().__init__(master, **kwargs)

    def winfo_width(self):
        return max(self.minimum_size[0], int(super().winfo_width() / self.ui_scale))

    def winfo_height(self):
        return max(self.minimum_size[1], int(super().winfo_height() / self.ui_scale))

    def update_scrollregion(self):
        self.configure(scrollregion=(0, 0, self.winfo_width()*self.ui_scale,
                                     self.winfo_height()*self.ui_scale))

    def bind(self, sequence=None, func=None, add=None):
        if func is not None and sequence and sequence != "<Configure>":
            original = func
            def converted(event):
                event = copy.copy(event)
                if isinstance(getattr(event, "x", None), (int, float)):
                    event.x = self.canvasx(event.x) / self.ui_scale
                    event.y = self.canvasy(event.y) / self.ui_scale
                return original(event)
            func = converted
        return super().bind(sequence, func, add)

    def _font(self, spec):
        if isinstance(spec, (tuple, list)):
            parts = list(spec)
            size = int(parts[1]) if len(parts) > 1 else 10
            pixels = size * BASE_DPI / 72 if size > 0 else abs(size)
            return (parts[0], -max(1, round(pixels*self.ui_scale)), *parts[2:])
        font = spec if isinstance(spec, tkfont.Font) else tkfont.nametofont(str(spec), root=self)
        actual = font.actual()
        size = int(font.cget("size"))
        actual.pop("size")
        pixels = size * BASE_DPI / 72 if size > 0 else abs(size)
        actual["size"] = -max(1, round(pixels*self.ui_scale))
        result = tkfont.Font(root=self, **actual)
        self._frame_images.append(result)  # retain named resources for this frame
        return result

    def _image(self, source):
        if not source or self.ui_scale == 1:
            return source
        key = (str(source), self.ui_scale)
        image = self._scaled_images.get(key)
        if image is None:
            # Both app image implementations are Pillow-backed Tk photos.
            pixels = ImageTk.getimage(source)
            image = ImageTk.PhotoImage(pixels.resize(
                (max(1, round(pixels.width*self.ui_scale)),
                 max(1, round(pixels.height*self.ui_scale)))), master=self)
            self._scaled_images[key] = image
            while len(self._scaled_images) > 96:
                self._scaled_images.popitem(last=False)
        self._frame_images.append(image)
        return image

    def _create(self, itemType, args, kw):
        args = tk._flatten(args)
        if args and isinstance(args[-1], dict):
            kw = dict(args[-1], **kw)
            args = args[:-1]
        kw = dict(kw)
        for name in ("width", "height", "activewidth", "disabledwidth", "offset"):
            if isinstance(kw.get(name), (int, float)):
                kw[name] *= self.ui_scale
        for name in ("dash", "arrowshape"):
            if isinstance(kw.get(name), (tuple, list)):
                kw[name] = tuple(max(1, round(n*self.ui_scale)) for n in kw[name])
        if "font" in kw:
            kw["font"] = self._font(kw["font"])
        for name in ("image", "activeimage", "disabledimage"):
            if name in kw:
                kw[name] = self._image(kw[name])
        return super()._create(itemType, tuple(x*self.ui_scale for x in args), kw)

    def bbox(self, *args):
        box = super().bbox(*args)
        return tuple(v/self.ui_scale for v in box) if box else None

    def coords(self, *args):
        if len(args) > 1:
            return super().coords(args[0], *(v*self.ui_scale for v in tk._flatten(args[1:])))
        return [v/self.ui_scale for v in super().coords(*args)]

    def move(self, tagOrId, xAmount, yAmount):
        return super().move(tagOrId, xAmount*self.ui_scale, yAmount*self.ui_scale)

    def delete(self, *args):
        result = super().delete(*args)
        if "all" in args:
            self._frame_images.clear()
        return result
