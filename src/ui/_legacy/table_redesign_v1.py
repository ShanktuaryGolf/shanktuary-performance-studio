"""Design-only Table workspace polish.

Keeps the dense sortable matrix and all existing interactions, but brings the
visual hierarchy in line with Shot / Club: quiet session summary, crisp column
header, low-noise rows, and a restrained current-shot treatment.
"""

import theme
from src.connections.presentation import metric_status, metric_value

_EXTERNAL_SOURCES = {"gspro", "cgp", "open_connect"}
_TABLE_METRICS = {
    "carry": "carry", "total": "total", "ball_speed": "ball_speed",
    "club_speed": "club_speed", "smash": "smash", "launch": "launch",
    "push_pull": "horizontal_launch", "spin": "spin", "sidespin": "sidespin",
    "axis": "spin_axis", "path": "club_path", "face": "face_to_path",
    "apex": "apex", "descent": "descent", "offline": "offline",
}


def _external(shot):
    return shot.get("_source") in _EXTERNAL_SOURCES


def _presence_row(shot, left_handed=False):
    """Format actual fields; missing and measured zero remain distinct."""
    result = {}
    for column, metric in _TABLE_METRICS.items():
        value = metric_value(shot, metric, left_handed=left_handed)
        if value is None:
            result[column] = "--"
            continue
        if column == "spin":
            text = f"{int(value)}"
        elif column == "sidespin":
            text = f"{int(value):+d}"
        elif column in ("push_pull", "axis", "path", "face", "offline"):
            text = f"{value:+.1f}"
        else:
            text = f"{value:.2f}" if column == "smash" else f"{value:.1f}"
        if metric_status(shot, metric, left_handed=left_handed) in ("MODELLED", "ESTIMATED"):
            text += "~"
        result[column] = text
    return result


def _presence_summary(shots, left_handed=False):
    """Field means exclude missing values; count still means active shots."""
    shots = [shot for shot in shots if not shot.get("excluded", False)]
    result = {"count": len(shots), "estimated": set(), "field_counts": {}}
    for metric in _TABLE_METRICS.values():
        values = []
        for shot in shots:
            value = metric_value(shot, metric, left_handed=left_handed)
            if value is None:
                continue
            values.append(value)
            if metric_status(shot, metric, left_handed=left_handed) in ("MODELLED", "ESTIMATED"):
                result["estimated"].add(metric)
        result[metric] = sum(values) / len(values) if values else None
        result["field_counts"][metric] = len(values)
    return result


def _presence_summary_parts(summary):
    specs = (("Carry", "carry", ".1f", "y"), ("Ball", "ball_speed", ".1f", " mph"),
             ("Club", "club_speed", ".1f", " mph"), ("Smash", "smash", ".2f", ""),
             ("Launch", "launch", ".1f", "°"), ("Spin", "spin", ".0f", " rpm"),
             ("Apex", "apex", ".1f", "y"), ("Offline", "offline", "+.1f", "y"))
    parts = []
    for label, key, fmt, unit in specs:
        value = summary[key]
        if value is None:
            parts.append(f"{label} --")
        else:
            mark = "~" if key in summary["estimated"] else ""
            parts.append(f"{label} {value:{fmt}}{mark}{unit}")
    return parts



def _mix(a, b, t):
    def rgb(s):
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    ar, ag, ab = rgb(a)
    br, bg, bb = rgb(b)
    vals = (
        round(ar + (br - ar) * t),
        round(ag + (bg - ag) * t),
        round(ab + (bb - ab) * t),
    )
    return "#%02X%02X%02X" % vals


_COLUMNS = [
    ("index", "#", "", 40, "c"),
    ("excluded", "Excl", "", 44, "c"),
    ("club", "Club", "", 70, "w"),
    ("carry", "Carry", "yds", 68, "c"),
    ("total", "Total", "yds", 68, "c"),
    ("ball_speed", "Ball Spd", "mph", 74, "c"),
    ("club_speed", "Club Spd", "mph", 74, "c"),
    ("smash", "Smash", "", 60, "c"),
    ("launch", "Launch", "deg", 64, "c"),
    ("push_pull", "Start", "deg", 72, "c"),
    ("spin", "Spin", "rpm", 68, "c"),
    ("sidespin", "Sidespin", "rpm", 72, "c"),
    ("axis", "Axis", "deg", 64, "c"),
    ("path", "Path", "deg", 64, "c"),
    ("face", "Face", "deg", 64, "c"),
    ("apex", "Apex", "yds", 62, "c"),
    ("descent", "Descent", "deg", 64, "c"),
    ("offline", "Offline", "yds", 72, "c"),
]


def _column_layout(x1, x2):
    """One set of boundaries/anchors for headers, values and sorting targets.

    Fractional boundaries avoid cumulative rounding drift. Fitting the entire
    width also prevents the final columns becoming zero-width at small sizes.
    Numeric labels and values share the same optical centre; Club stays left
    aligned for scanning names.
    """
    total = sum(column[3] for column in _COLUMNS)
    consumed = 0
    result = []
    for key, title, unit, width, align in _COLUMNS:
        left = x1 + (x2 - x1) * consumed / total
        consumed += width
        right = x1 + (x2 - x1) * consumed / total
        text_x = left + 9 if align == "w" else (left + right) / 2
        anchor = "w" if align == "w" else "center"
        result.append((key, title, unit, left, right, text_x, anchor))
    return result


def draw_shot_table_viewport(app, avail_w, h, offset_x=0):
    c = app.canvas
    app.table_row_rects.clear()
    app.table_header_rects.clear()
    app.table_checkbox_rects.clear()

    ui_scale = max(0.9, min(2.4, min(avail_w / 1100.0, h / 720.0)))
    font_scale = max(0.9, min(1.8, ui_scale))

    top_y = 60
    table_x1 = offset_x + 12
    table_x2 = offset_x + avail_w - 12

    # ------------------------------------------------------------------
    # Quiet pinned session summary
    # ------------------------------------------------------------------
    avg_h = int(44 * ui_scale)
    avg_y1 = top_y
    avg_y2 = avg_y1 + avg_h
    c.create_rectangle(table_x1, avg_y1, table_x2, avg_y2,
                       fill=theme.SURFACE, outline="")
    c.create_line(table_x1, avg_y2, table_x2, avg_y2,
                  fill=theme.HAIRLINE)

    has_external = any(_external(shot) for shot in app.session_shots)
    avgs = (_presence_summary(app.session_shots, getattr(app, "is_left_handed", False))
            if has_external else app.calculate_session_averages())
    active_count = int(avgs.get("count", 0) if avgs else 0)

    title_x = table_x1 + int(16 * font_scale)
    title_id = c.create_text(
        title_x, (avg_y1 + avg_y2) / 2,
        text=f"Session · {active_count} shots",
        fill=theme.ACCENT_TEXT,
        font=(theme.ui_font(), max(9, int(11 * font_scale)), "bold"),
        anchor="w",
    )
    title_bb = c.bbox(title_id)

    if avgs:
        metrics_x = (title_bb[2] + int(26 * font_scale)) if title_bb else (
            table_x1 + int(165 * font_scale)
        )
        if has_external:
            parts = _presence_summary_parts(avgs)
        else:
            all_clamped = all(
                app.compute_smash_confidence(
                    s.get("ball_speed_meters_per_second"),
                    s.get("vertical_launch_angle_degrees"),
                    s.get("total_spin_rpm"),
                )["clamped"]
                for s in app.session_shots
            ) if app.session_shots else False

            parts = [
                f"Carry {avgs.get('carry', 0.0):.1f}y",
                f"Ball {avgs.get('ball_speed', 0.0):.1f} mph",
            ]
            if not all_clamped:
                parts.extend([
                    f"Club {avgs.get('club_speed', 0.0):.1f} mph",
                    f"Smash {avgs.get('smash', 1.0):.2f}",
                ])
            parts.extend([
                f"Launch {avgs.get('launch_angle', 0.0):.1f}°",
                f"Spin {int(avgs.get('total_spin', 0.0))} rpm",
                f"Apex {avgs.get('apex', 0.0):.1f}y",
                f"Offline {avgs.get('offline', 0.0):+.1f}y",
            ])
        c.create_text(
            metrics_x, (avg_y1 + avg_y2) / 2,
            text="   ·   ".join(parts),
            fill=theme.TEXT_2,
            font=(theme.ui_font(), max(8, int(10 * font_scale))),
            anchor="w",
        )

    # ------------------------------------------------------------------
    # Sticky-feeling column header
    # Units live in the header so rows remain visually clean.
    # ------------------------------------------------------------------
    head_h = int(40 * ui_scale)
    head_y1 = avg_y2 + 8
    head_y2 = head_y1 + head_h
    head_bg = _mix(theme.SURFACE, theme.SURFACE_2, .42)
    c.create_rectangle(table_x1, head_y1, table_x2, head_y2,
                       fill=head_bg, outline="")
    c.create_line(table_x1, head_y2, table_x2, head_y2,
                  fill=theme.HAIRLINE)

    cols = _column_layout(table_x1, table_x2)

    title_font = (theme.ui_font(), max(8, int(10 * font_scale)), "bold")
    unit_font = (theme.ui_font(), max(7, int(8 * font_scale)))

    for col_key, col_title, unit, curr_x, cx2, tx, anchor in cols:
        app.table_header_rects.append((curr_x, head_y1, cx2, head_y2, col_key))
        is_sorted = (app.table_sort_col == col_key)
        txt_col = theme.ACCENT_TEXT if is_sorted else theme.TEXT_2

        title_y = head_y1 + head_h * (.33 if unit else .5)
        c.create_text(tx, title_y, text=col_title, fill=txt_col,
                      font=title_font, anchor=anchor)
        if unit:
            c.create_text(tx, head_y1 + head_h * .73, text=unit, fill=theme.TEXT_3,
                          font=unit_font, anchor=anchor)

        # A tiny marker in the top gutter never changes the label's centre
        # and cannot collide with a long label in a neighbouring column.
        if is_sorted:
            ax = (curr_x + cx2) / 2
            ay = head_y1 + 4 * ui_scale
            dx, dy = 3 * ui_scale, 2 * ui_scale
            direction = -1 if app.table_sort_asc else 1
            c.create_polygon(ax - dx, ay - direction * dy,
                             ax + dx, ay - direction * dy,
                             ax, ay + direction * dy,
                             fill=theme.ACCENT_LINE, outline="")

    # ------------------------------------------------------------------
    # Sortable dense rows
    # ------------------------------------------------------------------
    data_y1 = head_y2 + 3
    row_h = int(32 * ui_scale)
    avail_rows = max(1, (h - data_y1 - 15) // row_h)
    raw_items = list(enumerate(app.session_shots))

    def get_sort_val(item):
        idx, s = item
        if _external(s) and app.table_sort_col in _TABLE_METRICS:
            return metric_value(s, _TABLE_METRICS[app.table_sort_col],
                                left_handed=getattr(app, "is_left_handed", False))
        ogc = s.get("open_golf_coach", {})
        us = ogc.get("us_customary_units", {})
        key = app.table_sort_col
        if key == "index": return idx
        if key == "excluded": return 1 if s.get("excluded", False) else 0
        if key == "club": return s.get("club", "")
        if key == "carry": return us.get("carry_distance_yards", 0.0)
        if key == "total": return us.get("total_distance_yards", 0.0)
        if key == "ball_speed": return us.get("ball_speed_mph", 0.0)
        if key == "club_speed": return us.get("club_speed_mph", 0.0)
        if key == "smash": return ogc.get("smash_factor", 1.0)
        if key == "launch": return s.get("vertical_launch_angle_degrees", 0.0)
        if key == "push_pull": return s.get("horizontal_launch_angle_degrees", 0.0)
        if key == "spin": return ogc.get("total_spin_rpm", 0.0)
        if key == "sidespin": return ogc.get("sidespin_rpm", 0.0)
        if key == "axis": return ogc.get("spin_axis_degrees", 0.0)
        if key == "path": return app.resolve_handed(ogc.get("club_path_degrees"), 0.0)
        if key == "face": return app.resolve_handed(ogc.get("club_face_to_path_degrees"), 0.0)
        if key == "apex": return us.get("peak_height_yards", 0.0)
        if key == "descent": return ogc.get("descent_angle_degrees", 0.0)
        if key == "offline": return us.get("offline_distance_yards", 0.0)
        return idx

    # Missing external values stay last in either sort direction.
    present_items = [item for item in raw_items if get_sort_val(item) is not None]
    missing_items = [item for item in raw_items if get_sort_val(item) is None]
    sorted_items = sorted(present_items, key=get_sort_val,
                          reverse=not app.table_sort_asc) + missing_items
    visible_items = sorted_items[
        app.table_scroll_offset: app.table_scroll_offset + avail_rows
    ]

    row_font = (theme.ui_font(), max(8, int(11 * font_scale)))
    row_bold = (theme.ui_font(), max(8, int(11 * font_scale)), "bold")

    for r_i, (real_idx, shot) in enumerate(visible_items):
        ry1 = data_y1 + r_i * row_h
        ry2 = ry1 + row_h - 1
        is_sel = (real_idx == app.selected_shot_index)
        is_ex = shot.get("excluded", False)

        if is_sel:
            bg = _mix(theme.SURFACE, theme.WARN, .065)
        else:
            bg = theme.SURFACE if r_i % 2 == 0 else _mix(theme.SURFACE, theme.SURFACE_2, .55)
        c.create_rectangle(table_x1, ry1, table_x2, ry2,
                           fill=bg, outline="")
        c.create_line(table_x1, ry2, table_x2, ry2,
                      fill=_mix(theme.HAIRLINE, theme.BG, .25))
        if is_sel:
            c.create_rectangle(table_x1, ry1, table_x1 + 4, ry2,
                               fill=theme.WARN, outline="")

        app.table_row_rects.append((table_x1, ry1, table_x2, ry2, real_idx))

        if _external(shot):
            row_data = _presence_row(shot, getattr(app, "is_left_handed", False))
            row_data.update(index=f"#{real_idx + 1}", excluded="×" if is_ex else "✓",
                            club=shot.get("club", "Club"))
        else:
            ogc = shot.get("open_golf_coach", {})
            us = ogc.get("us_customary_units", {})
            c_val = us.get("carry_distance_yards", 0.0)
            tot_val = us.get("total_distance_yards", 0.0)
            bs_val = us.get("ball_speed_mph", 0.0)
            cs_val = us.get("club_speed_mph", 0.0)
            sm_val = ogc.get("smash_factor", 1.0)
            row_clamped = app.compute_smash_confidence(
                shot.get("ball_speed_meters_per_second"),
                shot.get("vertical_launch_angle_degrees"),
                shot.get("total_spin_rpm"),
            )["clamped"]
            la_val = shot.get("vertical_launch_angle_degrees", 0.0)
            hl_val = shot.get("horizontal_launch_angle_degrees", 0.0)
            sp_val = ogc.get("total_spin_rpm", 0.0)
            ss_val = ogc.get("sidespin_rpm", 0.0)
            sa_val = ogc.get("spin_axis_degrees", 0.0)
            cp_val = app.resolve_handed(ogc.get("club_path_degrees"), 0.0)
            fp_val = app.resolve_handed(ogc.get("club_face_to_path_degrees"), 0.0)
            ap_val = us.get("peak_height_yards", 0.0)
            da_val = ogc.get("descent_angle_degrees", 0.0)
            off_val = us.get("offline_distance_yards", 0.0)

            # Units are already in the headers; rows can be pure comparable values.
            row_data = {
                "index": f"#{real_idx + 1}",
                "excluded": "×" if is_ex else "✓",
                "club": shot.get("club", "Club"),
                "carry": f"{c_val:.1f}",
                "total": f"{tot_val:.1f}",
                "ball_speed": f"{bs_val:.1f}",
                "club_speed": "--" if row_clamped else f"{cs_val:.1f}",
                "smash": "--" if row_clamped else f"{sm_val:.2f}",
                "launch": f"{la_val:.1f}",
                "push_pull": f"{hl_val:+.1f}",
                "spin": f"{int(sp_val)}",
                "sidespin": f"{int(ss_val):+d}",
                "axis": f"{sa_val:+.1f}",
                "path": f"{cp_val:+.1f}",
                "face": f"{fp_val:+.1f}",
                "apex": f"{ap_val:.1f}",
                "descent": f"{da_val:.1f}",
                "offline": f"{off_val:+.1f}",
            }

        for col_key, _title, _unit, curr_x, cx2, tx, anchor in cols:
            val_text = row_data.get(col_key, "-")

            if col_key == "excluded":
                app.table_checkbox_rects.append((curr_x, ry1, cx2, ry2, real_idx))
                chk_col = theme.WARN if is_ex else theme.TEXT_3
                c.create_text((curr_x + cx2) / 2, (ry1 + ry2) / 2,
                              text=val_text, fill=chk_col,
                              font=(theme.ui_font(), max(8, int(10 * font_scale)), "bold"),
                              anchor="center")
            else:
                # Selected row is identified structurally, not by turning every
                # number orange. Keep orange on identity + two outcome anchors.
                if is_ex:
                    txt_col = theme.TEXT_3
                elif is_sel and col_key in ("index", "club", "carry", "offline"):
                    txt_col = theme.WARN
                else:
                    txt_col = theme.TEXT

                font = row_bold if (is_sel and col_key in ("index", "club", "carry", "offline")) else row_font
                c.create_text(tx, (ry1 + ry2) / 2, text=val_text,
                              fill=txt_col, font=font, anchor=anchor)

    if has_external:
        c.create_text(table_x2, h - 3, text="~ = estimated / modelled · -- = not reported",
                      fill=theme.TEXT_3, font=(theme.ui_font(), 7), anchor="se")
