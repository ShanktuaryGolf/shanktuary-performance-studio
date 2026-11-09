"""Concept-era analytical workspaces, with production state and interactions.

Coordinates are deliberately in the existing desktop coordinate system. The
shell owns viewport translation. No sample measurements are manufactured here.
"""

from __future__ import annotations

from contextlib import contextmanager

import theme
from src.ui import tokens as T

# This palette is private to painting, so compatibility browser tokens are not
# changed and worker/hardware state cannot accidentally become presentation.
PALETTE = {
    "BG": T.PAGE_BG,
    "RAIL": T.RAIL_BG,
    "SURFACE": T.SURFACE,
    "SURFACE_2": T.SURFACE_2,
    "HAIRLINE": T.HAIRLINE,
    "TEXT": T.TEXT,
    "TEXT_2": T.TEXT_2,
    "TEXT_3": T.TEXT_3,
    "ACCENT_DEEP": T.ACTIVE_BG,
    "ACCENT": T.TEAL_LINE,
    "ACCENT_LINE": T.TEAL_LINE,
    "ACCENT_TEXT": T.TEAL_TEXT,
    "WARN": T.GOLD,
    "GOLD": T.GOLD,
    "GOOD": T.SUCCESS,
    "GUIDE": T.GUIDE,
    "MUTED": T.TEXT_3,
}
AQUA = PALETTE["ACCENT"]
GOLD = PALETTE["GOLD"]


def panel(c, x0, y0, x1, y1, *, fill=None, outline=None, radius=12, **kw):
    from .concept_shell import panel as material_panel

    return material_panel(
        c,
        x0,
        y0,
        x1,
        y1,
        fill=fill if fill is not None else PALETTE["SURFACE"],
        outline=outline if outline is not None else PALETTE["HAIRLINE"],
        r=radius,
        **kw,
    )


def text(c, x, y, value, size=12, color=None, anchor="nw", bold=False, **kw):
    return c.create_text(
        x,
        y,
        text=value,
        fill=color or PALETTE["TEXT"],
        font=(theme.ui_font(), size, "bold" if bold else "normal"),
        anchor=anchor,
        **kw,
    )


def button(c, rect, label, active=False):
    panel(
        c,
        *rect,
        fill=PALETTE["ACCENT_DEEP"] if active else PALETTE["SURFACE"],
        outline=AQUA if active else PALETTE["HAIRLINE"],
        radius=9,
    )
    text(
        c,
        (rect[0] + rect[2]) / 2,
        (rect[1] + rect[3]) / 2,
        label,
        12,
        anchor="center",
        bold=True,
    )


@contextmanager
def palette(app, rounded=False):
    """Retain production geometry/actions while giving old panes new material."""
    missing = object()
    old = {k: getattr(theme, k, missing) for k in PALETTE}
    for k, value in PALETTE.items():
        setattr(theme, k, value)
    c = app.canvas
    rectangle = c.create_rectangle
    if rounded:

        def rounded_rect(*args, **kw):
            coords = args[0] if len(args) == 1 else args
            if len(coords) == 4:
                x0, y0, x1, y1 = coords
                if x1 - x0 >= 48 and y1 - y0 >= 22:
                    return panel(c, x0, y0, x1, y1, radius=10, **kw)
            return rectangle(*args, **kw)

        c.create_rectangle = rounded_rect
    try:
        yield
    finally:
        if rounded:
            c.create_rectangle = rectangle
        for k, value in old.items():
            if value is missing:
                delattr(theme, k)
            else:
                setattr(theme, k, value)


def _clear_bag_hits(app):
    for name in (
        "bag_club_card_rects",
        "bag_edit_btn_rects",
        "bag_move_up_rects",
        "bag_move_down_rects",
    ):
        setattr(app, name, [])


def draw_bag(app, avail_w, h, offset_x=0):
    """Equipment table and carry ladder from the approved My Bag composition."""
    c = app.canvas
    x0, x1 = offset_x + 16, offset_x + avail_w - 16
    with palette(app):
        _clear_bag_hits(app)
        c.create_rectangle(
            offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline=""
        )
        y = 60
        scope_w = min(250, (avail_w - 350) / 2)
        app.bag_scope_session_rect = (x0, y, x0 + scope_w, y + 42)
        app.bag_scope_all_rect = (x0 + scope_w, y, x0 + scope_w * 2, y + 42)
        button(
            c, app.bag_scope_session_rect, "Current session", app.bag_scope == "session"
        )
        button(
            c, app.bag_scope_all_rect, "All-time history", app.bag_scope == "all_time"
        )
        app.bag_autofill_btn_rect = (x1 - 300, y, x1 - 155, y + 42)
        app.bag_add_club_btn_rect = (x1 - 143, y, x1, y + 42)
        button(c, app.bag_autofill_btn_rect, "Auto-fill set")
        button(c, app.bag_add_club_btn_rect, "+ Add club")
        # Preserve ball selection/removal/addition, which is stamped on shots.
        ball_h = app._draw_bag_ball_row(x0, y + 48, avail_w - 32, x1)
        top, bottom = y + 52 + ball_h, h - 26
        split = x0 + (x1 - x0) * 0.635
        panel(c, x0, top, split - 7, bottom)
        panel(c, split + 7, top, x1, bottom)
        text(c, x0 + 18, top + 16, "Club mapping & gapping", 20, bold=True)
        text(
            c,
            x0 + 18,
            top + 48,
            "Shot averages • select a club or edit specifications",
            10,
            theme.TEXT_2,
        )
        left_width = split - x0 - 30
        columns = [
            x0 + 26,
            x0 + left_width * 0.27,
            x0 + left_width * 0.43,
            x0 + left_width * 0.61,
            x0 + left_width * 0.76,
        ]
        hy = top + 84
        panel(c, x0 + 10, hy, split - 17, hy + 48, fill=theme.SURFACE_2, radius=9)
        for xx, label in zip(columns, ("Club", "Loft", "Carry", "Spread", "Shots")):
            text(c, xx, hy + 13, label, 11, bold=True)
        row_h = 42
        list_top, list_bottom = hy + 54, bottom - 12
        visible = max(1, int((list_bottom - list_top) / row_h))
        max_scroll = max(0, len(app.bag) - visible) * row_h
        app.bag_scroll_offset = max(0, min(max_scroll, app.bag_scroll_offset))
        first = int(app.bag_scroll_offset / row_h)
        for index, club in enumerate(app.bag[first : first + visible]):
            ry = list_top + index * row_h
            name = club.get("name", "")
            stats = app.get_bag_club_stats(name, scope=app.bag_scope)
            selected = name == app.current_club
            color = GOLD if selected else theme.TEXT
            if selected:
                panel(
                    c,
                    x0 + 10,
                    ry,
                    split - 17,
                    ry + row_h - 3,
                    fill=T.SECTION_BG,
                    outline=GOLD,
                    width=1.5,
                )
            else:
                c.create_line(
                    x0 + 18, ry + row_h - 2, split - 22, ry + row_h - 2, fill=T.HAIRLINE
                )
            app.bag_club_card_rects.append(
                (x0 + 10, ry, split - 17, ry + row_h - 3, name)
            )
            loft = club.get("loft_deg")
            n = stats["shot_count"]
            values = (
                name,
                f"{loft:.1f}°" if loft else "--",
                f"{stats['avg_carry']:.0f} yd"
                if n and stats["avg_carry"] > 0
                else "--",
                f"±{stats['std_carry']:.0f} yd"
                if n and stats["avg_carry"] > 0
                else "--",
                str(n),
            )
            for col_index, (xx, value) in enumerate(zip(columns, values)):
                text(c, xx, ry + 11, value, 12, color, bold=col_index in (0, 2))
            # Keep edit and reordering reachable; use vector strokes, not
            # platform-dependent emoji glyphs, for the edit affordance.
            ex = split - 67
            app.bag_edit_btn_rects.append(
                (ex - 12, ry + 3, ex + 12, ry + row_h - 3, name)
            )
            c.create_line(ex - 5, ry + 26, ex + 5, ry + 14, fill=color, width=2)
            c.create_line(ex - 6, ry + 27, ex - 2, ry + 26, fill=color, width=2)
            ux = split - 37
            app.bag_move_up_rects.append((ux - 9, ry + 1, ux + 9, ry + 20, name))
            app.bag_move_down_rects.append((ux - 9, ry + 21, ux + 9, ry + 40, name))
            c.create_line(
                ux - 4,
                ry + 13,
                ux,
                ry + 9,
                ux + 4,
                ry + 13,
                fill=theme.TEXT_3,
                width=1.5,
            )
            c.create_line(
                ux - 4,
                ry + 28,
                ux,
                ry + 32,
                ux + 4,
                ry + 28,
                fill=theme.TEXT_3,
                width=1.5,
            )
        if len(app.bag) > visible:
            text(
                c,
                split - 24,
                bottom - 8,
                f"Scroll for all {len(app.bag)} clubs",
                8,
                theme.TEXT_3,
                anchor="se",
            )
        _bag_ladder(app, split + 7, top, x1, bottom)


def _bag_ladder(app, x0, y0, x1, y1):
    c = app.canvas
    text(c, x0 + 20, y0 + 16, "Carry & gap", 20, bold=True)
    text(
        c,
        x0 + 20,
        y0 + 48,
        "Average carry • distance to next club",
        10,
        PALETTE["TEXT_2"],
    )
    data = app.calculate_bag_gapping(scope=app.bag_scope)
    clubs = [item for item in data["clubs"] if item.get("avg_carry", 0) > 0]
    if not clubs:
        text(
            c,
            (x0 + x1) / 2,
            (y0 + y1) / 2,
            "No carry data in this scope.\nHit shots to build your distance ladder.",
            11,
            PALETTE["TEXT_3"],
            anchor="center",
            justify="center",
            width=x1 - x0 - 40,
        )
        return
    top, bottom = y0 + 106, y1 - 42
    step = (bottom - top) / max(1, len(clubs) - 1)
    cx = x0 + (x1 - x0) * 0.39
    c.create_line(
        cx, top - 12, cx, (bottom if len(clubs) > 1 else top) + 12, fill=AQUA, width=2
    )
    for i, item in enumerate(clubs):
        yy = top + i * step
        selected = item["name"] == app.current_club
        col = GOLD if selected else PALETTE["TEXT"]
        text(c, cx - 18, yy, item["name"], 11, col, anchor="e", bold=True)
        radius = 8 if selected else 5
        c.create_oval(
            cx - radius,
            yy - radius,
            cx + radius,
            yy + radius,
            fill=GOLD if selected else AQUA,
            outline="",
        )
        text(
            c,
            cx + 20,
            yy,
            f"{item['avg_carry']:.0f} yd",
            15,
            col,
            anchor="w",
            bold=True,
        )
        if i + 1 < len(clubs):
            gap = item["avg_carry"] - clubs[i + 1]["avg_carry"]
            rect = (x1 - 83, yy + step / 2 - 11, x1 - 13, yy + step / 2 + 11)
            panel(c, *rect, fill=PALETTE["SURFACE_2"], radius=11)
            text(
                c,
                (rect[0] + rect[2]) / 2,
                yy + step / 2,
                f"−{gap:.0f} yd",
                9,
                anchor="center",
            )


def draw_lab(app, avail_w, h, offset_x=0):
    """Recompose the four live pressure analyses without inventing foot data."""
    import obs_server

    from .lab_demo import active

    preview = active(app)
    c = app.canvas
    x0, x1, top, bottom = offset_x + 16, offset_x + avail_w - 16, 60, h - 22
    latest = None
    reviewing = app.is_reviewing_past_shot() and not preview
    manager = getattr(obs_server, "pressure_manager", None)
    if preview:
        latest = app.lab_demo_frames[-1] if app.lab_demo_frames else None
    elif reviewing:
        trace = app.get_pressure_trace(app.current_shot) if app.current_shot else None
        latest = trace[-1] if trace else None
    else:
        latest = getattr(manager, "latest_frame", None)
        if not latest and app.current_shot:
            trace = app.get_pressure_trace(app.current_shot)
            latest = trace[-1] if trace else None
    with palette(app):
        c.create_rectangle(
            offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline=""
        )
        demo = preview or bool(getattr(manager, "is_simulator", False))
        for i, (attr, label) in enumerate(
            (
                ("swing_lab_hw_rect", "Hardware"),
                ("swing_lab_tare_rect", "Tare unavailable" if preview else "Tare zero"),
                ("swing_lab_demo_rect", "Stop demo" if preview else "Demo swing"),
            )
        ):
            rect = (x1 - 426 + i * 146, top, x1 - 292 + i * 146, top + 36)
            setattr(app, attr, rect)
            button(c, rect, label, i == 2)
        if preview:
            tag = "SIMULATED · preview only · not saved"
        elif reviewing:
            tag = "Historical shot trace · final sample" if latest else "Historical shot · pressure unavailable"
        else:
            tag = "DEMO / SIMULATED" if demo else "Local board data"
        text(c, x0 + 4, top + 10, tag, 11, GOLD if demo and not reviewing else theme.TEXT_2)
        grid_top = top + 52
        metrics_y = bottom - 96
        half = (x1 - x0 - 16) / 2
        left_end, right_start = x0 + half, x0 + half + 16
        middle = grid_top + (metrics_y - grid_top - 16) * 0.51
        panels = [
            (x0, grid_top, left_end, middle, "Centre of pressure trail"),
            (right_start, grid_top, x1, middle, "Board-zone loads"),
            (x0, middle + 14, left_end, metrics_y - 14, "Weight transfer"),
            (right_start, middle + 14, x1, metrics_y - 14, "Force curve"),
        ]
        for px, py, qx, qy, title in panels:
            panel(c, px, py, qx, qy)
            text(c, px + 18, py + 14, title, 18, bold=True)
        # The CoP's actual millimetre axes are important: the concept artwork
        # cannot replace this with an invented anatomical pressure measurement.
        if latest:
            app.draw_cop_trajectory_canvas(
                x0 + 18, grid_top + 44, half - 36, middle - grid_top - 54, latest=latest
            )
        else:
            text(
                c,
                (x0 + left_end) / 2,
                (grid_top + middle) / 2,
                "No pressure captured for this shot" if reviewing else "Awaiting pressure data",
                12,
                theme.TEXT_3,
                anchor="center",
            )
        fw = (half - 66) / 2
        fh = middle - grid_top - 64
        if latest:
            app.draw_single_foot_heatmap(
                right_start + 20, grid_top + 45, fw, fh, is_left=True, latest=latest
            )
            app.draw_single_foot_heatmap(
                right_start + 46 + fw,
                grid_top + 45,
                fw,
                fh,
                is_left=False,
                latest=latest,
            )
        else:
            text(
                c,
                (right_start + x1) / 2,
                (grid_top + middle) / 2,
                (
                    "No pressure captured for this shot"
                    if reviewing
                    else "No board connected\nConnect boards in Setup or start Demo swing"
                ),
                11,
                theme.TEXT_3,
                anchor="center",
                justify="center",
                width=half - 44,
            )
        app.draw_force_timeline_canvas(
            x0 + 8, middle + 53, half - 16, metrics_y - middle - 77, series="transfer"
        )
        app.draw_force_timeline_canvas(
            right_start + 8,
            middle + 53,
            half - 16,
            metrics_y - middle - 77,
            series="force",
        )
        panel(c, x0, metrics_y, x1, bottom)
        left = latest.get("pct_left") if latest else None
        right = latest.get("pct_right") if latest else None
        lead, trail = (right, left) if app.is_left_handed else (left, right)
        values = [
            ("Total weight", latest.get("total_kg") if latest else None, "kg"),
            ("Force", latest.get("force_bw") if latest else None, "BW"),
            ("Lead", lead, "%"),
            ("Trail", trail, "%"),
            ("Torque", latest.get("torque_nm") if latest else None, "N·m"),
            ("Phase", latest.get("phase") if latest else None, ""),
        ]
        cell = (x1 - x0) / 6
        for i, (label, value, unit) in enumerate(values):
            xx = x0 + 20 + i * cell
            text(c, xx, metrics_y + 13, label, 11, theme.TEXT_2)
            if isinstance(value, (int, float)):
                shown = f"{value:.0f}{unit}" if unit == "%" else f"{value:.2f} {unit}"
            else:
                shown = str(value).title() if value is not None else "--"
            text(
                c,
                xx,
                metrics_y + 39,
                shown,
                20,
                theme.TEXT if value is not None else theme.TEXT_3,
                bold=True,
            )
            if i:
                c.create_line(
                    xx - 12, metrics_y + 15, xx - 12, bottom - 15, fill=theme.HAIRLINE
                )


def _index_progress(app, x0, y0, x1, y1):
    """Use the saved dated series, never the illustrative concept curve."""
    from src.analytics import index_history

    c = app.canvas
    text(c, x0, y0, "Progress", 17, bold=True)
    text(c, x0 + 110, y0 + 4, "(all-time)", 12, PALETTE["TEXT_2"])
    series = index_history.load()
    trend = index_history.trend(series)
    if not trend:
        text(c, x0, y0 + 58, "No history yet", 16, PALETTE["TEXT_2"])
        text(
            c,
            x0,
            y0 + 88,
            "Available Index scores are saved after each session.",
            11,
            PALETTE["TEXT_3"],
            width=x1 - x0 - 20,
        )
        return
    divider = x1 - 148
    c.create_line(divider, y0 + 36, divider, y1 - 8, fill=PALETTE["HAIRLINE"])
    delta = trend.get("delta")
    text(
        c,
        divider + 22,
        y0 + 35,
        f"{delta:+.1f}" if delta is not None else "--",
        28,
        AQUA if delta is None or delta >= 0 else GOLD,
        bold=True,
    )
    text(c, divider + 22, y0 + 81, "vs last snapshot", 10, PALETTE["TEXT_2"])
    text(c, divider + 22, y0 + 120, "Best", 12, PALETTE["TEXT_2"])
    text(c, divider + 22, y0 + 145, f"{trend['best']:.1f}", 31, GOLD, bold=True)
    points = [item for item in series if isinstance(item.get("score"), (int, float))]
    px, qx, py, qy = x0 + 42, divider - 28, y0 + 60, y1 - 32
    scores = [float(item["score"]) for item in points]
    lo, hi = min(scores) - 1, max(scores) + 1
    span = max(2, hi - lo)
    for i in range(4):
        yy = py + (qy - py) * i / 3
        text(
            c,
            px - 10,
            yy,
            f"{hi - span * i / 3:.0f}",
            10,
            PALETTE["TEXT_2"],
            anchor="e",
        )
        c.create_line(px, yy, qx, yy, fill=PALETTE["GUIDE"])
    coords = []
    for i, score in enumerate(scores):
        coords.extend(
            (
                px + (qx - px) * i / max(1, len(scores) - 1),
                qy - (score - lo) / span * (qy - py),
            )
        )
    if len(scores) > 1:
        c.create_polygon(
            px, qy, *coords, qx, qy, fill=PALETTE["ACCENT_DEEP"], outline=""
        )
        c.create_line(*coords, fill=AQUA, width=3, tags="index-sparkline")
    xx, yy = coords[-2:]
    c.create_oval(xx - 6, yy - 6, xx + 6, yy + 6, fill=GOLD, outline="")
    for xx, item, anchor in ((px, points[0], "nw"), (qx, points[-1], "ne")):
        text(c, xx, qy + 10, str(item["at"])[:10], 9, PALETTE["TEXT_2"], anchor=anchor)


def _index_combine(app, x0, y0, x1, y1):
    """The existing Combine history and launcher in their own concept card."""
    from src.analytics import combine

    c = app.canvas
    panel(c, x0, y0, x1, y1, tags="index-combine-pane")
    text(c, x0 + 20, y0 + 14, "Combine", 24, bold=True)
    text(c, x0 + 20, y0 + 54, "Structured test • recorded runs", 12, PALETTE["TEXT_2"])
    summary = combine.summary(combine.load())
    for xx, label, key, color in (
        (x0 + 38, "Latest", "latest", PALETTE["TEXT"]),
        (x0 + 244, "Best", "best", GOLD),
    ):
        text(c, xx, y0 + 95, label, 14, PALETTE["TEXT_2"])
        val = summary.get(key) if summary else None
        text(
            c,
            xx,
            y0 + 121,
            f"{val:.1f}" if isinstance(val, (int, float)) else "--",
            37,
            color if val is not None else PALETTE["TEXT_3"],
            bold=True,
        )
    c.create_line(x0 + 205, y0 + 95, x0 + 205, y0 + 167, fill=PALETTE["HAIRLINE"])
    rect = (x1 - 229, y0 + 100, x1 - 18, y0 + 168)
    panel(c, *rect, outline=AQUA, tags="index-open-combine")
    text(
        c,
        (rect[0] + rect[2]) / 2,
        (rect[1] + rect[3]) / 2,
        "Open Combine\nin 3D Range",
        14,
        anchor="center",
        bold=True,
        tags="index-open-combine",
    )
    app.concept_index_combine_rect = rect
    run = app.combine_result() if hasattr(app, "combine_result") else None
    if run and run.get("stations"):
        detail = "  •  ".join(
            f"{st['club']} {st['counted']}/{st['needed']}" for st in run["stations"]
        )
    elif summary:
        detail = (
            f"{summary['runs']} recorded runs • latest {summary['latest_date'][:10]}"
        )
    else:
        detail = "No combine yet • start one from the 3D Range"
    text(c, x0 + 24, y1 - 32, detail, 10, PALETTE["TEXT_3"], width=x1 - x0 - 48)


def draw_index(app, avail_w, h, offset_x=0):
    """Index is a calculated practice score, never represented as a handicap."""
    import shanktuary_performance_studio as production

    shots = [
        shot
        for sess in app.sessions
        for shot in sess.get("shots", [])
        if isinstance(shot, dict)
    ]
    result = production.player_shanktuary_index(
        shots, is_left_handed=app.is_left_handed
    )
    c = app.canvas
    x0, x1, top, bottom = offset_x + 16, offset_x + avail_w - 24, 60, h - 62
    split = x0 + (x1 - x0) * 0.52
    left_end, right = split - 8, split + 8
    score_bottom = top + (bottom - top) * 0.63
    with palette(app):
        c.create_rectangle(
            offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline=""
        )
        panel(c, x0, top, left_end, score_bottom, tags="index-score-pane")
        text(c, x0 + 20, top + 14, "Shanktuary Index", 24, bold=True)
        text(
            c,
            x0 + 20,
            top + 55,
            "Practice performance • not a validated handicap",
            12,
            theme.TEXT_2,
        )
        score = result.get("score") if result.get("status") == "available" else None
        text(
            c,
            x0 + 24,
            top + 88,
            f"{score:.1f}" if isinstance(score, (int, float)) else "--",
            94,
            GOLD if score is not None else theme.TEXT_3,
            bold=True,
        )
        count = len(result.get("established_clubs") or [])
        divider = x0 + (left_end - x0) * 0.53
        c.create_line(divider, top + 108, divider, top + 203, fill=theme.HAIRLINE)
        text(
            c,
            divider + 27,
            top + 148,
            f"{count} established clubs",
            14,
            theme.TEXT_2,
            anchor="w",
        )
        if score is None:
            text(
                c,
                x0 + 24,
                top + 217,
                result.get("reason") or "Hit shots to build your Index",
                10,
                theme.TEXT_3,
                width=left_end - x0 - 48,
            )
        c.create_line(x0 + 20, top + 244, left_end - 20, top + 244, fill=theme.HAIRLINE)
        _index_progress(app, x0 + 20, top + 259, left_end - 20, score_bottom - 14)
        _index_combine(app, x0, score_bottom + 16, left_end, bottom)
        area_bottom = top + (bottom - top) * 0.32
        panel(c, right, top, x1, area_bottom)
        text(c, right + 18, top + 12, "Game-area breakdown", 23, bold=True)
        text(
            c,
            right + 18,
            top + 51,
            "Index contribution • recorded shots",
            12,
            theme.TEXT_2,
        )
        areas = result.get("game_areas") or {}
        for i, code in enumerate(("A", "B", "C", "D")):
            area = areas.get(code) or {}
            yy = top + 98 + i * 38
            val = area.get("score")
            text(c, right + 18, yy, area.get("name", code), 13, anchor="w")
            bx = right + (x1 - right) * 0.48
            text(
                c,
                bx - 22,
                yy,
                f"{val:.1f}" if isinstance(val, (int, float)) else "--",
                15,
                anchor="e",
                bold=True,
            )
            panel(c, bx, yy - 7, x1 - 18, yy + 7, fill=theme.SURFACE_2, radius=7)
            if isinstance(val, (int, float)) and val > 0:
                panel(
                    c,
                    bx,
                    yy - 7,
                    bx + (x1 - 18 - bx) * min(1, val / 100),
                    yy + 7,
                    fill=AQUA,
                    outline="",
                    radius=7,
                )
            if i < 3:
                c.create_line(
                    right + 18, yy + 20, x1 - 18, yy + 20, fill=theme.HAIRLINE
                )
        py = area_bottom + 16
        panel(c, right, py, x1, bottom)
        text(c, right + 18, py + 12, "Per-club composites", 23, bold=True)
        text(c, right + 18, py + 51, "Index by club • recorded shots", 12, theme.TEXT_2)
        clubs = result.get("per_club") or result.get("clubs") or []
        if isinstance(clubs, dict):
            clubs = [dict(value, name=key) for key, value in clubs.items()]
        text(c, right + 20, py + 91, "Club", 12, theme.TEXT_2)
        text(
            c,
            right + (x1 - right) * 0.39,
            py + 91,
            "Index",
            12,
            theme.TEXT_2,
            anchor="ne",
        )
        c.create_line(right + 18, py + 118, x1 - 18, py + 118, fill=theme.HAIRLINE)
        yy = py + 139
        for club in clubs:
            if yy > bottom - 28:
                break
            val = (club.get("composite") or {}).get("score", club.get("score"))
            name = club.get("club", club.get("name", ""))
            text(c, right + 26, yy, name, 14, anchor="w", bold=True)
            bx = right + (x1 - right) * 0.46
            text(
                c,
                bx - 24,
                yy,
                f"{val:.1f}" if isinstance(val, (int, float)) else "--",
                15,
                anchor="e",
                bold=True,
            )
            panel(c, bx, yy - 7, x1 - 22, yy + 7, fill=theme.SURFACE_2, radius=7)
            if isinstance(val, (int, float)) and val > 0:
                panel(
                    c,
                    bx,
                    yy - 7,
                    bx + (x1 - 22 - bx) * min(1, val / 100),
                    yy + 7,
                    fill=AQUA,
                    outline="",
                    radius=7,
                )
            yy += 40
            sentence = app._pressure_sentence_for(name)
            if sentence and yy < bottom - 28:
                text(
                    c,
                    right + 26,
                    yy - 12,
                    sentence,
                    8,
                    theme.ACCENT_TEXT,
                    width=x1 - right - 48,
                )
                yy += 24
            c.create_line(right + 18, yy - 18, x1 - 18, yy - 18, fill=theme.HAIRLINE)
        if not clubs:
            text(
                c,
                (right + x1) / 2,
                py + 165,
                "Hit shots to build club data",
                12,
                theme.TEXT_3,
                anchor="center",
            )


def handle_index_click(app, x, y):
    """Route the complete visible Combine target, including its material."""
    rect = getattr(app, "concept_index_combine_rect", None)
    if rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
        app.launch_3d_range()
        return True
    return False


def _dropdown(c, rect, label, color=AQUA):
    panel(c, *rect, outline=PALETTE["TEXT_2"], radius=11)
    cy = (rect[1] + rect[3]) / 2
    c.create_oval(rect[0] + 19, cy - 7, rect[0] + 33, cy + 7, fill=color, outline="")
    text(c, rect[0] + 52, cy, label, 16, anchor="w", bold=True)
    c.create_line(
        rect[2] - 35,
        cy - 4,
        rect[2] - 27,
        cy + 4,
        rect[2] - 19,
        cy - 4,
        fill=PALETTE["TEXT"],
        width=1.5,
    )


def _provenance_badge(c, x, y, label, size=8):
    color = (
        GOLD
        if label in ("Estimate", "Modelled")
        else (AQUA if label == "Reported" else PALETTE["TEXT_2"])
    )
    width = max(56, len(label) * size * 0.70 + 14)
    panel(c, x, y - 11, x + width, y + 11, fill=PALETTE["BG"], outline=color, radius=6)
    text(c, x + width / 2, y, label, size, color, anchor="center")
    return width


def draw_fit(app, avail_w, h, offset_x=0):
    """Two selectable clubs, paired analytical plots, and source-aware summary."""
    import statistics

    from src.connections.presentation import metric_status, metric_value

    c = app.canvas
    x0, x1, top, bottom = offset_x + 16, offset_x + avail_w - 20, 52, h - 68
    app.concept_fit_details_rect = None
    app.concept_fit_selector_rects = []
    if getattr(app, "concept_fit_details", False):
        import shanktuary_performance_studio as production

        with palette(app, rounded=True):
            production.ShanktuaryApp.draw_fitting_viewport(
                app, avail_w, h - 30, offset_x=offset_x
            )
            rect = (x1 - 225, h - 38, x1, h - 6)
            button(c, rect, "Back to visual comparison")
            app.concept_fit_details_rect = rect
        return
    clubs = app.get_fitting_clubs()
    if app.fitting_baseline_club not in clubs:
        app.fitting_baseline_club = clubs[0] if clubs else app.current_club
    base = app.fitting_baseline_club
    test = getattr(app, "concept_fit_test_club", None)
    if test not in clubs or test == base:
        test = next(
            (name for name in clubs if name == app.current_club and name != base), None
        )
        test = test or next((name for name in clubs if name != base), None)
    app.concept_fit_test_club = test
    ordered = [name for name in (base, test) if name]
    app.fitting_submode_rects = []
    app.fitting_club_chip_rects = []
    app.fitting_baseline_chip_rects = []
    app.fitting_dot_rects = []
    with palette(app):
        c.create_rectangle(
            offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline=""
        )
        selector_w = (x1 - x0) * 0.31
        for i, (key, label, name, color) in enumerate(
            (("base", "Base club", base, AQUA), ("test", "Test club", test, GOLD))
        ):
            xx = x0 + 16 + i * (selector_w + 26)
            text(c, xx, top, label, 12, theme.ACCENT_TEXT)
            rect = (xx, top + 22, xx + selector_w, top + 68)
            _dropdown(c, rect, name or "Choose test club", color)
            app.concept_fit_selector_rects.append((*rect, key))
        app.fitting_add_club_rect = (
            x0 + 2 * (selector_w + 26) + 16,
            top + 22,
            min(x1, x0 + 2 * (selector_w + 26) + 216),
            top + 68,
        )
        button(c, app.fitting_add_club_rect, "+  New club")
        tab_y = top + 94
        for i, (key, label) in enumerate(
            (
                ("split", "Split view"),
                ("topdown", "Overhead dispersion"),
                ("side", "Trajectory side-view"),
            )
        ):
            width = (x1 - x0) / 3
            rect = (x0 + i * width, tab_y, x0 + (i + 1) * width, tab_y + 52)
            button(c, rect, label, app.fitting_submode == key)
            app.fitting_submode_rects.append((*rect, key))
        plot_y = tab_y + 72
        # The legacy splitter default was 0.52. Start at the approved 60/40
        # composition once, then continue honoring the user's drag ratio.
        if not getattr(app, "_concept_fit_split_initialized", False):
            if getattr(app, "fitting_splitter_ratio", 0.52) == 0.52:
                app.fitting_splitter_ratio = 0.60
            app._concept_fit_split_initialized = True
        split = x0 + (x1 - x0) * max(
            0.35, min(0.70, getattr(app, "fitting_splitter_ratio", 0.60))
        )
        app.fitting_splitter_rect = (split - 7, plot_y, split + 7, bottom)
        data, provenance = {}, {}
        for name in ordered:
            rows, states = [], {}
            for index, shot in enumerate(app.session_shots):
                if shot.get("club") != name or shot.get("excluded", False):
                    continue
                view = app.aim_corrected(shot)
                values = {
                    key: metric_value(view, key, app.is_left_handed)
                    for key in (
                        "carry",
                        "total",
                        "offline",
                        "apex",
                        "spin",
                        "ball_speed",
                        "launch",
                    )
                }
                for key, value in values.items():
                    if value is not None:
                        states.setdefault(key, []).append(
                            metric_status(view, key, app.is_left_handed)
                        )
                rows.append((index, values))
            data[name], provenance[name] = rows, states
        rx = split + 8
        panel(c, rx, plot_y, x1, bottom)
        text(c, rx + 22, plot_y + 12, "Comparison summary", 21, bold=True)
        text(
            c, rx + 22, plot_y + 48, "Base vs test • session averages", 12, theme.TEXT_2
        )
        table_x, table_end, table_y = rx + 12, x1 - 12, plot_y + 82
        metric_end = table_x + (table_end - table_x) * 0.40
        cw = (table_end - metric_end) / 2
        header_h, row_h = 64, 52
        table_bottom = table_y + header_h + row_h * 5
        panel(c, table_x, table_y, table_end, table_bottom, fill=theme.BG, radius=10)
        text(
            c, table_x + 14, table_y + header_h / 2, "Metric", 13, anchor="w", bold=True
        )
        for i, name in enumerate((base, test)):
            xx = metric_end + cw * (i + 0.5)
            text(
                c,
                xx,
                table_y + 23,
                name or "No test club",
                12,
                AQUA if i == 0 else GOLD,
                anchor="center",
                bold=True,
                width=cw - 12,
            )
            text(
                c,
                xx,
                table_y + 47,
                "(Base)" if i == 0 else "(Test)",
                10,
                theme.TEXT_2,
                anchor="center",
            )
        for xx in (metric_end, metric_end + cw):
            c.create_line(xx, table_y, xx, table_bottom, fill=theme.HAIRLINE)
        ranks = {"REPORTED": 0, "DERIVED": 1, "ESTIMATED": 2, "MODELLED": 3}
        labels = {
            "REPORTED": "Reported",
            "DERIVED": "Derived",
            "ESTIMATED": "Estimate",
            "MODELLED": "Modelled",
        }
        for j, (label, key, unit) in enumerate(
            (
                ("Carry", "carry", "yd"),
                ("Spread (σ)", "spread", "yd"),
                ("Apex", "apex", "ft"),
                ("Spin", "spin", "rpm"),
                ("Shots", "count", ""),
            )
        ):
            yy = table_y + header_h + row_h * (j + 0.5)
            c.create_line(
                table_x, yy - row_h / 2, table_end, yy - row_h / 2, fill=theme.HAIRLINE
            )
            text(c, table_x + 14, yy, label, 13, anchor="w")
            states = [
                state for name in ordered for state in provenance[name].get(key, [])
            ]
            status = (
                "Derived"
                if key in ("spread", "count")
                else labels[max(states, key=ranks.get)]
                if states
                else "Unavailable"
            )
            if metric_end - table_x > 185:
                _provenance_badge(c, metric_end - 81, yy, status)
            for i, name in enumerate((base, test)):
                rows = data.get(name, [])
                vals = [v.get("carry" if key == "spread" else key) for _, v in rows]
                vals = [v for v in vals if isinstance(v, (int, float))]
                value = (
                    len(rows)
                    if key == "count" and name
                    else (
                        statistics.pstdev(vals)
                        if key == "spread" and len(vals) > 1
                        else statistics.mean(vals)
                        if vals and key != "spread"
                        else None
                    )
                )
                if value is not None and key == "apex":
                    value *= 3  # The metric boundary returns apex in yards.
                out = (
                    "--"
                    if value is None
                    else (
                        f"±{value:.1f} {unit}"
                        if key == "spread"
                        else f"{value:,.0f} {unit}".strip()
                    )
                )
                text(
                    c,
                    metric_end + cw * (i + 0.5),
                    yy,
                    out,
                    16,
                    theme.TEXT if value is not None else theme.TEXT_3,
                    anchor="center",
                    bold=True,
                )
        legend_y = table_bottom + 43
        c.create_line(
            table_x, legend_y - 15, table_end, legend_y - 15, fill=theme.HAIRLINE
        )
        for i, (label, desc) in enumerate(
            (
                ("Reported", "From source"),
                ("Derived", "Calculated"),
                ("Estimate", "Not measured"),
                ("Unavailable", "Not reported"),
            )
        ):
            xx = table_x + 10 + i * (table_end - table_x) / 4
            _provenance_badge(c, xx, legend_y + 12, label, 7)
            text(c, xx, legend_y + 31, desc, 8, theme.TEXT_2)
        rect = (rx + 20, bottom - 43, x1 - 20, bottom - 10)
        button(c, rect, "Full comparison & recommendation")
        app.concept_fit_details_rect = rect
        bounds = (x0, plot_y, split - 8, bottom)
        if app.fitting_submode == "split":
            mid = (plot_y + bottom) / 2
            _fit_plot(app, (x0, plot_y, split - 8, mid - 7), data, base, False)
            _fit_plot(app, (x0, mid + 7, split - 8, bottom), data, base, True)
        else:
            _fit_plot(app, bounds, data, base, app.fitting_submode == "side")


def handle_fit_click(app, x, y):
    rect = getattr(app, "concept_fit_details_rect", None)
    if rect and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
        app.concept_fit_details = not getattr(app, "concept_fit_details", False)
        app.draw_screen()
        return True
    for x0, y0, x1, y1, kind in getattr(app, "concept_fit_selector_rects", []):
        if not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        import tkinter as tk

        previous = getattr(app, "_concept_fit_menu", None)
        if previous is not None:
            previous.destroy()
        menu = tk.Menu(
            app.root,
            tearoff=False,
            background=PALETTE["SURFACE"],
            foreground=PALETTE["TEXT"],
            activebackground=PALETTE["ACCENT_DEEP"],
            activeforeground=PALETTE["TEXT"],
            font=(theme.ui_font(), 12),
        )

        app._concept_fit_menu = menu
        previous_focus = app.root.focus_get()

        def dismiss(event=None):
            menu.unpost()
            menu.grab_release()
            menu.destroy()
            app._concept_fit_menu = None
            if previous_focus is not None and previous_focus.winfo_exists():
                previous_focus.focus_set()
            return "break"

        def select(name):
            dismiss()
            if kind == "base":
                app.fitting_baseline_club = name
            else:
                app.concept_fit_test_club = name
                app.current_club = name
            app.draw_screen()

        for name in app.get_fitting_clubs():
            if kind == "test" and name == app.fitting_baseline_club:
                continue
            menu.add_command(label=name, command=lambda name=name: select(name))
        menu.add_separator()
        menu.add_command(label="Cancel", command=dismiss)
        menu.bind("<Escape>", dismiss)
        # Tk's menu bindings own the grab until selection or outside-click
        # dismissal. Releasing it immediately after posting leaves Linux menus
        # stranded and prevents the normal outside-click behavior.
        menu.tk_popup(app.root.winfo_pointerx(), app.root.winfo_pointery())
        # On Linux, posting from a canvas may leave keyboard focus on the
        # toplevel (or outside the app). Explicitly focus this user-opened menu
        # so Escape reaches its dismissal binding, never the app's quit hotkey.
        menu.focus_force()
        return True
    return False


def _percentile(values, fraction):
    """Linearly interpolated empirical quantile (including small samples)."""
    import math

    values = sorted(values)
    if not values:
        return None
    index = (len(values) - 1) * fraction
    lo = math.floor(index)
    hi = math.ceil(index)
    return values[lo] + (values[hi] - values[lo]) * (index - lo)


def _ellipse_spread(pairs):
    """Axis-aligned W(lateral), D(carry) extents of the plotted normal ellipse.

    The 90% is a bivariate-normal model contour, not empirical coverage or a
    confidence interval. Population covariance matches the plotted contour.
    """
    import math
    import statistics

    pairs = [(x, y) for x, y in pairs if x is not None and y is not None
             and math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return None
    scale = math.sqrt(-2 * math.log(0.1))
    return (2 * scale * statistics.pstdev(y for x, y in pairs),
            2 * scale * statistics.pstdev(x for x, y in pairs))


def handle_dispersion_click(app, x, y):
    for rect, page in getattr(app, "dispersion_page_rects", []):
        if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
            app.dispersion_group_page = page
            app.draw_screen()
            return True
    return False


def _fit_plot(app, bounds, data, base, side):
    import math
    import statistics

    c = app.canvas
    x0, y0, x1, y1 = bounds
    panel(c, *bounds)
    text(
        c,
        x0 + 22,
        y0 + 10,
        "Trajectory (side-view)" if side else "Dispersion (overhead)",
        20,
        bold=True,
    )
    text(
        c,
        x0 + 22,
        y0 + 47,
        "Estimated paths • each shot’s carry & apex (not measured flight)"
        if side
        else "Carry position • available shots",
        10,
        PALETTE["TEXT_2"],
    )
    if not side:
        pairs = [(v.get("carry"), v.get("offline")) for rows in data.values() for _, v in rows]
        spread = _ellipse_spread(pairs)
        summary = (f"90% normal-model extent: {spread[0]:.1f} yd W × {spread[1]:.1f} yd D"
                   if spread else "90% normal-model extent: -- (needs 3 paired shots)")
        if len(data) > 1:
            summary += " • pooled groups"
        text(c, x0 + 22, y0 + 67, summary, 9, PALETTE["TEXT_2"])
    px, qx, py, qy = x0 + 80, x1 - 30, y0 + (100 if not side else 88), y1 - 42
    all_values = [
        v for rows in data.values() for _, v in rows if v.get("carry") is not None
    ]
    xmin = (
        0
        if side or not all_values
        else max(0, math.floor((min(v["carry"] for v in all_values) - 40) / 20) * 20)
    )
    xmax = max(200, max((v["carry"] for v in all_values), default=0) * 1.15)
    span = max(1, xmax - xmin)
    ymax = (
        max(40, max((v.get("apex") or 0 for v in all_values), default=0) * 1.2)
        if side
        else max(
            40, max((abs(v.get("offline") or 0) for v in all_values), default=0) * 1.2
        )
    )
    if side:
        from .concept_session import scenic

        # A side-view trajectory requires a flat side-profile scene, not
        # the behind-the-tee perspective used by the practice range.
        scenic(c, px, py, qx, qy)
    for i in range(5):
        xx = px + (qx - px) * i / 4
        yy = py + (qy - py) * i / 4
        c.create_line(xx, py, xx, qy, fill=PALETTE["GUIDE"])
        c.create_line(px, yy, qx, yy, fill=PALETTE["GUIDE"])
        text(
            c,
            xx,
            qy + 12,
            f"{xmin + span * i / 4:.0f} yd",
            10,
            PALETTE["TEXT_2"],
            anchor="n",
            tags="comparison-axis",
        )
        label = 3 * ymax * (1 - i / 4) if side else ymax * (1 - i / 2)
        text(
            c,
            px - 10,
            yy,
            f"{label:.0f} {'ft' if side else 'yd'}",
            10,
            PALETTE["TEXT_2"],
            anchor="e",
            tags="comparison-axis",
        )
    c.create_line(px, py, px, qy, qx, qy, fill=PALETTE["TEXT_2"], width=1)
    if not side:
        c.create_line(
            px, (py + qy) / 2, qx, (py + qy) / 2, fill=PALETTE["TEXT_2"], dash=(4, 4)
        )
    for ci, (name, rows) in enumerate(data.items()):
        color = (
            app.get_club_color(name)
            if getattr(app, "view_mode", None) == 3
            else AQUA
            if name == base
            else GOLD
            if ci <= 1
            else PALETTE["ACCENT_TEXT"]
        )
        if ci < 2 and x1 - x0 > 650 and getattr(app, "view_mode", None) != 3:
            lx, ly = x1 - 210, y0 + 30 + ci * 27
            c.create_oval(lx, ly - 6, lx + 12, ly + 6, fill=color, outline="")
            role = "Base" if name == base else "Test"
            text(c, lx + 23, ly, f"{role} − {name} (n={len(rows)})", 10, anchor="w")
        pairs = [
            (v["carry"], v["apex" if side else "offline"])
            for _, v in rows
            if v.get("carry") is not None
            and v.get("apex" if side else "offline") is not None
        ]
        if side:
            if not pairs:
                continue
            for carry, apex in pairs:
                if carry <= 0 or apex < 0:
                    continue
                coords = []
                for j in range(41):
                    t = j / 40
                    coords.extend((px + carry * t / xmax * (qx - px),
                                   qy - 4 * apex * t * (1 - t) / ymax * (qy - py)))
                c.create_line(*coords, fill=color, width=1.2, smooth=True,
                              dash=(5, 2), tags="estimated-shot-path")
            continue
        if len(pairs) >= 3:
            mx = statistics.mean(p[0] for p in pairs)
            my = statistics.mean(p[1] for p in pairs)
            vx = statistics.mean((p[0] - mx) ** 2 for p in pairs)
            vy = statistics.mean((p[1] - my) ** 2 for p in pairs)
            cov = statistics.mean((p[0] - mx) * (p[1] - my) for p in pairs)
            angle = 0.5 * math.atan2(2 * cov, vx - vy)
            disc = math.sqrt(max(0, (vx - vy) ** 2 + 4 * cov**2))
            major = math.sqrt(max(0, (vx + vy + disc) / 2)) * math.sqrt(-2 * math.log(0.1))
            minor = math.sqrt(max(0, (vx + vy - disc) / 2)) * math.sqrt(-2 * math.log(0.1))
            points = []
            for j in range(65):
                theta = 2 * math.pi * j / 64
                dx = major * math.cos(theta) * math.cos(angle) - minor * math.sin(
                    theta
                ) * math.sin(angle)
                dy = major * math.cos(theta) * math.sin(angle) + minor * math.sin(
                    theta
                ) * math.cos(angle)
                points.extend(
                    (
                        px + (mx + dx - xmin) / span * (qx - px),
                        (py + qy) / 2 - (my + dy) / ymax * (qy - py) / 2,
                    )
                )
            c.create_polygon(
                *points,
                fill=PALETTE["ACCENT_DEEP"] if name == base else "#26382E",
                outline=color,
                width=1.5,
                smooth=True,
            )
        for index, value in rows:
            carry, offline = value.get("carry"), value.get("offline")
            if carry is None or offline is None:
                continue
            xx = px + (carry - xmin) / span * (qx - px)
            yy = (py + qy) / 2 - offline / ymax * (qy - py) / 2
            c.create_oval(xx - 5, yy - 5, xx + 5, yy + 5, fill=color, outline="")
            target = (
                app.dispersion_dot_rects
                if getattr(app, "view_mode", None) == 3
                else app.fitting_dot_rects
            )
            target.append((xx, yy, index))
    available_pairs = [v for v in all_values if v.get("apex" if side else "offline") is not None]
    if not available_pairs:
        text(
            c,
            (px + qx) / 2,
            (py + qy) / 2,
            "No carry + apex data for estimated paths" if side else "No carry + lateral data to plot",
            11,
            PALETTE["TEXT_3"],
            anchor="center",
        )


def _source_icon(c, kind, cx, cy, color=None, max_width=100):
    """Use the shipped brand assets; only generic monitors get a pictogram."""
    color = color or PALETTE["TEXT"]
    if kind == "open_connect":
        c.create_rectangle(cx - 17, cy - 10, cx + 17, cy + 10, outline=color, width=2)
        c.create_line(cx, cy + 10, cx, cy + 17, fill=color, width=2)
        c.create_line(cx - 9, cy + 17, cx + 9, cy + 17, fill=color, width=2)
        return
    if kind not in ("nova", "gspro", "pureplay"):
        return
    import tkinter as tk

    from PIL import Image, ImageTk

    from .asset_paths import asset_path

    real = getattr(c, "_canvas", c)
    if not isinstance(real, tk.Canvas):
        return  # Recorder canvases have no Tcl image interpreter.
    scale = getattr(real, "ui_scale", 1)
    key = (kind, round(max_width * scale), round(32 * scale))
    cache = getattr(real, "_setup_source_logos", None)
    if cache is None:
        cache = real._setup_source_logos = {}
    if key not in cache:
        try:
            with Image.open(asset_path(f"{kind}_logo.png")) as source:
                pixels = source.convert("RGBA")
                pixels.thumbnail((max(1, key[1]), max(1, key[2])), Image.Resampling.LANCZOS)
            cache[key] = ImageTk.PhotoImage(pixels, master=real)
        except (OSError, tk.TclError):
            return  # The visible source name remains; never invent a brand mark.
    # Rasterize at the display scale once, as with the shell's brand mark.
    tk.Canvas._create(real, "image", (cx * scale, (cy + getattr(c, "dy", 0)) * scale),
                      {"image": cache[key], "anchor": "center", "tags": "setup-source-logo"})


def _board_outline(c, cx, cy, mirror=False):
    """An anatomical outline only; no invented live pressure texture."""
    sign = -1 if mirror else 1
    points = [
        (-7, -22),
        (-19, -12),
        (-20, 5),
        (-12, 20),
        (-11, 37),
        (-4, 49),
        (9, 47),
        (16, 35),
        (10, 14),
        (14, -1),
        (10, -19),
    ]
    c.create_polygon(
        *[v for x, y in points for v in (cx + sign * x, cy + y)],
        fill=PALETTE["SURFACE_2"],
        outline=PALETTE["TEXT_3"],
        width=1.5,
        smooth=True,
    )
    for xx, yy, r in (
        (9, -29, 7),
        (-3, -33, 5),
        (-13, -30, 4),
        (-21, -24, 3),
        (-25, -16, 2.5),
    ):
        xx = cx + sign * xx
        c.create_oval(
            xx - r,
            cy + yy - r,
            xx + r,
            cy + yy + r,
            fill=PALETTE["SURFACE_2"],
            outline=PALETTE["TEXT_3"],
        )


def draw_setup(app, avail_w, h, offset_x=0):
    """Concept overview with real connection, board, display and data actions."""
    import obs_server
    import shanktuary_performance_studio as production
    from user_data import get_data_dir

    c = app.canvas
    x0, x1, top, bottom = offset_x + 20, offset_x + avail_w - 24, 52, h - 88
    app.concept_setup_actions = {}
    if getattr(app, "concept_setup_page", "overview") == "details":
        from .concept_boards import draw

        return draw(app, avail_w, h, offset_x)
    with palette(app):
        c.create_rectangle(
            offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline=""
        )
        tabs = (
            ("overview", "Connections"),
            ("details", "Boards & calibration"),
            ("display", "Display"),
            ("data", "Data sources"),
        )
        tw = (x1 - x0) / 4
        for i, (action, label) in enumerate(tabs):
            rect = (x0 + i * tw, top, x0 + (i + 1) * tw, top + 47)
            button(c, rect, label, i == 0)
            app.concept_setup_actions[action] = rect
        cards_top = top + 70
        split = x0 + (x1 - x0) * 0.63
        cards_bottom = bottom - 184
        panel(c, x0, cards_top, split - 8, cards_bottom)
        panel(c, split + 8, cards_top, x1, cards_bottom)
        text(c, x0 + 20, cards_top + 10, "Shot source", 24, bold=True)
        text(
            c,
            x0 + 20,
            cards_top + 48,
            "Select the source for shot and session data",
            13,
            theme.TEXT_2,
        )
        source = production.gspro_settings.effective_source()
        names = (
            ("nova", "Nova"),
            ("gspro", "GSPro"),
            ("pureplay", "PurePlay"),
            ("open_connect", "Another\nmonitor"),
        )
        cw = (split - x0 - 58) / 4
        by = cards_top + 82
        for i, (key, label) in enumerate(names):
            rect = (x0 + 20 + i * (cw + 8), by, x0 + 20 + i * (cw + 8) + cw, by + 95)
            panel(
                c,
                *rect,
                fill=theme.ACCENT_DEEP if source == key else theme.SURFACE_2,
                outline=AQUA if source == key else theme.HAIRLINE,
            )
            _source_icon(c, key, (rect[0] + rect[2]) / 2, by + 28, max_width=max(24, cw - 20))
            text(
                c,
                (rect[0] + rect[2]) / 2,
                by + 67,
                label,
                14,
                anchor="center",
                bold=True,
            )
            app.concept_setup_actions["source_" + key] = rect
        folder_y = by + 112
        panel(c, x0 + 16, folder_y, split - 22, folder_y + 101, fill=theme.SURFACE_2)
        text(c, x0 + 28, folder_y + 7, "Local session data", 16, bold=True)
        text(
            c,
            x0 + 28,
            folder_y + 34,
            "Current storage location • managed by the application",
            10,
            theme.TEXT_2,
        )
        path_rect = (x0 + 28, folder_y + 61, split - 184, folder_y + 92)
        panel(c, *path_rect, fill=theme.BG, radius=7)
        text(
            c,
            path_rect[0] + 10,
            (path_rect[1] + path_rect[3]) / 2,
            str(get_data_dir()),
            9,
            theme.TEXT_2,
            anchor="w",
            width=path_rect[2] - path_rect[0] - 20,
        )
        rect = (split - 169, folder_y + 60, split - 34, folder_y + 93)
        button(c, rect, "Open session log")
        app.concept_setup_actions["logs"] = rect
        # The concept's proposed remote companion is not an implemented
        # settings model. Present actual source status, not a fake host/test UI.
        status_y = folder_y + 116
        panel(
            c,
            x0 + 16,
            status_y,
            split - 22,
            cards_bottom - 14,
            fill=theme.SURFACE_2,
            outline=theme.HAIRLINE,
        )
        text(c, x0 + 30, status_y + 10, "Connection status", 18, bold=True)
        snapshot = production.connection_setup_controller().snapshot()
        state = snapshot.get("state", "idle")
        text(
            c,
            x0 + 30,
            status_y + 44,
            snapshot.get("message") or "No shot source connected",
            12,
            AQUA if state == "ready" else theme.TEXT_2,
            width=split - x0 - 240,
        )
        rect = (split - 184, status_y + 38, split - 34, status_y + 77)
        button(c, rect, "Configure source")
        app.concept_setup_actions["source_configure"] = rect
        text(
            c,
            x0 + 30,
            cards_bottom - 42,
            "Guided connection and test-shot checks use the selected source.",
            10,
            theme.TEXT_3,
        )
        rx = split + 32
        text(c, rx, cards_top + 14, "Balance boards (local)", 23, bold=True)
        manager = getattr(obs_server, "pressure_manager", None)
        simulated = bool(getattr(manager, "is_simulator", False))
        backend = getattr(manager, "backend", None)
        connected = bool(backend and getattr(backend, "is_open", False))
        text(
            c,
            rx,
            cards_top + 56,
            "Demo / simulated"
            if simulated
            else "Local hardware connected"
            if connected
            else "No local board connected",
            12,
            GOLD if simulated else theme.TEXT_2,
        )
        board_y = cards_top + 106
        bw = (x1 - rx - 32) / 2
        for i, side in enumerate(("left", "right")):
            bx = rx + i * (bw + 16)
            panel(c, bx, board_y, bx + bw, board_y + 194, fill=theme.SURFACE_2)
            _board_outline(c, bx + bw / 2, board_y + 62, mirror=i == 1)
            lead = (side == "right") if app.is_left_handed else (side == "left")
            text(
                c,
                bx + bw / 2,
                board_y + 131,
                "Lead board" if lead else "Trail board",
                15,
                anchor="center",
                bold=True,
            )
            assigned = bool(getattr(manager, "assigned_" + side, None))
            text(
                c,
                bx + bw / 2,
                board_y + 166,
                ("Assigned: " + side.title()) if assigned else "Not assigned",
                11,
                AQUA if assigned else theme.TEXT_3,
                anchor="center",
            )
        rect = (rx, cards_bottom - 142, x1 - 18, cards_bottom - 92)
        button(c, rect, "Open board setup")
        app.concept_setup_actions["boards"] = rect
        lower = cards_bottom + 16
        lower_split = x0 + (x1 - x0) * 0.54
        panel(c, x0, lower, lower_split - 8, bottom)
        panel(c, lower_split + 8, lower, x1, bottom)
        text(c, x0 + 20, lower + 10, "Display", 23, bold=True)
        text(
            c, x0 + 20, lower + 47, "User interface and view settings", 12, theme.TEXT_2
        )
        dw = (lower_split - x0 - 64) / 3
        dy = lower + 106
        for i, (label, value, action) in enumerate(
            (
                ("Handedness", "Left" if app.is_left_handed else "Right", "hand"),
                ("Units", "Yards / MPH", None),
                ("UI scale", getattr(app, "ui_scale_choice", "Auto"), "scale"),
            )
        ):
            xx = x0 + 22 + i * (dw + 12)
            text(c, xx, dy - 26, label, 11, theme.TEXT_2)
            rect = (xx, dy, xx + dw, dy + 40)
            button(c, rect, value)
            if action:
                app.concept_setup_actions[action] = rect
                c.create_line(
                    rect[2] - 22,
                    dy + 17,
                    rect[2] - 17,
                    dy + 22,
                    rect[2] - 12,
                    dy + 17,
                    fill=theme.TEXT_2,
                    width=1.5,
                )
        ax = lower_split + 28
        text(c, ax, lower + 10, "Aim calibration", 23, bold=True)
        text(
            c, ax, lower + 47, "Align shot direction with target line", 12, theme.TEXT_2
        )
        offset = float(app.aim_offset_deg or 0)
        status = (
            "Not calibrated"
            if offset == 0
            else f"{abs(offset):.1f}° {'right' if offset > 0 else 'left'} of target"
        )
        panel(c, ax, dy - 8, ax + 218, dy + 39, fill=theme.SURFACE_2, radius=23)
        text(c, ax + 109, dy + 15, status, 12, theme.TEXT_2, anchor="center")
        rect = (x1 - 200, dy - 8, x1 - 18, dy + 41)
        button(c, rect, "Configure")
        app.concept_setup_actions["aim"] = rect
        legend_y = bottom + 38
        text(
            c,
            x0 + 6,
            legend_y,
            "Source credibility (data labels):",
            10,
            anchor="w",
            bold=True,
        )
        for i, label in enumerate(("Reported", "Derived", "Estimate", "Unavailable")):
            _provenance_badge(c, x0 + 263 + i * 134, legend_y, label, 10)


def handle_setup_click(app, x, y):
    """Called before production handlers, using visible canvas hit geometry."""
    if getattr(app, "concept_setup_page", "overview") == "details":
        from .concept_boards import handle_click

        if handle_click(app, x, y):
            return True
    for action, rect in getattr(app, "concept_setup_actions", {}).items():
        if not (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
            continue
        if action in ("details", "boards"):
            app.concept_setup_page = "details"
        elif action == "overview":
            app.concept_setup_page = "overview"
        elif action.startswith("source_") or action == "data":
            app.open_shot_source_picker()
        elif action == "hand":
            app.is_left_handed = not app.is_left_handed
        elif action in ("scale", "display"):
            app.show_tools_menu = True
        elif action == "logs":
            app.open_log_folder()
        elif action == "aim":
            app.show_aim_modal = True
            app.aim_modal_active_field = "distance"
        app.draw_screen()
        return True
    return getattr(app, "concept_setup_page", "overview") != "details"


def draw_dispersion(app, avail_w, h, offset_x=0):
    """Session grouping, split-by-ball and prior-session comparison."""
    import statistics

    from src.connections.presentation import metric_value

    c = app.canvas
    x0, x1, top, bottom = offset_x + 16, offset_x + avail_w - 16, 60, h - 22
    mode = getattr(app, "dispersion_view_submode", "split")
    data = {}
    split_ball = bool(getattr(app, "dispersion_split_by_ball", False))
    for index, shot in enumerate(app.session_shots):
        if shot.get("excluded"):
            continue
        name = shot.get("club", app.current_club)
        key = f"{name} · {shot.get('ball') or 'no ball'}" if split_ball else name
        view = app.aim_corrected(shot)
        values = {
            key: metric_value(view, key, app.is_left_handed)
            for key in ("carry", "total", "offline", "apex")
        }
        data.setdefault(key, []).append((index, values))
    with palette(app):
        c.create_rectangle(
            offset_x, 52, offset_x + avail_w, h, fill=theme.BG, outline=""
        )
        app.design_dispersion_tab_rects = []
        for i, (key, label) in enumerate(
            (("split", "Split view"), ("topdown", "Overhead"), ("side", "Side view"))
        ):
            rect = (x0 + i * 150, top, x0 + (i + 1) * 150, top + 40)
            button(c, rect, label, mode == key)
            app.design_dispersion_tab_rects.append((rect, key))
        app.dispersion_split_rect = (x1 - 195, top, x1, top + 40)
        button(
            c,
            app.dispersion_split_rect,
            "Split by ball: " + ("On" if split_ball else "Off"),
            split_ball,
        )
        split = x0 + (x1 - x0) * 0.58
        plot_y = top + 58
        app.dispersion_dot_rects = []
        app.dispersion_club_chip_rects = []
        selected = getattr(app, "dispersion_selected_club", "ALL")
        plot_data = {
            name: rows
            for name, rows in data.items()
            if selected == "ALL"
            or name == selected
            or name.startswith(selected + " · ")
        }
        all_rect = (x0 + 470, top, x0 + 610, top + 40)
        button(c, all_rect, "All clubs", selected == "ALL")
        app.dispersion_club_chip_rects.append((*all_rect, "ALL"))
        if mode == "split":
            mid = plot_y + (bottom - plot_y) * 0.56
            _fit_plot(
                app,
                (x0, plot_y, split - 8, mid - 7),
                plot_data,
                app.current_club,
                False,
            )
            _fit_plot(
                app, (x0, mid + 7, split - 8, bottom), plot_data, app.current_club, True
            )
        else:
            _fit_plot(
                app,
                (x0, plot_y, split - 8, bottom),
                plot_data,
                app.current_club,
                mode == "side",
            )
        rx = split + 8
        mid = plot_y + (bottom - plot_y) * 0.49
        panel(c, rx, plot_y, x1, mid - 7)
        text(c, rx + 18, plot_y + 16, "Club gapping & spread", 20, bold=True)
        text(
            c,
            rx + 18,
            plot_y + 48,
            "Average carry • 10th–90th percentile range (derived)",
            10,
            theme.TEXT_2,
        )
        groups = []
        for name, rows in data.items():
            carries = [v["carry"] for _, v in rows if v.get("carry") is not None]
            if carries:
                groups.append(
                    (name, statistics.mean(carries), _percentile(carries, 0.1), _percentile(carries, 0.9))
                )
        groups.sort(key=lambda row: row[1])
        max_c = max((max(row[1], row[3]) for row in groups), default=1) or 1
        yy = plot_y + 94
        page_size = max(1, int((mid - 56 - yy) / 44) + 1)
        pages = max(1, (len(groups) + page_size - 1) // page_size)
        page = min(max(0, getattr(app, "dispersion_group_page", 0)), pages - 1)
        app.dispersion_group_page = page
        app.dispersion_page_rects = []
        if pages > 1:
            by = mid - 40
            text(c, rx + 18, by + 12, f"Groups {page * page_size + 1}–{min(len(groups), (page + 1) * page_size)} of {len(groups)}", 9, theme.TEXT_2, anchor="w")
            for label, target, bx in (("Previous", page - 1, x1 - 172), ("Next", page + 1, x1 - 87)):
                if 0 <= target < pages:
                    rect = (bx, by, bx + 78, by + 26)
                    button(c, rect, label)
                    app.dispersion_page_rects.append((rect, target))
        for name, mean, lo, hi in groups[page * page_size:(page + 1) * page_size]:
            active = name == app.current_club or name.startswith(
                app.current_club + " · "
            )
            color = app.get_club_color(name)
            app.dispersion_club_chip_rects.append(
                (rx + 10, yy - 20, x1 - 10, yy + 20, name)
            )
            if active:
                panel(
                    c,
                    rx + 10,
                    yy - 20,
                    x1 - 10,
                    yy + 20,
                    fill=T.SECTION_BG,
                    outline=GOLD,
                )
            text(c, rx + 22, yy, name, 11, color, anchor="w", bold=True)
            text(
                c,
                rx + (x1 - rx) * 0.43,
                yy,
                f"{mean:.0f} yd",
                13,
                color,
                anchor="e",
                bold=True,
            )
            bx = rx + (x1 - rx) * 0.48
            barw = (x1 - rx) * 0.26
            xx0, xx1 = bx + lo / max_c * barw, bx + hi / max_c * barw
            c.create_line(xx0, yy, xx1, yy, fill=AQUA, width=4)
            for xx in (xx0, xx1):
                c.create_line(xx, yy - 7, xx, yy + 7, fill=AQUA, width=1)
            xm = bx + mean / max_c * barw
            c.create_oval(
                xm - 4,
                yy - 4,
                xm + 4,
                yy + 4,
                fill=GOLD if active else AQUA,
                outline="",
            )
            text(c, x1 - 20, yy, f"{lo:.0f}–{hi:.0f}", 10, theme.TEXT_2, anchor="e")
            yy += 44
        if not groups:
            text(
                c,
                (rx + x1) / 2,
                plot_y + 130,
                "No carry data available",
                12,
                theme.TEXT_3,
                anchor="center",
            )
        lower = mid + 7
        panel(c, rx, lower, x1, bottom)
        text(c, rx + 18, lower + 17, "Last vs session average", 19, bold=True)
        text(
            c,
            rx + 18,
            lower + 50,
            (selected if selected != "ALL" else app.current_club) + " • non-excluded shots",
            9,
            theme.TEXT_2,
        )
        comparison_group = selected if selected != "ALL" else app.current_club
        comparison_club, separator, comparison_ball = comparison_group.partition(" · ")

        def matches_comparison(shot):
            return (shot.get("club", app.current_club) == comparison_club
                    and not shot.get("excluded")
                    and (not separator or (shot.get("ball") or "no ball") == comparison_ball))

        previous = []
        active_index = getattr(app, "active_session_index", len(app.sessions) - 1)
        for session in reversed(app.sessions[:active_index]):
            candidate = [
                shot
                for shot in session.get("shots", [])
                if matches_comparison(shot)
            ]
            if candidate:
                previous = candidate
                break
        current = [
            shot
            for shot in app.session_shots
            if matches_comparison(shot)
        ]
        centers = [rx + (x1 - rx) * fraction for fraction in (0.49, 0.72, 0.91)]
        for xx, label in zip(centers, ("Previous", "Current", "Change")):
            text(c, xx, lower + 90, label, 9, theme.TEXT_2, anchor="center", bold=True)
        for i, (label, key) in enumerate(
            (
                ("Carry (yd)", "carry"),
                ("Total (yd)", "total"),
                ("Abs lateral (yd)", "offline"),
            )
        ):
            yy = lower + 126 + i * 40
            text(c, rx + 18, yy, label, 11, anchor="w")
            means = []
            for shots in (previous, current):
                vals = [
                    metric_value(app.aim_corrected(shot), key, app.is_left_handed)
                    for shot in shots
                ]
                vals = [
                    abs(v) if key == "offline" else v
                    for v in vals
                    if isinstance(v, (int, float))
                ]
                means.append(statistics.mean(vals) if vals else None)
            delta = means[1] - means[0] if None not in means else None
            for j, value in enumerate((*means, delta)):
                shown = (
                    "--"
                    if value is None
                    else (f"{value:+.1f}" if j == 2 else f"{value:.1f}")
                )
                text(
                    c,
                    centers[j],
                    yy,
                    shown,
                    12,
                    GOLD if j == 2 and value is not None else theme.TEXT,
                    anchor="center",
                    bold=True,
                )
            c.create_line(rx + 14, yy + 23, x1 - 14, yy + 23, fill=theme.HAIRLINE)
        spreads = []
        for shots in (previous, current):
            values = [app.aim_corrected(shot) for shot in shots]
            spreads.append(_ellipse_spread([(metric_value(v, "carry", app.is_left_handed),
                                             metric_value(v, "offline", app.is_left_handed)) for v in values]))
        delta = tuple(b - a for a, b in zip(*spreads)) if all(v is not None for v in spreads) else None
        yy = lower + 246
        text(c, rx + 18, yy, "90% W × D (yd)", 10, anchor="w")
        for j, value in enumerate((*spreads, delta)):
            shown = "--" if value is None else (f"{value[0]:+.1f} × {value[1]:+.1f}" if j == 2 else f"{value[0]:.1f} × {value[1]:.1f}")
            text(c, centers[j], yy, shown, 10, GOLD if j == 2 else theme.TEXT, anchor="center", bold=True)
        text(c, rx + 18, yy + 25, "Normal-model ellipse extent • needs 3 paired shots", 8, theme.TEXT_3)
        text(
            c,
            rx + 18,
            bottom - 30,
            "Derived from available data • -- means unavailable",
            8,
            theme.TEXT_3,
        )
