"""Live, provenance-aware Shot and Club workspaces for the approved concept.

All geometry is presentation only. Native payloads and contact marks remain owned
by the production app. Scenic artwork is explicitly illustrative; plots require
actual supplied metrics and unavailable readings never become invented zeros.
"""

from __future__ import annotations

import math
from collections import Counter

import theme
from src.analytics.strike import (
    FACE_MAX_H_MM,
    FACE_MAX_V_MM,
    contact_location,
)
from src.connections.presentation import metric_status, metric_value, shot_shape

from . import tokens as T
from .concept_shell import panel, text

STATUS = {
    "REPORTED": "Reported",
    "DERIVED": "Derived",
    "ESTIMATED": "Estimate",
    "MODELLED": "Modelled",
    "NOT REPORTED": "Unavailable",
}


def view(app, shot=None):
    raw = app.current_shot if shot is None else shot
    if not isinstance(raw, dict):
        return {}
    try:
        return app.aim_corrected(raw)
    except AttributeError:
        # Pure painter fixtures intentionally omit initialized aim state.
        # Normal initialized apps still surface any unrelated renderer error.
        if not hasattr(app, "aim_offset_deg"):
            return dict(raw)
        raise


def value(app, shot, key):
    return metric_value(shot, key, bool(getattr(app, "is_left_handed", False)))


def status(app, shot, key):
    return STATUS[metric_status(shot, key, bool(getattr(app, "is_left_handed", False)))]


def number(v, unit="", precision=0):
    return "--" if v is None else f"{v:,.{precision}f}" + (f" {unit}" if unit else "")


def badge(c, x, y, label, color=T.GOLD):
    width = max(82, len(label) * 8.5 + 24)
    panel(c, x, y - 14, x + width, y + 14, fill=T.PAGE_BG, outline=color, r=14)
    text(c, x + width / 2, y, label, 12, color, bold=True, anchor="center")
    return width


def section(c, x, y, heading, subtitle="", size=22):
    text(c, x, y, heading, size, bold=True)
    if subtitle:
        text(c, x, y + 33, subtitle, 12, T.TEXT_2)


def metrics(app, shot, rect, entries, heading=None):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    top = y0 + 23
    if heading:
        bw = badge(c, x0 + 14, top, heading)
        idx = getattr(app, "selected_shot_index", -1)
        text(
            c,
            x0 + bw + 29,
            top,
            f"Shot {idx + 1}" if idx >= 0 else "Awaiting a shot",
            12,
            T.TEXT_2,
        )
        top += 42
    else:
        top += 2
    # Give wide values (rpm and mph) the room the approved metric rail gives
    # them, rather than shrinking every numeric result to the narrowest cell.
    weights = {
        "ball_speed": 1.2,
        "club_speed": 1.1,
        "spin": 1.3,
        "launch": 0.9,
        "horizontal_launch": 0.9,
        "apex": 0.9,
    }
    unit_width = (x1 - x0 - 24) / sum(weights.get(entry[0], 1) for entry in entries)
    x = x0 + 13
    for i, (key, label, unit, precision) in enumerate(entries):
        cw = unit_width * weights.get(key, 1)
        if i:
            c.create_line(x - 7, top - 8, x - 7, y1 - 20, fill=T.HAIRLINE)
        text(c, x, top, label, 11, T.TEXT_2)
        val = value(app, shot, key)
        display = number(val, unit, precision)
        value_size = 22
        measure = getattr(app, "_text_width", None)
        while value_size > 11:
            measured = (
                measure(display, (theme.ui_font(), value_size, "bold"))
                if callable(measure)
                else len(display) * value_size * 0.8
            )
            if measured <= cw - 15:
                break
            value_size -= 1
        text(
            c,
            x,
            top + 30,
            display,
            value_size,
            T.TEXT if val is not None else T.TEXT_3,
            bold=True,
        )
        st = status(app, shot, key)
        text(
            c,
            x,
            top + 58,
            st,
            10,
            T.GOLD if st in ("Estimate", "Modelled") else T.TEXT_2,
        )
        x += cw


def recent(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    text(c, x0 + 14, y0 + 26, "Recent Shots", 16, bold=True)
    app.design_shot_card_rects = []
    app.design_shot_delete_rects = []
    shots = app.session_shots or []
    idx = getattr(app, "selected_shot_index", -1)
    selected = idx if 0 <= idx < len(shots) else len(shots) - 1
    app.concept_session_rects = [
        ((x0 + 8, y0 + 5, x0 + 164, y0 + 42), "collapse", None)
    ]
    for delta, xx, label in ((-1, x1 - 35, "‹"), (1, x1 - 13, "›")):
        enabled = 0 <= selected + delta < len(shots)
        text(
            c,
            xx,
            y0 + 26,
            label,
            21,
            T.TEAL_TEXT if enabled else T.TEXT_3,
            anchor="center",
        )
        if enabled:
            app.concept_session_rects.append(
                ((xx - 11, y0 + 9, xx + 11, y0 + 37), "step", delta)
            )
    start = max(0, min(selected - 3, len(shots) - 4))
    if not shots:
        text(c, x0 + 14, y0 + 65, "No shots yet", 11, T.TEXT_3)
        text(c, x0 + 14, y0 + 88, "Connect a source in Setup", 8, T.TEXT_3)
    for row, index in enumerate(reversed(range(start, min(start + 4, len(shots))))):
        yy = y0 + 50 + row * 36
        rect2 = (x0 + 8, yy, x1 - 8, yy + 35)
        if index == selected:
            panel(c, *rect2, fill=T.ACTIVE_BG, outline=T.TEAL_LINE, r=7)
        c.create_oval(
            x0 + 18,
            yy + 12,
            x0 + 26,
            yy + 22,
            fill=T.TEAL_LINE if index == selected else "",
            outline=T.TEAL_TEXT,
        )
        text(c, x0 + 38, yy + 18, str(index + 1), 14, bold=index == selected)
        text(
            c,
            x1 - 34,
            yy + 18,
            number(value(app, view(app, shots[index]), "carry"), "yd"),
            12,
            T.TEXT_2,
            anchor="e",
        )
        if index == selected:
            text(c, x1 - 19, yy + 18, "×", 13, T.TEXT_3, anchor="center")
            app.concept_session_rects.append(
                ((x1 - 29, yy + 3, x1 - 9, yy + 32), "delete", index)
            )
        app.design_shot_card_rects.append((*rect2, index))


def scenic(c, x0, y0, x1, y1):
    """A deterministic illustrative horizon, independent of shot data."""
    from .concept_art import range_landscape

    if range_landscape(c, x0, y0, x1, y1):
        # Side-profile charts cannot borrow the range camera's converging
        # ground grid. Retain the mountain panorama, with a flat chart field.
        c.create_rectangle(
            x0,
            y0 + (y1 - y0) * 0.54,
            x1,
            y1,
            fill="#07332F",
            outline="",
        )
        return
    panel(c, x0, y0, x1, y1, fill="#052D34", outline=T.HAIRLINE, r=10)
    w, h = x1 - x0, y1 - y0
    horizon = y0 + h * 0.50
    for layer, (col, base, amp) in enumerate(
        (("#10414A", 0.43, 0.10), ("#0A343C", 0.49, 0.065), ("#062730", 0.56, 0.045))
    ):
        pts = [x0, y1]
        for i in range(61):
            xx = x0 + w * i / 60
            yy = y0 + h * (
                base
                + amp * math.sin(i * 0.21 + layer)
                + amp * 0.4 * math.sin(i * 0.58 + 1)
            )
            pts.extend((xx, yy))
        pts.extend((x1, y1))
        c.create_polygon(*pts, fill=col, outline="")
    # Sparse evergreen silhouettes along the dark ridge.
    for i in range(max(4, int(w / 13))):
        xx = x0 + 8 + i * 13
        if xx > x1 - 5:
            break
        ht = 8 + 7 * (0.5 + 0.5 * math.sin(i * 2.7))
        yy = horizon + 11 + 5 * math.sin(i * 0.35)
        c.create_polygon(
            xx - 5, yy, xx, yy - ht, xx + 5, yy, fill="#05252B", outline=""
        )
    ground = y0 + h * 0.60
    c.create_polygon(x0, ground, x1, ground, x1, y1, x0, y1, fill="#07332F", outline="")


def trajectory(app, shot, rect, title=True):
    c = app.canvas
    x0, y0, x1, y1 = rect
    scenic(c, *rect)
    if title:
        text(
            c,
            x0 + 12,
            y0 + 17,
            "Trajectory (side view · illustrative)",
            12,
            T.TEXT_2,
            bold=True,
        )
    left, right = x0 + 32, x1 - 22
    bottom = y1 - 28
    carry, apex = value(app, shot, "carry"), value(app, shot, "apex")
    c.create_line(left, bottom, right, bottom, fill=T.TEXT_2, dash=(5, 5))
    if carry is None or apex is None or carry <= 0 or apex < 0:
        text(
            c,
            (x0 + x1) / 2,
            y0 + (y1 - y0) * 0.42,
            "Trajectory unavailable",
            11,
            T.TEXT_2,
            anchor="center",
        )
        return
    max_carry = max(50, math.ceil(carry * 1.2 / 50) * 50)
    ymax = max(20, math.ceil(apex * 1.25 / 10) * 10)
    usable = max(20, (y1 - y0) * 0.58)
    pts = []
    for i in range(61):
        f = i / 60
        pts.extend(
            (
                left + (right - left) * carry / max_carry * f,
                bottom - 4 * apex * f * (1 - f) / ymax * usable,
            )
        )
    c.create_line(
        *pts, fill=T.TEAL_LINE, width=3, smooth=True, tags="flight-trajectory"
    )
    for xx, yy, col in ((pts[0], pts[1], T.TEXT), (pts[-2], pts[-1], T.GOLD)):
        c.create_oval(xx - 4, yy - 4, xx + 4, yy + 4, fill=col, outline="")
    for i in range(5):
        xx = left + (right - left) * i / 4
        text(c, xx, y1 - 12, f"{max_carry * i / 4:.0f}", 10, T.TEXT_2, anchor="center")
    text(c, right, y0 + 18, "yd", 10, T.TEXT_3, anchor="e")


def dispersion(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect, fill="#05252F")
    text(c, x0 + 12, y0 + 18, "Dispersion (overhead)", 12, bold=True)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + 10
    r = max(20, min((x1 - x0) * 0.41, (y1 - y0) * 0.36))
    for f in (0.33, 0.66, 1):
        c.create_oval(
            cx - r * f, cy - r * f, cx + r * f, cy + r * f, outline=T.HAIRLINE
        )
    c.create_line(cx - r, cy, cx + r, cy, fill=T.GUIDE)
    c.create_line(cx, cy - r, cx, cy + r, fill=T.TEXT_2)
    points = []
    for i, raw in enumerate(app.session_shots or []):
        shot = view(app, raw)
        carry, off = value(app, shot, "carry"), value(app, shot, "offline")
        if carry is not None and off is not None:
            points.append((i, carry, off))
    if not points:
        text(c, cx, cy, "No landing data", 9, T.TEXT_3, anchor="center")
        return
    mean = sum(p[1] for p in points) / len(points)
    extent = max(10, max(max(abs(p[2]), abs(p[1] - mean)) for p in points) * 1.15)
    for idx, carry, off in points:
        xx, yy = cx + off / extent * r, cy - (carry - mean) / extent * r
        selected = idx == getattr(app, "selected_shot_index", -1)
        rr = 5 if selected else 3
        c.create_oval(
            xx - rr,
            yy - rr,
            xx + rr,
            yy + rr,
            fill=T.GOLD if selected else T.TEAL_LINE,
            outline="",
        )
        app.land_dot_coords.append((xx, yy, idx))
    text(c, x1 - 12, y1 - 12, f"±{extent:.0f} yd · mean carry", 9, T.TEXT_3, anchor="e")


def contact(app, rect, compact=False):
    """Retain measured/manual contact hit geometry, without a fabricated marker."""
    c = app.canvas
    x0, y0, x1, y1 = rect
    app.contact_clear_rect = None
    app.contact_face_rect = None
    app.contact_face_geometry = None
    current = getattr(app, "current_shot", None)
    reading = contact_location(current)
    from .concept_art import club_face_layout

    club = (current or {}).get("club") or getattr(app, "current_club", "")
    label_space = 60 if compact else 90
    path, art_rect, geom = club_face_layout(
        club, (x0 + 8, y0 + (34 if reading.source == "marked" else 10),
               x1 - 8, max(y0 + 35, y1 - label_space)),
        app.is_left_handed,
    )
    ax0, ay0, ax1, ay1 = art_rect
    cx = (x0 + x1) / 2
    try:
        image = app.get_scaled_club_asset(
            path, int(ay1 - ay0), mirror=app.is_left_handed, pad_square=False
        )
    except TypeError:
        image = app.get_scaled_club_asset(
            path, int(ay1 - ay0), mirror=app.is_left_handed
        )
    if image:
        c.create_image(ax0, ay0, image=image, anchor="nw", tags="contact-artwork")
    else:
        # A missing asset remains an explicitly generic schematic, not an
        # unrelated iron silhouette or fabricated contact measurement.
        panel(c, ax0, ay0, ax1, ay1, fill=T.SURFACE, outline=T.TEAL_SOFT, r=12)
        text(c, cx, (ay0 + ay1) / 2, "Clubface schematic", 11, T.TEXT_2, anchor="center")
    if isinstance(current, dict):
        app.contact_face_geometry = geom
        app.contact_face_rect = art_rect
    for peer in getattr(app, "session_shots", []) or []:
        if (
            peer is current
            or not isinstance(peer, dict)
            or peer.get("club") != (current or {}).get("club")
        ):
            continue
        marked = contact_location(peer)
        if marked.source == "marked" and marked.complete:
            px, py = geom.mm_to_px(marked.horizontal_mm, marked.vertical_mm)
            c.create_oval(
                px - 2,
                py - 2,
                px + 2,
                py + 2,
                fill="",
                outline=T.PAGE_BG,
                tags="contact-peer",
            )
    if (
        reading.complete
        and abs(reading.horizontal_mm) <= FACE_MAX_H_MM
        and abs(reading.vertical_mm) <= FACE_MAX_V_MM
    ):
        xx, yy = geom.mm_to_px(reading.horizontal_mm, reading.vertical_mm)
        c.create_oval(xx - 8, yy - 8, xx + 8, yy + 8, outline=T.GOLD, width=2)
        c.create_oval(
            xx - 3,
            yy - 3,
            xx + 3,
            yy + 3,
            fill=T.GOLD,
            outline="",
            tags="contact-marker",
        )
    label = reading.headline if reading.available else "Impact unavailable"
    detail = reading.badge if reading.available else "No face-contact measurement"
    # Preserve history-backed estimates, but never manufacture a precise sweet
    # spot when no marks exist. A hollow area and its source label stay distinct
    # from measured/marked contact.
    if (
        not reading.available
        and isinstance(current, dict)
        and current.get("_source") != "pureplay"
    ):
        from src.analytics.strike_estimate import estimate

        from .contact_panel import all_shots

        est = estimate(current, all_shots(app))
        if est.basis != "none":
            xx, yy = geom.mm_to_px(est.horizontal_mm, est.vertical_mm)
            rr = est.radius_mm * geom.px_per_mm
            c.create_oval(
                xx - rr,
                yy - rr,
                xx + rr,
                yy + rr,
                outline=T.TEAL_LINE,
                width=2,
                tags="contact-estimate",
            )
            label = "Approximate strike"
            detail = est.label
    text(
        c,
        cx,
        y1 - (29 if compact else 46),
        label,
        15,
        T.TEXT,
        bold=True,
        anchor="center",
        tags="contact-heading",
    )
    text(
        c,
        cx,
        y1 - (9 if compact else 23),
        detail,
        10,
        T.TEXT_2,
        anchor="center",
        tags="contact-credibility",
    )
    disclaimer = (
        "Ball data does not establish face contact"
        if (current or {}).get("_source") == "pureplay"
        else "Nova measures ball flight, not face contact"
    )
    if not compact:
        text(c, cx, y1 - 4, disclaimer, 9, T.TEXT_3, anchor="center")
    if reading.source == "marked":
        app.contact_clear_rect = (x1 - 88, y0, x1 - 8, y0 + 24)
        text(c, x1 - 12, y0 + 12, "clear mark", 9, T.TEAL_TEXT, anchor="e")


def trends(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    section(
        c,
        x0 + 16,
        y0 + 22,
        "Session Trends",
        "Carry (yd) · last 10 shots with carry data",
        size=20,
    )
    points = [
        (i + 1, value(app, view(app, s), "carry"))
        for i, s in enumerate(app.session_shots or [])
    ]
    points = [p for p in points if p[1] is not None][-10:]
    if not points:
        text(c, x0 + 18, y0 + 100, "Trends appear after your first shot.", 11, T.TEXT_3)
        return
    lo, hi = min(p[1] for p in points), max(p[1] for p in points)
    pad = max(3, (hi - lo) * 0.2)
    lo -= pad
    hi += pad
    left, right, top, bottom = x0 + 45, x1 - 25, y0 + 78, y1 - 33
    for i in range(5):
        yy = top + (bottom - top) * i / 4
        c.create_line(left, yy, right, yy, fill=T.HAIRLINE)
        text(c, left - 8, yy, f"{hi - (hi - lo) * i / 4:.0f}", 10, T.TEXT_2, anchor="e")
    coords = []
    for i, (idx, val) in enumerate(points):
        xx = left + (right - left) * i / max(1, len(points) - 1)
        yy = bottom - (val - lo) / (hi - lo) * (bottom - top)
        coords.extend((xx, yy))
        text(c, xx, bottom + 17, str(idx), 10, T.TEXT_2, anchor="center")
    if len(points) > 1:
        c.create_polygon(
            left, bottom, *coords, right, bottom, fill="#0B4747", outline=""
        )
        c.create_line(*coords, fill=T.TEAL_LINE, width=3)
    for i in range(len(points)):
        xx, yy = coords[2 * i : 2 * i + 2]
        col = T.GOLD if i == len(points) - 1 else T.TEAL_TEXT
        c.create_oval(xx - 4, yy - 4, xx + 4, yy + 4, fill=col, outline="")


def shape_mix(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    section(
        c,
        x0 + 16,
        y0 + 22,
        "Shot Shape Mix",
        "Reported or model-labelled shot shapes",
        size=20,
    )
    counts = Counter()
    for raw in app.session_shots or []:
        label, _ = shot_shape(view(app, raw), app.is_left_handed)
        if not label:
            continue
        low = label.lower()
        category = (
            "Draw"
            if "draw" in low or "hook" in low
            else "Fade"
            if "fade" in low or "slice" in low
            else "Straight"
            if "straight" in low
            else "Other"
        )
        counts[category] += 1
    total = sum(counts.values())
    r = max(30, min((y1 - y0 - 82) / 2, (x1 - x0) * 0.16))
    cx, cy = x0 + 30 + r, y0 + 70 + r
    c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=T.HAIRLINE, width=15)
    angle = 90
    colors = {
        "Draw": T.TEAL,
        "Straight": T.TEAL_LINE,
        "Fade": T.TEAL_TEXT,
        "Other": T.TEXT_3,
    }
    for label, col in colors.items():
        n = counts[label]
        if n and total:
            extent = -360 * n / total
            c.create_arc(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                start=angle,
                extent=extent,
                style="arc",
                outline=col,
                width=18,
            )
            angle += extent
    text(c, cx, cy - 6, str(total), 28, bold=True, anchor="center")
    text(c, cx, cy + 22, "Shots", 13, T.TEXT_2, anchor="center")
    xx = x0 + (x1 - x0) * 0.49
    for i, label in enumerate(colors):
        yy = y0 + 94 + i * 37
        if label == "Other" and not counts[label]:
            continue
        c.create_oval(xx, yy - 5, xx + 10, yy + 5, fill=colors[label], outline="")
        text(c, xx + 23, yy, label, 13)
        text(
            c,
            x1 - 50,
            yy,
            f"{counts[label] / total:.0%}  ({counts[label]})" if total else "--",
            12,
            T.TEXT_2,
            anchor="e",
        )


def draw_shot(app, width, height, offset_x=0):
    c = app.canvas
    shot = view(app)
    c.create_rectangle(
        offset_x, 52, offset_x + width, height, fill=T.PAGE_BG, outline=""
    )
    x0, x1 = offset_x + 20, offset_x + width - 20
    y0 = 60
    top_h = 198
    collapsed = getattr(app, "concept_recent_collapsed", False)
    recent_w = 0 if collapsed else min(218, (x1 - x0) * 0.19)
    if not collapsed:
        recent(app, (x0, y0, x0 + recent_w, y0 + top_h))
    else:
        app.design_shot_card_rects = []
        app.design_shot_delete_rects = []
        app.concept_session_rects = []
    entries = [
        ("carry", "Carry", "yd", 0),
        ("total", "Total", "yd", 0),
        ("ball_speed", "Ball speed", "mph", 0),
        ("club_speed", "Club speed", "mph", 0),
        ("launch", "VLA", "°", 1),
        ("horizontal_launch", "HLA", "°", 1),
        ("spin", "Spin", "rpm", 0),
        ("apex", "Apex", "yd", 0),
        ("offline", "Offline", "yd", 0),
    ]
    metrics(
        app,
        shot,
        (x0 + (recent_w + 14 if recent_w else 0), y0, x1, y0 + 164),
        entries,
        "Result",
    )
    if collapsed:
        rect = (x1 - 165, y0 + 8, x1 - 12, y0 + 37)
        panel(c, *rect, fill=T.SURFACE, outline=T.TEAL_LINE, r=7)
        text(c, x1 - 88, y0 + 23, "Recent Shots +", 10, anchor="center")
        app.concept_session_rects.append((rect, "collapse", None))
    mid_y = y0 + top_h + 14
    mid_h = max(245, (height - 140) * 0.43)
    lower_y = mid_y + mid_h + 14
    left_end = x0 + (x1 - x0) * 0.66
    panel(c, x0, mid_y, left_end, mid_y + mid_h)
    bw = badge(c, x0 + 12, mid_y + 21, "Shape")
    text(
        c,
        x0 + bw + 28,
        mid_y + 21,
        "Shot shape · Trajectory and dispersion (derived)",
        12,
        T.TEXT_2,
    )
    plot_end = x0 + (left_end - x0) * 0.70
    trajectory(app, shot, (x0 + 10, mid_y + 43, plot_end, mid_y + mid_h - 14))
    dispersion(app, (plot_end + 10, mid_y + 43, left_end - 10, mid_y + mid_h - 14))
    cause_x = left_end + 14
    panel(c, cause_x, mid_y, x1, mid_y + mid_h)
    badge(c, cause_x + 12, mid_y + 21, "Cause")
    text(c, cause_x + 108, mid_y + 21, "Club delivery · Availability", 12, T.TEXT_2)
    contact(
        app,
        (cause_x + 10, mid_y + 42, x1 - 10, mid_y + mid_h - 82),
        compact=True,
    )
    for i, (key, label) in enumerate(
        (("club_path", "Path"), ("face_to_target", "Face"))
    ):
        yy = mid_y + mid_h - 63 + i * 25
        text(c, cause_x + 18, yy, label, 12, bold=True)
        c.create_line(cause_x + 18, yy + 13, x1 - 18, yy + 13, fill=T.HAIRLINE)
        text(
            c,
            x1 - 18,
            yy,
            number(value(app, shot, key), "°", 1) + " · " + status(app, shot, key),
            11,
            T.TEXT_2,
            anchor="e",
        )
    text(
        c,
        cause_x + 18,
        mid_y + mid_h - 14,
        "Ball flight alone cannot establish face contact.",
        9,
        T.TEXT_2,
    )
    split = x0 + (x1 - x0) * 0.47
    trends(app, (x0, lower_y, split, height - 44))
    shape_mix(app, (split + 14, lower_y, x1, height - 44))


def draw_club(app, width, height, offset_x=0):
    c = app.canvas
    shot = view(app)
    app.design_shot_card_rects = []
    app.design_shot_delete_rects = []
    app.concept_session_rects = []
    c.create_rectangle(
        offset_x, 52, offset_x + width, height, fill=T.PAGE_BG, outline=""
    )
    x0, x1 = offset_x + 20, offset_x + width - 20
    metrics(
        app,
        shot,
        (x0, 64, x1, 172),
        [
            ("carry", "Carry", "yd", 0),
            ("ball_speed", "Ball speed", "mph", 0),
            ("launch", "Launch", "°", 1),
            ("spin", "Spin", "rpm", 0),
            ("club_speed", "Club speed", "mph", 1),
            ("club_path", "Path", "°", 1),
            ("face_to_target", "Face", "°", 1),
        ],
    )
    gap = 14
    mid = x0 + (x1 - x0) * 0.53
    y0 = 186
    y1 = height - 110
    # The approved Club page uses a shallow delivery/spin row and a taller
    # launch/contact row, with the session controls in their own bottom strip.
    ym = y0 + (y1 - y0 - gap) * 0.45 + gap / 2
    for r in (
        (x0, y0, mid - gap / 2, ym - gap / 2),
        (mid + gap / 2, y0, x1, ym - gap / 2),
        (x0, ym + gap / 2, mid - gap / 2, y1),
        (mid + gap / 2, ym + gap / 2, x1, y1),
    ):
        panel(c, *r)
    section(
        c,
        x0 + 18,
        y0 + 27,
        "Club Path & Face",
        "Overhead directions relative to target",
    )
    left, right = x0 + 25, mid - 25
    # Center the entire padded, rotated sprite inside the card's illustration
    # region. The old target line sat near the bottom, letting its lower half
    # spill into Launch & Loft on taller windows.
    art_top, art_bottom = y0 + 90, ym - gap / 2 - 16
    base = (art_top + art_bottom) / 2
    cx = left + (right - left) * 0.33
    art_extent = max(1, min(art_bottom - art_top, 2 * (cx - left)))
    c.create_line(left, base, right, base, fill=T.TEXT_2, dash=(5, 5))
    text(c, left, base - 15, "Target line", 11, T.TEXT_2)
    face_angle = value(app, shot, "face_to_target")
    overhead = getattr(app, "get_rotated_overhead_asset", lambda *a, **kw: None)(
        max(1, int(art_extent)), face_angle or 0, mirror=app.is_left_handed,
        max_extent=max(1, int(art_extent)),
    )
    if overhead:
        c.create_image(cx, base - 1, image=overhead, anchor="c")
    else:
        panel(
            c,
            cx - 15,
            base - 64,
            cx + 13,
            base + 24,
            fill="#708084",
            outline="#BDCBCD",
            r=10,
        )
        for i in range(5):
            c.create_line(
                cx - 10 + i * 4, base - 52, cx - 10 + i * 4, base + 8, fill="#394C50"
            )
    for j, (key, label, col) in enumerate(
        (("club_path", "Path", T.TEAL_LINE), ("face_to_target", "Face", T.GOLD))
    ):
        v = value(app, shot, key)
        yy = y0 + 110 + j * 40
        text(c, right - 195, yy, label + " " + number(v, "°", 1), 14, col, bold=True)
        text(c, right, yy, status(app, shot, key), 10, T.TEXT_2, anchor="e")
        if v is not None:
            length = (right - cx) * 0.8
            angle = math.radians(max(-70, min(70, v)) * 3)
            c.create_line(
                cx,
                base,
                cx + length * math.cos(angle),
                base - length * math.sin(angle),
                fill=col,
                width=3,
                arrow="last",
            )
    sx = mid + gap / 2
    section(c, sx + 18, y0 + 27, "Spin", "Ball spin and axis · illustrative geometry")
    bx, by = sx + (x1 - sx) * 0.28, y0 + (ym - y0) * 0.64
    radius = min(62, (ym - y0) * 0.26)
    from .asset_paths import asset_path

    ball = app.get_scaled_club_asset(
        asset_path("golf_ball.png"), int(radius * 2), pad_square=False
    )
    if ball:
        c.create_image(bx, by, image=ball, anchor="center", tags="spin-illustration")
    else:
        c.create_oval(
            bx - radius,
            by - radius,
            bx + radius,
            by + radius,
            fill="#CAD7DA",
            outline="#8CA7AC",
            width=2,
        )
        for row in range(-4, 5):
            for col in range(-4, 5):
                dx, dy = (
                    col * radius * 0.19 + (row % 2) * radius * 0.08,
                    row * radius * 0.20,
                )
                if dx * dx + dy * dy < radius * radius * 0.8:
                    c.create_oval(
                        bx + dx - 3,
                        by + dy - 3,
                        bx + dx + 3,
                        by + dy + 3,
                        fill="#B2C4C8",
                        outline="#D8E4E6",
                    )
    spin = value(app, shot, "spin")
    axis = value(app, shot, "spin_axis")
    if spin is not None:
        c.create_arc(
            bx - radius - 12,
            by - radius - 12,
            bx + radius + 12,
            by + radius + 12,
            start=25,
            extent=285,
            style="arc",
            outline=T.TEAL_LINE,
            width=3,
        )
    if axis is not None:
        a = math.radians(axis)
        dx = radius * 1.2 * math.cos(a)
        dy = radius * 1.2 * math.sin(a)
        c.create_line(
            bx - dx, by + dy, bx + dx, by - dy, fill=T.TEXT, dash=(5, 4), width=2
        )
    text(c, sx + (x1 - sx) * 0.53, y0 + 105, number(spin, "rpm"), 28, bold=True)
    text(c, sx + (x1 - sx) * 0.53, y0 + 140, status(app, shot, "spin"), 12, T.TEXT_2)
    text(
        c,
        sx + (x1 - sx) * 0.53,
        y0 + 185,
        "Spin axis " + number(axis, "°", 1),
        13,
        T.TEXT_2,
    )
    launch_y = ym + gap / 2
    section(
        c,
        x0 + 18,
        launch_y + 27,
        "Launch & Loft",
        "Flight shape · illustrative side view",
    )
    trajectory(app, shot, (x0 + 14, launch_y + 71, mid - 128, y1 - 22), False)
    panel(c, mid - 119, launch_y + 72, mid - 22, y1 - 32, fill=T.PAGE_BG)
    for j, (key, label) in enumerate((("launch", "Launch"), ("dynamic_loft", "Loft"))):
        yy = launch_y + 91 + j * 88
        text(c, mid - 107, yy, label, 11, T.TEXT_2)
        text(
            c, mid - 107, yy + 28, number(value(app, shot, key), "°", 1), 22, bold=True
        )
        text(c, mid - 107, yy + 51, status(app, shot, key), 10, T.TEXT_2)
    section(
        c,
        sx + 18,
        launch_y + 27,
        "Impact Location",
        "Clubface schematic · click to mark your strike",
    )
    reading = contact_location(app.current_shot)
    text(
        c,
        x1 - 18,
        launch_y + 27,
        reading.badge,
        9,
        T.TEAL_TEXT if reading.available else T.TEXT_3,
        anchor="e",
    )
    contact(app, (sx + 12, launch_y + 66, x1 - 12, y1 - 8))
    shots = app.session_shots or []
    selected = getattr(app, "selected_shot_index", -1)
    footer_y = y1 + 16
    footer_mid = footer_y + 26
    controls_end = x0 + (x1 - x0) * 0.40
    panel(c, x0, footer_y, controls_end, footer_y + 52)
    panel(c, controls_end + 16, footer_y, x1, footer_y + 52)
    text(
        c,
        x0 + 16,
        footer_mid,
        f"Shot {max(0, selected + 1)} / {len(shots)}",
        12,
        T.TEXT_2,
    )
    for delta, xx, label in ((-1, x0 + 165, "‹ Previous"), (1, x0 + 285, "Next ›")):
        enabled = 0 <= selected + delta < len(shots)
        text(c, xx, footer_mid, label, 11, T.TEAL_TEXT if enabled else T.TEXT_3)
        if enabled:
            app.concept_session_rects.append(
                ((xx - 4, footer_y + 5, xx + 98, footer_y + 47), "step", delta)
            )
    if 0 <= selected < len(shots):
        text(c, controls_end - 16, footer_mid, "Delete shot", 10, T.TEXT_3, anchor="e")
        app.concept_session_rects.append(
            (
                (controls_end - 100, footer_y + 5, controls_end - 8, footer_y + 47),
                "delete",
                selected,
            )
        )
    text(
        c,
        (controls_end + 16 + x1) / 2,
        footer_mid,
        "Reported  •  Derived  •  Estimate / Modelled  •  Unavailable",
        11,
        T.TEAL_TEXT,
        anchor="center",
    )


def handle_session_click(app, x, y):
    """Handle old-shot navigation/deletion before contact and card selection."""
    for rect, action, arg in getattr(app, "concept_session_rects", []):
        if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
            if action == "collapse":
                app.concept_recent_collapsed = not getattr(
                    app, "concept_recent_collapsed", False
                )
                app.draw_screen()
            elif action == "delete":
                app.delete_shot(arg)  # Production confirmation/persistence path.
            else:
                idx = getattr(app, "selected_shot_index", -1) + arg
                if 0 <= idx < len(app.session_shots):
                    app.selected_shot_index = idx
                    app.current_shot = app.session_shots[idx]
                    app.draw_screen()
            return True
    return False
