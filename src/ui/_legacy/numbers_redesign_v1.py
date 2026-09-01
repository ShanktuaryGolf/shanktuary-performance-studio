"""Design-only polish for the Numbers workspace.

Keeps the existing 4x4 metric grid and metric choices intact. This pass only
improves hierarchy: bigger labels/values, units grouped with the value, one
blue hero metric, quiet provenance/status captions, and dim unavailable cards.
"""

import theme


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


def draw_big_numbers_viewport(
    app, avail_w, h, carry, total, ball_speed, club_speed, smash, launch, spin,
    spin_axis, club_path, face_to_path, apex, offline, closure_rate=0.0,
    attack_angle=0.0, dynamic_loft=0.0, hang_time=0.0, offset_x=0,
):
    c = app.canvas
    ui_scale = max(0.9, min(2.5, min(avail_w / 1100.0, h / 720.0)))

    top_y = 58
    bot_y = h - 16
    pad_x = int(14 * ui_scale)
    grid_w = avail_w - pad_x * 2
    grid_h = bot_y - top_y

    if getattr(app, "is_left_handed", False):
        path_dir = "In-Out" if club_path < 0 else "Out-In"
    else:
        path_dir = "In-Out" if club_path > 0 else "Out-In"

    face_dir = "Open" if face_to_path > 0 else "Closed"
    axis_dir = "R" if spin_axis > 0 else "L"
    off_dir = "L" if offline < 0 else "R"
    apex_ft = apex * 3.0

    clamped = app.compute_smash_confidence(
        (app.current_shot or {}).get("ball_speed_meters_per_second"),
        (app.current_shot or {}).get("vertical_launch_angle_degrees"),
        (app.current_shot or {}).get("total_spin_rpm"),
    )["clamped"] if app.current_shot else False

    cards = [
        # label, value, unit, value colour, status, unavailable
        ("CARRY DISTANCE", f"{carry:.1f}", "YARDS", theme.ACCENT_TEXT, "", False),
        ("TOTAL DISTANCE", f"{total:.1f}", "YARDS", theme.TEXT, "", False),
        ("BALL SPEED", f"{ball_speed:.1f}", "MPH", theme.TEXT, "", False),
        ("CLUB SPEED", "--" if clamped else f"{club_speed:.1f}",
         "" if clamped else "MPH", theme.MUTED if clamped else theme.TEXT,
         "DERIVED" if not clamped else "UNAVAILABLE", clamped),
        ("SMASH FACTOR", "--" if clamped else f"{smash:.2f}",
         "" if clamped else "RATIO", theme.MUTED if clamped else theme.TEXT,
         "DERIVED" if not clamped else "UNAVAILABLE", clamped),
        ("LAUNCH ANGLE", f"{launch:.1f}°", "", theme.TEXT, "", False),
        ("TOTAL SPIN", f"{int(spin)}", "RPM", theme.TEXT, "", False),
        ("SPIN AXIS", f"{abs(spin_axis):.1f}° {axis_dir}", "", theme.TEXT,
         "DRAW" if spin_axis < 0 else ("FADE" if spin_axis > 0 else "STRAIGHT"), False),
        ("CLOSURE RATE", f"{int(closure_rate)}", "DEG / SEC", theme.TEXT,
         "DERIVED", False),
        ("APEX HEIGHT", f"{apex_ft:.1f}", "FEET", theme.TEXT, "", False),
        ("CLUB PATH", f"{abs(club_path):.1f}° {path_dir}", "", theme.TEXT,
         "DERIVED", False),
        ("FACE TO PATH", f"{abs(face_to_path):.1f}° {face_dir}", "", theme.TEXT,
         "DERIVED", False),
        ("ATTACK ANGLE", "--", "", theme.MUTED, "NOT MEASURED", True),
        ("DYNAMIC LOFT", "--", "", theme.MUTED, "NOT MEASURED", True),
        ("HANG TIME", f"{hang_time:.1f}s", "", theme.TEXT, "", False),
        ("OFFLINE", f"{abs(offline):.1f} {off_dir}", "YARDS",
         theme.TEXT if abs(offline) <= 4.0 else theme.WARN,
         "ON TARGET" if abs(offline) <= 4.0 else "", False),
    ]

    rows, cols = 4, 4
    col_gap = int(12 * ui_scale)
    row_gap = int(12 * ui_scale)
    card_w = (grid_w - (cols - 1) * col_gap) // cols
    card_h = (grid_h - (rows - 1) * row_gap) // rows

    label_font = (theme.ui_font(), max(9, int(11 * ui_scale)), "bold")
    status_font = (theme.ui_font(), max(7, int(8 * ui_scale)), "bold")
    unit_font = (theme.ui_font(), max(8, int(9 * ui_scale)), "bold")

    page_bg = theme.BG
    live_card_bg = _mix(theme.SURFACE, theme.SURFACE_2, .18)
    unavailable_bg = _mix(page_bg, theme.SURFACE, .45)

    for idx, (label, value, unit, value_col, status, unavailable) in enumerate(cards):
        r = idx // cols
        col = idx % cols

        x1 = offset_x + pad_x + col * (card_w + col_gap)
        y1 = top_y + r * (card_h + row_gap)
        x2 = x1 + card_w
        y2 = y1 + card_h

        bg = unavailable_bg if unavailable else live_card_bg
        c.create_rectangle(x1, y1, x2, y2, fill=bg, outline="")

        # A barely-there lower hairline keeps the grid legible without turning
        # it into a spreadsheet of boxed cells.
        c.create_line(x1, y2, x2, y2,
                      fill=_mix(theme.HAIRLINE, bg, .45), width=1)

        label_col = theme.TEXT_3 if not unavailable else _mix(theme.TEXT_3, page_bg, .18)
        status_col = (
            theme.ACCENT_TEXT if status in ("DRAW", "FADE", "STRAIGHT", "ON TARGET")
            else theme.TEXT_3
        )
        if unavailable:
            status_col = _mix(theme.TEXT_3, page_bg, .12)

        c.create_text(
            x1 + int(15 * ui_scale), y1 + int(17 * ui_scale),
            text=label, fill=label_col, font=label_font, anchor="w"
        )
        if status:
            c.create_text(
                x2 - int(15 * ui_scale), y1 + int(17 * ui_scale),
                text=status, fill=status_col, font=status_font, anchor="e"
            )

        # Larger central value, with unit immediately below so the card reads
        # as one information group instead of three disconnected vertical zones.
        val_len = len(value)
        if val_len > 10:
            f_size = max(15, int(20 * ui_scale))
        elif val_len > 7:
            f_size = max(18, int(24 * ui_scale))
        else:
            f_size = max(21, int(31 * ui_scale))
        value_font = (theme.ui_font(), f_size, "bold")

        group_y = y1 + card_h * .55
        c.create_text(
            (x1 + x2) / 2, group_y,
            text=value, fill=value_col, font=value_font, anchor="center"
        )

        if unit:
            c.create_text(
                (x1 + x2) / 2, group_y + int(32 * ui_scale),
                text=unit, fill=theme.TEXT_3 if not unavailable else label_col,
                font=unit_font, anchor="center"
            )
