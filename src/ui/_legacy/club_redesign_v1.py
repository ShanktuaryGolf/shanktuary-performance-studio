"""Club-page polish for the isolated design sandbox.

Keeps the existing four-quadrant instrument layout, but improves hierarchy,
removes duplicated spin data, tightens the Spin panel, and makes strike-state
certainty explicit.
"""

import math

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


def _delivery_takeaway(app, path, face_path, path_known=True, face_path_known=True):
    if not path_known and not face_path_known:
        return "Club delivery not reported by this source"

    # Path signs are mirrored for LH in the production page.
    if path_known:
        in_to_out = path < 0 if getattr(app, "is_left_handed", False) else path > 0
        if abs(path) <= 0.7:
            p = "Neutral path"
        else:
            p = "In-to-out delivery" if in_to_out else "Out-to-in delivery"
    else:
        p = "Path not reported"

    if face_path_known:
        if abs(face_path) <= 0.6:
            f = "face nearly square to path"
        elif face_path > 0:
            f = "face open to path"
        else:
            f = "face closed to path"
    else:
        f = "face not reported"
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
    from src.analytics.strike import contact_location

    contact = contact_location(app.current_shot)
    return ("reported" if contact.available else "unknown",
            contact.horizontal_mm, contact.vertical_mm)


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
                     top_bar_h=108, club_path_known=True, face_to_path_known=True,
                     face_to_target_known=True):
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
                  text=_delivery_takeaway(app, club_path, face_to_path,
                                          path_known=club_path_known,
                                          face_path_known=face_to_path_known),
                  fill=theme.ACCENT_TEXT if (club_path_known or face_to_path_known) else theme.TEXT_3,
                  font=small_bold, anchor="e")

    # --- Q2: remove duplicated backspin. Show actual club-delivery inputs only
    # when the shot payload contains them.
    q2_top = mid_y
    shot = app.current_shot or {}
    ogc = shot.get("open_golf_coach", {}) if isinstance(shot, dict) else {}
    dyn = _handed(app, ogc.get("dynamic_loft_degrees") or
                  (shot.get("dynamic_loft_degrees") if isinstance(shot, dict) else None), 0.0)
    aoa = _handed(app, ogc.get("angle_of_attack_degrees") or
                  (shot.get("angle_of_attack_degrees") if isinstance(shot, dict) else None), 0.0)

    # Mask only the strip these right-aligned labels occupy. The old fixed
    # 175x77 block reached far left of the widest label ("DYNAMIC LOFT",
    # ~100px) and down past the trajectory apex, erasing the top of the
    # ball-flight arc so it looked cut off mid-curve.
    rows = int(abs(dyn) > 0.05) + int(abs(aoa) > 0.05)
    if rows:
        mask_w = 0
        for label in ("DYNAMIC LOFT", "ATTACK ANGLE"):
            probe = c.create_text(-4000, -4000, text=label, font=cap_f, anchor="w")
            bb = c.bbox(probe)
            c.delete(probe)
            if bb:
                mask_w = max(mask_w, bb[2] - bb[0])
        mask_w = int(mask_w + 16 * fs)
        mask_bottom = q2_top + int(34 * fs) + (rows - 1) * int(40 * fs) + int(26 * fs)
        c.create_rectangle(gut_r - mask_w, q2_top + int(18 * fs),
                           gut_r + 2, mask_bottom,
                           fill=theme.BG, outline="")
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

    # Q4 is owned by the shared production contact painter. Do not repaint it.

    # Redraw quadrant dividers because Q3/Q4 overlays intentionally covered
    # their interior edges.
    c.create_line(mid_x, top_bar_h, mid_x, h - 10,
                  fill=theme.HAIRLINE, width=2)
    c.create_line(offset_x, mid_y, offset_x + avail_w, mid_y,
                  fill=theme.HAIRLINE, width=2)
