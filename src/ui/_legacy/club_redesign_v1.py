"""Club-page polish for the isolated design sandbox.

Keeps the existing four-quadrant instrument layout, but improves hierarchy,
removes duplicated spin data, tightens the Spin panel, and makes strike-state
certainty explicit.
"""

import math

import overview_redesign_v12 as shot_v12
import shanktuary_performance_studio as studio
import theme


def _num(value, default=0.0):
    try:
        if isinstance(value, dict):
            for key in ("right_handed", "left_handed", "value"):
                if key in value:
                    return float(value[key] or default)
            return default
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _handed(app, value, default=0.0):
    try:
        resolved = app.resolve_handed(value, default)
        return float(resolved if resolved is not None else default)
    except Exception:
        return _num(value, default)


def _delivery_takeaway(app, path, face_path):
    # Path signs are mirrored for LH in the production page.
    in_to_out = path < 0 if getattr(app, "is_left_handed", False) else path > 0
    if abs(path) <= 0.7:
        p = "Neutral path"
    else:
        p = "In-to-out delivery" if in_to_out else "Out-to-in delivery"

    if abs(face_path) <= 0.6:
        f = "face nearly square to path"
    elif face_path > 0:
        f = "face open to path"
    else:
        f = "face closed to path"
    return f"{p} · {f}"


def draw_top_metric_toolbar(app, avail_w, ball_speed, club_speed, smash, carry,
                            total, offline, hang_time, eff_pct, offset_x=0,
                            smash_clamped=False):
    """Club page ribbon: six useful metrics, quieter than the diagnostics."""
    c = app.canvas
    t_scale = max(0.9, min(2.0, avail_w / 1200.0))
    top_y = 52
    bar_h = int(56 * t_scale)
    bot_y = top_y + bar_h
    c.create_rectangle(offset_x, top_y, offset_x + avail_w, bot_y,
                       fill=theme.BG, outline="")
    c.create_line(offset_x, bot_y, offset_x + avail_w, bot_y,
                  fill=theme.HAIRLINE)

    off_abs = abs(offline)
    off_dir = "L" if offline < 0 else "R"
    off_str = f"{off_abs:.1f} {off_dir} YDS" if off_abs > 0.1 else "0.0 STRAIGHT"
    derived_col = theme.MUTED if smash_clamped else theme.TEXT_2

    metrics = [
        ("BALL SPEED", f"{ball_speed:.1f} MPH", theme.TEXT),
        ("CLUB SPEED", "-- MPH" if smash_clamped else f"{club_speed:.1f} MPH", derived_col),
        ("SMASH", "--" if smash_clamped else f"{smash:.2f}", derived_col),
        ("CARRY", f"{carry:.1f} YDS", theme.ACCENT_TEXT),
        ("TOTAL", f"{total:.1f} YDS", theme.TEXT),
        ("OFFLINE", off_str,
         theme.TEXT if off_abs <= 4.0 else (theme.WARN if off_abs <= 12.0 else theme.DANGER)),
    ]

    lbl_font = (theme.ui_font(), max(7, int(8 * t_scale)), "bold")
    val_font = (theme.ui_font(), max(10, int(13 * t_scale)), "bold")
    col_w = avail_w / len(metrics)
    pad = int(18 * t_scale)
    for i, (label, val, col) in enumerate(metrics):
        lx = int(offset_x + i * col_w) + pad
        c.create_text(lx, top_y + int(14 * t_scale), text=label,
                      fill=theme.TEXT_3, font=lbl_font, anchor="w")
        c.create_text(lx, top_y + int(39 * t_scale), text=val,
                      fill=col, font=val_font, anchor="w")


def _impact_state(app):
    shot = app.current_shot or {}
    ogc = shot.get("open_golf_coach", {}) if isinstance(shot, dict) else {}
    impact = (
        shot.get("face_impact") or shot.get("impact_location") or
        ogc.get("face_impact") or ogc.get("impact_location") or
        ogc.get("face_contact") or {}
    ) if isinstance(shot, dict) else {}

    measured = False
    if isinstance(impact, dict) and impact:
        measured = any(k in impact for k in (
            "lateral_offset_mm", "heel_toe_mm", "horizontal_offset_mm", "x_mm",
            "vertical_offset_mm", "high_low_mm", "y_mm",
        ))

    conf = app.compute_smash_confidence(
        shot.get("ball_speed_meters_per_second") if isinstance(shot, dict) else None,
        shot.get("vertical_launch_angle_degrees") if isinstance(shot, dict) else None,
        shot.get("total_spin_rpm") if isinstance(shot, dict) else None,
    )
    magnitude_known = not bool(conf.get("clamped"))
    hx, vy = shot_v12._impact_offsets_mm(app)
    dir_known = math.hypot(hx, vy) >= 0.5

    if measured:
        return "measured", hx, vy
    if dir_known and magnitude_known:
        return "estimated", hx, vy
    if dir_known:
        return "direction", hx, vy
    return "unknown", 0.0, 0.0


def _direction_text(hx, vy):
    if vy > 1.0:
        vertical = "High"
    elif vy < -1.0:
        vertical = "Low"
    else:
        vertical = "Near centre"

    if hx > 1.0:
        horizontal = "Heel"
    elif hx < -1.0:
        horizontal = "Toe"
    else:
        horizontal = "Near centre"
    return vertical, horizontal


def polish_club_page(app, avail_w, h, club_path, face_to_target, face_to_path,
                     vert_launch, horiz_launch, sidespin, backspin, total_spin,
                     spin_axis, apex_yds, descent, opt_max, eff_pct, shot_name,
                     shot_rank, smash, ball_speed=0.0, offset_x=0,
                     top_bar_h=108):
    """Overlay only the areas that need polish after production draws the page."""
    c = app.canvas
    avail_h = h - top_bar_h - 10
    quad_w = avail_w // 2
    quad_h = avail_h // 2
    mid_x = offset_x + quad_w
    mid_y = top_bar_h + quad_h
    scale = max(0.85, min(2.5, min(quad_w / 380.0, quad_h / 230.0)))
    fs = max(0.85, min(1.85, scale))

    cap_f = (theme.ui_font(), max(7, int(8 * fs)))
    val_f = (theme.ui_font(), max(9, int(12 * fs)))
    small_bold = (theme.ui_font(), max(7, int(8 * fs)), "bold")
    body_f = (theme.ui_font(), max(8, int(9 * fs)))

    gut_l = offset_x + int(18 * fs)
    gut_r = mid_x - int(18 * fs)
    gut_l3 = mid_x + int(18 * fs)
    gut_r3 = offset_x + avail_w - int(18 * fs)

    # --- Q1: fold Derived into the title and add an immediate interpretation.
    # Cover only the old floating DERIVED label; leave the existing club graphic
    # and numerical annotations intact.
    c.create_rectangle(gut_r - int(120 * fs), top_bar_h + 2,
                       gut_r + 2, top_bar_h + int(54 * fs),
                       fill=theme.BG, outline="")
    tag_x = gut_l + int(128 * fs)
    tag_y = top_bar_h + int(16 * fs)
    c.create_rectangle(tag_x, tag_y - int(7 * fs),
                       tag_x + int(52 * fs), tag_y + int(8 * fs),
                       fill=theme.SURFACE_2, outline="")
    c.create_text(tag_x + int(26 * fs), tag_y,
                  text="DERIVED", fill=theme.TEXT_3,
                  font=(theme.ui_font(), max(6, int(7 * fs)), "bold"),
                  anchor="center")
    c.create_text(gut_r, top_bar_h + int(39 * fs),
                  text=_delivery_takeaway(app, club_path, face_to_path),
                  fill=theme.ACCENT_TEXT, font=small_bold, anchor="e")

    # --- Q2: remove duplicated backspin. Show actual club-delivery inputs only
    # when the shot payload contains them.
    q2_top = mid_y
    c.create_rectangle(gut_r - int(175 * fs), q2_top + int(18 * fs),
                       gut_r + 2, q2_top + int(95 * fs),
                       fill=theme.BG, outline="")
    shot = app.current_shot or {}
    ogc = shot.get("open_golf_coach", {}) if isinstance(shot, dict) else {}
    dyn = _handed(app, ogc.get("dynamic_loft_degrees") or
                  (shot.get("dynamic_loft_degrees") if isinstance(shot, dict) else None), 0.0)
    aoa = _handed(app, ogc.get("angle_of_attack_degrees") or
                  (shot.get("angle_of_attack_degrees") if isinstance(shot, dict) else None), 0.0)
    yy = q2_top + int(34 * fs)
    if abs(dyn) > 0.05:
        c.create_text(gut_r, yy, text="DYNAMIC LOFT", fill=theme.TEXT_3,
                      font=cap_f, anchor="ne")
        c.create_text(gut_r, yy + int(16 * fs), text=f"{dyn:.1f}°",
                      fill=theme.TEXT, font=val_f, anchor="ne")
        yy += int(40 * fs)
    if abs(aoa) > 0.05:
        c.create_text(gut_r, yy, text="ATTACK ANGLE", fill=theme.TEXT_3,
                      font=cap_f, anchor="ne")
        c.create_text(gut_r, yy + int(16 * fs), text=f"{aoa:.1f}°",
                      fill=theme.TEXT, font=val_f, anchor="ne")

    # --- Q3: redraw Spin with a smaller graphic and tighter information cluster.
    q3_top, q3_bot = top_bar_h, mid_y
    q3_cx = mid_x + quad_w / 2
    q3_cy = q3_top + quad_h / 2
    c.create_rectangle(mid_x + 2, q3_top + 2,
                       offset_x + avail_w - 2, q3_bot - 2,
                       fill=theme.BG, outline="")
    c.create_text(gut_l3, q3_top + int(16 * fs), text="SPIN",
                  fill=theme.TEXT_3, font=cap_f, anchor="w")
    c.create_text(q3_cx, q3_top + int(32 * fs), text=shot_name,
                  fill=theme.ACCENT_TEXT,
                  font=(theme.ui_font(), max(10, int(12 * fs))), anchor="center")

    ball_r = int(23 * scale)
    spin_cy = q3_cy - int(6 * scale)
    c.create_oval(q3_cx - ball_r, spin_cy - ball_r,
                  q3_cx + ball_r, spin_cy + ball_r,
                  fill=theme.TEXT, outline=theme.TEXT_2, width=2)
    axis_rad = math.radians(spin_axis)
    spin_len = int(38 * scale)
    ax1, ay1 = app.rotate_point(q3_cx, spin_cy + spin_len,
                                q3_cx, spin_cy, axis_rad)
    ax2, ay2 = app.rotate_point(q3_cx, spin_cy - spin_len,
                                q3_cx, spin_cy, axis_rad)
    c.create_line(ax1, ay1, ax2, ay2, fill=theme.ACCENT_LINE,
                  width=max(3, int(4 * scale)), arrow="last",
                  arrowshape=(int(12 * scale), int(15 * scale), int(5 * scale)))

    info_y = q3_cy + int(36 * fs)
    c.create_text(gut_l3, info_y, text="SPIN AXIS", fill=theme.TEXT_3,
                  font=cap_f, anchor="nw")
    c.create_text(gut_l3, info_y + int(16 * fs),
                  text=f"{abs(spin_axis):.1f}° {'right' if spin_axis > 0 else 'left'}",
                  fill=theme.TEXT, font=val_f, anchor="nw")
    c.create_text(gut_r3, info_y, text="TOTAL / BACKSPIN", fill=theme.TEXT_3,
                  font=cap_f, anchor="ne")
    c.create_text(gut_r3, info_y + int(16 * fs),
                  text=f"{int(total_spin)} / {int(backspin)} rpm",
                  fill=theme.TEXT, font=val_f, anchor="ne")

    # --- Q4: certainty-aware strike state. Never plot a precise-looking point
    # when we cannot locate it.
    q4_top, q4_bot = mid_y, h - 10
    q4_cx = mid_x + quad_w / 2
    q4_cy = q4_top + quad_h / 2
    c.create_rectangle(mid_x + 2, q4_top + 2,
                       offset_x + avail_w - 2, q4_bot - 2,
                       fill=theme.BG, outline="")

    state, hx, vy = _impact_state(app)
    vertical, horizontal = _direction_text(hx, vy)
    state_label = {
        "measured": "MEASURED",
        "estimated": "ESTIMATE",
        "direction": "DIRECTION ESTIMATE",
        "unknown": "UNAVAILABLE",
    }[state]
    state_col = theme.ACCENT_TEXT if state == "measured" else (
        theme.WARN if state in ("estimated", "direction") else theme.TEXT_3)

    cap_y = q4_top + int(16 * fs)
    c.create_text(gut_l3, cap_y, text="IMPACT LOCATION",
                  fill=theme.TEXT_3, font=cap_f, anchor="w")
    chip_x = gut_l3 + int(118 * fs)
    c.create_rectangle(chip_x, cap_y - int(8 * fs),
                       chip_x + int((62 if state != "direction" else 116) * fs),
                       cap_y + int(9 * fs), fill=theme.SURFACE_2, outline="")
    c.create_text(chip_x + int((31 if state != "direction" else 58) * fs), cap_y,
                  text=state_label, fill=state_col, font=small_bold,
                  anchor="center")

    info_y = q4_top + int(42 * fs)
    if state == "unknown":
        c.create_text(gut_l3, info_y, text="Location unavailable",
                      fill=theme.TEXT, font=(theme.ui_font(), max(10, int(13 * fs)), "bold"),
                      anchor="nw")
        c.create_text(gut_l3, info_y + int(27 * fs),
                      text="No reliable strike direction from this shot",
                      fill=theme.TEXT_3, font=body_f, anchor="nw")
    else:
        if state in ("measured", "estimated"):
            v_txt = f"{vertical} · {abs(vy):.1f} mm" if abs(vy) > 0.5 else vertical
            h_txt = f"{horizontal} · {abs(hx):.1f} mm" if abs(hx) > 0.5 else horizontal
        else:
            v_txt, h_txt = vertical, horizontal
        c.create_text(gut_l3, info_y, text="VERTICAL", fill=theme.TEXT_3,
                      font=cap_f, anchor="nw")
        c.create_text(gut_l3, info_y + int(16 * fs), text=v_txt,
                      fill=theme.TEXT, font=val_f, anchor="nw")
        c.create_text(gut_l3, info_y + int(43 * fs), text="HORIZONTAL",
                      fill=theme.TEXT_3, font=cap_f, anchor="nw")
        c.create_text(gut_l3, info_y + int(59 * fs), text=h_txt,
                      fill=theme.TEXT, font=val_f, anchor="nw")

    face_h = int(126 * scale)
    face_img = app.get_scaled_club_asset(
        studio.FACE_PATH, face_h, mirror=getattr(app, "is_left_handed", False))
    if face_img:
        c.create_image(q4_cx + int(32 * scale), q4_cy + int(2 * scale),
                       image=face_img, anchor="c")

    face_cx = q4_cx + int(32 * scale)
    sweet_dx = -43.5 / 220.0
    sweet_dy = -40.0 / 220.0
    center_x = face_cx + (-int(sweet_dx * face_h) if getattr(app, "is_left_handed", False)
                          else int(sweet_dx * face_h))
    center_y = q4_cy + int(2 * scale) + int(sweet_dy * face_h)
    cross_len = int(14 * scale)
    c.create_line(center_x - cross_len, center_y, center_x + cross_len, center_y,
                  fill=theme.GUIDE, width=1, dash=(2, 2))
    c.create_line(center_x, center_y - cross_len, center_x, center_y + cross_len,
                  fill=theme.GUIDE, width=1, dash=(2, 2))

    if state != "unknown":
        target_w = 290 * (face_h / 220.0)
        scale_px = ((167.0 - 36.0) / 290.0 * target_w) / 52.0
        dx_px = -int(hx * scale_px) if getattr(app, "is_left_handed", False) else int(hx * scale_px)
        impact_x = center_x + dx_px
        impact_y = center_y - int(vy * scale_px)
        col = theme.ACCENT_TEXT if state == "measured" else theme.WARN
        if state == "measured":
            r = int(9 * scale)
            c.create_oval(impact_x - r, impact_y - r, impact_x + r, impact_y + r,
                          fill="", outline=col, width=2)
        else:
            r = int((12 if state == "estimated" else 18) * scale)
            c.create_oval(impact_x - r, impact_y - r, impact_x + r, impact_y + r,
                          fill="", outline=col, width=1, dash=(4, 3))
        dot = max(3, int(3.2 * scale))
        c.create_oval(impact_x - dot, impact_y - dot, impact_x + dot, impact_y + dot,
                      fill=col, outline="")

    if state == "measured":
        foot = f"{math.hypot(hx, vy):.1f} mm from centre"
    elif state == "estimated":
        foot = f"~{math.hypot(hx, vy):.0f} mm from centre · estimated"
    elif state == "direction":
        foot = "Direction estimate only · distance not known"
    else:
        foot = "No face-location estimate shown"
    c.create_text(gut_l3, q4_bot - int(30 * fs), text=foot,
                  fill=theme.TEXT_3, font=cap_f, anchor="w")
    c.create_text(gut_l3, q4_bot - int(14 * fs),
                  text="Nova measures ball flight, not face contact",
                  fill=theme.TEXT_3, font=cap_f, anchor="w")

    # Redraw quadrant dividers because Q3/Q4 overlays intentionally covered
    # their interior edges.
    c.create_line(mid_x, top_bar_h, mid_x, h - 10,
                  fill=theme.HAIRLINE, width=2)
    c.create_line(offset_x, mid_y, offset_x + avail_w, mid_y,
                  fill=theme.HAIRLINE, width=2)
