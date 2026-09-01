"""Numbers palette pass matching the accepted Shot / shell direction.

Keeps the accepted 4x4 Numbers layout from v1, while moving the page onto the
richer navy + teal-undertone material. Gold remains the hero/emphasis color;
teal is reserved for status/data cues rather than turning every metric blue.
"""

import overview_redesign_v8 as shot_v8
import overview_redesign_v14 as shot_v14
import theme

GOLD = shot_v14.GOLD
GOLD_LIGHT = shot_v14.GOLD_LIGHT
TEAL = shot_v14.TEAL
TEAL_LINE = shot_v14.TEAL_LINE
TEAL_TEXT = shot_v14.TEAL_TEXT

PAGE_BG = "#091B24"
CARD_BG = "#0E2631"
CARD_RAISED = "#12303B"
CARD_OFF = "#0B2029"
HAIRLINE = "#35515B"
TEXT = "#F0F2EF"
TEXT_2 = "#B5C1C5"
TEXT_3 = "#7B929A"
LABEL = "#90A6AC"


def _mix(a, b, t):
    def rgb(s):
        s = s.lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    aa, bb = rgb(a), rgb(b)
    vals = tuple(round(x + (y - x) * t) for x, y in zip(aa, bb))
    return "#%02X%02X%02X" % vals


def _background(app, avail_w, h, offset_x=0):
    img = shot_v8._material_image(
        app, "numbers_v2_bg", avail_w, max(1, h - 52),
        top="#0D2732", bottom="#07151E",
        left="#0A2933", right="#091923",
        mottle=.050, fibers=.020, grain=.015, seed=227,
    )
    app.canvas.create_image(offset_x, 52, image=img, anchor="nw")


def draw_big_numbers_viewport(
    app, avail_w, h, carry, total, ball_speed, club_speed, smash, launch, spin,
    spin_axis, club_path, face_to_path, apex, offline, closure_rate=0.0,
    attack_angle=0.0, dynamic_loft=0.0, hang_time=0.0, offset_x=0,
):
    c = app.canvas
    _background(app, avail_w, h, offset_x=offset_x)

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
        ("CARRY DISTANCE", f"{carry:.1f}", "YARDS", GOLD_LIGHT, "", False),
        ("TOTAL DISTANCE", f"{total:.1f}", "YARDS", TEXT, "", False),
        ("BALL SPEED", f"{ball_speed:.1f}", "MPH", TEXT, "", False),
        ("CLUB SPEED", "--" if clamped else f"{club_speed:.1f}",
         "" if clamped else "MPH", TEXT_3 if clamped else TEXT,
         "DERIVED" if not clamped else "UNAVAILABLE", clamped),
        ("SMASH FACTOR", "--" if clamped else f"{smash:.2f}",
         "" if clamped else "RATIO", TEXT_3 if clamped else TEXT,
         "DERIVED" if not clamped else "UNAVAILABLE", clamped),
        ("LAUNCH ANGLE", f"{launch:.1f}°", "", TEXT, "", False),
        ("TOTAL SPIN", f"{int(spin)}", "RPM", TEXT, "", False),
        ("SPIN AXIS", f"{abs(spin_axis):.1f}° {axis_dir}", "", TEXT,
         "DRAW" if spin_axis < 0 else ("FADE" if spin_axis > 0 else "STRAIGHT"), False),
        ("CLOSURE RATE", f"{int(closure_rate)}", "DEG / SEC", TEXT,
         "DERIVED", False),
        ("APEX HEIGHT", f"{apex_ft:.1f}", "FEET", TEXT, "", False),
        ("CLUB PATH", f"{abs(club_path):.1f}° {path_dir}", "", TEXT,
         "DERIVED", False),
        ("FACE TO PATH", f"{abs(face_to_path):.1f}° {face_dir}", "", TEXT,
         "DERIVED", False),
        ("ATTACK ANGLE", "--", "", TEXT_3, "NOT MEASURED", True),
        ("DYNAMIC LOFT", "--", "", TEXT_3, "NOT MEASURED", True),
        ("HANG TIME", f"{hang_time:.1f}s", "", TEXT, "", False),
        ("OFFLINE", f"{abs(offline):.1f} {off_dir}", "YARDS",
         TEXT if abs(offline) <= 4.0 else GOLD_LIGHT,
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

    for idx, (label, value, unit, value_col, status, unavailable) in enumerate(cards):
        r = idx // cols
        col = idx % cols
        x1 = offset_x + pad_x + col * (card_w + col_gap)
        y1 = top_y + r * (card_h + row_gap)
        x2 = x1 + card_w
        y2 = y1 + card_h

        bg = CARD_OFF if unavailable else CARD_BG
        c.create_rectangle(x1, y1, x2, y2, fill=bg, outline="")
        c.create_line(x1, y2, x2, y2,
                      fill=_mix(HAIRLINE, bg, .32), width=1)

        label_col = _mix(LABEL, PAGE_BG, .18) if unavailable else LABEL
        if status in ("DRAW", "FADE", "STRAIGHT", "ON TARGET"):
            status_col = TEAL_TEXT
        else:
            status_col = TEXT_3
        if unavailable:
            status_col = _mix(TEXT_3, PAGE_BG, .18)

        c.create_text(
            x1 + int(15 * ui_scale), y1 + int(17 * ui_scale),
            text=label, fill=label_col, font=label_font, anchor="w",
        )
        if status:
            c.create_text(
                x2 - int(15 * ui_scale), y1 + int(17 * ui_scale),
                text=status, fill=status_col, font=status_font, anchor="e",
            )

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
            text=value, fill=value_col, font=value_font, anchor="center",
        )
        if unit:
            c.create_text(
                (x1 + x2) / 2, group_y + int(32 * ui_scale),
                text=unit,
                fill=TEXT_3 if not unavailable else label_col,
                font=unit_font, anchor="center",
            )
