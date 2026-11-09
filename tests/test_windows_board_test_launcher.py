"""Source-only launch guards; these tests do not claim Windows hardware proof."""
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def setup_module_object():
    spec = importlib.util.spec_from_file_location('board_setup', ROOT / 'windows_review_setup.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_windows_setup_uses_dedicated_environment(tmp_path):
    m = setup_module_object()
    (tmp_path / 'requirements-review.txt').write_text('Pillow==11.3.0\n')
    (tmp_path / '.venv-board-test').mkdir()
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs['env']['PYTHONNOUSERSITE'] == '1'
        assert Path(kwargs['env']['TMP']).is_relative_to(tmp_path)

    with patch.object(m, 'ROOT', tmp_path), patch.object(m.sys, 'platform', 'win32'), \
         patch.object(m.sys, 'version_info', (3, 12, 0)), \
         patch.object(m.platform, 'machine', return_value='AMD64'), \
         patch('builtins.input', return_value='y'), patch.object(m.subprocess, 'run', side_effect=run):
        m.main()
    assert len(calls) == 4
    assert calls[0][-1] == str(tmp_path / '.venv-board-test')
    assert '--no-deps' in calls[1] and '--only-binary=:all:' in calls[1]
    assert calls[-1][-3].endswith('hardware_review.py')
    assert calls[-1][-1] == str(tmp_path / 'board-test-state')


def test_setup_cancel_does_not_install_or_launch(tmp_path):
    m = setup_module_object()
    (tmp_path / 'requirements-review.txt').write_text('Pillow==11.3.0\n')
    with patch.object(m, 'ROOT', tmp_path), patch.object(m.sys, 'platform', 'win32'), \
         patch.object(m.sys, 'version_info', (3, 12, 0)), \
         patch.object(m.platform, 'machine', return_value='AMD64'), \
         patch('builtins.input', return_value='n'), patch.object(m.subprocess, 'run') as run:
        m.main()
    run.assert_not_called()


def test_native_pairing_requires_confirmation_and_explicit_new_count():
    tree = ast.parse((ROOT / 'scripts/hardware_review.py').read_text())
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    fn = next(n for n in main.body if isinstance(n, ast.FunctionDef) and n.name == 'confirm_pairing')
    calls = []
    messagebox = SimpleNamespace(askyesno=lambda *a, **k: False)
    dialog = SimpleNamespace(askinteger=lambda *a, **k: 2)
    scope = dict(messagebox=messagebox, simpledialog=dialog, root=None,
                 original_pairing=lambda **kw: calls.append(kw))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), 'confirm', 'exec'), scope)
    scope['confirm_pairing']()
    assert not calls
    messagebox.askyesno = lambda *a, **k: True
    dialog.askinteger = lambda *a, **k: None
    scope['confirm_pairing']()
    assert not calls
    dialog.askinteger = lambda *a, **k: 1
    scope['confirm_pairing']()
    assert calls == [{'target_count': 1}]


def test_review_paths_and_no_legacy_checkout_import():
    for name in ('hardware_review.py', 'review_desktop.py'):
        text = (ROOT / 'scripts' / name).read_text()
        assert 'user_data.legacy_data_dirs = lambda: []' in text
        assert "LOCALAPPDATA=str(state/'localappdata')" in text
        assert text.index('user_data.legacy_data_dirs = lambda: []') < text.index('    import obs_server')
    hardware = (ROOT / 'scripts/hardware_review.py').read_text()
    assert "os.environ.pop('SPS_UI_PREVIEW', None)" in hardware
    assert 'manager._init_subsystem()' in hardware
    assert 'manager.set_simulator = physical_only' in hardware
    assert 'lab_demo.toggle = no_demo' in hardware
    assert '_review_sample' not in hardware
    assert "('run-'" in hardware


def test_overlay_does_not_invent_a_shot():
    text = (ROOT / 'assets/overlay.html').read_text()
    assert 'latestShot || sampleShot' not in text
    assert 'if (!latestShot)' in text


def test_auxiliary_preview_isolates_windows_paths_and_legacy_data():
    text = (ROOT / 'scripts/preview_concept.py').read_text()
    assert 'USERPROFILE=str(STATE)' in text
    assert 'LOCALAPPDATA=str(STATE / "localappdata")' in text
    assert 'APPDATA=str(STATE / "appdata")' in text
    assert 'user_data.legacy_data_dirs = lambda: []' in text
    assert text.index('user_data.legacy_data_dirs = lambda: []') < text.index('    from src.ui.desktop import')
    for name in ('SPS_OPENFP_URL', 'SPS_GSPRO_DB', 'SPS_PUREPLAY_PROFILES'):
        assert name in text


def test_empty_isolated_history_blocks_all_obs_legacy_fallbacks(tmp_path, monkeypatch):
    import json

    import obs_server
    import user_data
    from scripts.review_state import prepare_isolated_history

    isolated = tmp_path / 'isolated'
    legacy = tmp_path / 'checkout'
    legacy.mkdir()
    legacy_path = legacy / user_data.HISTORY_NAME
    legacy_path.write_text(json.dumps({'bag': [{'name': 'PRIVATE LEGACY CLUB'}],
                                      'sessions': [{'shots': [{'private': True}]}]}))
    monkeypatch.setattr(user_data, 'get_data_dir', lambda: isolated)
    monkeypatch.setattr(user_data, 'legacy_data_dirs', lambda: [legacy])
    path = prepare_isolated_history()
    monkeypatch.setattr(obs_server, 'DATA_DIR', isolated)
    monkeypatch.setattr(obs_server, 'SESSION_LOG_PATH', path)
    monkeypatch.setattr(obs_server, 'SCRIPT_DIR', legacy)
    original_read = Path.read_text

    def guarded_read(self, *args, **kwargs):
        assert self != legacy_path, 'Review attempted to read legacy checkout data'
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', guarded_read)
    state = obs_server.obs_state
    assert state.load_bag()['clubs'] == []
    assert state._read_history() == {'sessions': [], 'bag': []}
    assert state.load_index() == {}
    state.combine_status()
    assert user_data.legacy_data_dirs() == []


def test_isolated_history_preserves_review_data_and_rejects_corruption(tmp_path, monkeypatch):
    import user_data
    from scripts.review_state import prepare_isolated_history

    monkeypatch.setattr(user_data, 'get_data_dir', lambda: tmp_path)
    monkeypatch.setattr(user_data, 'legacy_data_dirs', lambda: [])
    path = prepare_isolated_history()
    content = '{"sessions": [{"id": "my-review", "shots": []}], "bag": []}'
    path.write_text(content)
    assert prepare_isolated_history().read_text() == content
    path.write_text('invalid JSON')
    import pytest
    with pytest.raises(ValueError):
        prepare_isolated_history()


def test_all_preview_launchers_seed_history_before_app_import():
    for name in ('hardware_review.py', 'review_desktop.py', 'preview_concept.py'):
        text = (ROOT / 'scripts' / name).read_text()
        boundary = '    from src.ui.desktop import' if name == 'preview_concept.py' else '    import obs_server'
        assert text.index('prepare_isolated_history()') < text.index(boundary)
