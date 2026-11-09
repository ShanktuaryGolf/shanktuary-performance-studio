"""Established Shot/Club compositions with presence-aware source data.

Keep this at the display boundary: payloads and session history are never
filled with defaults or changed. Unknown geometry is not drawn.
"""
import math
import statistics

import theme
from src.connections.presentation import metric_status, metric_value, shot_shape

BG = "#0E2733"
RIBBON = "#132E3C"
LINE = "#35515B"
GOLD = "#D4A24F"
TEAL = "#78C4C1"


def _text(c, x, y, text, size=11, color=None, **kwargs):
    return c.create_text(x, y, text=text, anchor="nw", fill=color or theme.TEXT,
                         font=(theme.ui_font(), size), **kwargs)


def _value(shot, key, app):
    return metric_value(shot, key, getattr(app, "is_left_handed", False))


def _metric(app, shot, x, y, key, label, unit="", size=19):
    value = _value(shot, key, app)
    status = metric_status(shot, key, getattr(app, "is_left_handed", False))
    _text(app.canvas, x, y, label, 10, theme.TEXT_2)
    digits = 0 if key in ("spin", "backspin", "sidespin") else 2 if key == "smash" else 1
    display = "--" if value is None else f"{value:.{digits}f} {unit}".strip()
    _text(app.canvas, x, y + 19, display, size, GOLD if key == "carry" else theme.TEXT)
    _text(app.canvas, x, y + 54, status, 8, TEAL)


def _section(app, x, y, title, note=None, width=240):
    _text(app.canvas, x, y, title, 15)
    if note:
        _text(app.canvas, x, y + 30, note, 10, theme.TEXT_2, width=max(70, width))


def _rows(app, shot, x, y, width, entries):
    for i, (key, label, unit) in enumerate(entries):
        _metric(app, shot, x + (i % 2) * width / 2, y + (i // 2) * 70,
                key, label, unit, 16)


def _dispersion(app, shots, x, y, width, height):
    points = [(s, _value(s, "carry", app), _value(s, "offline", app)) for s in shots]
    points = [(s, car, off) for s, car, off in points if car is not None and off is not None]
    _section(app, x, y, "Dispersion",
             "Carry and offline required" if not points else "Carry landing pattern", width)
    if not points:
        _text(app.canvas, x, y + 85, "Carry or offline not reported\nLanding positions unavailable", 12,
              theme.TEXT_2, width=width)
        return
    top, bottom = y + 70, y + height - 25
    left, right = x + 32, x + width - 20
    max_off = max(5, max(abs(p[2]) for p in points) * 1.2)
    low = min(p[1] for p in points) - 5
    high = max(p[1] for p in points) + 5
    centre = (left + right) / 2
    app.canvas.create_line(centre, top, centre, bottom, fill=TEAL, dash=(4, 6))
    _text(app.canvas, centre - 23, bottom + 5, "TARGET", 8, TEAL)
    for shot, carry, offline in points:
        xx = centre + offline / max_off * (right - left) / 2
        yy = bottom - (carry - low) / (high - low) * (bottom - top)
        current = app.current_shot or {}
        same_shot = shot is current or (shot.get("shotId") is not None
                                         and shot.get("shotId") == current.get("shotId")
                                         and shot.get("_source") == current.get("_source"))
        r = 6 if same_shot else 3
        app.canvas.create_oval(xx-r, yy-r, xx+r, yy+r, fill=GOLD, outline="")
    if any(metric_status(s, "carry") != "REPORTED" or metric_status(s, "offline") != "REPORTED"
           for s, _, _ in points):
        _text(app.canvas, x, y + 50, "Includes estimated/derived positions", 8, TEAL)


def _shape(app, shot, x, y, width, height):
    label, status = shot_shape(shot, getattr(app, "is_left_handed", False))
    # One compact line leaves the launch/spin rows and trace disclaimer intact.
    note = f"{label} | {status}" if label else "Ball launch and spin"
    _section(app, x, y, "Shot Shape", note, width)
    _rows(app, shot, x, y + 65, width, [
        ("horizontal_launch", "Start Line", "deg"), ("spin_axis", "Spin Axis", "deg"),
        ("launch", "Launch", "deg"), ("spin", "Spin Rate", "rpm")])
    hla = _value(shot, "horizontal_launch", app)
    if hla is not None and height >= 260:
        cx, cy = x + width / 2, y + height - 20
        length = min(75, height - 215)
        app.canvas.create_line(cx, cy, cx, cy - length, fill=LINE, dash=(3, 5))
        app.canvas.create_line(cx, cy, cx + math.sin(math.radians(hla)) * length,
                               cy - math.cos(math.radians(hla)) * length,
                               fill=GOLD, width=2, arrow="last")
        _text(app.canvas, x, y + height - 5, "Launch direction, not a flight trace", 8, TEAL, width=width)


def _strike(app, x, y, width, face_height=48):
    _section(app, x, y, "Strike", "Impact location not reported", width)
    # No centre dot or inferred face contact for a ball-only source.
    asset = None
    if hasattr(app, "get_scaled_club_asset"):
        from shanktuary_performance_studio import FACE_PATH
        asset = app.get_scaled_club_asset(
            FACE_PATH, face_height, mirror=bool(getattr(app, "is_left_handed", False)),
            pad_square=False)
        if asset and hasattr(asset, "width") and asset.width() > width - 12:
            face_height = max(12, int(face_height * (width - 12) / asset.width()))
            asset = app.get_scaled_club_asset(
                FACE_PATH, face_height, mirror=bool(getattr(app, "is_left_handed", False)),
                pad_square=False)
    if asset:
        app.canvas.create_image(x + width/2, y + 68 + face_height/2, image=asset, anchor="c")
    else:
        _text(app.canvas, x, y + 62, "No contact measurement", 12, theme.TEXT_2, width=width)


def _session(app, shots, x, y, width, height):
    _section(app, x, y, "Session", f"{len(shots)} shots for this club", width)
    entries = [("carry", "Avg Carry", "yd"), ("ball_speed", "Avg Ball Speed", "mph"),
               ("spin", "Avg Spin", "rpm"), ("club_speed", "Avg Club Speed", "mph")]
    for i, (key, label, unit) in enumerate(entries):
        xx = x + width * i / len(entries)
        values = [_value(s, key, app) for s in shots]
        values = [v for v in values if v is not None]
        _text(app.canvas, xx, y + 55, label, 10, theme.TEXT_2)
        _text(app.canvas, xx, y + 76,
              f"{statistics.mean(values):.1f} {unit}" if values else "--", 16)
        statuses = sorted({metric_status(s, key) for s in shots if _value(s, key, app) is not None})
        _text(app.canvas, xx, y + 110, " / ".join(statuses) if values else "NOT REPORTED", 8, TEAL)
        if len(values) > 1 and height >= 150:
            recent = values[-16:]
            lo, hi = min(recent), max(recent)
            span = max(1, hi - lo)
            coords = []
            for n, value in enumerate(recent):
                coords.extend((xx + n * (width / 4 - 35) / (len(recent)-1),
                               y + 148 - (value-lo) / span * 22))
            app.canvas.create_line(*coords, fill=TEAL, width=2)


def draw_connection_page(app, width, height, offset_x=0):
    """Draw Shot overview or Club delivery using supplied metrics only."""
    shot = app.aim_corrected(app.current_shot)
    for name in ("contact_face_rect", "contact_face_geometry", "contact_clear_rect",
                 "overview_viewall_rect", "overview_prev_rect", "overview_next_rect"):
        setattr(app, name, None)
    app.overview_bar_rects = []
    c = app.canvas
    c.create_rectangle(offset_x, 52, offset_x + width, height, fill=BG, outline="")
    if app.view_mode == 1:
        _draw_club(app, shot, width, height, offset_x)
    else:
        _draw_shot(app, shot, width, height, offset_x)


def _draw_shot(app, shot, width, height, offset_x):
    c = app.canvas
    x, right = offset_x + 24, offset_x + width - 24
    usable = right - x
    ribbon_y, ribbon_h = 66, 160
    c.create_rectangle(x, ribbon_y, right, ribbon_y+ribbon_h, fill=RIBBON, outline="")
    c.create_rectangle(x, ribbon_y, x+4, ribbon_y+ribbon_h, fill=GOLD, outline="")
    club = shot.get("club") or getattr(app, "current_club", "")
    _text(c, x+18, ribbon_y+17, "Shot Overview", 12 if width < 1000 else 15, TEAL)
    _text(c, x+18, ribbon_y+52, club, 19)
    _text(c, x+18, ribbon_y+90, "Supplied ball data", 10, theme.TEXT_2)
    # Keep the identity labels clear of Carry even with wider Linux fonts.
    identity = min(200, max(180, usable * .18))
    columns = [(("carry", "Carry", "yd"), ("total", "Total", "yd")),
               (("ball_speed", "Ball Speed", "mph"), ("club_speed", "Club Speed", "mph")),
               (("launch", "VLA", "deg"), ("horizontal_launch", "HLA", "deg")),
               (("spin", "Spin Rate", "rpm"), ("spin_axis", "Spin Axis", "deg")),
               (("apex", "Apex", "yd"), ("offline", "Offline", "yd"))]
    step = (usable-identity)/len(columns)
    for i, pair in enumerate(columns):
        xx = x+identity+i*step
        c.create_line(xx-8, ribbon_y+14, xx-8, ribbon_y+ribbon_h-14, fill=LINE)
        for row, (key, label, unit) in enumerate(pair):
            _metric(app, shot, xx, ribbon_y+12+row*74, key, label, unit, 16)
    top = ribbon_y+ribbon_h+24
    session_h = 165 if height >= 800 else 125
    bottom = max(top+240, height-session_h-38)
    gap = 24
    left_w, centre_w = usable*.39, usable*.28
    centre_x, right_x = x+left_w+gap, x+left_w+gap+centre_w+gap
    right_w = right-right_x
    club_shots = [app.aim_corrected(s) for s in getattr(app, "session_shots", [])
                  if not s.get("excluded") and (s.get("club") or getattr(app, "current_club", "")) == club]
    shots = club_shots
    for xx in (centre_x-gap/2, right_x-gap/2):
        c.create_line(xx, top, xx, bottom, fill=LINE)
    _dispersion(app, shots, x, top, left_w, bottom-top)
    _shape(app, shot, centre_x, top, centre_w, bottom-top-12)
    _strike(app, right_x, top, right_w)
    delivery_y = top+min(140, (bottom-top)*.45)
    c.create_line(right_x, delivery_y-12, right, delivery_y-12, fill=LINE)
    _section(app, right_x, delivery_y, "Club Delivery")
    _rows(app, shot, right_x, delivery_y+35, right_w, [
        ("club_path", "Club Path", "deg"), ("face_to_path", "Face to Path", "deg")])
    session_y = bottom+22
    c.create_line(x, session_y-8, right, session_y-8, fill=LINE)
    _session(app, shots, x, session_y, usable, height-session_y-12)


def _draw_club(app, shot, width, height, offset_x):
    c = app.canvas
    keys = [("ball_speed", "Ball Speed", "mph"), ("club_speed", "Club Speed", "mph"),
            ("smash", "Smash", ""), ("carry", "Carry", "yd"),
            ("total", "Total", "yd"), ("offline", "Offline", "yd")]
    for i, (key, label, unit) in enumerate(keys):
        _metric(app, shot, offset_x+22+i*width/6, 65, key, label, unit, 17)
    top, bottom = 145, height-34
    middle_x, middle_y = offset_x+width/2, (top+bottom)/2
    c.create_line(offset_x+20, top-12, offset_x+width-20, top-12, fill=LINE)
    c.create_line(middle_x, top, middle_x, bottom, fill=LINE)
    c.create_line(offset_x+20, middle_y, offset_x+width-20, middle_y, fill=LINE)
    panel_w = width/2-48
    x = offset_x+24
    _section(app, x, top+12, "Club Delivery", "Reported and modelled club data", panel_w)
    _rows(app, shot, x, top+76, panel_w, [
        ("club_path", "Club Path", "deg"), ("face_to_target", "Face to Target", "deg"),
        ("face_to_path", "Face to Path", "deg"), ("closure_rate", "Closure Rate", "deg/s")])
    _section(app, middle_x+24, top+12, "Launch & Delivery", "Ball launch does not measure club delivery", panel_w)
    _rows(app, shot, middle_x+24, top+76, panel_w, [
        ("launch", "Launch", "deg"), ("horizontal_launch", "Start Line", "deg"),
        ("attack_angle", "Attack Angle", "deg"), ("dynamic_loft", "Dynamic Loft", "deg")])
    _section(app, x, middle_y+20, "Spin")
    _rows(app, shot, x, middle_y+68, panel_w, [
        ("spin", "Total Spin", "rpm"), ("spin_axis", "Spin Axis", "deg"),
        ("backspin", "Backspin", "rpm"), ("sidespin", "Sidespin", "rpm")])
    _strike(app, middle_x+24, middle_y+20, panel_w, face_height=100)
    _text(c, offset_x+24, height-23,
          "Missing measurements stay blank. Source estimates are labelled; ball data does not establish face contact.",
          9, theme.TEXT_2, width=width-48)
