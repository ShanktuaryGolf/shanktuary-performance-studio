"""Concept session table backed by production sorting, exclusion and exports.

The normal view prioritizes twelve readable columns. Technical columns remain
available through Details. Inclusion means the existing `excluded` flag, not a
new selection model. Exports always use the existing whole-session export flow.
"""

from __future__ import annotations

from src.connections.presentation import metric_status, metric_value

from . import tokens as T
from .concept_shell import panel, text

PRIMARY = [
    ("excluded", "Use", "", 48),
    ("index", "Shot", "", 60),
    ("club", "Club", "", 98),
    ("carry", "Carry", "yd", 80),
    ("total", "Total", "yd", 80),
    ("ball_speed", "Ball", "mph", 86),
    ("club_speed", "Club", "mph", 86),
    ("smash", "Smash", "", 74),
    ("launch", "Launch", "°", 80),
    ("spin", "Spin", "rpm", 90),
    ("axis", "Axis", "°", 78),
    ("apex", "Apex", "yd", 78),
    ("offline", "Offline", "yd", 80),
]
TECHNICAL = [
    ("index", "Shot", "", 55),
    ("club", "Club", "", 98),
    ("push_pull", "Start", "°", 85),
    ("sidespin", "Sidespin", "rpm", 100),
    ("path", "Path", "°", 85),
    ("face", "Face/path", "°", 96),
    ("face_target", "Face/target", "°", 100),
    ("descent", "Descent", "°", 85),
    ("attack_angle", "Attack", "°", 85),
    ("dynamic_loft", "Dyn. loft", "°", 90),
    ("closure_rate", "Closure", "°/s", 92),
    ("hang_time", "Hang time", "s", 90),
]
KEYS = {
    "push_pull": "horizontal_launch",
    "axis": "spin_axis",
    "path": "club_path",
    "face": "face_to_path",
    "face_target": "face_to_target",
}


def _metric(app, shot, key):
    return metric_value(shot, KEYS.get(key, key), left_handed=app.is_left_handed)


def _format(app, shot, key):
    value = _metric(app, shot, key)
    if value is None:
        return "—", T.TEXT_3
    if key in ("spin", "sidespin", "closure_rate"):
        result = f"{value:,.0f}"
    elif key == "smash":
        result = f"{value:.2f}"
    else:
        result = (
            f"{value:+.1f}"
            if key in ("offline", "axis", "push_pull", "path", "face")
            else f"{value:.1f}"
        )
    status = metric_status(shot, KEYS.get(key, key), left_handed=app.is_left_handed)
    if status in ("ESTIMATED", "MODELLED"):
        return result + "~", T.GOLD
    return result, T.TEXT


def _button(app, rect, label, action, active=False):
    panel(
        app.canvas,
        *rect,
        fill=T.ACTIVE_BG if active else T.SURFACE,
        outline=T.TEAL_LINE if active else T.HAIRLINE,
        r=9,
    )
    text(
        app.canvas,
        (rect[0] + rect[2]) / 2,
        (rect[1] + rect[3]) / 2,
        label,
        11,
        bold=True,
        anchor="center",
    )
    app.concept_table_rects.append((rect, action))


def _rows(app):
    club = getattr(app, "concept_table_club", None)
    included_only = getattr(app, "concept_table_included_only", False)
    result = [
        (index, app.aim_corrected(shot))
        for index, shot in enumerate(app.session_shots)
        if (club is None or shot.get("club") == club)
        and (not included_only or not shot.get("excluded", False))
    ]
    key = app.table_sort_col

    def value(item):
        index, shot = item
        if key == "index":
            return index
        if key == "club":
            return str(shot.get("club", ""))
        if key == "excluded":
            return bool(shot.get("excluded", False))
        return _metric(app, shot, key)

    present = [row for row in result if value(row) is not None]
    missing = [row for row in result if value(row) is None]
    return sorted(present, key=value, reverse=not app.table_sort_asc) + missing


def draw(app, avail_w, h, offset_x=0):
    c = app.canvas
    app.table_row_rects = []
    app.table_header_rects = []
    app.table_checkbox_rects = []
    app.concept_table_rects = []
    x0, x1 = offset_x + 20, offset_x + avail_w - 20
    c.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill=T.PAGE_BG, outline="")
    panel(c, x0, 64, x1, h - 175)
    text(c, x0 + 20, 94, "Shot table", 23, bold=True)
    text(
        c,
        x0 + 20,
        126,
        "Live session data · source values, calculations and estimates",
        11,
        T.TEXT_2,
    )
    club = getattr(app, "concept_table_club", None)
    _button(app, (x1 - 500, 83, x1 - 315, 125), (club or "All clubs") + "  ▾", "club")
    only = getattr(app, "concept_table_included_only", False)
    _button(
        app,
        (x1 - 301, 83, x1 - 120, 125),
        "Included only" if only else "All shots",
        "include",
        only,
    )
    detailed = getattr(app, "concept_table_details", False)
    _button(
        app,
        (x1 - 106, 83, x1 - 18, 125),
        "Summary" if detailed else "Details",
        "details",
        detailed,
    )
    c.create_line(x0 + 20, 148, x1 - 20, 148, fill=T.HAIRLINE)
    labels = [
        ("Reported / native", T.TEAL_LINE),
        ("Derived / calculated", T.TEXT_2),
        ("~ Estimate / model", T.GOLD),
        ("— Unavailable", T.TEXT_3),
    ]
    for i, (label, color) in enumerate(labels):
        xx = x0 + 26 + i * (x1 - x0 - 50) / 4
        if i < 2:
            c.create_oval(
                xx, 165, xx + 11, 176, fill=color if i == 0 else "", outline=color
            )
        text(c, xx + 20, 171, label, 11, T.TEXT_2)
    columns = TECHNICAL if detailed else PRIMARY
    weights = sum(row[3] for row in columns)
    left, right = x0 + 10, x1 - 10
    head_y, row_y = 202, 257
    bottom = h - 266
    panel(c, left, head_y, right, bottom, fill=T.PAGE_BG, r=10)
    panel(c, left, head_y, right, row_y, fill=T.SURFACE, r=10)
    layout = []
    cursor = left
    for key, label, unit, weight in columns:
        edge = cursor + (right - left) * weight / weights
        tx = (cursor + edge) / 2
        text(c, tx, head_y + 20, label, 12, bold=True, anchor="center")
        if unit:
            text(c, tx, head_y + 40, unit, 10, T.TEXT_2, anchor="center")
        if app.table_sort_col == key:
            c.create_line(
                cursor + 6, head_y + 3, edge - 6, head_y + 3, fill=T.GOLD, width=2
            )
        app.table_header_rects.append((cursor, head_y, edge, row_y, key))
        layout.append((key, cursor, edge))
        if cursor > left:
            c.create_line(cursor, head_y + 7, cursor, bottom - 7, fill=T.HAIRLINE)
        cursor = edge
    rows = _rows(app)
    capacity = max(1, int((bottom - row_y) / 43))
    start = max(
        0, min(getattr(app, "table_scroll_offset", 0), max(0, len(rows) - capacity))
    )
    app.table_scroll_offset = start
    for visible, (index, shot) in enumerate(rows[start : start + capacity]):
        yy = row_y + visible * 43
        selected = index == app.selected_shot_index
        excluded = bool(shot.get("excluded", False))
        if selected:
            panel(
                c, left + 1, yy, right - 1, yy + 43, fill="#263F35", outline=T.GOLD, r=8
            )
        else:
            c.create_line(left, yy + 43, right, yy + 43, fill=T.HAIRLINE)
        app.table_row_rects.append((left, yy, right, yy + 43, index))
        for key, a, b in layout:
            tx = (a + b) / 2
            if key == "excluded":
                app.table_checkbox_rects.append((a, yy, b, yy + 43, index))
                panel(
                    c,
                    tx - 9,
                    yy + 12,
                    tx + 9,
                    yy + 30,
                    fill=T.SURFACE if excluded else T.TEAL_TEXT,
                    outline=T.TEXT_3 if excluded else T.TEAL_LINE,
                    r=3,
                )
                if not excluded:
                    c.create_line(
                        tx - 5,
                        yy + 20,
                        tx - 1,
                        yy + 25,
                        tx + 6,
                        yy + 16,
                        fill=T.PAGE_BG,
                        width=2,
                    )
            else:
                if key == "index":
                    value, color = str(index + 1), T.GOLD if selected else T.TEXT
                elif key == "club":
                    value, color = shot.get("club", "—"), T.TEXT
                else:
                    value, color = _format(app, shot, key)
                text(
                    c,
                    tx,
                    yy + 22,
                    value,
                    13,
                    T.TEXT_3 if excluded else color,
                    selected,
                    anchor="center",
                )
    if not rows:
        text(
            c,
            (left + right) / 2,
            (row_y + bottom) / 2,
            "No shots match this view",
            17,
            T.TEXT_2,
            anchor="center",
        )
    included = [shot for _, shot in rows if not shot.get("excluded", False)]
    cy = h - 222
    c.create_line(x0 + 17, cy - 18, x0 + 17, cy + 18, fill=T.GOLD, width=3)
    text(
        c,
        x0 + 32,
        cy,
        f"{len(included)} of {len(rows)} shown shots included",
        12,
        bold=True,
    )
    summaries = []
    for key, label, unit in [
        ("carry", "Carry", "yd"),
        ("ball_speed", "Ball", "mph"),
        ("spin", "Spin", "rpm"),
    ]:
        values = [_metric(app, s, key) for s in included]
        values = [v for v in values if v is not None]
        summaries.append(
            f"{label} avg: {sum(values) / len(values):.1f} {unit}"
            if values
            else f"{label}: —"
        )
    text(c, x0 + 340, cy, "  ·  ".join(summaries), 10, T.TEXT_2)
    _button(app, (x1 - 277, cy - 21, x1 - 148, cy + 21), "Export CSV", "csv")
    _button(app, (x1 - 137, cy - 21, x1 - 18, cy + 21), "Export PDF", "pdf")
    panel(c, x0, h - 151, x1, h - 94)
    text(
        c,
        x0 + 18,
        h - 122,
        f"Rows {start + 1 if rows else 0}–{min(start + capacity, len(rows))} of {len(rows)} · Scroll for more",
        11,
        T.TEXT_2,
    )
    _button(app, (x1 - 290, h - 143, x1 - 172, h - 102), "Session notes", "notes")
    _button(app, (x1 - 158, h - 143, x1 - 18, h - 102), "Recent shots →", "recent")


def handle_click(app, x, y):
    for rect, action in getattr(app, "concept_table_rects", []):
        if not (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
            continue
        if action == "details":
            app.concept_table_details = not getattr(app, "concept_table_details", False)
        elif action == "include":
            app.concept_table_included_only = not getattr(
                app, "concept_table_included_only", False
            )
        elif action == "club":
            options = [None] + list(
                dict.fromkeys(s.get("club") for s in app.session_shots if s.get("club"))
            )
            current = getattr(app, "concept_table_club", None)
            app.concept_table_club = (
                options[(options.index(current) + 1) % len(options)]
                if current in options
                else None
            )
            app.table_scroll_offset = 0
        elif action in ("csv", "pdf"):
            app.export_session_report(action)
        elif action == "notes":
            app.edit_session_notes()
        elif action == "recent":
            app.set_mode(9)
        app.draw_screen()
        return True
    return False
