"""Unified local-board workspace, using production hardware actions and state.

Pairing, assignment and calibration are not simulated by this painter. Idle
and guided views share the approved five-stage composition; production owns
progression and the existing setup hit targets own device operations.
"""

from __future__ import annotations

import math
import time

from . import tokens as T
from .concept_shell import panel, text

STAGES = (
    ("pair", "Pair"),
    ("assign", "Assign"),
    ("align", "50/50"),
    ("width", "Stance width"),
    ("ready", "Ready"),
)


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _status(owner, method):
    try:
        return getattr(owner, method)() or {}
    except Exception:
        return {}


def snapshot(pm):
    """Only actual hardware enumeration and successful calibration prove state."""
    import obs_server

    openfp = getattr(pm, "pressure_source", "wbb") == "openfp"
    dual = openfp or getattr(pm, "board_mode", "single") == "dual"
    demo = bool(getattr(pm, "is_simulator", False))
    backend = getattr(pm, "backend", None)
    connected = bool(backend and getattr(backend, "is_open", False))
    frame = getattr(pm, "latest_frame", None) or {}
    timestamp = _number(frame.get("timestamp"))
    streaming = (
        connected and timestamp is not None and 0 <= time.monotonic() - timestamp <= 1.5
    )
    if openfp and not streaming:
        reading = getattr(backend, "last_dual_reading", None)
        timestamp = _number(getattr(reading, "timestamp", None))
        streaming = (
            connected
            and timestamp is not None
            and 0 <= time.monotonic() - timestamp <= 1.5
        )
    try:
        devices = (
            [obs_server.board_id_to_text(p) for p in pm.enumerate_boards()]
            if pm and not openfp
            else []
        )
    except Exception:
        devices = []
    left = obs_server.board_id_to_text(getattr(pm, "assigned_left", ""))
    right = obs_server.board_id_to_text(getattr(pm, "assigned_right", ""))
    assignment = _status(getattr(pm, "assignment_wizard", None), "get_status")
    alignment = _status(pm, "get_alignment_status")
    stance = _status(pm, "get_stance_width_status")
    paired = connected if openfp else len(devices) >= (2 if dual else 1)
    assigned = (
        not dual
        or openfp
        or bool(
            left and right and left != right and left in devices and right in devices
        )
    )
    aligned = (
        not alignment.get("active")
        and str(alignment.get("message", "")).startswith("✓")
        and alignment.get("configuration_matches", True)
    )
    measured = (
        stance.get("state") == "done"
        and (_number(stance.get("stance_width_mm")) or 0) > 0
        and stance.get("configuration_matches", True)
    )
    # Saved/default width and unit multipliers do not prove a calibration ran.
    ready = paired and assigned and aligned and measured and streaming and not demo
    return dict(
        openfp=openfp,
        dual=dual,
        demo=demo,
        backend=backend,
        connected=connected,
        streaming=streaming,
        frame=frame if streaming else {},
        devices=devices,
        left=left,
        right=right,
        assignment=assignment,
        alignment=alignment,
        stance=stance,
        paired=paired and not demo,
        assigned=assigned,
        aligned=aligned,
        measured=measured,
        ready=ready,
    )


def _button(c, rect, label, active=False, primary=False, enabled=True, size=12):
    panel(
        c,
        *rect,
        fill=T.TEAL_LINE
        if primary and enabled
        else T.ACTIVE_BG
        if active
        else T.SURFACE,
        outline=T.TEAL_LINE if active or primary else T.HAIRLINE,
        r=9,
    )
    text(
        c,
        (rect[0] + rect[2]) / 2,
        (rect[1] + rect[3]) / 2,
        label,
        size,
        T.PAGE_BG if primary and enabled else T.TEXT if enabled else T.TEXT_3,
        bold=enabled,
        anchor="center",
    )


def _clear_hits(app):
    for name in (
        "mode_1",
        "mode_2",
        "pair",
        "pin_copy",
        "bt_settings",
        "wizard",
        "step_a",
        "step_b",
        "guided",
        "align",
        "stance",
        "tare",
        "openfp_url",
        "openfp_dash",
        "log_folder",
        "aim_measure",
        "aim_reset",
    ):
        setattr(app, f"setup_{name}_rect", None)
    for name in (
        "pressure_source",
        "assign_left",
        "assign_right",
        "source_btn",
        "aim_nudge",
    ):
        setattr(app, f"setup_{name}_rects", [])
    app.board_workspace_rects = {}
    app.setup_device_paths = []
    for name in ("cancel", "skip", "done", "back"):
        setattr(app, f"board_modal_{name}_rect", None)


def _draw_stages(c, rect, state, current):
    x0, y0, x1, y1 = rect
    panel(c, *rect, r=12)
    stride = (x1 - x0 - 28) / 5
    complete = {
        "pair": state["paired"],
        "assign": state["assigned"] and state["paired"],
        "align": state["aligned"],
        "width": state["measured"],
        "ready": state["ready"],
    }
    for i, (key, label) in enumerate(STAGES):
        left, cy = x0 + 14 + i * stride, (y0 + y1) / 2
        active = current == key
        if active:
            panel(
                c,
                left + 4,
                cy - 21,
                left + stride - 18,
                cy + 21,
                fill=T.ACTIVE_BG,
                outline=T.TEAL_LINE,
                r=18,
            )
        cx = left + 25
        c.create_oval(
            cx - 15,
            cy - 15,
            cx + 15,
            cy + 15,
            fill=T.TEAL_LINE if active or complete[key] else T.SURFACE,
            outline=T.TEAL_LINE if active or complete[key] else T.TEXT_2,
            width=2,
        )
        text(
            c,
            cx,
            cy,
            "✓" if complete[key] else str(i + 1),
            13,
            T.PAGE_BG if active or complete[key] else T.TEXT_2,
            True,
            anchor="center",
        )
        text(c, left + 49, cy, label, 13, T.TEXT if active else T.TEXT_2, active)
        if i < 4:
            c.create_line(
                left + stride - 14, cy, left + stride + 3, cy, fill=T.GUIDE, width=2
            )


def _draw_board(c, rect, label, load, role):
    x0, y0, x1, y1 = rect
    cx = (x0 + x1) / 2
    text(c, cx, y0 - 23, label, 18, bold=True, anchor="center")
    # A physical-board silhouette, never an anatomical pressure map.
    c.create_polygon(
        x0 + 24,
        y0,
        x1 - 24,
        y0,
        x1 - 16,
        y0 + 4,
        x1 - 12,
        y0 + 18,
        x1,
        y1 - 18,
        x1 - 4,
        y1,
        x1 - 18,
        y1 + 2,
        x0 + 18,
        y1 + 2,
        x0 + 4,
        y1,
        x0,
        y1 - 18,
        x0 + 12,
        y0 + 18,
        x0 + 16,
        y0 + 4,
        fill=T.SURFACE,
        outline=T.TEAL_SOFT,
        width=2,
        smooth=True,
        splinesteps=20,
    )
    for x, y in (
        (x0 + 20, y0 + 15),
        (x1 - 20, y0 + 15),
        (x0 + 12, y1 - 16),
        (x1 - 12, y1 - 16),
    ):
        c.create_oval(x - 2, y - 2, x + 2, y + 2, fill=T.PAGE_BG, outline=T.TEXT_2)
    text(
        c,
        cx,
        (y0 + y1) / 2 - 10,
        f"{load:.1f}" if load is not None else "—",
        29,
        T.TEXT if load is not None else T.TEXT_3,
        True,
        anchor="center",
    )
    text(
        c,
        cx,
        (y0 + y1) / 2 + 26,
        "kg · live load" if load is not None else "No live load",
        10,
        T.TEXT_2,
        anchor="center",
    )
    text(
        c,
        cx,
        y1 - 30,
        role,
        10,
        T.TEAL_TEXT if role in ("LEFT", "RIGHT") else T.TEXT_3,
        anchor="center",
    )


def _pin_details(app):
    try:
        from src.hardware.pressure.bluetooth_windows import (
            get_host_bluetooth_mac,
            mac_to_wii_pin,
            mac_to_wii_pin_display,
            pin_is_typeable,
        )

        mac = get_host_bluetooth_mac() or ""
        app.setup_pin_text = mac_to_wii_pin(mac) if mac else ""
        if mac:
            return mac_to_wii_pin_display(mac), (
                "Plain ASCII — can be pasted into Windows"
                if pin_is_typeable(mac)
                else "Windows cannot accept these bytes — use Pair Board"
            )
    except Exception:
        pass
    app.setup_pin_text = ""
    return (
        "PIN unavailable",
        "Pair through your operating system if native pairing is unavailable.",
    )


def draw(app, avail_w, h, offset_x=0, guided=False):
    import obs_server

    pm = getattr(obs_server, "pressure_manager", None)
    state = snapshot(pm)
    if guided and getattr(app, "setup_flow_skipped", []):
        state["ready"] = False
    c = app.canvas
    _clear_hits(app)
    app.concept_setup_actions = {}
    app.setup_device_paths = state["devices"]
    x0, x1 = offset_x + 20, offset_x + avail_w - 24
    c.create_rectangle(offset_x, 52, offset_x + avail_w, h, fill=T.PAGE_BG, outline="")
    done = guided and bool(getattr(app, "setup_flow_done", False))
    step = app._flow_step() if guided and not done else None
    error = (getattr(app, "setup_flow_error", "") or "") if guided else ""
    current = step or (
        "pair"
        if not state["paired"]
        else "assign"
        if state["dual"] and not state["assigned"]
        else "align"
        if not state["aligned"]
        else "width"
        if not state["measured"]
        else "ready"
    )

    # Honest replacement for the concept's proposed remote-link control.
    panel(c, x0, 52, x1, 94, r=11)
    for i, (key, label) in enumerate(
        (("wbb", "Wii Boards · Local"), ("openfp", "Open-FP · LAN / beta"))
    ):
        rect = (x0 + 12 + i * 208, 59, x0 + 210 + i * 208, 87)
        active = state["openfp"] == (key == "openfp")
        _button(c, rect, label, active=active, enabled=not guided, size=11)
        if not guided:
            app.setup_pressure_source_rects.append((*rect, key))
    text(
        c,
        x1 - 190,
        73,
        "DEMO / SIMULATED" if state["demo"] else "Local hardware only",
        10,
        T.GOLD if state["demo"] else T.TEXT_2,
        anchor="e",
    )
    if not guided:
        rect = (x1 - 174, 59, x1 - 12, 87)
        _button(c, rect, "Back to setup", size=10)
        app.concept_setup_actions["overview"] = rect
    _draw_stages(c, (x0, 110, x1, 168), state, current)

    top, bottom = 184, h - 282
    split = x0 + (x1 - x0) * 0.56
    panel(c, x0, top, x1, bottom, r=14)
    c.create_line(split, top + 24, split, bottom - 24, fill=T.GUIDE)
    text(c, x0 + 24, top + 32, "PLATES" if state["openfp"] else "MODE", 12, bold=True)
    modes = (
        ("single", "Single board"),
        ("dual", "Two boards"),
        ("openfp", "Open-FP (beta)"),
    )
    mw = (split - x0 - 130) / 3
    for i, (key, label) in enumerate(modes):
        rect = (
            x0 + 102 + i * (mw + 5),
            top + 15,
            x0 + 102 + i * (mw + 5) + mw,
            top + 49,
        )
        active = (
            state["openfp"]
            if key == "openfp"
            else not state["openfp"] and state["dual"] == (key == "dual")
        )
        _button(
            c,
            rect,
            label,
            active=active,
            enabled=not guided,
            size=10,
        )
        if not guided:
            if key == "openfp":
                app.setup_pressure_source_rects.append((*rect, key))
            elif state["openfp"]:
                app.board_workspace_rects["switch_wbb_" + key] = rect
            else:
                setattr(app, f"setup_mode_{1 if key == 'single' else 2}_rect", rect)
    count = 2 if state["dual"] else 1
    bw = min(194, (split - x0 - 110) / count)
    gap = 54
    left = x0 + (split - x0 - count * bw - (count - 1) * gap) / 2
    board_top, board_bottom = top + 103, bottom - 72
    wizard = getattr(pm, "assignment_wizard", None)
    page = max(
        0,
        min(
            getattr(app, "board_device_page", 0),
            max(0, (len(state["devices"]) - 1) // count),
        ),
    )
    for i in range(count):
        bx = left + i * (bw + gap)
        idx = page * count + i
        device = state["devices"][idx] if idx < len(state["devices"]) else None
        load, role = None, "Not detected" if not device else "Unassigned"
        if count == 1 and state["streaming"]:
            load = _number(state["frame"].get("total_kg"))
        if state["openfp"]:
            role = "LEFT" if i == 0 else "RIGHT"
            reading = (
                getattr(state["backend"], "last_dual_reading", None)
                if state["connected"]
                else None
            )
            if reading and 0 <= time.monotonic() - reading.timestamp < 1:
                load = _number(
                    getattr(reading.left if i == 0 else reading.right, "total", None)
                )
        else:
            if device and device == state["left"]:
                role = "LEFT"
            elif device and device == state["right"]:
                role = "RIGHT"
            if step == "assign" and state["assignment"].get("phase") in (
                "waiting_left",
                "waiting_right",
                "complete",
            ):
                # Wizard status is keyed to its own board handles, not scan order.
                wizard_device = getattr(
                    wizard, "board_a" if i == 0 else "board_b", None
                )
                if wizard_device is not None:
                    weight_key = "board_a_weight" if i == 0 else "board_b_weight"
                    load = (_number(state["assignment"].get(weight_key))
                            if state["assignment"].get(weight_key + "_valid", True)
                            else None)
                    role = (
                        "LEFT"
                        if wizard_device == getattr(wizard, "left_board", None)
                        else "RIGHT"
                        if wizard_device == getattr(wizard, "right_board", None)
                        else "Assigning"
                    )
        label = (
            ("Left plate" if i == 0 else "Right plate")
            if state["openfp"]
            else (f"Board {chr(65 + idx)}" if count == 2 else "Balance board")
        )
        _draw_board(c, (bx, board_top, bx + bw, board_bottom), label, load, role)
        if count == 2 and not state["openfp"]:
            for j, (side, label) in enumerate(
                (("left", "Set left"), ("right", "Set right"))
            ):
                rect = (
                    bx + j * (bw / 2 + 3),
                    board_bottom + 13,
                    bx + (j + 1) * bw / 2 + j * 3 - 3,
                    board_bottom + 44,
                )
                enabled = bool(device) and not guided
                _button(c, rect, label, enabled=enabled, size=10)
                if enabled:
                    getattr(app, f"setup_assign_{side}_rects").append((rect, device))
        else:
            text(
                c,
                bx + bw / 2,
                board_bottom + 27,
                "Sides reported by device"
                if state["openfp"]
                else "Single-board layout",
                10,
                T.TEXT_2,
                anchor="center",
            )
    if len(state["devices"]) > count and not guided:
        rect = (x0 + 18, bottom - 25, split - 18, bottom - 5)
        _button(
            c,
            rect,
            f"Detected boards {page * count + 1}–{min(len(state['devices']), (page + 1) * count)} of {len(state['devices'])} · Next",
            size=9,
        )
        app.board_workspace_rects["devices"] = rect

    rx, rw = split + 30, x1 - split - 58
    phase = state["assignment"].get("phase")
    if done:
        heading, note = (
            "Setup flow finished",
            "You can step off the boards. Skipped steps are not calibrated.",
        )
    elif error:
        heading, note = "Setup needs attention", error
    elif step == "assign" and state["assignment"].get("health_message"):
        heading = ("Board readings need attention"
                   if state["assignment"].get("health_state") == "error"
                   else "Checking live board readings")
        note = state["assignment"]["health_message"]
    elif step == "assign":
        heading, note = {
            "waiting_left": (
                "Step onto your left board",
                "Keep your left foot on one board until it is assigned.",
            ),
            "waiting_right": (
                "Now step onto your right board",
                "Keep both feet down. The other board will be your right.",
            ),
            "complete": (
                "Both boards assigned",
                "The guided flow will continue to 50/50 stance.",
            ),
        }.get(
            phase,
            (
                "Assign your boards",
                state["assignment"].get("message") or "Waiting for board assignment.",
            ),
        )
    elif step == "align":
        heading, note = (
            "Stand in your address position",
            state["alignment"].get("message") or "Take your stance and hold still.",
        )
    elif step == "width":
        heading, note = (
            "Measure stance width",
            state["stance"].get("instruction") or "Shift your weight left, then right.",
        )
    elif not state["paired"] and not state["demo"]:
        heading, note = (
            (
                "Connect your Open-FP plates.",
                "Check the plate address and local network connection. Live data is required before calibration.",
            )
            if state["openfp"]
            else (
                "Pair your balance boards.",
                "Connect the boards to this computer first. Pair Board opens guided pairing; Scan checks boards already paired by your operating system.",
            )
        )
    elif state["ready"]:
        heading, note = (
            "Ready for practice",
            "Assignment, 50/50 calibration and stance-width measurement are complete for the connected boards.",
        )
    elif state["dual"] and not state["openfp"]:
        heading, note = (
            "Step onto your left board,\nthen your right.",
            "Assign which board is left and right for this session. Stand normally and step onto each board in turn.",
        )
    else:
        heading, note = (
            "Find your balanced stance.",
            "Stand at address for 50/50 calibration, then shift your weight to measure your natural stance width.",
        )
    text(
        c,
        rx,
        top + 29,
        heading,
        24,
        T.GOLD if error else T.TEXT,
        True,
        anchor="nw",
        width=rw,
    )
    text(c, rx, top + 135, note, 12, T.TEXT_2, anchor="nw", width=rw)
    status_y = bottom - 151
    panel(
        c,
        rx,
        status_y,
        x1 - 28,
        status_y + 51,
        fill=T.SECTION_BG,
        outline=T.TEAL_SOFT,
        r=10,
    )
    if state["demo"]:
        status = "Demo / simulated · not connected hardware"
    elif state["openfp"]:
        status = (
            "streaming"
            if state["streaming"]
            else "Connected · waiting for live data"
            if state["connected"]
            else "searching…"
        )
    else:
        n = len(state["devices"])
        status = (
            f"{n} board{'s' if n != 1 else ''} detected"
            if n
            else "No balance board detected"
        )
    if step == "align" and state["alignment"].get("active"):
        remaining = _number(state["alignment"].get("remaining_sec"))
        status = (
            f"{remaining:.1f}s remaining"
            if remaining is not None
            else "Calibration running"
        )
    elif (step == "width" or done) and state["measured"]:
        status = f"Measured stance width: {state['stance']['stance_width_mm']:.0f} mm"
    text(
        c,
        rx + 18,
        status_y + 25,
        status,
        12,
        T.TEAL_TEXT if state["paired"] else T.TEXT_2,
        True,
        width=rw - 36,
    )
    if guided:
        by = bottom - 77
        if done:
            app.board_modal_done_rect = (rx, by, x1 - 28, by + 47)
            _button(c, app.board_modal_done_rect, "Done", primary=True)
        else:
            labels = [("back", "Back"), ("cancel", "Cancel"), ("skip", "Skip step")]
            aw = (rw - 16) / 3
            for i, (key, label) in enumerate(labels):
                rect = (rx + i * (aw + 8), by, rx + i * (aw + 8) + aw, by + 47)
                enabled = key != "back" or getattr(app, "setup_flow_index", 0) > 0
                _button(c, rect, label, enabled=enabled, size=11)
                if enabled:
                    setattr(app, f"board_modal_{key}_rect", rect)
    else:
        rect = (rx, bottom - 77, x1 - 28, bottom - 30)
        needs_pair = not state["paired"] and not state["demo"]
        label = (
            ("Change plate address  →" if state["openfp"] else "Pair Board  →")
            if needs_pair
            else (
                "Start step-on wizard  →"
                if state["dual"] and not state["openfp"]
                else "Start guided calibration  →"
            )
        )
        _button(c, rect, label, primary=True, size=15)
        if needs_pair:
            app.board_workspace_rects[
                "primary_address" if state["openfp"] else "primary_pair"
            ] = rect
        else:
            app.setup_guided_rect = rect
            app.setup_wizard_rect = (
                rect if state["dual"] and not state["openfp"] else None
            )

    lower, end = bottom + 16, h - 20
    lower_split = x0 + (x1 - x0) * 0.35
    panel(c, x0, lower, lower_split - 10, end, r=13)
    panel(c, lower_split + 10, lower, x1, end, r=13)
    _draw_pair_panel(app, state, x0, lower, lower_split - 10, end, guided)
    nx, nw = lower_split + 30, x1 - lower_split - 50
    text(c, nx, lower + 28, "Next steps", 20, bold=True)
    text(
        c,
        x1 - 20,
        lower + 28,
        "Ready" if state["ready"] else "Not yet calibrated",
        11,
        T.TEAL_TEXT if state["ready"] else T.GOLD,
        anchor="e",
    )
    cards = (
        ("align", "50/50 stance", "Balance both boards"),
        ("stance", "Measure stance width", "Find your natural width"),
        ("tare", "Tare zero", "Step off to set a zero"),
    )
    cw = (nw - 28) / 3
    for i, (key, label, sub) in enumerate(cards):
        xx, yy = nx + i * (cw + 14), lower + 59
        rect = (xx, yy, xx + cw, yy + 99)
        _button(c, rect, "", enabled=not guided)
        _step_icon(c, key, xx + cw / 2, yy + 22)
        text(
            c,
            xx + cw / 2,
            yy + 51,
            label,
            11,
            T.TEXT if not guided else T.TEXT_3,
            True,
            anchor="center",
        )
        text(c, xx + cw / 2, yy + 77, sub, 9, T.TEXT_2, anchor="center")
        if not guided:
            setattr(app, f"setup_{key}_rect", rect)
    panel(
        c,
        nx,
        lower + 174,
        x1 - 20,
        end - 16,
        fill=T.SECTION_BG,
        outline=T.TEAL_LINE if state["ready"] else T.GOLD,
        r=10,
    )
    message = (
        "Ready for practice · Calibration verified in this session."
        if state["ready"]
        else "Demo data only · Calibration does not verify physical boards."
        if state["demo"]
        else "Skipped: "
        + ", ".join(getattr(app, "setup_flow_skipped", []))
        + ". Review before practice."
        if done and getattr(app, "setup_flow_skipped", [])
        else "Not yet calibrated · Complete the steps above to calibrate."
    )
    text(
        c,
        nx + 15,
        (lower + 174 + end - 16) / 2,
        message,
        10,
        T.TEAL_TEXT if state["ready"] else T.GOLD,
        width=nw - 30,
    )


def _step_icon(c, key, cx, cy):
    """Small vector instrument marks; avoid platform-dependent emoji tiles."""
    if key == "align":
        c.create_line(cx, cy - 12, cx, cy + 12, fill=T.TEXT_2, width=2)
        c.create_line(cx - 18, cy - 7, cx + 18, cy - 7, fill=T.TEXT_2, width=2)
        c.create_line(cx - 9, cy + 12, cx + 9, cy + 12, fill=T.TEXT_2, width=2)
        for dx in (-13, 13):
            c.create_polygon(
                cx + dx,
                cy - 7,
                cx + dx - 6,
                cy + 4,
                cx + dx + 6,
                cy + 4,
                fill="",
                outline=T.TEXT_2,
                width=2,
            )
    elif key == "stance":
        c.create_line(cx - 19, cy, cx + 19, cy, fill=T.TEXT_2, width=2)
        for sign in (-1, 1):
            c.create_line(
                cx + sign * 12,
                cy - 6,
                cx + sign * 19,
                cy,
                cx + sign * 12,
                cy + 6,
                fill=T.TEXT_2,
                width=2,
            )
    else:
        c.create_oval(cx - 10, cy - 10, cx + 10, cy + 10, outline=T.TEXT_2, width=2)
        c.create_line(cx - 16, cy, cx + 16, cy, fill=T.TEXT_2, width=2)
        c.create_line(cx, cy - 16, cx, cy + 16, fill=T.TEXT_2, width=2)


def _draw_pair_panel(app, state, x0, y0, x1, y1, guided):
    c = app.canvas
    text(
        c,
        x0 + 20,
        y0 + 28,
        "Open-FP plates" if state["openfp"] else "Pair boards (local)",
        20,
        bold=True,
    )
    text(
        c,
        x0 + 20,
        y0 + 61,
        "FORCE PLATES" if state["openfp"] else "BALANCE BOARDS",
        9,
        T.TEXT_2,
    )
    if state["openfp"]:
        import obs_server

        pm = getattr(obs_server, "pressure_manager", None)
        text(
            c,
            x0 + 20,
            y0 + 85,
            getattr(pm, "openfp_url", None) or "open-fp.local:7000",
            11,
            width=x1 - x0 - 40,
        )
        buttons = (("openfp_url", "Change address"), ("openfp_dash", "Open dashboard"))
        note = "Calibrate the plates in the Open-FP dashboard first. Experimental hardware."
    else:
        buttons = (("pair", "Pair Board"), ("scan", "Scan"))
        pin, note = _pin_details(app)
        text(c, x0 + 20, y0 + 152, pin, 10, T.TEAL_TEXT)
        if app.setup_pin_text:
            rect = (x1 - 103, y0 + 137, x1 - 20, y0 + 164)
            _button(c, rect, "Copy PIN", enabled=not guided, size=9)
            if not guided:
                app.setup_pin_copy_rect = rect
    bw = (x1 - x0 - 48) / 2
    for i, (key, label) in enumerate(buttons):
        rect = (x0 + 20 + i * (bw + 8), y0 + 99, x0 + 20 + i * (bw + 8) + bw, y0 + 133)
        _button(c, rect, label, enabled=not guided, size=11)
        if not guided:
            if key == "scan":
                app.board_workspace_rects[key] = rect
            else:
                setattr(app, f"setup_{key}_rect", rect)
    text(
        c,
        x0 + 20,
        y0 + 174 if not state["openfp"] else y0 + 153,
        note,
        9,
        T.TEXT_2,
        anchor="nw",
        width=x1 - x0 - 40,
    )
    if not state["openfp"]:
        rect = (x0 + 20, y1 - 40, x1 - 20, y1 - 13)
        _button(c, rect, "Bluetooth settings", enabled=not guided, size=9)
        if not guided:
            app.setup_bt_settings_rect = rect


def handle_click(app, x, y):
    """Only supplemental actions; existing device callbacks remain authoritative."""
    import obs_server

    pm = getattr(obs_server, "pressure_manager", None)
    for action, rect in getattr(app, "board_workspace_rects", {}).items():
        if not (rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]):
            continue
        if action in ("switch_wbb_single", "switch_wbb_dual"):
            # These are explicit source + mode choices, not paint-time changes.
            # Activate the saved Wii calibration before choosing its board mode.
            if pm:
                try:
                    pm.set_pressure_source("wbb")
                    pm.set_board_mode("single" if action.endswith("single") else "dual")
                    app.copy_feedback = "Pressure source: Wii Balance Boards"
                except Exception as exc:
                    app.copy_feedback = f"Could not switch source: {exc}"
                app.root.after(2000, app.clear_copy_feedback)
            app.draw_screen()
            return True
        if action == "primary_pair":
            app.start_pairing_flow()
            return True
        if action == "primary_address":
            # Reuse the production address handler, with the same validation.
            from types import SimpleNamespace

            import shanktuary_performance_studio as production

            rect = app.setup_openfp_url_rect
            if rect:
                production.ShanktuaryApp.handle_mouse_press(
                    app,
                    SimpleNamespace(
                        x=(rect[0] + rect[2]) / 2, y=(rect[1] + rect[3]) / 2
                    ),
                )
            return True
        if action == "scan":
            try:
                devices = pm.enumerate_boards(max_age_sec=0) if pm else []
                app.copy_feedback = f"{len(devices)} paired board(s) detected. Pair new boards through Bluetooth first."
            except Exception as exc:
                app.copy_feedback = f"Board scan failed: {exc}"
            app.root.after(4000, app.clear_copy_feedback)
        elif action == "devices":
            state = snapshot(pm)
            count = 2 if state["dual"] else 1
            pages = max(1, math.ceil(len(state["devices"]) / count))
            app.board_device_page = (getattr(app, "board_device_page", 0) + 1) % pages
        app.draw_screen()
        return True
    return False


def previous_step(app):
    """Back stops the active sampler before restarting the previous step."""
    import obs_server

    index = getattr(app, "setup_flow_index", 0)
    if index <= 0 or getattr(app, "setup_flow_done", False):
        return
    pm = getattr(obs_server, "pressure_manager", None)
    step = app._flow_step()
    method = {
        "assign": "reset_assignment_wizard",
        "align": "cancel_stance_alignment",
        "width": "cancel_stance_width_calibration",
    }.get(step)
    if pm and method and hasattr(pm, method):
        getattr(pm, method)()
    app.setup_flow_index = index - 1
    skipped = getattr(app, "setup_flow_skipped", [])
    if app._flow_step() in skipped:
        skipped.remove(app._flow_step())
    app._enter_setup_flow_step()
    app.draw_screen()
