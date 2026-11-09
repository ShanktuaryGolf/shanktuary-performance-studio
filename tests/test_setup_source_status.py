"""Connections retains source selection and actual link status before a shot.

Board setup is now its own workspace. These assertions exercise the shipped
Connections page and real connection wizard/controller, rather than the
removed legacy shot-source card inside board details.
"""
import queue
from types import SimpleNamespace

import pytest

tk = pytest.importorskip('tkinter')


@pytest.fixture
def app(tmp_path, monkeypatch):
    import shanktuary_performance_studio as studio
    from src.connections.controller import SourceConnections
    from src.ui import ShanktuaryDesktopApp

    monkeypatch.setenv('SPS_SHOT_SOURCE_FILE', str(tmp_path/'source.json'))
    monkeypatch.setenv('SPS_SKIP_SPLASH', '1')
    monkeypatch.setenv('SPS_UI_PREVIEW', '1')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    monkeypatch.delenv('SPS_SHOT_SOURCE', raising=False)
    # The settings cache is process-wide, not keyed by SPS_SHOT_SOURCE_FILE.
    # A new temp path alone leaves the previous parametrization's source live.
    # Restore the caller's cache on teardown while starting this test empty.
    monkeypatch.setattr(studio.gspro_settings, '_cache', None)
    assert studio.gspro_settings.load_settings(refresh=True)['source'] == 'nova'
    assert not (tmp_path/'source.json').exists()
    monkeypatch.setattr(studio, 'SESSION_LOG_PATH', str(tmp_path/'history.json'))
    monkeypatch.setattr(studio, 'source_connections', SourceConnections(queue.Queue()))
    monkeypatch.setattr(studio, 'nova_status', {'connected': False, 'host': ''})
    monkeypatch.setattr(studio, 'gspro_status', {'connected': False})
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip('graphical display required')
    root.geometry('1600x1000')
    application = ShanktuaryDesktopApp(root)
    root.update()
    application.set_mode(10)
    assert getattr(application, 'concept_setup_page', 'overview') == 'overview'
    yield root, application, studio
    studio.source_connections.stop()
    root.destroy()


def _texts(app):
    return [app.canvas.itemcget(i, 'text') for i in app.canvas.find_all() if app.canvas.type(i) == 'text']


def _click(app, rect):
    app.handle_mouse_press(SimpleNamespace(x=(rect[0]+rect[2])/2, y=(rect[1]+rect[3])/2))


def _wizard_click(wizard, action, payload=None):
    targets = [r for r in wizard._hit_rects if r[4] == action and (payload is None or r[5] == payload)]
    assert targets, f'No {action}/{payload} control on {wizard.page}'
    x0, y0, x1, y1, _, _ = targets[-1]
    wizard._on_click(SimpleNamespace(x=(x0+x1)/2, y=(y0+y1)/2))


def test_setup_shows_connected_when_nova_link_is_up_but_no_shot_arrived(app):
    root, application, studio = app
    controller = studio.connection_setup_controller()
    controller.start('nova')
    studio.nova_status.update(connected=True, host='192.168.40.249:2920')
    application.nova_connected = False  # stale shot-arrival flag must not win
    application.draw_screen()
    root.update()
    texts = _texts(application)
    assert 'Connected. Hit a test shot.' in texts, texts
    assert not controller.snapshot()['shot_received']
    assert controller.snapshot()['state'] == 'connected'
    assert 'Connecting…' not in texts
    assert 'No shot source connected' not in texts
    assert 'Ready to play' not in texts


def test_setup_shows_offline_when_nova_link_is_down(app):
    root, application, studio = app
    controller = studio.connection_setup_controller()
    controller.start('nova')
    studio.nova_status.update(connected=False, last_message='Nova offline')
    application.draw_screen()
    root.update()
    assert 'Nova offline' in _texts(application)
    assert 'Connected. Hit a test shot.' not in _texts(application)
    assert controller.snapshot()['state'] != 'ready'


def test_setup_exposes_source_picker_and_preserves_both_choice(app, monkeypatch):
    root, application, studio = app
    from src.ui.connection_wizard import ConnectionWizard

    assert {'source_nova', 'source_gspro', 'source_open_connect', 'source_pureplay'} <= application.concept_setup_actions.keys()
    opened = []
    def inspect_picker(wizard):
        offered = {r[5] for r in wizard._hit_rects if r[4] == 'source'}
        assert {'nova', 'gspro', 'pureplay', 'open_connect'} <= offered
        if not wizard.advanced:
            _wizard_click(wizard, 'advanced')
        offered = {r[5] for r in wizard._hit_rects if r[4] == 'source'}
        assert {'both', 'cgp'} <= offered
        _wizard_click(wizard, 'source', 'both')
        assert wizard.source == 'both'
        assert studio.source_connections.snapshot()['source'] == 'both'
        assert studio.gspro_settings.effective_source() == 'nova', 'Selection alone must not start/persist a connection'
        opened.append(True)
        wizard._on_close()
    monkeypatch.setattr(ConnectionWizard, 'run', inspect_picker)
    _click(application, application.concept_setup_actions['source_configure'])
    assert opened == [True]


@pytest.mark.parametrize('source', ['gspro', 'both'])
def test_clicking_source_on_setup_persists_only_after_explicit_connect(app, monkeypatch, source):
    root, application, studio = app
    from src.ui.connection_wizard import ConnectionWizard

    completed = []
    def connect_picker(wizard):
        if source == 'both' and not wizard.advanced:
            _wizard_click(wizard, 'advanced')
        _wizard_click(wizard, 'source', source)
        _wizard_click(wizard, 'continue')
        assert studio.gspro_settings.effective_source() == 'nova'
        _wizard_click(wizard, 'connect')
        assert studio.gspro_settings.effective_source() == source
        assert studio.source_connections.active_for('gspro')
        assert studio.source_connections.active_for('nova') == (source == 'both')
        # A live GSPro link must be recognized even with Nova down in Both mode.
        studio.gspro_status.update(connected=True, db_found=True)
        assert wizard.controller.snapshot()['state'] == 'connected'
        assert not wizard.controller.snapshot()['shot_received']
        completed.append(True)
        wizard._on_close()
    monkeypatch.setattr(ConnectionWizard, 'run', connect_picker)
    _click(application, application.concept_setup_actions['source_gspro'])
    root.update()
    assert completed == [True]
    assert studio.gspro_settings.effective_source() == source
    assert 'GSPro' in _texts(application)


@pytest.mark.parametrize('scale', ['100%', '150%', '200%'])
def test_setup_uses_shipped_logos_in_source_order_inside_cards(app, scale):
    root, application, studio = app
    application.set_ui_scale(scale, persist=False)
    application.draw_screen()
    root.update()
    keys = ['source_nova', 'source_gspro', 'source_pureplay', 'source_open_connect']
    rects = [application.concept_setup_actions[key] for key in keys]
    assert [rect[0] for rect in rects] == sorted(rect[0] for rect in rects)
    canvas = application.canvas
    images = canvas.find_withtag('setup-source-logo')
    assert len(images) == 3
    # Native image bounds must include viewport translation and exactly one DPI scale.
    for item, rect in zip(images, rects):
        x0, y0, x1, y1 = tk.Canvas.bbox(canvas, item)
        factor = canvas.ui_scale
        assert rect[0] * factor <= x0 < x1 <= rect[2] * factor
        assert rect[1] * factor <= y0 < y1 <= rect[3] * factor
    assert {key[0] for key in canvas._setup_source_logos} == {'nova', 'gspro', 'pureplay'}
