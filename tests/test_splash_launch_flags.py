"""The --splash / --no-splash launch flags.

Testing the splash repeatedly used to mean deleting the settings file by
hand, which also destroyed the user's real shot-source choice. These flags
make it a normal launch option; this locks in the precedence rules.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SPS_SHOT_SOURCE_FILE", str(tmp_path / "s.json"))
    monkeypatch.delenv("SPS_SHOT_SOURCE", raising=False)
    monkeypatch.delenv("SPS_SKIP_SPLASH", raising=False)


def _shows(argv, onboarded):
    """Replicate main()'s splash decision for the given flags/state."""
    import importlib

    from src.gspro import settings as gspro_settings
    from src.ui import splash as splash_mod

    import shanktuary_app

    gspro_settings.save_settings(source="nova", onboarded=onboarded)
    importlib.reload(splash_mod)

    args = shanktuary_app.parse_args(argv)
    return bool(args.splash or (splash_mod.should_show_splash()
                                and not args.no_splash))


def test_first_run_shows_the_splash_by_default():
    assert _shows([], onboarded=False) is True


def test_after_onboarding_the_splash_stays_away():
    assert _shows([], onboarded=True) is False


def test_splash_flag_forces_it_even_after_onboarding():
    """The point of --splash: re-test without erasing saved settings."""
    assert _shows(["--splash"], onboarded=True) is True


def test_no_splash_flag_suppresses_it_on_a_first_run():
    assert _shows(["--no-splash"], onboarded=False) is False


def test_the_two_flags_cannot_be_combined():
    import shanktuary_app

    with pytest.raises(SystemExit):
        shanktuary_app.parse_args(["--splash", "--no-splash"])


def test_forcing_the_splash_does_not_erase_the_saved_choice(tmp_path):
    """--splash must not wipe settings the way `rm` did."""
    import json

    from src.gspro import settings as gspro_settings
    import shanktuary_app

    gspro_settings.save_settings(source="gspro", onboarded=True)
    shanktuary_app.parse_args(["--splash"])

    path = tmp_path / "s.json"
    assert path.is_file(), "settings file was removed"
    assert json.loads(path.read_text())["source"] == "gspro"
