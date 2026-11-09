"""Tools & outputs workspace over the existing desktop/browser actions.

Thumbnails are previews of available session data, never demonstration shots.
The complete legacy menu remains reachable through More commands.
"""

from __future__ import annotations

from . import tokens as T
from .concept_workspaces import panel, text


def _metric(app, key, unit, precision=0):
    from src.connections.presentation import metric_status, metric_value

    shot = getattr(app, "current_shot", None)
    value = metric_value(shot, key, getattr(app, "is_left_handed", False))
    labels = {
        "REPORTED": "Reported",
        "DERIVED": "Derived",
        "ESTIMATED": "Estimate",
        "MODELLED": "Modelled",
        "NOT REPORTED": "Unavailable",
    }
    status = labels[metric_status(shot, key, getattr(app, "is_left_handed", False))]
    value = "--" if value is None else f"{value:,.{precision}f} {unit}".strip()
    return value, status


def _action(app, rect, label, action, *, active=False, size=14):
    c = app.canvas
    panel(c, *rect, outline=T.GOLD if active else T.HAIRLINE, radius=11)
    text(
        c,
        (rect[0] + rect[2]) / 2,
        (rect[1] + rect[3]) / 2,
        label,
        size,
        anchor="center",
        bold=True,
    )
    app.concept_tools_rects.append((rect, action))


def _overlay_preview(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    # A transparency checker represents the browser overlay's alpha canvas,
    # not an invented background setting or a screenshot of a live stream.
    step = 12
    for row, yy in enumerate(range(round(y0), round(y1), step)):
        for col, xx in enumerate(range(round(x0), round(x1), step)):
            color = "#3E494E" if (row + col) % 2 else "#536066"
            c.create_rectangle(
                xx, yy, min(x1, xx + step), min(y1, yy + step), fill=color, outline=""
            )
    panel(c, x0, y0, x1, y1, fill="", radius=12)
    panel(c, x0 + 12, y0 + 12, x0 + 180, y0 + 54, fill=T.PAGE_BG, radius=5)
    text(c, x0 + 23, y0 + 19, "SHANKTUARY", 14, T.GOLD, bold=True)
    text(c, x0 + 24, y0 + 39, "PERFORMANCE STUDIO", 5, T.TEXT_2)
    bx, by, bw = x1 - 130, y0 + 20, 118
    panel(c, bx, by, bx + bw, y1 - 32, fill=T.SURFACE, outline=T.TEAL_LINE, radius=9)
    entries = (
        ("Carry", "carry", "yd", 0),
        ("Ball speed", "ball_speed", "mph", 0),
        ("Spin", "spin", "rpm", 0),
    )
    step_y = (y1 - by - 42) / 3
    for i, (label, key, unit, precision) in enumerate(entries):
        yy = by + 12 + i * step_y
        value, _ = _metric(app, key, unit, precision)
        text(c, bx + 12, yy, label, 9, T.TEXT_2)
        text(c, bx + 12, yy + 18, value, 15, bold=True)
        if i < 2:
            c.create_line(
                bx + 12, yy + step_y - 4, bx + bw - 12, yy + step_y - 4, fill=T.HAIRLINE
            )
    c.create_polygon(
        x0,
        y1 - 25,
        x0 + (x1 - x0) * 0.38,
        y1 - 14,
        x1,
        y1 - 27,
        x1,
        y1,
        x0,
        y1,
        fill=T.PAGE_BG,
        outline="",
    )
    c.create_line(
        x0,
        y1 - 25,
        x0 + (x1 - x0) * 0.38,
        y1 - 14,
        x1,
        y1 - 27,
        fill=T.TEAL_LINE,
        width=2,
        smooth=True,
    )
    text(c, x0 + 12, y1 - 10, "Preview • current shot", 8, T.TEXT_2, anchor="sw")


def _report_preview(app, rect):
    from src.connections.presentation import metric_value

    c = app.canvas
    x0, y0, x1, y1 = rect
    for offset in (18, 9):
        panel(
            c,
            x0 + offset,
            y0 - offset / 2,
            x1 + offset / 2,
            y1 + offset / 2,
            fill="#80999D",
            outline="#9BB0B3",
            radius=3,
        )
    panel(c, x0, y0, x1, y1, fill="#DDE7E9", outline="#C7D9DC", radius=4)
    panel(c, x0 + 10, y0 + 10, x1 - 10, y0 + 49, fill=T.PAGE_BG, radius=2)
    text(c, x0 + 19, y0 + 29, "SHANKTUARY", 11, T.GOLD, anchor="w", bold=True)
    text(c, x1 - 19, y0 + 29, "Session report", 9, T.TEXT, anchor="e", bold=True)
    shots = [
        shot for shot in getattr(app, "session_shots", []) if not shot.get("excluded")
    ]
    left = getattr(app, "is_left_handed", False)
    graph = (x0 + 18, y0 + 67, x0 + (x1 - x0) * 0.46, y1 - 50)
    gx0, gy0, gx1, gy1 = graph
    for i in range(5):
        xx, yy = gx0 + (gx1 - gx0) * i / 4, gy0 + (gy1 - gy0) * i / 4
        c.create_line(xx, gy0, xx, gy1, fill="#ADC3C7")
        c.create_line(gx0, yy, gx1, yy, fill="#ADC3C7")
    pairs = [
        (metric_value(s, "carry", left), metric_value(s, "offline", left))
        for s in shots
    ]
    pairs = [
        (carry, offline)
        for carry, offline in pairs
        if carry is not None and offline is not None
    ]
    if pairs:
        max_c = max(1, max(carry for carry, _ in pairs)) * 1.1
        spread = max(10, max(abs(offline) for _, offline in pairs)) * 1.1
        for carry, offline in pairs:
            xx = gx0 + carry / max_c * (gx1 - gx0)
            yy = (gy0 + gy1) / 2 - offline / spread * (gy1 - gy0) / 2
            c.create_oval(xx - 2, yy - 2, xx + 2, yy + 2, fill="#078A85", outline="")
    else:
        text(
            c,
            (gx0 + gx1) / 2,
            (gy0 + gy1) / 2,
            "No carry data",
            8,
            "#526E75",
            anchor="center",
        )
    rx = x0 + (x1 - x0) * 0.52
    entries = (
        ("Carry", "carry", "yd"),
        ("Ball speed", "ball_speed", "mph"),
        ("Spin", "spin", "rpm"),
        ("Launch", "launch", "°"),
    )
    for i, (label, key, unit) in enumerate(entries):
        yy = y0 + 77 + i * 29
        values = [metric_value(shot, key, left) for shot in shots]
        values = [value for value in values if value is not None]
        shown = f"{sum(values) / len(values):,.0f} {unit}" if values else "--"
        text(c, rx, yy, label, 7, "#19323A", anchor="w")
        text(c, x1 - 16, yy, shown, 8, "#19323A", anchor="e", bold=True)
        c.create_line(rx, yy + 13, x1 - 16, yy + 13, fill="#ADC3C7")
    text(
        c,
        x0 + 18,
        y1 - 22,
        f"Current session • {len(shots)} included shots",
        8,
        "#526E75",
        anchor="w",
    )


def _projection_preview(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect, fill="#062D29", radius=11)
    # Floor mat top-down grid: no trajectory or measured divot is fabricated.
    grid_end = x0 + (x1 - x0) * 0.48
    for i in range(7):
        xx = x0 + 14 + (grid_end - x0 - 28) * i / 6
        yy = y0 + 18 + (y1 - y0 - 36) * i / 6
        c.create_line(xx, y0 + 12, xx, y1 - 12, fill="#17473F", dash=(3, 5))
        c.create_line(x0 + 12, yy, grid_end, yy, fill="#17473F", dash=(3, 5))
    text(
        c,
        (x0 + grid_end) / 2,
        (y0 + y1) / 2,
        "Floor layout\npreview",
        12,
        T.TEXT_2,
        anchor="center",
        justify="center",
    )
    bx, by = grid_end + 10, y0 + 17
    cw, ch = (x1 - bx - 20) / 2, (y1 - y0 - 42) / 2
    for i, (label, key, unit, precision) in enumerate(
        (
            ("Carry", "carry", "yd", 0),
            ("Ball speed", "ball_speed", "mph", 0),
            ("Launch", "launch", "°", 1),
            ("Spin", "spin", "rpm", 0),
        )
    ):
        xx, yy = bx + (i % 2) * (cw + 7), by + (i // 2) * (ch + 7)
        panel(c, xx, yy, xx + cw, yy + ch, fill=T.SURFACE, radius=9)
        value, status = _metric(app, key, unit, precision)
        text(c, xx + 10, yy + 10, label, 9, T.TEXT_2)
        text(c, xx + 10, yy + 33, value, 15, bold=True)
        text(c, xx + 10, yy + ch - 20, status, 8, T.TEXT_2)


def draw(app, avail_w, h, offset_x=0):
    """Paint local viewport coordinates; the desktop owns header translation."""
    c = app.canvas
    x0, x1, top, bottom = offset_x + 20, offset_x + avail_w - 24, 80, h - 68
    app.concept_tools_rects = []
    c.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill=T.PAGE_BG, outline="")
    _action(app, (x1 - 165, 49, x1, 74), "More commands", "legacy_tools", size=10)
    mid = top + (bottom - top) * 0.50
    upper_split = x0 + (x1 - x0) * 0.55
    lower_split = x0 + (x1 - x0) * 0.60
    cards = (
        (
            x0,
            top,
            upper_split - 8,
            mid - 8,
            "Broadcast & overlays",
            "Stream-ready graphics and layouts",
        ),
        (
            upper_split + 8,
            top,
            x1,
            mid - 8,
            "Session report",
            "Create shareable results from the current session",
        ),
        (
            x0,
            mid + 8,
            lower_split - 8,
            bottom,
            "Floor projection",
            "On-floor viewing modes for the hit area",
        ),
        (
            lower_split + 8,
            mid + 8,
            x1,
            bottom,
            "Support",
            "Logs and diagnostics for troubleshooting",
        ),
    )
    for px, py, qx, qy, title, subtitle in cards:
        panel(c, px, py, qx, qy)
        text(c, px + 20, py + 10, title, 24, bold=True)
        text(c, px + 20, py + 52, subtitle, 12, T.TEXT_2)
    bx, by, br, bb = cards[0][:4]
    action_x = br - 218
    _overlay_preview(app, (bx + 20, by + 98, action_x - 16, bb - 22))
    for i, (label, action) in enumerate(
        (
            ("OBS Overlay\nConfig", "open_config"),
            ("Copy\nOverlay URL", "copy_obs_url"),
            ("Open\nCanvas Editor", "open_editor"),
        )
    ):
        yy = by + 98 + i * 81
        _action(app, (action_x, yy, br - 15, yy + 64), label, action)
    rx, ry, rr, rb = cards[1][:4]
    report_end = rr - 184
    _report_preview(app, (rx + 23, ry + 109, report_end, rb - 35))
    _action(
        app, (report_end + 25, ry + 119, rr - 16, ry + 204), "Export\nCSV", "export_csv"
    )
    _action(
        app, (report_end + 25, ry + 230, rr - 16, ry + 315), "Export\nPDF", "export_pdf"
    )
    fx, fy, fr, fb = cards[2][:4]
    action_x = fr - 227
    _projection_preview(app, (fx + 20, fy + 88, action_x - 18, fb - 22))
    for i, (label, action) in enumerate(
        (
            ("Virtual Divot", "open_divot"),
            ("Metric Tiles", "open_tiles"),
            ("Whole Layout", "open_layout"),
        )
    ):
        yy = fy + 78 + i * 57
        _action(app, (action_x, yy, fr - 16, yy + 47), label, action, size=13)
    _action(
        app,
        (action_x, fy + 251, fr - 16, fb - 23),
        "Switch to\nDivot Mode",
        "set_mode_0",
        active=True,
        size=13,
    )
    sx, sy, sr, sb = cards[3][:4]
    _action(
        app,
        (sx + 24, sy + 108, sr - 24, sy + 172),
        "Open Log Folder",
        "open_log_folder",
        size=16,
    )
    c.create_line(sx + 20, sy + 216, sr - 20, sy + 216, fill=T.HAIRLINE)
    yy = sy + 267
    text(c, sx + 24, yy, "Display size", 13, anchor="w")
    right = sr - 20
    _action(
        app, (right - 308, yy - 20, right - 258, yy + 20), "−", "scale_minus", size=22
    )
    text(
        c,
        right - 215,
        yy,
        f"{round(getattr(app, 'ui_scale', 1) * 100)}%",
        15,
        anchor="center",
        bold=True,
    )
    _action(
        app, (right - 168, yy - 20, right - 118, yy + 20), "+", "scale_plus", size=22
    )
    _action(
        app,
        (right - 90, yy - 20, right + 4, yy + 20),
        "Auto",
        "scale_auto",
        active=getattr(app, "ui_scale_choice", "Auto") == "Auto",
        size=13,
    )


def handle_click(app, x, y):
    """Invoke existing output functions and stable browser routes exactly once."""
    import obs_server
    import shanktuary_performance_studio as production

    for rect, action in getattr(app, "concept_tools_rects", []):
        if not (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
            continue
        url = f"http://localhost:{obs_server.OBS_PORT}"
        routes = {
            "open_config": "/config",
            "open_editor": "/?edit=true",
            "open_divot": "/divot",
            "open_tiles": "/tiles",
            "open_layout": "/?mode=projector",
        }
        if action in routes:
            production.webbrowser.open(url + routes[action])
        elif action == "copy_obs_url":
            app.copy_to_clipboard(url)
        elif action in ("export_csv", "export_pdf"):
            app.export_session_report(action.removeprefix("export_"))
        elif action == "open_log_folder":
            app.open_log_folder()
        elif action == "set_mode_0":
            app.set_mode(0)
        elif action == "scale_minus":
            app.step_ui_scale(-1)
        elif action == "scale_plus":
            app.step_ui_scale(1)
        elif action == "scale_auto":
            app.set_ui_scale("Auto")
        elif action == "legacy_tools":
            app.show_tools_menu = True
        app.draw_screen()
        return True
    return False
