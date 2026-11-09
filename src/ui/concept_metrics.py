"""Source-aware Numbers and scenic desktop Range workspaces."""

import math

from src.connections.presentation import metric_status, metric_value

from . import tokens as T
from .concept_shell import panel, text

METRICS = [
    ("Carry", "carry", "yd"),
    ("Total", "total", "yd"),
    ("Ball speed", "ball_speed", "mph"),
    ("Club speed", "club_speed", "mph"),
    ("Smash", "smash", ""),
    ("Launch", "launch", "°"),
    ("Spin", "spin", "rpm"),
    ("Spin axis", "spin_axis", "°"),
    ("Club path", "club_path", "°"),
    ("Face to path", "face_to_path", "°"),
    ("Apex", "apex", "yd"),
    ("Offline", "offline", "yd"),
    ("Closure rate", "closure_rate", "°/s"),
    ("Attack angle", "attack_angle", "°"),
    ("Dynamic loft", "dynamic_loft", "°"),
    ("Hang time", "hang_time", "s"),
]


def formatted(app, shot, key, unit):
    value = metric_value(shot, key, left_handed=app.is_left_handed)
    status = metric_status(shot, key, left_handed=app.is_left_handed)
    if value is None:
        return "—", "Unavailable"
    spec = (
        ".2f"
        if key == "smash"
        else ".0f"
        if key
        in (
            "carry",
            "total",
            "spin",
            "apex",
            "ball_speed",
            "club_speed",
            "closure_rate",
        )
        else ".1f"
    )
    suffix = (
        (" L" if value < 0 else " R")
        if key in ("offline", "spin_axis") and value
        else ""
    )
    val = abs(value) if suffix else value
    status = {
        "NATIVE": "Native",
        "DERIVED": "Derived",
        "MODELLED": "Modelled",
        "ESTIMATED": "Estimate",
        "UNAVAILABLE": "Unavailable",
        "MEASURED": "Measured",
    }.get(status, status.title())
    return f"{val:{spec}}{unit if unit == '°' else ' ' + unit}{suffix}".strip(), status


def numbers(app, width, height, offset_x=0):
    c = app.canvas
    x0 = offset_x + 20
    x1 = offset_x + width - 20
    c.create_rectangle(offset_x, 52, x1 + 20, height, fill=T.PAGE_BG, outline="")
    shot = app.aim_corrected(app.current_shot or {})
    panel(c, x0, 60, x1, 110)
    text(
        c,
        x0 + 22,
        85,
        "Club: " + str((app.current_shot or {}).get("club") or app.current_club),
        14,
        bold=True,
    )
    text(
        c,
        x0 + 350,
        85,
        "Shot: "
        + (str(app.selected_shot_index + 1) if app.current_shot else "Waiting"),
        14,
    )
    gap = 12
    cw = (x1 - x0 - gap * 3) / 4
    ch = (height - 241 - gap * 3) / 4
    for i, (label, key, unit) in enumerate(METRICS):
        x = x0 + (i % 4) * (cw + gap)
        y = 135 + (i // 4) * (ch + gap)
        value, status = formatted(app, shot, key, unit)
        col = (
            T.TEXT
            if status == "Unavailable"
            else T.GOLD
            if key == "carry"
            else T.TEXT
        )
        panel(
            c,
            x,
            y,
            x + cw,
            y + ch,
            fill=T.SURFACE,
            outline=T.GOLD if key == "carry" else T.HAIRLINE,
        )
        text(c, x + 20, y + 26, label, 18, bold=True)
        size = min(44, max(22, int(cw / (len(value) * 0.58))))
        text(c, x + 20, y + ch * 0.52, value, size, col, True)
        pill_w = min(cw - 40, app._text_width(status, ("Noto Sans", 13)) + 54)
        badge = (
            T.TEXT
            if status == "Unavailable"
            else T.GOLD
            if status in ("Estimate", "Modelled")
            else T.TEAL_LINE
        )
        panel(
            c,
            x + 20,
            y + ch - 44,
            x + 20 + pill_w,
            y + ch - 12,
            fill=T.PAGE_BG,
            outline=badge,
            r=14,
        )
        c.create_oval(
            x + 31,
            y + ch - 33,
            x + 40,
            y + ch - 24,
            fill=badge if status != "Derived" else T.PAGE_BG,
            outline=badge,
        )
        text(c, x + 49, y + ch - 28, status, 13)


def landscape(c, x0, y0, x1, y1):
    """Original vector terrain, not an image of fabricated telemetry."""
    from .concept_art import range_landscape

    if range_landscape(c, x0, y0, x1, y1, sky_crop=0.20):
        return y0 + (y1 - y0) * 0.425
    w = x1 - x0
    h = y1 - y0
    horizon = y0 + h * 0.43
    c.create_rectangle(x0, y0, x1, y1, fill="#06252F", outline="")
    for band in range(60):
        frac = band / 59
        r = round(5 + frac * 1)
        g = round(26 + frac * 35)
        b = round(37 + frac * 32)
        yy = y0 + band * h * 0.48 / 60
        c.create_rectangle(
            x0,
            yy,
            x1,
            yy + h * 0.48 / 60 + 1,
            fill=f"#{r:02x}{g:02x}{b:02x}",
            outline="",
        )
    for layer, color in ((0, "#0A3945"), (1, "#072E39"), (2, "#04262D")):
        pts = [x0, horizon + 40]
        for j in range(81):
            xx = x0 + j * w / 80
            yy = (
                horizon
                - 30
                + layer * 22
                + math.sin(j * 0.28 + layer) * 18
                + math.sin(j * 0.69 + layer) * 8
            )
            pts.extend((xx, yy))
        pts.extend((x1, horizon + 60))
        c.create_polygon(*pts, fill=color, outline="")
    for j in range(90):
        xx = x0 + j * w / 89
        hh = 13 + (math.sin(j * 3.7) + 1) * 15
        yy = horizon + 33
        c.create_polygon(
            xx - 7, yy, xx, yy - hh, xx + 7, yy, fill="#03282C", outline=""
        )
    ground = horizon + 35
    c.create_rectangle(x0, ground, x1, y1, fill="#04342F", outline="")
    for band in range(9):
        yy = ground + (y1 - ground) * (band / 8) ** 1.8
        c.create_line(x0, yy, x1, yy, fill="#15534C")
    for i in range(-10, 11):
        c.create_line(
            (x0 + x1) / 2 + i * w * 0.025,
            ground,
            (x0 + x1) / 2 + i * w * 0.15,
            y1,
            fill="#12564D",
        )
    return ground


def project_downrange(distance, offline, elevation, bounds):
    """Project yards to a camera behind the tee; no source value is modified."""
    x0, y0, x1, y1 = bounds
    horizon = y0 + (y1 - y0) * 0.425
    ground_span = y1 - 50 - horizon
    camera_height, near_depth = 12.0, 35.0
    focal = ground_span * near_depth / camera_height
    depth = near_depth + max(0, distance)
    return (
        (x0 + x1) / 2 + focal * offline / depth,
        horizon + focal * (camera_height - elevation) / depth,
    )


def downrange_trajectory(carry, apex, offline, bounds, horizontal_launch=None):
    """Derived flight path constrained to supplied carry/apex/landing location.

    This is a visualization, not a replacement ball-flight physics model.
    Missing launch direction uses only the known landing lateral displacement.
    """
    result = []
    for j in range(61):
        t = j / 60
        startline = (
            math.tan(math.radians(horizontal_launch)) * carry * t
            if horizontal_launch is not None
            else offline * t
        )
        lateral = startline * (1 - t) + offline * t * t
        result.append(
            project_downrange(carry * t, lateral, 4 * apex * t * (1 - t), bounds)
        )
    return result


def range_page(app, width, height, offset_x=0):
    c = app.canvas
    x0 = offset_x + 20
    x1 = offset_x + width - 20
    c.create_rectangle(offset_x, 52, x1 + 20, height, fill=T.PAGE_BG, outline="")
    shot = app.aim_corrected(app.current_shot or {})
    panel(c, x0, 70, x1, 198)
    entries = [METRICS[i] for i in (0, 1, 2, 5, 6)]
    for i, (label, key, unit) in enumerate(entries):
        x = x0 + 18 + i * (x1 - x0) / 5
        value, status = formatted(app, shot, key, unit)
        text(c, x, 95, label, 16, T.TEXT_2)
        text(c, x, 135, value, 32, bold=True)
        text(c, x, 177, status, 12, T.TEAL_TEXT if status != "Unavailable" else T.TEXT_3)
        if i:
            c.create_line(x - 14, 82, x - 14, 187, fill=T.HAIRLINE)
    top = 210
    bottom = height - 150
    landscape(c, offset_x, top, offset_x + width, bottom)
    cx = (x0 + x1) / 2
    app.range_launch_web_rect = (cx - 160, top + 18, cx + 160, top + 72)
    panel(c, *app.range_launch_web_rect, fill=T.SURFACE, outline=T.TEAL_LINE)
    text(c, cx + 18, top + 45, "Open 3D Range", 18, bold=True, anchor="center")
    bx, by = cx - 113, top + 45
    c.create_line(bx, by-12, bx+12, by-5, bx+12, by+8, bx, by+15,
                  bx-12, by+8, bx-12, by-5, bx, by-12, fill=T.TEXT, width=1.7)
    c.create_line(bx-12, by-5, bx, by+2, bx+12, by-5, fill=T.TEXT, width=1.7)
    c.create_line(bx, by+2, bx, by+15, fill=T.TEXT, width=1.7)
    # A pinhole-style downrange camera shares the scene's horizon. Distance
    # runs into the screen, lateral offline runs across it, and height projects
    # vertically. A side profile must never be pasted onto this perspective.
    session_id = id(app.get_active_session())
    if getattr(app, "_concept_range_session", None) != session_id:
        app._concept_range_session = session_id
        app.concept_range_after = 0
    after = min(len(app.session_shots), getattr(app, "concept_range_after", 0))
    shots = app.session_shots[after:][-15:]
    vals = []
    for native in shots:
        s = app.aim_corrected(native)
        carry = metric_value(s, "carry")
        apex = metric_value(s, "apex")
        offline = metric_value(s, "offline")
        launch = metric_value(s, "horizontal_launch")
        if (
            carry is not None
            and apex is not None
            and offline is not None
            and carry > 0
            and apex >= 0
        ):
            vals.append((native, carry, apex, offline, launch))
    target = getattr(app, "concept_range_target", 150)
    bounds = (offset_x, top, offset_x + width, bottom)
    horizon = top + (bottom - top) * 0.425
    baseline = bottom - 50
    # Distance lines converge on the same horizon as terrain grid artwork.
    last_label_y = float("inf")
    for yard in (50, 100, 150, 200, 250, 300):
        left, yy = project_downrange(yard, -32, 0, bounds)
        right, _ = project_downrange(yard, 32, 0, bounds)
        c.create_line(left, yy, right, yy, fill=T.GUIDE, dash=(4, 6))
        if last_label_y - yy >= 22:
            text(c, x1 - 28, yy, f"{yard} yd", 9, T.TEXT_2, anchor="e")
            last_label_y = yy
    for native, carry, apex, offline, launch in vals:
        selected = native is app.current_shot
        points = downrange_trajectory(carry, apex, offline, bounds, launch)
        coords = [n for point in points for n in point]
        c.create_line(
            *coords,
            fill=T.GOLD if selected else "#477D79",
            width=3 if selected else 1.5,
            smooth=True,
            tags="downrange-flight",
        )
        land_x, land_y = points[-1]
        c.create_oval(
            land_x - 5,
            land_y - 5,
            land_x + 5,
            land_y + 5,
            fill=T.GOLD if selected else T.TEAL_SOFT,
            outline="",
        )
        if selected:
            text(
                c,
                land_x + 14,
                land_y - 17,
                f"{carry:.0f} yd · {abs(offline):.1f} {'L' if offline < 0 else 'R'}"
                if offline
                else f"{carry:.0f} yd · on line",
                10,
                T.GOLD,
            )
    # Target rings are circles on the ground, projected through the same camera.
    for radius in (5, 10, 15):
        coords = []
        for j in range(65):
            angle = j * math.tau / 64
            coords.extend(
                project_downrange(
                    target + radius * math.sin(angle),
                    radius * math.cos(angle),
                    0,
                    bounds,
                )
            )
        c.create_line(*coords, fill=T.TEAL_LINE, width=1, smooth=True)
    tx, ty = project_downrange(target, 0, 0, bounds)
    text(c, tx, ty + 21, f"Target {target} yd", 9, T.TEAL_TEXT, anchor="center")
    c.create_line(cx, horizon, cx, baseline, fill=T.GUIDE, dash=(3, 6))
    c.create_oval(cx - 5, baseline - 5, cx + 5, baseline + 5, fill=T.TEXT, outline="")
    if not vals:
        text(
            c,
            cx,
            (top + bottom) / 2,
            "Waiting for carry, apex and offline data",
            18,
            T.TEXT_2,
            anchor="center",
        )
    panel(c, x0, height - 150, x1, height - 62)
    text(c, x0 + 34, height - 107, "Club", 16, T.TEXT_2)
    text(c, x1 - 414, height - 107, "Target distance", 15, T.TEXT_2)
    for divider_x in (x0 + 458, x1 - 444):
        c.create_line(divider_x, height-135, divider_x, height-77, fill=T.HAIRLINE)
    app.concept_range_rects = []
    for rect, label, action in (
        (
            (x0 + 108, height - 132, x0 + 408, height - 82),
            app.current_club + "  ▾",
            "club",
        ),
        (
            (cx - 125, height - 132, cx + 125, height - 82),
            "Show session" if after else "Clear display",
            "clear",
        ),
        (
            (x1 - 234, height - 132, x1 - 32, height - 82),
            f"{target} yd  ▾",
            "target",
        ),
    ):
        panel(c, *rect, fill=T.SURFACE, outline=T.TEXT_2, r=9)
        text(
            c,
            (rect[0] + rect[2]) / 2,
            (rect[1] + rect[3]) / 2,
            label,
            14,
            bold=True,
            anchor="center",
        )
        app.concept_range_rects.append((rect, action))
    text(
        c,
        x1 - 6,
        height - 37,
        "Flight path is a derived visualization",
        8,
        T.TEXT_3,
        anchor="e",
    )

    if getattr(app, "concept_range_target_open", False):
        for i, distance in enumerate((50, 100, 150, 200, 250, 300)):
            rect = (x1 - 270, height - 348 + i * 33, x1 - 14, height - 315 + i * 33)
            panel(c, *rect, fill=T.ACTIVE_BG if distance == target else T.SURFACE, r=3)
            text(c, rect[0] + 16, (rect[1] + rect[3]) / 2, f"{distance} yd", 11)
            app.concept_range_rects.append((rect, f"target:{distance}"))


def handle_range_click(app, x, y):
    for rect, action in getattr(app, "concept_range_rects", []):
        if rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
            if action == "club":
                app.show_club_menu = True
            elif action == "clear":
                app.concept_range_after = (
                    0
                    if getattr(app, "concept_range_after", 0)
                    else len(app.session_shots)
                )
            elif action == "target":
                app.concept_range_target_open = not getattr(
                    app, "concept_range_target_open", False
                )
            elif action.startswith("target:"):
                app.concept_range_target = int(action.split(":")[1])
                app.concept_range_target_open = False
            app.draw_screen()
            return True
    if getattr(app, "concept_range_target_open", False):
        app.concept_range_target_open = False
        app.draw_screen()
        return True
    return False
