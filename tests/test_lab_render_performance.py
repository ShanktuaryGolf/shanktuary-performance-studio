"""Deterministic display-work budgets; no hardware or wall-clock speed claims."""
from collections import OrderedDict
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_concept_ui import desktop as native_desktop  # noqa: F401
from test_lab_pressure_honesty import Canvas
from test_lab_trail_decay import frame, manager

import obs_server
from shanktuary_performance_studio import ShanktuaryApp
from src.ui import desktop, scaling
from src.ui.lab_pressure_view import (
    LIVE_HISTORY_MAX_SAMPLES,
    frame_delay_ms,
    live_timeline_samples,
    pressure_render_snapshot,
    render_live_frame,
    sync_live_history,
)


def test_deadline_includes_paint_and_never_catches_up_in_bursts():
    assert frame_delay_ms(10, now=10) == 34
    assert frame_delay_ms(10, now=10.025) == 9
    assert frame_delay_ms(10, now=10.2) == 8


def test_live_poll_has_one_owner_and_preserves_static_setup_cadence(monkeypatch):
    monkeypatch.setattr('time.monotonic', lambda: 100)
    monkeypatch.setattr(obs_server, 'pressure_manager', manager(frame()))
    app = SimpleNamespace(swing_lab_history=[], view_mode=8, show_board_assign_modal=False,
        root=SimpleNamespace(after=Mock()), draw_screen=Mock(), tick_setup_flow=Mock(),
        poll_pressure_stream=Mock())
    desktop.ShanktuaryDesktopApp.poll_pressure_stream(app)
    app.draw_screen.assert_called_once()
    assert app.root.after.call_args.args[0] == 34
    app.lab_demo_running = True
    app.draw_screen.reset_mock()
    desktop.ShanktuaryDesktopApp.poll_pressure_stream(app)
    app.draw_screen.assert_not_called()
    assert app.root.after.call_args.args[0] == 100
    app.view_mode = 10
    desktop.ShanktuaryDesktopApp.poll_pressure_stream(app)
    assert app.root.after.call_args.args[0] == 100


def test_one_health_snapshot_per_frame_and_no_stale_reuse(monkeypatch):
    monkeypatch.setattr('time.monotonic', lambda: 100)
    class Backend:
        is_open = True
        calls = 0
        def get_diagnostics(self):
            self.calls += 1
            return {'ready': True}
    pm = manager(frame())
    pm.backend = Backend()
    app = SimpleNamespace(swing_lab_history=[])
    with pressure_render_snapshot(app, pm):
        for _ in range(4):
            assert render_live_frame(app, pm, synchronize=True) is pm.latest_frame
        with pressure_render_snapshot(app, pm):
            assert render_live_frame(app, pm) is pm.latest_frame
    assert pm.backend.calls == 1
    pm.backend.is_open = False
    with pressure_render_snapshot(app, pm):
        assert render_live_frame(app, pm) is None
    assert app.swing_lab_history == []
    with pytest.raises(RuntimeError), pressure_render_snapshot(app, pm):
        raise RuntimeError('paint failed')
    assert not app._lab_render_snapshot_active and app._lab_render_snapshot is None


@pytest.mark.parametrize('hz', [10, 30, 60])
def test_faster_display_keeps_live_time_window_and_all_available_samples(hz):
    pm = manager()
    app = SimpleNamespace(swing_lab_history=[])
    for i in range(25 * hz + 1):
        stamp = 100 + i / hz
        pm.latest_frame = frame(stamp)
        sync_live_history(app, pm, stamp)
    assert len(app.swing_lab_history) <= LIVE_HISTORY_MAX_SAMPLES
    samples = live_timeline_samples(app.swing_lab_history, 125)
    assert samples[0]['timestamp'] == 113
    assert samples[-1]['timestamp'] == 125
    assert len(samples) == 12 * hz + 1


def test_text_width_cache_uses_exact_font_and_is_bounded(monkeypatch):
    calls = []
    def font(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(measure=lambda text: len(text) * 7)
    monkeypatch.setattr(desktop, 'logical_font', font)
    app = SimpleNamespace(root=object())
    measure = lambda text: desktop.ShanktuaryDesktopApp._text_width(app, text, ('Test', 12, 'bold'))
    for _ in range(100):
        assert measure('same label') == 70
    assert len(calls) == 1 and calls[0]['weight'] == 'bold'
    for i in range(600):
        measure(str(i))
    assert len(app._logical_text_widths) == 512


def test_scaled_image_cache_retains_frequently_used_static_assets(monkeypatch):
    uploads = []
    class Pixels:
        width, height = 10, 10
        def resize(self, size):
            return self
    monkeypatch.setattr(scaling.ImageTk, 'getimage', lambda source: Pixels())
    def photo(*args, **kwargs):
        result = object()
        uploads.append(result)
        return result
    monkeypatch.setattr(scaling.ImageTk, 'PhotoImage', photo)
    canvas = SimpleNamespace(ui_scale=1.5, _scaled_images=OrderedDict(), _frame_images=[])
    for i in range(200):
        static = scaling.ScaledCanvas._image(canvas, 'static-panel')
        if i == 0:
            original = static
        assert static is original
        scaling.ScaledCanvas._image(canvas, f'dynamic-foot-{i}')
        canvas._frame_images.clear()
    assert len(uploads) == 201 and len(canvas._scaled_images) == 96


def test_curve_batching_keeps_every_original_vertex(monkeypatch):
    monkeypatch.setattr('time.monotonic', lambda: 100)
    frames = [dict(frame(88.1+i/10), pct_left=i%100, pct_right=100-i%100,
                   force_bw=1+i/120) for i in range(120)]
    monkeypatch.setattr(obs_server, 'pressure_manager', manager(frames[-1]))
    app = ShanktuaryApp.__new__(ShanktuaryApp)
    app.canvas = Canvas()
    app.swing_lab_history = frames
    app.is_left_handed = False
    app.is_reviewing_past_shot = lambda: False
    app.pressure_display_trail = lambda: (frames, False)
    for series in ('transfer', 'force'):
        app.draw_force_timeline_canvas(0, 0, 400, 200, series=series)
    curves = [item for item in app.canvas.items if item[2].get('tags') == 'pressure-curve']
    assert len(curves) == 3
    assert all(len(coords) == 240 for _, coords, _ in curves)
    for _, coords, options in curves:
        assert list(coords[::2]) == pytest.approx([46 + i/119*338 for i in range(120)])
        assert options['width'] == 2 and options['smooth'] is False
    assert list(curves[0][1][1::2]) == pytest.approx([174 - (i%100)/100*152 for i in range(120)])


def test_string_sample_timestamps_keep_accepted_input_contract():
    app = SimpleNamespace(swing_lab_history=[])
    pm = manager(frame('100'))
    assert sync_live_history(app, pm, 100) is pm.latest_frame
    pm.latest_frame = frame('121')
    sync_live_history(app, pm, 121)
    assert app.swing_lab_history == [pm.latest_frame]


def test_device_sized_heatmap_skips_second_upload(monkeypatch):
    monkeypatch.setattr(scaling.ImageTk, 'getimage', lambda source: pytest.fail('No readback needed'))
    source = SimpleNamespace(_sps_device_scale=1.5)
    canvas = SimpleNamespace(ui_scale=1.5)
    assert scaling.ScaledCanvas._image(canvas, source) is source


def test_scaled_canvas_tag_delete_and_explicit_layering(native_desktop):
    app, root, errors = native_desktop
    c = app.canvas
    c.delete('all')
    with c.retained_frame('tag-delete'):
        old = c.create_text(30, 30, text='old', tags='discard')
    c.delete('discard')
    with c.retained_frame('tag-delete'):
        new = c.create_text(30, 30, text='new', tags='discard')
        cover = c.create_rectangle(20, 20, 40, 40, fill='red')
        c.tag_raise(new)
    assert old != new and c.type(new) == 'text'
    assert c.find_all() == (cover, new)
    with c.retained_frame('tag-delete'):
        new = c.create_text(30, 30, text='new', tags='discard')
        assert c.find_all() == (new,)
        cover = c.create_rectangle(20, 20, 40, 40, fill='red')
        c.tag_lower(cover)
    assert c.find_all() == (cover, new)
    assert not errors


@pytest.mark.parametrize('scale', ['100%', '150%'])
def test_retained_lab_matches_fresh_paint_across_data_and_tab_changes(native_desktop, monkeypatch, scale):
    import hashlib

    app, root, errors = native_desktop
    monkeypatch.setattr('time.monotonic', lambda: 100)
    pm = manager(frame())
    pm.is_simulator = True
    monkeypatch.setattr(obs_server, 'pressure_manager', pm)
    app.current_shot = None
    app.set_ui_scale(scale, persist=False)
    app.view_mode = 8
    c = app.canvas

    def signature():
        result = []
        for item in c.find_all():
            options = {key: value[-1] for key, value in c.itemconfigure(item).items()}
            image = options.get('image')
            if image:
                pixels = c.tk.call(image, 'data', '-format', 'png')
                options['image'] = hashlib.sha256(pixels).hexdigest()
            result.append((c.type(item), c.coords(item), options))
        return result

    for state in ('loaded', 'more-samples', 'stale', 'zero', 'new-source', 'disconnected'):
        if state == 'more-samples':
            app.swing_lab_history = [dict(frame(99+i/120), force_bw=1, pct_left=40, pct_right=60)
                                     for i in range(120)]
            pm.latest_frame = frame(100, x=30)
        elif state == 'stale':
            pm.latest_frame = frame(95)
        elif state == 'zero':
            pm.latest_frame = dict(frame(100, load=0), raw_cells=[0, 0, 0, 0])
        elif state == 'new-source':
            pm.backend = SimpleNamespace(is_open=True)
        elif state == 'disconnected':
            pm.backend.is_open = False
        app.draw_screen()
        retained = signature()
        with monkeypatch.context() as patch:
            patch.setattr(c, 'retained_frame', lambda key: nullcontext())
            app.draw_screen()
            fresh = signature()
        assert retained == fresh, state
        app.draw_screen()
        assert c._retained_lab.item_count == len(c.find_all())
    app.set_mode(12)
    assert c._retained_lab.item_count == 0
    app.set_mode(8)
    assert c._retained_lab.item_count == len(c.find_all())
    assert not errors


@pytest.mark.parametrize('scale', [1, 1.25, 1.5, 2])
def test_single_upload_preserves_original_scaled_raster_pixels(native_desktop, scale):
    from PIL import ImageTk

    from src.ui.foot_heatmap import _foot_pixels

    app, root, errors = native_desktop
    pixels = _foot_pixels(81, 129, True, 128, 27)
    original_photo = ImageTk.PhotoImage(pixels, master=app.canvas)
    old_path = ImageTk.getimage(original_photo)
    size = (round(81 * scale), round(129 * scale))
    if scale != 1:
        old_path = old_path.resize(size)
        pixels = pixels.resize(size)
    candidate_photo = ImageTk.PhotoImage(pixels, master=app.canvas)
    candidate = ImageTk.getimage(candidate_photo)
    assert candidate.size == old_path.size
    assert candidate.tobytes() == old_path.tobytes()
    assert not errors
