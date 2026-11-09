"""Output separation, migration and concurrent editor saves use isolated files."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

import obs_server


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(obs_server, 'CONFIG_DIR', tmp_path)
    monkeypatch.setattr(obs_server, 'LAYOUT_FILE', tmp_path / 'overlay_layout.json')
    state = obs_server.OBSState()
    state.broadcast = lambda message: None
    return state


@pytest.mark.parametrize('first', ['overlay', 'projection'])
def test_legacy_migration_and_reload(state, first):
    legacy = {'widgets': {'carry': {'x': 44, 'visible': False}}, 'unknown': {'keep': 17},
              'divot_calibration': {'scale': 2.2}, 'studio_presets': {'old': {'widgets': {}}}}
    obs_server.LAYOUT_FILE.write_text(json.dumps(legacy))
    assert state.load_layout('projection') == legacy
    assert not obs_server.LAYOUT_FILE.with_name('projection_layout.json').exists()
    draft = copy.deepcopy(legacy)
    draft['widgets']['carry']['x'] = 99
    assert state.save_layout(draft, first, legacy)
    other = 'projection' if first == 'overlay' else 'overlay'
    assert state.load_layout(other) == legacy
    reloaded = obs_server.OBSState()
    assert reloaded.load_layout(first) == draft
    assert reloaded.load_layout(other) == legacy
    # Legacy default API continues to address overlay only.
    assert reloaded.load_layout() == reloaded.load_layout('overlay')


def test_same_output_concurrent_unrelated_changes_are_merged(state):
    base = state.load_layout()
    first = copy.deepcopy(base)
    second = copy.deepcopy(base)
    first['widgets']['carry']['x'] = 117
    second['widgets']['carry']['rotation'] = 31
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(lambda draft: state.save_layout(draft, 'overlay', base), [first, second]))
    result = state.load_layout()
    assert result['widgets']['carry']['x'] == 117
    assert result['widgets']['carry']['rotation'] == 31
    assert state.load_layout('projection') == base


def test_invalid_output_and_corrupt_legacy_do_not_overwrite(state):
    with pytest.raises(ValueError):
        state.load_layout('invalid')
    obs_server.LAYOUT_FILE.write_text('broken original')
    assert not state.save_layout({'widgets': {}}, 'projection')
    assert obs_server.LAYOUT_FILE.read_text() == 'broken original'


def test_output_browser_routes_are_explicit():
    from pathlib import Path
    assets = Path(__file__).resolve().parents[1] / 'assets'
    editor = (assets / 'studio-editor.js').read_text()
    renderer = (assets / 'overlay.html').read_text()
    assert "const layoutUrl = '/api/layout?output=' + output" in editor
    assert "'X-Studio-Layout-Merge':'1'" in editor
    assert "msg.projection_layout || msg.layout" in renderer
    assert "(msg.output || 'overlay') !== output" in renderer
    assert 'existingControls.hidden = false' in (assets / 'studio-projection.js').read_text()


def test_http_scoped_save_and_legacy_default(state, monkeypatch):
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    monkeypatch.setattr(obs_server, 'obs_state', state)
    server = ThreadingHTTPServer(('127.0.0.1', 0), obs_server.OBSHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f'http://127.0.0.1:{server.server_port}/api/layout'

    def request(url, data=None):
        headers = {'Content-Type': 'application/json', 'X-Studio-Layout-Merge': '1'}
        req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=headers)
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    try:
        baseline = request(root)
        draft = copy.deepcopy(baseline)
        draft['widgets']['carry']['x'] = 314
        assert request(root + '?output=projection', {'base': baseline, 'draft': draft})['status'] == 'ok'
        assert request(root) == baseline
        assert request(root + '?output=projection') == draft
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
