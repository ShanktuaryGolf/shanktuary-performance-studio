"""Session history: real sessions, shot history, notes and an honest preview.

The three-column workspace follows approved concept 20. Mutating actions use
production callbacks, including their deletion confirmations. Filtering and
pagination retain original session/shot indices and never rewrite source data.
Coordinates are local to the shared 124px viewport; public hit rectangles are
translated with the other concept workspaces.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime

import theme
from src.connections.presentation import metric_status, metric_value, shot_shape

from . import tokens as T
from .concept_session import trajectory, view
from .concept_shell import icon, panel, text

STATUS = {
    "REPORTED": "Reported",
    "DERIVED": "Derived",
    "ESTIMATED": "Estimate",
    "MODELLED": "Modelled",
    "NOT REPORTED": "Unavailable",
}
METRICS = (
    ("carry", "Carry", "yd", 0),
    ("ball_speed", "Ball speed", "mph", 0),
    ("spin", "Spin", "rpm", 0),
    ("launch", "Launch", "°", 1),
    ("spin_axis", "Spin axis", "°", 1),
    ("face_to_path", "Face to path", "°", 1),
)


def _short(app, value, width, size=11, bold=False):
    value = str(value or "")
    measure = getattr(app, "_text_width", None)
    font = (theme.ui_font(), size, "bold" if bold else "normal")

    def length(s):
        return measure(s, font) if callable(measure) else len(s) * size * 0.7

    if length(value) <= width:
        return value
    while value and length(value + "…") > width:
        value = value[:-1]
    return value + "…"


def _hit(app, rect, action, payload=None):
    app.concept_history_rects.append((rect, action, payload))


def _button(app, rect, label, action, payload=None, *, active=False, enabled=True, size=10):
    c = app.canvas
    panel(c, *rect, fill=T.ACTIVE_BG if active else T.SURFACE,
          outline=T.TEAL_LINE if active else T.HAIRLINE, r=8)
    text(c, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2,
         _short(app, label, rect[2] - rect[0] - 12, size), size,
         T.TEXT if enabled else T.TEXT_3, anchor="center")
    if enabled:
        _hit(app, rect, action, payload)


def _badge(app, rect, label):
    color = T.GOLD if label in ("Estimate", "Modelled", "Derived") else (
        T.TEXT_3 if label == "Unavailable" else T.TEAL_LINE)
    panel(app.canvas, *rect, fill=T.PAGE_BG, outline=color, r=11)
    text(app.canvas, (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2,
         label, 8, T.TEXT_2 if label == "Unavailable" else T.TEXT, anchor="center")


def _metric(app, shot, key):
    return metric_value(shot, key, bool(getattr(app, "is_left_handed", False)))


def _status(app, shot, key):
    return STATUS[metric_status(shot, key, bool(getattr(app, "is_left_handed", False)))]


def _source_status(app, shot):
    statuses = [_status(app, shot, key) for key in ("carry", "ball_speed", "spin")]
    for label in ("Modelled", "Estimate", "Derived", "Reported"):
        if label in statuses:
            return label
    return "Unavailable"


def _result(app, shot):
    return shot_shape(shot, bool(getattr(app, "is_left_handed", False)))[0] or "—"


def _shot_notes(shot):
    return str(shot.get("notes") or shot.get("note") or "")


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_label(shots):
    """Show an observed span only when there are actual dated timestamps.

    Legacy display timestamps contain just a clock time and cannot establish a
    reliable span across dates. No duration is fabricated for those sessions.
    """
    times = []
    for shot in shots:
        value = shot.get("timestamp_ns")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            times.append(value / 1e9)
        else:
            stamp = _date(shot.get("timestamp"))
            if stamp is not None:
                times.append(stamp.timestamp())
    if len(times) != len(shots) or len(times) < 2:
        return "—"
    span = max(times) - min(times)
    return f"{span / 60:.0f} min" if span >= 60 else f"{span:.0f} sec"


def session_order(app):
    def key(item):
        index, session = item
        stamp = _date(session.get("created_at"))
        return (stamp.timestamp() if stamp else float("-inf"), index)

    return sorted(enumerate(app.sessions), key=key,
                  reverse=not getattr(app, "concept_history_oldest", False))


def history_rows(app):
    club = getattr(app, "concept_history_club", None)
    result_filter = getattr(app, "concept_history_result", None)
    inclusion = getattr(app, "concept_history_inclusion", None)
    search = getattr(app, "concept_history_search", "").casefold()
    rows = []
    for index, raw in enumerate(app.session_shots):
        shot = view(app, raw)
        if club is not None and raw.get("club") != club:
            continue
        if result_filter is not None and _result(app, shot) != result_filter:
            continue
        if inclusion is not None and (not bool(raw.get("excluded", False))) != inclusion:
            continue
        if search and search not in _shot_notes(raw).casefold():
            continue
        rows.append((index, shot))
    key = getattr(app, "concept_history_sort", "index")

    def value(row):
        index, shot = row
        if key == "index":
            return index
        if key == "club":
            return str(shot.get("club") or "")
        if key == "result":
            return _result(app, shot)
        return _metric(app, shot, key)

    present = [row for row in rows if value(row) is not None]
    missing = [row for row in rows if value(row) is None]
    return sorted(present, key=value,
                  reverse=not getattr(app, "concept_history_ascending", False)) + missing


def _sync_session(app, session):
    if getattr(app, "_history_session_identity", None) != id(session):
        app._history_session_identity = id(session)
        app.concept_history_page = 0
        app.concept_history_club = None
        app.concept_history_result = None
        app.concept_history_inclusion = None
        app.concept_history_search = ""
        app._history_menu = None


def _draw_sessions(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    text(c, x0 + 14, y0 + 29, "Sessions", 18, bold=True)
    _button(app, (x1 - 92, y0 + 15, x1 - 12, y0 + 46),
            "Oldest ▾" if getattr(app, "concept_history_oldest", False) else "Recent ▾", "order")
    ordered = session_order(app)
    capacity = max(1, int((y1 - y0 - 135) / 88))
    offset = max(0, min(getattr(app, "concept_history_session_offset", 0), max(0, len(ordered) - capacity)))
    app.concept_history_session_offset = offset
    app._history_session_capacity = capacity
    app._history_list_bounds = rect
    for row, (index, session) in enumerate(ordered[offset:offset + capacity]):
        yy = y0 + 65 + row * 88
        selected = index == app.active_session_index
        box = (x0 + 10, yy, x1 - 10, yy + 77)
        panel(c, *box, fill=T.ACTIVE_BG if selected else T.SURFACE,
              outline=T.GOLD if selected else T.HAIRLINE, r=10, width=2 if selected else 1)
        icon(c, 12, x0 + 24, yy + 34, T.TEXT if selected else T.TEXT_2)
        text(c, x0 + 65, yy + 26, _short(app, session.get("name", "Session"), x1 - x0 - 86, 13, True),
             13, bold=True)
        stamp = str(session.get("created_at") or "Date unavailable")
        text(c, x0 + 65, yy + 52,
             _short(app, f"{stamp[:10]} · {len(session.get('shots') or [])} shots", x1 - x0 - 82, 10),
             10, T.TEXT_2)
        _hit(app, box, "session", index)
    if not ordered:
        text(c, x0 + 18, y0 + 96, "No saved sessions", 12, T.TEXT_2)
    text(c, x0 + 14, y1 - 71, f"{len(ordered)} saved sessions", 9, T.TEXT_2)
    for delta, label, xx in ((-1, "‹", x1 - 76), (1, "›", x1 - 43)):
        enabled = offset > 0 if delta < 0 else offset + capacity < len(ordered)
        _button(app, (xx, y1 - 86, xx + 29, y1 - 56), label, "sessions_page", delta,
                enabled=enabled, size=16)
    _button(app, (x0 + 12, y1 - 45, x1 - 12, y1 - 12), "+ New session", "new", size=11)


def _draw_summary(app, session, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    name_width = x1 - x0 - 185
    text(c, x0 + 15, y0 + 28, _short(app, session.get("name", "Session"), name_width, 21, True),
         21, bold=True)
    _button(app, (x1 - 158, y0 + 15, x1 - 126, y0 + 47), "✎", "rename", size=14)
    _button(app, (x1 - 114, y0 + 15, x1 - 14, y0 + 47), "Session ▾", "menu", "session")
    stamp = session.get("created_at") or "Date unavailable"
    text(c, x0 + 16, y0 + 61, _short(app, f"{stamp} · {len(app.session_shots)} shots", x1 - x0 - 30, 12),
         12, T.TEXT_2)
    sy = y0 + 85
    panel(c, x0 + 12, sy, x1 - 12, y1 - 11, fill=T.PAGE_BG, r=10)
    left = x0 + 28
    text(c, left, sy + 21, "Shots", 11, T.TEXT_2)
    text(c, left, sy + 51, str(len(app.session_shots)), 22, bold=True)
    left += 96
    c.create_line(left - 16, sy + 15, left - 16, y1 - 26, fill=T.HAIRLINE)
    text(c, left, sy + 21, "Recorded span", 10, T.TEXT_2)
    text(c, left, sy + 51, duration_label(app.session_shots), 20, bold=True)
    left += 132
    c.create_line(left - 16, sy + 15, left - 16, y1 - 26, fill=T.HAIRLINE)
    text(c, left, sy + 21, "Club mix (shots)", 10, T.TEXT_2)
    clubs = Counter(str(s.get("club") or "Unknown") for s in app.session_shots)
    mixed = "   ·   ".join(f"{club}  {count}" for club, count in clubs.most_common()) or "No shots yet"
    text(c, left, sy + 51, _short(app, mixed, x1 - left - 25, 11), 11, T.TEXT)


def _draw_table(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    width = x1 - x0
    filter_width = (width - 40) / 4
    labels = (
        (getattr(app, "concept_history_club", None) or "All clubs", "club"),
        (getattr(app, "concept_history_result", None) or "All results", "result"),
        ({None: "Include: All", True: "Included", False: "Excluded"}[getattr(app, "concept_history_inclusion", None)], "inclusion"),
        (getattr(app, "concept_history_search", "") or "Search notes…", "search"),
    )
    for i, (label, field) in enumerate(labels):
        xx = x0 + 12 + i * (filter_width + 5)
        _button(app, (xx, y0 + 12, xx + filter_width, y0 + 45),
                label + (" ▾" if field != "search" else ""), "search" if field == "search" else "menu", field)
    c.create_line(x0 + 1, y0 + 59, x1 - 1, y0 + 59, fill=T.HAIRLINE)
    columns = (("use", "", 30), ("index", "Shot", 43), ("club", "Club", 52),
               ("carry", "Carry", 65), ("ball_speed", "Ball speed", 72), ("spin", "Spin", 73),
               ("result", "Result", 75), ("source", "Source", 76), ("notes", "Notes", 73), ("delete", "", 26))
    scale = (width - 16) / sum(col[2] for col in columns)
    cursor = x0 + 8
    layout = []
    hy, row_y = y0 + 59, y0 + 100
    for key, label, weight in columns:
        edge = cursor + weight * scale
        layout.append((key, cursor, edge))
        mark = " ↑" if getattr(app, "concept_history_ascending", False) else " ↓"
        label = label + mark if key == getattr(app, "concept_history_sort", "index") else label
        text(c, (cursor + edge) / 2, hy + 21, label, 9, bold=True, anchor="center")
        if key in ("index", "club", "carry", "ball_speed", "spin", "result"):
            _hit(app, (cursor, hy, edge, row_y), "sort", key)
        cursor = edge
    page_size = min(getattr(app, "concept_history_page_size", 8), max(1, int((y1 - row_y - 123) / 39)))
    rows = history_rows(app)
    pages = max(1, math.ceil(len(rows) / page_size))
    page = max(0, min(getattr(app, "concept_history_page", 0), pages - 1))
    app.concept_history_page = page
    app._history_pages = pages
    app._history_visible_indices = [index for index, _ in rows]
    app._history_table_bounds = rect
    start = page * page_size
    for row, (index, shot) in enumerate(rows[start:start + page_size]):
        yy = row_y + row * 39
        selected = index == app.selected_shot_index
        included = not bool(shot.get("excluded", False))
        if selected:
            panel(c, x0 + 5, yy, x1 - 5, yy + 39, fill=T.ACTIVE_BG, outline=T.TEAL_LINE, r=9)
        else:
            c.create_line(x0 + 10, yy + 39, x1 - 10, yy + 39, fill=T.HAIRLINE)
        # Cell controls are hit-tested before the encompassing selection row.
        for key, a, b in layout:
            tx = (a + b) / 2
            if key == "use":
                panel(c, tx - 7, yy + 12, tx + 7, yy + 26,
                      fill=T.TEAL_LINE if included else T.PAGE_BG, outline=T.TEAL_LINE if included else T.TEXT_2, r=3)
                if included:
                    c.create_line(tx - 4, yy + 19, tx - 1, yy + 22, tx + 4, yy + 16, fill=T.PAGE_BG, width=1.5)
                _hit(app, (a, yy, b, yy + 39), "include", index)
            elif key == "delete":
                c.create_rectangle(tx - 4, yy + 14, tx + 4, yy + 26, outline=T.TEXT_2)
                c.create_line(tx - 6, yy + 12, tx + 6, yy + 12, fill=T.TEXT_2)
                c.create_line(tx - 2, yy + 9, tx + 2, yy + 9, fill=T.TEXT_2)
                _hit(app, (a, yy, b, yy + 39), "delete_shot", index)
            elif key == "source":
                _badge(app, (a + 3, yy + 9, b - 3, yy + 30), _source_status(app, shot))
            else:
                if key == "index":
                    display = str(index + 1)
                elif key == "club":
                    display = shot.get("club") or "—"
                elif key == "result":
                    display = _result(app, shot)
                elif key == "notes":
                    display = _shot_notes(shot) or "—"
                    _hit(app, (a, yy, b, yy + 39), "shot_notes", index)
                else:
                    value = _metric(app, shot, key)
                    unit = {"carry": " yd", "ball_speed": " mph", "spin": ""}.get(key, "")
                    display = "—" if value is None else f"{value:,.0f}{unit}"
                text(c, tx, yy + 20, _short(app, display, b - a - 7, 9), 9,
                     T.TEXT if included else T.TEXT_3, selected, anchor="center")
        _hit(app, (x0 + 8, yy, x1 - 8, yy + 39), "shot", index)
    if not rows:
        text(c, (x0 + x1) / 2, row_y + 80,
             "No shots match these filters" if app.session_shots else "No shots recorded in this session",
             12, T.TEXT_2, anchor="center")
        if app.session_shots:
            _button(app, (x0 + width / 2 - 66, row_y + 104, x0 + width / 2 + 66, row_y + 137),
                    "Clear filters", "clear")
    py = y1 - 104
    c.create_line(x0 + 12, py - 12, x1 - 12, py - 12, fill=T.HAIRLINE)
    text(c, x0 + 15, py + 15, f"Showing {start + 1 if rows else 0}–{min(start + page_size, len(rows))} of {len(rows)} shots",
         9, T.TEXT_2)
    _button(app, (x0 + width * .45, py, x0 + width * .45 + 28, py + 30), "‹", "page", -1,
            enabled=page > 0, size=15)
    text(c, x0 + width * .45 + 67, py + 15, f"{page + 1} / {pages}", 10, T.TEXT_2, anchor="center")
    _button(app, (x0 + width * .45 + 106, py, x0 + width * .45 + 134, py + 30), "›", "page", 1,
            enabled=page < pages - 1, size=15)
    _button(app, (x1 - 114, py, x1 - 12, py + 30), f"Rows: {page_size} ▾", "menu", "page_size")
    c.create_line(x0 + 12, y1 - 61, x1 - 12, y1 - 61, fill=T.HAIRLINE)
    _button(app, (x0 + 14, y1 - 48, x0 + 164, y1 - 12), "↓  Export CSV", "csv", size=12)
    _button(app, (x0 + 176, y1 - 48, x0 + 326, y1 - 12), "▤  Export PDF", "pdf", size=12)
    text(c, x1 - 14, y1 - 30, "Full session", 9, T.TEXT_3, anchor="e")


def _draw_notes(app, session, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    text(c, x0 + 15, y0 + 27, "Notes", 18, bold=True)
    _button(app, (x1 - 64, y0 + 13, x1 - 13, y0 + 43), "Edit", "notes")
    box = (x0 + 14, y0 + 49, x1 - 14, y1 - 35)
    panel(c, *box, fill=T.PAGE_BG, outline=T.HAIRLINE, r=7)
    notes = str(session.get("notes") or "")
    # Fit a small visible excerpt without imposing an artificial storage limit.
    lines = []
    for paragraph in (notes or "Add session notes…").splitlines():
        line = ""
        for word in paragraph.split():
            test = f"{line} {word}".strip()
            if _short(app, test, x1 - x0 - 50, 12) != test and line:
                lines.append(line)
                line = word
            else:
                line = test
        lines.append(line)
    capacity = max(1, int((box[3] - box[1] - 18) / 23))
    for i, line in enumerate(lines[:capacity]):
        if i == capacity - 1 and len(lines) > capacity:
            line = _short(app, line, x1 - x0 - 67, 12) + "…"
        text(c, x0 + 25, box[1] + 20 + i * 23,
             _short(app, line, x1 - x0 - 50, 12), 12, T.TEXT if notes else T.TEXT_3)
    _hit(app, box, "notes")
    text(c, x1 - 15, y1 - 15, f"{len(notes):,} characters", 9, T.TEXT_2, anchor="e")


def _draw_preview(app, rect):
    c = app.canvas
    x0, y0, x1, y1 = rect
    panel(c, *rect)
    shots = app.session_shots
    index = app.selected_shot_index
    raw = shots[index] if 0 <= index < len(shots) else None
    shot = view(app, raw) if raw is not None else {}
    text(c, x0 + 15, y0 + 26, f"Shot {index + 1}" if raw is not None else "Shot preview", 18, bold=True)
    text(c, x0 + 15, y0 + 56, _short(app, f"{shot.get('club') or '—'} · {_result(app, shot)}", x1 - x0 - 30, 12),
         12, T.TEXT_2)
    for delta, label, xx in ((-1, "‹", x1 - 154), (1, "›", x1 - 45)):
        _button(app, (xx, y0 + 13, xx + 31, y0 + 44), label, "step", delta,
                enabled=raw is not None and 0 <= index + delta < len(shots), size=17)
    text(c, x1 - 84, y0 + 29, f"{index + 1 if raw is not None else 0} of {len(shots)}", 9, T.TEXT_2, anchor="center")
    plot_bottom = min(y0 + 250, y1 - 226)
    trajectory(app, shot, (x0 + 2, y0 + 79, x1 - 2, plot_bottom), title=False)
    text(c, x0 + 15, y0 + 86, "Illustrative flight · yd", 8, T.TEXT_2)
    my = plot_bottom + 15
    panel(c, x0 + 10, my, x1 - 10, my + 204, fill=T.PAGE_BG, r=10)
    cw = (x1 - x0 - 40) / 3
    for n, (key, label, unit, precision) in enumerate(METRICS):
        xx = x0 + 19 + n % 3 * cw
        yy = my + 22 + n // 3 * 99
        if n % 3:
            c.create_line(xx - 7, yy - 8, xx - 7, yy + 76, fill=T.HAIRLINE)
        if n == 3:
            c.create_line(x0 + 22, yy - 21, x1 - 22, yy - 21, fill=T.HAIRLINE)
        text(c, xx, yy, label, 10, T.TEXT_2)
        value = _metric(app, shot, key)
        display = "—" if value is None else f"{value:,.{precision}f}" + (unit if unit == "°" else f" {unit}")
        size = 18
        while size > 11 and _short(app, display, cw - 12, size, True) != display:
            size -= 1
        text(c, xx, yy + 28, display, size, T.TEXT if value is not None else T.TEXT_3, bold=True)
        status = _status(app, shot, key)
        _badge(app, (xx, yy + 48, xx + min(cw - 11, max(65, len(status) * 6 + 12)), yy + 69), status)


def _draw_menu(app, center, table):
    field = getattr(app, "_history_menu", None)
    if not field:
        return
    x0, y0, x1, _ = table
    if field == "session":
        options = [("Rename session", "rename", None), ("Edit session notes", "notes", None),
                   ("Delete session…", "delete_session", None), ("Remove empty sessions", "empty", None)]
        mx, my, width = center[2] - 230, center[1] + 52, 216
    else:
        if field == "club":
            options = [("All clubs", "filter", (field, None))] + [
                (club, "filter", (field, club)) for club in dict.fromkeys(str(s.get("club")) for s in app.session_shots if s.get("club"))]
            column = 0
        elif field == "result":
            options = [("All results", "filter", (field, None))] + [
                (label, "filter", (field, label)) for label in dict.fromkeys(_result(app, view(app, s)) for s in app.session_shots)]
            column = 1
        elif field == "inclusion":
            options = [(label, "filter", (field, value)) for label, value in (("All shots", None), ("Included", True), ("Excluded", False))]
            column = 2
        elif field == "page_size":
            options = [(f"{count} rows", "filter", (field, count)) for count in (4, 6, 8)]
            column = 3
        else:
            return
        width = max(160, (x1 - x0 - 40) / 4)
        mx = min(x1 - width - 12, x0 + 12 + column * ((x1 - x0 - 40) / 4 + 5))
        my = y0 + 48 if field != "page_size" else table[3] - 215
    # A large historical club/result list remains usable without overflowing.
    max_items = max(3, int((table[3] - my - 10) / 33))
    offset = max(0, min(getattr(app, "_history_menu_offset", 0), max(0, len(options) - max_items)))
    visible = options[offset:offset + max_items]
    panel(app.canvas, mx, my, mx + width, my + len(visible) * 33 + 10,
          fill=T.SECTION_BG, outline=T.TEAL_LINE, r=8)
    menu_rects = []
    for i, (label, action, payload) in enumerate(visible):
        yy = my + 5 + i * 33
        text(app.canvas, mx + 12, yy + 16, _short(app, label, width - 24, 11), 11,
             T.GOLD if action == "delete_session" else T.TEXT)
        menu_rects.append(((mx, yy, mx + width, yy + 33), action, payload))
    app.concept_history_rects = menu_rects + app.concept_history_rects
    app._history_menu_count = len(menu_rects)
    app._history_menu_max_offset = max(0, len(options) - max_items)


def draw(app, avail_w, h, offset_x=0):
    """Paint the complete session history workspace below the shared shell."""
    session = app.get_active_session()
    _sync_session(app, session)
    app.concept_history_rects = []
    x0, x1 = offset_x + 20, offset_x + avail_w - 20
    y0, y1 = 64, h - 65
    app.canvas.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill=T.PAGE_BG, outline="")
    left_width = max(220, min(254, (x1 - x0) * .20))
    right_width = max(345, min(380, (x1 - x0) * .29))
    left = (x0, y0, x0 + left_width, y1)
    center = (left[2] + 14, y0, x1 - right_width - 14, y0 + 174)
    table = (center[0], y0 + 186, center[2], y1)
    right = (x1 - right_width, y0, x1, y0 + 193)
    _draw_sessions(app, left)
    _draw_summary(app, session, center)
    _draw_table(app, table)
    _draw_notes(app, session, right)
    _draw_preview(app, (right[0], right[3] + 13, right[2], y1))
    _draw_menu(app, center, table)


def _select_shot(app, index):
    if 0 <= index < len(app.session_shots):
        app.selected_shot_index = index
        app.current_shot = app.session_shots[index]


def handle_click(app, x, y):
    """Handle published (translated) hit boxes. Return whether consumed."""
    menu = getattr(app, "_history_menu", None)
    targets = getattr(app, "concept_history_rects", [])
    if menu:
        targets = targets[:getattr(app, "_history_menu_count", 0)]
    for rect, action, payload in targets:
        if not (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
            continue
        if menu:
            app._history_menu = None
        if action == "menu":
            app._history_menu = payload
            app._history_menu_offset = 0
        elif action == "session":
            app.switch_session(payload)
        elif action == "new":
            app.create_new_session()
        elif action == "rename":
            app.rename_active_session()
        elif action == "delete_session":
            app.delete_session(app.active_session_index, confirm=True)
        elif action == "empty":
            app.delete_empty_sessions()
        elif action == "notes":
            app.edit_session_notes()
        elif action in ("csv", "pdf"):
            app.export_session_report(action)
        elif action == "delete_shot":
            app.delete_shot(payload, confirm=True)
        elif action == "shot":
            _select_shot(app, payload)
        elif action == "step":
            _select_shot(app, app.selected_shot_index + payload)
        elif action == "include":
            if 0 <= payload < len(app.session_shots):
                shot = app.session_shots[payload]
                shot["excluded"] = not bool(shot.get("excluded", False))
                app.save_session_to_file()
        elif action == "sort":
            if getattr(app, "concept_history_sort", "index") == payload:
                app.concept_history_ascending = not getattr(app, "concept_history_ascending", False)
            else:
                app.concept_history_sort = payload
                app.concept_history_ascending = True
            app.concept_history_page = 0
        elif action == "filter":
            field, value = payload
            setattr(app, "concept_history_" + field, value)
            app.concept_history_page = 0
        elif action == "clear":
            for field in ("club", "result", "inclusion"):
                setattr(app, "concept_history_" + field, None)
            app.concept_history_search = ""
            app.concept_history_page = 0
        elif action == "order":
            app.concept_history_oldest = not getattr(app, "concept_history_oldest", False)
            app.concept_history_session_offset = 0
        elif action == "sessions_page":
            app.concept_history_session_offset = max(0, app.concept_history_session_offset + payload * app._history_session_capacity)
        elif action == "page":
            app.concept_history_page = max(0, min(app._history_pages - 1, app.concept_history_page + payload))
        elif action in ("search", "shot_notes"):
            from tkinter import simpledialog

            if action == "search":
                initial = getattr(app, "concept_history_search", "")
                value = simpledialog.askstring("Search shot notes", "Find text in shot notes (leave blank for all):",
                                               initialvalue=initial, parent=app.root)
                if value is not None:
                    app.concept_history_search = value.strip()
                    app.concept_history_page = 0
            elif 0 <= payload < len(app.session_shots):
                shot = app.session_shots[payload]
                value = simpledialog.askstring(f"Shot {payload + 1} notes", "Shot notes:",
                                               initialvalue=_shot_notes(shot), parent=app.root)
                if value is not None:
                    shot["notes"] = value
                    app.save_session_to_file()
        app.draw_screen()
        return True
    if menu:
        app._history_menu = None
        app.draw_screen()
        return True
    return False


def handle_scroll(app, delta, mouse_x):
    """Scroll the session list, an open menu, or the paged shot table."""
    if getattr(app, "_history_menu", None):
        app._history_menu_offset = max(0, min(getattr(app, "_history_menu_max_offset", 0),
                                             getattr(app, "_history_menu_offset", 0) + delta))
    elif getattr(app, "_history_list_bounds", (0, 0, 0, 0))[0] <= mouse_x <= getattr(app, "_history_list_bounds", (0, 0, 0, 0))[2]:
        capacity = getattr(app, "_history_session_capacity", 1)
        app.concept_history_session_offset = max(0, min(max(0, len(app.sessions) - capacity),
                                                       getattr(app, "concept_history_session_offset", 0) + delta))
    else:
        app.concept_history_page = max(0, min(getattr(app, "_history_pages", 1) - 1,
                                             getattr(app, "concept_history_page", 0) + delta))
    app.draw_screen()
    return True
