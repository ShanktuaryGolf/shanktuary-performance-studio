"""Source-neutral rendering without Nova-specific inferred contact/delivery."""
import theme

from .presentation import metric_status, metric_value


def draw_connection_metrics(app, width, height, offset_x=0):
    shot = app.aim_corrected(app.current_shot)
    c = app.canvas
    for name in ("contact_face_rect", "contact_face_geometry", "contact_clear_rect"):
        setattr(app, name, None)
    entries = (("ball_speed", "BALL SPEED", "mph"), ("club_speed", "CLUB SPEED", "mph"),
               ("carry", "CARRY", "yd"), ("total", "TOTAL", "yd"),
               ("launch", "LAUNCH", "°"), ("horizontal_launch", "START LINE", "°"),
               ("spin", "SPIN", "rpm"), ("spin_axis", "SPIN AXIS", "°"),
               ("apex", "APEX", "yd"), ("offline", "OFFLINE", "yd"),
               ("smash", "SMASH", ""), ("descent", "DESCENT", "°"),
               ("club_path", "CLUB PATH", "°"), ("face_to_path", "FACE TO PATH", "°"),
               ("attack_angle", "ATTACK ANGLE", "°"), ("dynamic_loft", "DYNAMIC LOFT", "°"))
    top, gap = 100, 12
    cell_w = (width - 48 - gap * 3) / 4
    cell_h = max(85, (height - top - 75 - gap * 3) / 4)
    for index, (key, label, unit) in enumerate(entries):
        x = offset_x + 24 + (index % 4) * (cell_w + gap)
        y = top + (index // 4) * (cell_h + gap)
        c.create_rectangle(x, y, x + cell_w, y + cell_h, fill=theme.SURFACE, outline=theme.HAIRLINE)
        value, status = metric_value(shot, key, left_handed=getattr(app, "is_left_handed", False)), metric_status(shot, key)
        c.create_text(x + 16, y + 16, text=label, anchor="nw", fill=theme.TEXT_2, font=(theme.ui_font(), 9))
        c.create_text(x + 16, y + 40, text="--" if value is None else f"{value:.1f} {unit}", anchor="nw", fill=theme.TEXT, font=(theme.ui_font(), 22))
        c.create_text(x + 16, y + cell_h - 20, text=status, anchor="nw", fill=theme.TEXT_3, font=(theme.ui_font(), 8))
    c.create_text(offset_x + 24, height - 38, text="Only supplied values are reported. Estimates are labelled; missing data stays blank.", anchor="w", fill=theme.TEXT_2, font=(theme.ui_font(), 9))
