"""Persistent storage works without writing to the installation directory."""
import json
from pathlib import Path

import pytest

import user_data


def test_linux_uses_absolute_xdg_data_home(tmp_path, monkeypatch):
    monkeypatch.setattr(user_data.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert user_data.get_data_dir() == tmp_path / "shanktuary"


def test_relative_xdg_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(user_data.sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", "relative")
    assert user_data.get_data_dir() == tmp_path / ".local/share/shanktuary"


def test_windows_uses_local_appdata(tmp_path, monkeypatch):
    monkeypatch.setattr(user_data.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert user_data.get_data_dir() == tmp_path / "shanktuary"


def test_mac_uses_application_support(tmp_path, monkeypatch):
    monkeypatch.setattr(user_data.sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert user_data.get_data_dir() == tmp_path / "Library/Application Support/shanktuary"


def legacy(tmp_path):
    old = tmp_path / "install"
    (old / "pressure_traces").mkdir(parents=True)
    (old / user_data.HISTORY_NAME).write_text('{"sessions": [], "bag": [{"name": "7 Iron"}]}')
    (old / "pressure_traces/a.json.gz").write_bytes(b"trace")
    return old


def test_migration_copies_history_and_traces_keeps_originals(tmp_path):
    old = legacy(tmp_path)
    new = tmp_path / "userdata"
    user_data.prepare_data_dir(new, [old])
    for relative in [user_data.HISTORY_NAME, "pressure_traces/a.json.gz"]:
        assert (old / relative).read_bytes() == (new / relative).read_bytes()
    assert not list(new.glob(".migrate-*"))


def test_current_history_is_never_replaced(tmp_path):
    old = legacy(tmp_path)
    new = tmp_path / "userdata"
    new.mkdir()
    (new / user_data.HISTORY_NAME).write_text("current data")
    user_data.prepare_data_dir(new, [old])
    assert (new / user_data.HISTORY_NAME).read_text() == "current data"
    assert (new / "pressure_traces/a.json.gz").read_bytes() == b"trace"


def test_failed_migration_keeps_original_and_retries(tmp_path, monkeypatch):
    old = legacy(tmp_path)
    new = tmp_path / "userdata"
    copy = user_data._copy_without_overwrite
    def fail_history(src, dst):
        if src.name == user_data.HISTORY_NAME:
            raise OSError("disk full")
        copy(src, dst)
    monkeypatch.setattr(user_data, "_copy_without_overwrite", fail_history)
    with pytest.raises(OSError, match="disk full"):
        user_data.prepare_data_dir(new, [old])
    assert not (new / user_data.HISTORY_NAME).exists()
    assert (old / user_data.HISTORY_NAME).exists()
    (new / "pressure_traces/a.json.gz").write_bytes(b"new trace wins")
    monkeypatch.setattr(user_data, "_copy_without_overwrite", copy)
    user_data.prepare_data_dir(new, [old])
    assert (new / "pressure_traces/a.json.gz").read_bytes() == b"new trace wins"
    assert (new / user_data.HISTORY_NAME).exists()


def test_bad_legacy_history_does_not_create_empty_replacement(tmp_path):
    old = legacy(tmp_path)
    (old / user_data.HISTORY_NAME).write_text("broken json")
    new = tmp_path / "userdata"
    with pytest.raises(ValueError):
        user_data.prepare_data_dir(new, [old])
    assert not (new / user_data.HISTORY_NAME).exists()
    assert (old / user_data.HISTORY_NAME).read_text() == "broken json"


def test_atomic_write_failure_keeps_previous_data(tmp_path, monkeypatch):
    path = tmp_path / "history.json"
    path.write_text("previous")
    def fail(*args):
        raise PermissionError("read-only")
    monkeypatch.setattr(user_data.os, "replace", fail)
    with pytest.raises(PermissionError):
        user_data.atomic_write_json(path, {"sessions": []})
    assert path.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [path]


def test_save_failure_is_visible_and_retry_clears_error(tmp_path, monkeypatch):
    import shanktuary_performance_studio as studio
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.sessions = []; app.clubs = []; app.bag = []; app.is_left_handed = False
    app._record_index_snapshot = lambda: None
    app._record_combine_run = lambda: None
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(tmp_path / "history.json"))
    def fail(*args):
        raise PermissionError("denied")
    monkeypatch.setattr(studio, "atomic_write_json", fail)
    assert app.save_session_to_file() is False
    assert "denied" in app.persistence_error
    assert "not saved" in app.copy_feedback
    monkeypatch.setattr(studio, "atomic_write_json", user_data.atomic_write_json)
    assert app.save_session_to_file() is True
    assert app.persistence_error is None
    assert json.loads((tmp_path / "history.json").read_text())["sessions"] == []


def test_blocked_migration_prevents_history_save(tmp_path, monkeypatch):
    import shanktuary_performance_studio as studio
    app = studio.ShanktuaryApp.__new__(studio.ShanktuaryApp)
    app.sessions = []; app.clubs = []; app.bag = []; app.is_left_handed = False
    app._history_save_blocked = True
    path = tmp_path / "history.json"
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(path))
    assert app.save_session_to_file() is False
    assert not path.exists()


def test_desktop_and_server_share_history_path():
    import obs_server
    import shanktuary_performance_studio as studio
    assert Path(studio.SESSION_LOG_PATH) == obs_server.SESSION_LOG_PATH


def test_bag_transfer_uses_current_user_history(tmp_path, monkeypatch):
    import bag_transfer
    monkeypatch.setattr(bag_transfer, "get_data_dir", lambda: tmp_path)
    assert Path(bag_transfer.default_history_path()) == tmp_path / user_data.HISTORY_NAME


@pytest.mark.parametrize("name", user_data.ANCILLARY_NAMES)
def test_migrate_missing_analytics_with_existing_history(tmp_path, name):
    old = legacy(tmp_path)
    (old / name).write_text('[{"score": 42}]')
    new = tmp_path / "userdata"
    new.mkdir()
    (new / user_data.HISTORY_NAME).write_text("current history")
    user_data.prepare_data_dir(new, [old])
    assert (new / name).read_bytes() == (old / name).read_bytes()
    assert (new / user_data.HISTORY_NAME).read_text() == "current history"
    (new / name).write_text("current analytics")
    user_data.prepare_data_dir(new, [old])
    assert (new / name).read_text() == "current analytics"
    assert (old / name).read_text() == '[{"score": 42}]'


def test_missing_analytics_retry_after_copy_failure(tmp_path, monkeypatch):
    old = legacy(tmp_path)
    new = tmp_path / "userdata"
    name = user_data.ANCILLARY_NAMES[0]
    (old / name).write_text("[]")
    new.mkdir()
    (new / user_data.HISTORY_NAME).write_text("current history")
    copy = user_data._copy_without_overwrite
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(user_data, "_copy_without_overwrite", fail)
    with pytest.raises(OSError):
        user_data.prepare_data_dir(new, [old])
    assert (old / name).exists()
    monkeypatch.setattr(user_data, "_copy_without_overwrite", copy)
    user_data.prepare_data_dir(new, [old])
    assert (new / name).read_text() == "[]"


def test_splash_reads_legacy_bag_without_writing(tmp_path, monkeypatch):
    import shanktuary_performance_studio as studio
    old = legacy(tmp_path)
    current = tmp_path / "userdata" / user_data.HISTORY_NAME
    monkeypatch.setattr(studio, "SESSION_LOG_PATH", str(current))
    monkeypatch.setattr(studio, "legacy_data_dirs", lambda: [old])
    assert studio.load_bag_specs_for_splash()["7 Iron"]["name"] == "7 Iron"
    assert not current.parent.exists()
    current.parent.mkdir()
    current.write_text('{"bag": [{"name": "Driver"}]}')
    assert list(studio.load_bag_specs_for_splash()) == ["Driver"]
