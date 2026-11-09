"""Large aim-calibration dialog over the existing measurement/shot workflows."""

import math

from src.analytics.aim import (
    MAX_AIM_OFFSET_DEG,
    MIN_CALIBRATION_SHOTS,
    offset_from_geometry,
    offset_from_shots,
)

from . import tokens as T
from .concept_shell import panel, text, veil


def angle(app):
    try:
        return offset_from_geometry(
            float(app.aim_modal_distance), float(app.aim_modal_lateral or 0)
        )
    except (TypeError, ValueError):
        return None


def draw(app, w, h):
    c = app.canvas
    veil(c, w, h)
    width, height = min(850, w - 60), min(740, h - 40)
    x0 = (w + 272 - width) / 2
    x1 = x0 + width
    y0 = (h - height) / 2
    y1 = y0 + height
    app.aim_modal_box_rect = (x0, y0, x1, y1)
    panel(c, x0, y0, x1, y1, outline=T.TEAL_LINE, r=18)
    text(c, x0 + 30, y0 + 44, "Aim calibration", 30, bold=True)
    app.concept_aim_rects = []

    def button(rect, label, action, active=False):
        panel(
            c,
            *rect,
            fill=T.ACTIVE_BG if active else T.PAGE_BG,
            outline=T.TEAL_LINE if active else T.TEAL_SOFT,
            r=11,
        )
        text(
            c,
            (rect[0] + rect[2]) / 2,
            (rect[1] + rect[3]) / 2,
            label,
            14,
            bold=active,
            anchor="center",
        )
        app.concept_aim_rects.append((rect, action))

    close = (x1 - 61, y0 + 18, x1 - 18, y0 + 62)
    text(c, x1 - 39, y0 + 39, "×", 28, anchor="center")
    app.concept_aim_rects.append((close, "cancel"))
    tab = getattr(app, "concept_aim_tab", "measure")
    mid = (x0 + x1) / 2
    button(
        (x0 + 30, y0 + 85, mid, y0 + 131),
        "Measure distance & offset",
        "measure",
        tab == "measure",
    )
    button(
        (mid, y0 + 85, x1 - 30, y0 + 131),
        "Calibrate from shots",
        "shots",
        tab == "shots",
    )
    app.aim_modal_field_rects = {}
    shown = angle(app)
    if tab == "measure":
        fields = (
            (
                "distance",
                "Target distance (feet)",
                app.aim_modal_distance,
                x0 + 32,
                x0 + 286,
            ),
            (
                "lateral",
                "Lateral offset (inches)",
                app.aim_modal_lateral,
                x0 + 334,
                x0 + 573,
            ),
        )
        for key, label, value, left, right in fields:
            text(c, left, y0 + 169, label, 15, T.TEXT_2)
            rect = (left, y0 + 192, right, y0 + 248)
            app.aim_modal_field_rects[key] = rect
            active = app.aim_modal_active_field == key
            panel(c, *rect, outline=T.TEAL_LINE if active else T.TEAL_SOFT)
            text(
                c,
                left + 17,
                y0 + 220,
                (value + " |" if active else value) or "Enter value",
                22,
                bold=True,
            )
        text(c, x0 + 615, y0 + 169, "Side", 15, T.TEXT_2)
        try:
            lateral = float(app.aim_modal_lateral or 0)
        except ValueError:
            lateral = 0
        button((x0 + 615, y0 + 192, x0 + 716, y0 + 248), "Left", "left", lateral < 0)
        button((x0 + 716, y0 + 192, x1 - 30, y0 + 248), "Right", "right", lateral >= 0)
        rect = (x0 + 30, y0 + 274, x1 - 30, y0 + 491)
        panel(c, *rect, fill=T.PAGE_BG)
        text(
            c,
            x0 + 47,
            y0 + 296,
            "Top-down setup · schematic, not to scale",
            12,
            T.TEXT_2,
        )
        sx, ex = x0 + 100, x1 - 80
        base = y0 + 396
        endpoint = base - max(-44, min(44, (shown or 0) * 9))
        c.create_line(sx, base, ex, base, fill=T.TEXT_2, dash=(4, 4))
        c.create_line(sx, base, ex, endpoint, fill=T.TEAL_LINE, width=3, dash=(8, 5))
        panel(
            c,
            sx - 44,
            base - 24,
            sx + 12,
            base + 18,
            fill=T.SURFACE_2,
            outline=T.TEAL_LINE,
            r=5,
        )
        c.create_oval(sx - 6, base - 6, sx + 6, base + 6, fill=T.TEXT, outline="")
        for radius in (24, 16, 7):
            c.create_oval(
                ex - radius,
                endpoint - radius,
                ex + radius,
                endpoint + radius,
                outline=T.GOLD,
                width=3,
            )
        text(
            c,
            (sx + ex) / 2,
            y0 + 464,
            f"{app.aim_modal_distance or '—'} ft to screen / net",
            14,
            anchor="center",
        )
        text(
            c,
            x1 - 47,
            y0 + 328,
            "Enter measurements"
            if shown is None
            else f"Preview correction: {shown:+.2f}°",
            14,
            T.TEAL_LINE,
            anchor="e",
        )
        text(c, x0 + 35, y0 + 550, "Fine adjust", 15, bold=True)
        for i, delta in enumerate((-1.0, -0.1, 0.1, 1.0)):
            left = x0 + 194 + i * 116
            button(
                (left, y0 + 526, left + 103, y0 + 570),
                f"{delta:+.1f}°",
                f"nudge:{delta}",
            )
        button((x1 - 142, y0 + 526, x1 - 30, y0 + 570), "Reset", "reset")
    else:
        panel(c, x0 + 30, y0 + 163, x1 - 30, y0 + 491, fill=T.PAGE_BG)
        count = len(app.aim_calib_shots)
        text(c, mid, y0 + 218, "Aim at one target", 24, bold=True, anchor="center")
        text(
            c,
            mid,
            y0 + 263,
            "Collect real shots, then apply the measured start-line correction.",
            13,
            T.TEXT_2,
            anchor="center",
        )
        text(
            c,
            mid,
            y0 + 326,
            f"{count} / {MIN_CALIBRATION_SHOTS} shots",
            36,
            T.GOLD,
            True,
            anchor="center",
        )
        text(
            c,
            mid,
            y0 + 374,
            "Collecting calibration shots" if app.aim_calibrating else "Ready to begin",
            15,
            T.TEXT_2,
            anchor="center",
        )
        button(
            (mid - 160, y0 + 413, mid + 160, y0 + 460),
            "Stop collecting" if app.aim_calibrating else "Start collecting",
            "collect",
            app.aim_calibrating,
        )
        text(
            c,
            mid,
            y0 + 549,
            f"Current saved correction: {app.aim_offset_deg:+.2f}°",
            15,
            T.TEXT_2,
            anchor="center",
        )
    panel(c, x0 + 30, y1 - 146, x1 - 30, y1 - 98, fill=T.PAGE_BG)
    text(
        c,
        x0 + 47,
        y1 - 122,
        "Correction affects displayed start line and offline; native shot data stays unchanged.",
        12,
        T.TEXT_2,
    )
    app.aim_modal_cancel_rect = (x1 - 378, y1 - 72, x1 - 214, y1 - 24)
    app.aim_modal_save_rect = (x1 - 198, y1 - 72, x1 - 30, y1 - 24)
    button(app.aim_modal_cancel_rect, "Cancel", "cancel")
    button(app.aim_modal_save_rect, "Apply", "apply", True)


def apply(app):
    if getattr(app, "concept_aim_tab", "measure") == "shots":
        ready = offset_from_shots(app.aim_calib_shots) is not None
        app.finish_aim_calibration()
        if ready:
            app.show_aim_modal = False
    else:
        from shanktuary_performance_studio import ShanktuaryApp

        ShanktuaryApp.apply_aim_measurements(app)


def handle_click(app, x, y):
    for rect, action in getattr(app, "concept_aim_rects", []):
        if not (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
            continue
        if action in ("measure", "shots"):
            app.concept_aim_tab = action
        elif action == "cancel":
            app.show_aim_modal = False
            if getattr(app, "concept_aim_tab", "measure") == "shots":
                app.aim_calibrating = False
                app.aim_calib_shots = []
        elif action == "apply":
            apply(app)
        elif action == "collect":
            if not app.aim_calibrating:
                app.aim_calib_shots = []
            app.aim_calibrating = not app.aim_calibrating
        elif action == "reset":
            app.aim_modal_lateral = "0"
        elif action in ("left", "right"):
            try:
                value = abs(float(app.aim_modal_lateral or 0))
                app.aim_modal_lateral = f"{value * (-1 if action == 'left' else 1):g}"
            except ValueError:
                pass
        elif action.startswith("nudge:"):
            shown = angle(app)
            if shown is not None:
                target = max(
                    -MAX_AIM_OFFSET_DEG,
                    min(MAX_AIM_OFFSET_DEG, shown + float(action.split(":")[1])),
                )
                app.aim_modal_lateral = f"{math.tan(math.radians(target)) * float(app.aim_modal_distance) * 12:.6g}"
        app.draw_screen()
        return True
    return False
