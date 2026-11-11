"""Passive live-pressure presentation and short, time-based CoP trails."""
import math
import time
from contextlib import contextmanager, nullcontext

COP_TRAIL_SECONDS = 1.75
LIVE_MAX_AGE_SECONDS = 1.5
LAB_FRAME_SECONDS = 1 / 30
LIVE_HISTORY_SECONDS = 20.0
LIVE_TIMELINE_SECONDS = 12.0
LIVE_HISTORY_MAX_SAMPLES = 1200
_UNSET = object()


def frame_delay_ms(started, interval=LAB_FRAME_SECONDS, now=None):
    """Budget paint time inside the interval and leave Tk room for input."""
    now = time.monotonic() if now is None else now
    return max(8, math.ceil((started + interval - now) * 1000))


@contextmanager
def pressure_render_snapshot(app, manager, frame=_UNSET):
    """One passive, coherent sensor-health observation for every Lab panel."""
    if getattr(app, "_lab_render_snapshot_active", False):
        yield
        return
    if frame is _UNSET:
        frame = sync_live_history(app, manager)
    app._lab_render_snapshot_active = True
    app._lab_render_snapshot = frame
    try:
        yield
    finally:
        app._lab_render_snapshot_active = False
        app._lab_render_snapshot = None


def render_live_frame(app, manager, *, synchronize=False):
    if getattr(app, "_lab_render_snapshot_active", False):
        return app._lab_render_snapshot
    return sync_live_history(app, manager) if synchronize else current_live_frame(manager)


def live_timeline_samples(frames, reference_time):
    """Keep the former ~12-second live window at any UI cadence, with all samples."""
    result = []
    for frame in frames[-LIVE_HISTORY_MAX_SAMPLES:]:
        stamp = finite_number(frame.get("timestamp")) if isinstance(frame, dict) else None
        if stamp is not None and 0 <= reference_time - stamp <= LIVE_TIMELINE_SECONDS:
            result.append(frame)
    return result


def finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def current_live_frame(manager, now=None):
    """Return an observed usable frame, never a saved shot or an open handle alone."""
    if manager is None:
        return None
    now = time.monotonic() if now is None else now
    with getattr(manager, "lock", nullcontext()):
        backend = getattr(manager, "backend", None)
        if backend is None or not backend.is_open:
            return None
        frame = getattr(manager, "latest_frame", None)
        if not isinstance(frame, dict):
            return None
        stamp = finite_number(frame.get("timestamp"))
        if stamp is None or not 0 <= now - stamp <= LIVE_MAX_AGE_SECONDS:
            return None
        diagnostic = getattr(type(backend), "get_diagnostics", None)
        if diagnostic:
            try:
                state = diagnostic(backend)
                if (state.get("ready") is False or state.get("recovery_blocked")
                        or state.get("calibration_status") == "unavailable"):
                    return None
            except Exception:
                return None
        return frame


def source_key(manager):
    """Display-only ownership fingerprint; no device operations or persistence."""
    return (id(manager), id(getattr(manager, "backend", None)),
            getattr(manager, "pressure_source", None), getattr(manager, "board_mode", None),
            bool(getattr(manager, "is_simulator", False)),
            getattr(manager, "assigned_left", None), getattr(manager, "assigned_right", None),
            getattr(manager, "openfp_url", None))


def sync_live_history(app, manager, now=None):
    """Keep transient display history local to the current fresh source.

    Repeated samples do not extend history or their lifetime. Source changes
    reject a lingering old frame until a new one arrives. Stored shot traces
    are never modified.
    """
    key = source_key(manager)
    previous = getattr(app, "_lab_live_source_key", None)
    history = getattr(app, "swing_lab_history", None)
    if history is None:
        history = app.swing_lab_history = []
    frame = current_live_frame(manager, now)
    if previous is not None and previous != key:
        history.clear()
        last_frame = getattr(app, "_lab_last_live_frame", None)
        if last_frame is not None:
            app._lab_rejected_frame = last_frame
        app._lab_last_live_frame = None
        app._lab_last_live_stamp = None
    app._lab_live_source_key = key
    if frame is None or frame is getattr(app, "_lab_rejected_frame", None):
        history.clear()
        app._lab_last_live_stamp = None
        return None
    stamp = finite_number(frame.get("timestamp"))
    last_stamp = getattr(app, "_lab_last_live_stamp", None)
    if last_stamp is not None and stamp < last_stamp:
        history.clear()
    if frame is not getattr(app, "_lab_last_live_frame", None) and stamp != last_stamp:
        history.append(frame)
        # A faster painter must not shorten the force/transfer time window.
        first = 0
        while first < len(history):
            prior = finite_number(history[first].get("timestamp"))
            if prior is not None and stamp - prior <= LIVE_HISTORY_SECONDS:
                break
            first += 1
        del history[:first]
        del history[:-LIVE_HISTORY_MAX_SAMPLES]
    app._lab_last_live_frame = frame
    app._lab_last_live_stamp = stamp
    app._lab_rejected_frame = None
    return frame


def cop_trail_segments(frames, reference_time, *, stored=False):
    """Validated segment pairs plus fade strength, without altering input data."""
    segments, previous = [], None
    for frame in frames[-600:]:
        if not isinstance(frame, dict):
            previous = None
            continue
        x, y = finite_number(frame.get("cop_x")), finite_number(frame.get("cop_y"))
        load = finite_number(frame.get("total_kg"))
        stamp = finite_number(frame.get("timestamp"))
        if x is None or y is None or load is None or load < 1:
            previous = None
            continue
        age = 0 if stored else (reference_time - stamp if stamp is not None else None)
        if age is None or not 0 <= age <= COP_TRAIL_SECONDS:
            previous = None
            continue
        if previous is not None:
            prior_stamp = finite_number(previous.get("timestamp"))
            if stored or (prior_stamp is not None and 0 < stamp - prior_stamp <= .5):
                strength = 1.0 if stored else (1.0 - age / COP_TRAIL_SECONDS) ** 1.6
                segments.append((previous, frame, strength))
        previous = frame
    return segments


def fade_color(foreground, background, strength):
    strength = max(0.0, min(1.0, strength))
    fg = [int(foreground[i:i + 2], 16) for i in (1, 3, 5)]
    bg = [int(background[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(b + (f - b) * strength):02x}' for f, b in zip(fg, bg))
