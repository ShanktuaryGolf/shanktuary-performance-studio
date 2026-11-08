"""Tests for persisted shot-source settings and the GSPro/Nova source gate.

Covers the gap in the original env-var-only port: a user must be able to
choose GSPro in the UI, have it persist, and have it take effect without
setting an environment variable or restarting the app.
"""

import importlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gspro import settings as gspro_settings  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Point the settings module at a throwaway file and clear env overrides."""
    path = tmp_path / "shot_source.json"
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(path))
    monkeypatch.delenv("SPS_SHOT_SOURCE", raising=False)
    monkeypatch.delenv("SPS_GSPRO_DB", raising=False)
    monkeypatch.delenv("SPS_PUREPLAY_PROFILES", raising=False)
    importlib.reload(gspro_settings)
    yield path
    importlib.reload(gspro_settings)


# -- defaults ------------------------------------------------------------

def test_default_source_is_nova_and_not_onboarded():
    s = gspro_settings.load_settings(refresh=True)
    assert s["source"] == "nova"
    assert s["onboarded"] is False
    assert gspro_settings.nova_enabled() is True
    assert gspro_settings.gspro_enabled() is False


def test_missing_file_does_not_raise(isolated_settings):
    assert not isolated_settings.exists()
    assert gspro_settings.effective_source() == "nova"


# -- persistence ---------------------------------------------------------

def test_saving_gspro_persists_and_takes_effect(isolated_settings):
    gspro_settings.save_settings(source="gspro", onboarded=True)

    stored = json.loads(isolated_settings.read_text())
    assert stored["source"] == "gspro"
    assert stored["onboarded"] is True

    # A fresh module (simulating an app restart) reads the same choice.
    importlib.reload(gspro_settings)
    assert gspro_settings.effective_source() == "gspro"
    assert gspro_settings.gspro_enabled() is True
    # In gspro-only mode Nova shots must be dropped to avoid double ingest.
    assert gspro_settings.nova_enabled() is False


def test_both_ingests_from_each_source():
    gspro_settings.save_settings(source="both")
    assert gspro_settings.gspro_enabled() is True
    assert gspro_settings.nova_enabled() is True


def test_invalid_source_is_rejected():
    with pytest.raises(ValueError):
        gspro_settings.save_settings(source="trackman")


def test_corrupt_settings_file_falls_back_to_default(isolated_settings):
    isolated_settings.write_text("{not json")
    importlib.reload(gspro_settings)
    assert gspro_settings.effective_source() == "nova"


def test_unknown_stored_source_falls_back_to_default(isolated_settings):
    isolated_settings.write_text(json.dumps({"source": "bogus"}))
    importlib.reload(gspro_settings)
    assert gspro_settings.effective_source() == "nova"


# -- environment overrides ----------------------------------------------

def test_env_var_overrides_stored_source_and_reports_locked(monkeypatch):
    gspro_settings.save_settings(source="nova")
    monkeypatch.setenv("SPS_SHOT_SOURCE", "gspro")
    importlib.reload(gspro_settings)

    s = gspro_settings.load_settings(refresh=True)
    assert s["source"] == "gspro"
    assert s["source_locked"] is True


def test_env_override_does_not_overwrite_the_users_stored_choice(
    isolated_settings, monkeypatch
):
    gspro_settings.save_settings(source="nova")
    monkeypatch.setenv("SPS_SHOT_SOURCE", "gspro")
    importlib.reload(gspro_settings)
    gspro_settings.save_settings(onboarded=True)

    stored = json.loads(isolated_settings.read_text())
    assert stored["source"] == "nova", "env override leaked into persisted state"

    # Unsetting the variable restores what the user actually picked.
    monkeypatch.delenv("SPS_SHOT_SOURCE")
    importlib.reload(gspro_settings)
    assert gspro_settings.effective_source() == "nova"


def test_db_path_env_override_wins_and_is_locked(monkeypatch, tmp_path):
    db = tmp_path / "GSPro.db"
    db.write_text("")
    monkeypatch.setenv("SPS_GSPRO_DB", str(db))
    importlib.reload(gspro_settings)

    s = gspro_settings.load_settings(refresh=True)
    assert s["db_path"] == str(db)
    assert s["db_path_locked"] is True
    assert gspro_settings.effective_db_path() == str(db)


def test_explicit_db_path_is_used_when_no_env_override(tmp_path):
    db = tmp_path / "custom" / "GSPro.db"
    db.parent.mkdir()
    db.write_text("")
    gspro_settings.save_settings(source="gspro", db_path=str(db))
    assert gspro_settings.effective_db_path() == str(db)


def test_blank_db_path_falls_back_to_auto_location():
    gspro_settings.save_settings(source="gspro", db_path="")
    from src.gspro.locate import locate_gspro_database_path

    assert gspro_settings.effective_db_path() == locate_gspro_database_path()


# -- splash --------------------------------------------------------------

def test_splash_is_shown_until_onboarding_completes(monkeypatch):
    monkeypatch.delenv("SPS_SKIP_SPLASH", raising=False)
    from src.ui import splash

    importlib.reload(splash)
    assert splash.should_show_splash() is True

    gspro_settings.save_settings(source="gspro", onboarded=True)
    assert splash.should_show_splash() is False


def test_splash_can_be_suppressed_by_env(monkeypatch):
    from src.ui import splash

    importlib.reload(splash)
    monkeypatch.setenv("SPS_SKIP_SPLASH", "1")
    assert splash.should_show_splash() is False


def test_read_only_install_dir_falls_back_to_the_user_home(tmp_path, monkeypatch):
    """A frozen install under Program Files must not silently lose the choice."""
    monkeypatch.delenv("SPS_SHOT_SOURCE_FILE", raising=False)
    ro = tmp_path / "install"
    ro.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(gspro_settings, "_settings_path",
                        lambda: str(ro / "locked" / "s.json"))

    real_write = gspro_settings._write_json

    def fail_on_install(path, data):
        if str(ro) in str(path):
            return False
        return real_write(path, data)

    monkeypatch.setattr(gspro_settings, "_write_json", fail_on_install)
    gspro_settings.save_settings(source="gspro", onboarded=True)

    fallback = home / ".shanktuary" / gspro_settings.SETTINGS_FILENAME
    assert fallback.is_file(), "choice was not written to the user-home fallback"
    assert json.loads(fallback.read_text())["source"] == "gspro"


def test_pureplay_persists_without_enabling_other_sources(isolated_settings):
    folder = str(isolated_settings.parent / "Profiles")
    gspro_settings.save_settings(source="pureplay", pureplay_profiles_path=folder)
    importlib.reload(gspro_settings)
    settings = gspro_settings.load_settings()
    assert settings["source"] == "pureplay"
    assert settings["pureplay_profiles_path"] == folder
    assert not gspro_settings.nova_enabled()
    assert not gspro_settings.gspro_enabled()


def test_pureplay_folder_override_does_not_replace_saved_preference(monkeypatch):
    gspro_settings.save_settings(pureplay_profiles_path="saved-profiles")
    monkeypatch.setenv("SPS_PUREPLAY_PROFILES", "forced-profiles")
    settings = gspro_settings.load_settings(refresh=True)
    assert settings["pureplay_profiles_path_locked"]
    assert settings["pureplay_profiles_path"] == os.path.abspath("forced-profiles")
    gspro_settings.save_settings(source="pureplay")
    monkeypatch.delenv("SPS_PUREPLAY_PROFILES")
    assert gspro_settings.load_settings(refresh=True)["pureplay_profiles_path"] == os.path.abspath("saved-profiles")


def test_pureplay_folder_clear_and_invalid_type():
    gspro_settings.save_settings(pureplay_profiles_path="somewhere")
    assert gspro_settings.save_settings(pureplay_profiles_path=" ")["pureplay_profiles_path"] == ""
    with pytest.raises(ValueError):
        gspro_settings.save_settings(pureplay_profiles_path=123)
