"""Unified selected-shot dashboard with honestly identified pressure data.

Four load cells do not measure an anatomical pressure image. The concept's
pressure-card proportions are preserved with board-load gauges instead.
"""

from __future__ import annotations

import math

from . import tokens as T
from .concept_art import range_landscape
from .concept_session import draw_shot, scenic
from .concept_shell import panel, text


def finite(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def pressure_view(app, shot):
    """Never silently present live load as a historical shot's impact."""
    trace = list(app.get_pressure_trace(shot) or []) if shot else []
    trace = [frame for frame in trace if isinstance(frame, dict)]
    if trace:
        timed = [
            (abs(t), frame)
            for frame in trace
            if (t := finite(frame.get("rel_time_s"))) is not None
        ]
        if timed:
            distance, frame = min(timed, key=lambda item: item[0])
            if distance <= 0.15:
                return trace, frame, "At impact · selected shot"
        impact = next(
            (
                frame
                for frame in trace
                if str(frame.get("phase", "")).lower() == "impact"
            ),
            None,
        )
        if impact:
            return trace, impact, "Impact phase · selected shot"
        return trace, trace[-1], "Recorded trace · final sample"
    summary = shot.get("pressure_metrics", {}) if isinstance(shot, dict) else {}
    left = finite(summary.get("pct_left_at_impact"))
    if left is not None and 0 <= left <= 100:
        return (
            [],
            {"pct_left": left, "pct_right": 100 - left},
            "At impact · summary only",
        )
    if shot is None and callable(getattr(app, "board_is_streaming", None)) and app.board_is_streaming():
        import obs_server

        manager = getattr(obs_server, "pressure_manager", None)
        latest = getattr(manager, "latest_frame", None)
        if isinstance(latest, dict):
            frames = [
                frame
                for frame in getattr(app, "swing_lab_history", [])
                if isinstance(frame, dict)
            ]
            label = (
                "DEMO · live load, not shot-synced"
                if getattr(manager, "is_simulator", False)
                else "Live board load · not shot-synced"
            )
            return frames, latest, label
    return (
        [],
        None,
        "No pressure captured for this shot" if shot else "Awaiting local board data",
    )


def _percentage(frame, key):
    result = finite(frame.get(key)) if frame else None
    return result if result is not None and 0 <= result <= 100 else None


def _board(c, rect, label, load):
    x0, y0, x1, y1 = rect
    panel(c, *rect, fill=T.PAGE_BG, outline=T.TEAL_SOFT, r=16)
    for x in (x0 + 12, x1 - 12):
        for y in (y0 + 12, y1 - 12):
            c.create_oval(x - 2, y - 2, x + 2, y + 2, outline=T.TEAL_SOFT)
    # A uniform load gauge reports an aggregate, not invented toe/heel pixels.
    left, right, top, bottom = x0 + 28, x1 - 28, y0 + 35, y1 - 40
    panel(c, left, top, right, bottom, fill=T.SURFACE, r=12)
    if load is not None and load > 0:
        fy = bottom - (bottom - top) * load / 100
        panel(
            c,
            left,
            fy,
            right,
            bottom,
            fill=T.TEAL,
            outline="",
            r=min(12, (bottom - fy) / 2),
        )
    text(c, (x0 + x1) / 2, y0 + 21, label, 11, T.TEXT_2, anchor="center", bold=True)
    text(
        c,
        (x0 + x1) / 2,
        (top + bottom) / 2,
        f"{load:.0f}%" if load is not None else "--",
        29,
        T.TEXT,
        anchor="center",
        bold=True,
    )
    text(c, (x0 + x1) / 2, y1 - 20, "Share of total load", 9, T.TEXT_2, anchor="center")


def _transfer(app, trace, frame, rect, empty_hint=None):
    c = app.canvas
    x0, y0, x1, y1 = rect
    left, right, top, bottom = x0 + 55, x1 - 16, y0 + 8, y1 - 32
    key = "pct_right" if app.is_left_handed else "pct_left"
    samples = [(i, f, _percentage(f, key)) for i, f in enumerate(trace)]
    samples = [s for s in samples if s[2] is not None]
    for i in range(6):
        yy = bottom - (bottom - top) * i / 5
        c.create_line(left, yy, right, yy, fill=T.HAIRLINE)
        text(c, left - 10, yy, f"{i * 20}%", 10, T.TEXT_2, anchor="e")
    if len(samples) < 2:
        if empty_hint:
            cx, cy = (left + right) / 2, (top + bottom) / 2
            half = min(210, (right - left) / 2 - 12)
            c.create_rectangle(cx - half, cy - 40, cx + half, cy + 40,
                               fill=T.SURFACE, outline=T.TEAL_SOFT, dash=(4, 4))
            text(c, cx, cy - 13, "No pressure data", 17, anchor="center", bold=True)
            text(c, cx, cy + 16, empty_hint, 11, T.TEXT_2, anchor="center",
                 width=half * 2 - 20)
            return
        text(
            c,
            (left + right) / 2,
            (top + bottom) / 2,
            "No pressure-transfer trace captured",
            12,
            T.TEXT_3,
            anchor="center",
        )
        return
    times = [finite(f.get("rel_time_s")) for _, f, _ in samples]
    timed = all(t is not None for t in times) and max(times) > min(times)

    def xpos(index, time):
        return left + (right - left) * (
            (time - min(times)) / (max(times) - min(times))
            if timed
            else index / max(1, len(trace) - 1)
        )

    coords = []
    for (i, _, load), time in zip(samples, times):
        coords.extend((xpos(i, time), bottom - (bottom - top) * load / 100))
    c.create_line(
        *coords, fill=T.TEAL_LINE, width=3, smooth=False, tags="overview-pressure-trace"
    )
    if timed:
        for i in range(5):
            t = min(times) + (max(times) - min(times)) * i / 4
            text(
                c,
                left + (right - left) * i / 4,
                bottom + 18,
                f"{t:+.1f}s",
                9,
                T.TEXT_2,
                anchor="center",
            )
        if min(times) <= 0 <= max(times):
            xx = xpos(0, 0)
            c.create_line(xx, top, xx, bottom, fill=T.GOLD, width=2)
            text(c, xx, top - 3, "Impact", 9, T.GOLD, anchor="s")
    else:
        text(c, left, bottom + 18, "Start of recorded samples", 9, T.TEXT_2)
        text(c, right, bottom + 18, "Latest sample", 9, T.TEXT_2, anchor="e")


def _duration(shots):
    timestamps = [finite(s.get("timestamp_ns")) for s in shots]
    timestamps = [t for t in timestamps if t is not None]
    if len(timestamps) < 2:
        return "Shot span unavailable"
    seconds = (max(timestamps) - min(timestamps)) / 1e9
    if not 0 <= seconds < 86400 * 7:
        return "Shot span unavailable"
    return (
        f"{int(seconds // 60)} min shot span"
        if seconds >= 60
        else f"{int(seconds)} sec shot span"
    )


def _button(app, rect, label, action):
    panel(app.canvas, *rect, fill=T.ACTIVE_BG, outline=T.TEAL_LINE, r=12)
    text(app.canvas, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2,
         label, 14, bold=True, anchor="center")
    app.concept_overview_rects.append((rect, action))


def _empty_board(c, rect):
    """Unfilled local-board outlines do not imply a pressure reading."""
    x0, y0, x1, y1 = rect
    panel(c, x0, y0, x1, y1, fill=T.PAGE_BG, outline=T.TEAL_SOFT, r=18)
    for xx in (x0 + 14, x1 - 14):
        for yy in (y0 + 14, y1 - 14):
            c.create_oval(xx - 2, yy - 2, xx + 2, yy + 2, outline=T.TEXT_2)


def _recent_session(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    text(c, x0 + 20, y0 + 31, "Recent session", 23, bold=True)
    # Sessions are appended by production in creation order. Never fabricate a
    # saved session, date, shot count or proposed remote-storage capability.
    session = next((s for s in reversed(getattr(app, "sessions", []))
                    if isinstance(s, dict) and s.get("shots")), None)
    if session:
        from .concept_history import _short

        text(c, x0 + 20, y0 + 81, "Local session", 13, bold=True)
        text(c, x0 + 20, y0 + 113,
             _short(app, session.get("name") or "Untitled session", x1 - x0 - 40, 13),
             13, T.TEXT_2)
        stamp = str(session.get("created_at") or "Date unavailable")
        text(c, x0 + 20, y0 + 145,
             _short(app, f"{stamp} · {len(session['shots'])} shots", x1 - x0 - 40),
             11, T.TEXT_2)
    else:
        text(c, x0 + 20, y0 + 85, "No recorded sessions", 15, bold=True)
        text(c, x0 + 20, y0 + 123, "Your session history will appear here.",
             12, T.TEXT_2, width=x1 - x0 - 40)
    c.create_line(x0 + 20, y1 - 92, x1 - 20, y1 - 92, fill=T.HAIRLINE)
    _button(app, (x0 + 20, y1 - 72, x1 - 20, y1 - 22), "Open session", "history")


def _draw_empty(app, avail_w, h, offset_x):
    """Approved disconnected composition, using only actual local state."""
    c = app.canvas
    # Input from a previous populated Overview or Club page must not survive
    # this composition and intercept one of the empty-state actions.
    app.concept_overview_rects = []
    app.concept_session_rects = []
    app.design_shot_card_rects = []
    app.design_shot_delete_rects = []
    app.contact_face_rect = app.contact_face_geometry = app.contact_clear_rect = None
    x0, x1, top = offset_x + 20, offset_x + avail_w - 20, 60
    bottom = min(832, max(800, h - 28))
    main_bottom = top + (bottom - top) * .60
    split = x0 + (x1 - x0) * .59
    panel(c, x0, top, split - 8, main_bottom)
    scenery = (x0 + 2, top + 65, split - 10, main_bottom - 108)
    if not range_landscape(c, *scenery):
        scenic(c, *scenery)
    text(c, x0 + 22, top + 31, "Latest shot", 24, bold=True)
    text(c, x0 + 22, top + 63, "No shot data", 13, T.TEXT_2)
    cx = (x0 + split - 8) / 2
    cy = top + 144
    # Club outline is an empty-state illustration, never a contact measurement.
    c.create_line(cx + 45, cy - 35, cx + 24, cy + 17, cx - 30, cy + 4,
                  cx - 49, cy + 7, cx - 51, cy + 36, cx - 36, cy + 45,
                  cx + 12, cy + 45, cx + 31, cy + 31, cx + 56, cy - 35,
                  fill=T.TEXT_2, width=2.5, smooth=True)
    for yy in (cy + 23, cy + 30, cy + 37):
        c.create_line(cx - 39, yy, cx + 12, yy, fill=T.TEAL_SOFT)
    text(c, cx, top + 225, "No shots received", 22, bold=True, anchor="center")
    text(c, cx, top + 259, "Connect a shot source to receive shots.",
         13, T.TEXT_2, anchor="center")
    _button(app, (cx - 154, top + 289, cx + 154, top + 337),
            "Start connection setup", "source")
    metrics_y = main_bottom - 108
    panel(c, x0, metrics_y, split - 8, main_bottom)
    cell = (split - 8 - x0) / 4
    for i, label in enumerate(("Carry", "Ball speed", "Launch", "Spin")):
        xx = x0 + i * cell
        if i:
            c.create_line(xx, metrics_y + 16, xx, main_bottom - 16, fill=T.HAIRLINE)
        text(c, xx + 22, metrics_y + 24, label, 12, T.TEXT_2)
        text(c, xx + 22, metrics_y + 54, "—", 23, bold=True)
        text(c, xx + 22, metrics_y + 82, "Unavailable", 11, T.TEXT_3)

    rx = split + 8
    panel(c, rx, top, x1, main_bottom)
    trace, frame, label = pressure_view(app, None)
    live = frame is not None
    text(c, rx + 22, top + 31, "Pressure & balance", 24, bold=True)
    text(c, rx + 22, top + 63, label if live else "Local boards not connected",
         12, T.TEXT_2, width=x1 - rx - 44)
    bw = (x1 - rx - 70) / 2
    board_y, board_bottom = top + 105, main_bottom - 124
    left, right = _percentage(frame, "pct_left"), _percentage(frame, "pct_right")
    lead, trail = (right, left) if app.is_left_handed else (left, right)
    for i, (name, load) in enumerate((("Lead board", lead), ("Trail board", trail))):
        bx = rx + 26 + i * (bw + 18)
        rect = (bx, board_y, bx + bw, board_bottom)
        if live:
            _board(c, rect, name, load)
        else:
            _empty_board(c, rect)
            text(c, bx + bw / 2, board_bottom + 22, name, 11, T.TEXT_2, anchor="center")
    bx = (rx + x1) / 2
    _button(app, (bx - 140, main_bottom - 72, bx + 140, main_bottom - 24),
            "Open board setup" if live else "Connect local boards", "boards")

    lower_top = main_bottom + 18
    lower_split = x0 + (x1 - x0) * .70
    panel(c, x0, lower_top, lower_split - 8, bottom)
    text(c, x0 + 22, lower_top + 31, "Pressure transfer", 23, bold=True)
    text(c, x0 + 22, lower_top + 62,
         "Lead load % · " + label if live else "Lead load % · Awaiting local board data",
         12, T.TEXT_2)
    _transfer(app, trace, frame, (x0 + 8, lower_top + 85, lower_split - 20, bottom - 6),
              empty_hint="Connect local boards to view pressure transfer." if not live
              else "Waiting for more live board samples.")
    _recent_session(app, (lower_split + 8, lower_top, x1, bottom))


def draw(app, avail_w, h, offset_x=0):
    """One selected-shot dashboard, with recorded pressure below analysis."""
    c = app.canvas
    shots = app.session_shots or []
    selected = getattr(app, "current_shot", None)
    c.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill=T.PAGE_BG, outline="")
    if selected is None and not shots:
        _draw_empty(app, avail_w, h, offset_x)
        return
    draw_shot(app, avail_w, 876, offset_x)
    x0, x1 = offset_x + 20, offset_x + avail_w - 20
    y0, bottom = 858, max(1290, h - 36)
    split = x0 + (x1 - x0) * .38
    panel(c, x0, y0, split - 8, bottom)
    panel(c, split + 8, y0, x1, bottom)
    trace, frame, label = pressure_view(app, selected)
    text(c, x0 + 22, y0 + 30, "Pressure & balance", 22, bold=True)
    text(c, x0 + 22, y0 + 62, label, 11, T.TEXT_2)
    left, right = _percentage(frame, "pct_left"), _percentage(frame, "pct_right")
    lead, trail = (right, left) if app.is_left_handed else (left, right)
    bw = (split - x0 - 72) / 2
    _board(c, (x0 + 22, y0 + 90, x0 + 22 + bw, bottom - 86), "Lead board", lead)
    _board(c, (x0 + 42 + bw, y0 + 90, split - 30, bottom - 86), "Trail board", trail)
    text(c, x0 + 22, bottom - 58, "Lead " + (f"{lead:.0f}%" if lead is not None else "--"), 16, bold=True)
    text(c, split - 30, bottom - 58, "Trail " + (f"{trail:.0f}%" if trail is not None else "--"), 16, bold=True, anchor="e")
    text(c, (x0 + split) / 2, bottom - 26, "Board load, not anatomical pressure imaging", 9, T.TEXT_3, anchor="center")
    text(c, split + 30, y0 + 30, "Pressure transfer", 22, bold=True)
    text(c, split + 30, y0 + 62, "Lead load % · " + label, 11, T.TEXT_2)
    _transfer(app, trace, frame, (split + 20, y0 + 94, x1 - 20, bottom - 94))
    club = (selected or {}).get("club") or app.current_club
    text(c, split + 30, bottom - 48, f"Session · {len(shots)} shots · {club} · {_duration(shots)}", 12, T.TEXT_2)
    app.concept_overview_rects = [
        ((x0, y0, split - 8, bottom), "pressure"),
        ((split + 20, bottom - 78, x1 - 20, bottom - 18), "session"),
    ]


def handle_click(app, x, y):
    for rect, action in getattr(app, "concept_overview_rects", []):
        if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
            if action == "source":
                app.open_shot_source_picker()
            elif action == "boards":
                app.concept_setup_page = "details"
                app.set_mode(10)
            else:
                app.set_mode({"pressure": 8, "session": 4, "history": 13}[action])
            return True
    return False
