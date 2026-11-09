"""Ephemeral Lab-only preview. Never touches hardware, capture, or shot storage."""
import math
import time

from src.hardware.pressure import SensorReading
from src.processing.pressure import CoPCalculator, ShotSynchronizedPressureBuffer


def demo_frame(seconds):
    """Deterministic illustrative four-zone load, explicitly synthetic."""
    phase = seconds % 4.0
    angle = phase * math.tau / 4.0
    left = 0.5 - 0.30 * math.sin(angle)
    front = 0.52 + 0.12 * math.cos(angle)
    force = 1.0 + 0.35 * math.exp(-((phase - 2.7) / 0.35) ** 2)
    total = 80 * force
    sample = CoPCalculator().compute(SensorReading(
        total * left * front, total * (1-left) * front,
        total * left * (1-front), total * (1-left) * (1-front),
        timestamp=seconds,
    ))
    sample.force_bw = force
    label = ("Address" if phase < .6 else "Backswing" if phase < 1.8
             else "Downswing" if phase < 2.6 else "Impact" if phase < 2.9
             else "Finish")
    frame = ShotSynchronizedPressureBuffer().push(sample, phase=label)
    frame["simulated"] = True
    frame["torque_nm"] = None  # No torsional measurement in this illustration.
    return frame


def active(app):
    running = getattr(app, "lab_demo_running", False)
    if running and (getattr(app, "view_mode", 8) != 8 or
                    app.current_shot is not app.lab_demo_selected_shot):
        stop(app)
        return False
    return running


def stop(app):
    app.lab_demo_running = False
    timer = getattr(app, "lab_demo_timer", None)
    if timer is not None:
        app.root.after_cancel(timer)
    app.lab_demo_timer = None
    app.lab_demo_frames = []


def toggle(app):
    if active(app):
        stop(app)
        app.draw_screen()
        return False
    app.lab_demo_running = True
    app.lab_demo_selected_shot = app.current_shot
    app.lab_demo_started = time.monotonic()
    app.lab_demo_frames = []
    tick(app)
    return True


def tick(app):
    app.lab_demo_timer = None
    if not active(app):
        return
    elapsed = time.monotonic() - app.lab_demo_started
    # Seed a short visible trace immediately, then animate a rolling window.
    app.lab_demo_frames = [demo_frame(max(0, elapsed + 4 - i * .05))
                           for i in reversed(range(81))]
    app.draw_screen()
    app.lab_demo_timer = app.root.after(100, lambda: tick(app))
