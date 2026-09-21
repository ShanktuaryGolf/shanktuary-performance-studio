"""Board device ids must survive the calibration round-trip.

Reported from a Windows run: the board was paired and healthy, yet the app
logged forever

    Wii Balance Board at b"b'\\\\\\\\?\\\\HID#{00001124-...}'" could not be opened.

Note the doubled b'' prefix. hidapi returns Windows device paths as BYTES;
_save_calibration() wrote str(bytes), which stores the Python repr -- the
literal characters b'\\\\?\\HID#... -- and the load path then encoded that repr
back to bytes, producing a path no device has. The board could never be
reopened again, and re-pairing could not help because the corruption was in
the saved calibration, not in Bluetooth.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import obs_server

# A real Windows WBB path, as hidapi hands it over.
REAL_PATH = (rb"\\?\HID#{00001124-0000-1000-8000-00805f9b34fb}"
             rb"_VID&0002057e_PID&0306#8&257e6876&1&0000"
             rb"#{4d1e55b2-f16f-11cf-88cb-001111000030}")


class TestBoardIdRoundTrip:
    def test_bytes_path_round_trips_exactly(self):
        text = obs_server.board_id_to_text(REAL_PATH)
        assert obs_server.board_id_to_bytes(text) == REAL_PATH

    def test_text_form_is_not_a_python_repr(self):
        """The bug in one assertion: str(bytes) starts with b' and that is
        what got written to the calibration file."""
        text = obs_server.board_id_to_text(REAL_PATH)
        assert not text.startswith("b'"), f"stored a bytes repr: {text[:20]}"
        assert not text.startswith('b"')
        assert text.startswith("\\\\?\\HID#")

    def test_str_would_have_corrupted_it(self):
        """Pin the old behaviour so nobody reintroduces str() here."""
        corrupted = str(REAL_PATH).encode("utf-8")
        assert corrupted != REAL_PATH

    def test_survives_a_json_round_trip(self):
        """This is the actual path the value takes: memory -> JSON -> memory."""
        text = obs_server.board_id_to_text(REAL_PATH)
        reloaded = json.loads(json.dumps({"assigned_left": text}))["assigned_left"]
        assert obs_server.board_id_to_bytes(reloaded) == REAL_PATH

    def test_repairs_an_already_corrupted_id(self):
        """Users who ran an affected build have a poisoned calibration file;
        it must heal itself rather than need manual deletion."""
        corrupted = str(REAL_PATH)          # exactly what was written to disk
        assert obs_server.board_id_to_bytes(corrupted) == REAL_PATH

    def test_plain_string_paths_are_untouched(self):
        """Linux evdev paths are ordinary strings and must not be mangled."""
        p = "/dev/input/event17"
        assert obs_server.board_id_to_text(p) == p
        assert obs_server.board_id_to_bytes(p) == p.encode("latin-1")

    def test_none_is_handled(self):
        assert obs_server.board_id_to_text(None) == ""
        assert obs_server.board_id_to_bytes(None) is None

    def test_high_bytes_survive(self):
        raw = bytes([0x80, 0xFF, 0x41, 0x00, 0x42])
        assert obs_server.board_id_to_bytes(
            obs_server.board_id_to_text(raw)) == raw


class TestCalibrationPersistence:
    def test_saved_assignment_reopens_the_same_device(self, tmp_path, monkeypatch):
        """End to end: assign bytes paths, save, reload, and confirm what comes
        back out can actually be handed to hid.open_path()."""
        cal = tmp_path / "wbb_calibration.json"
        pm = obs_server.PressureManager.__new__(obs_server.PressureManager)
        pm.lock = __import__("threading").RLock()
        pm.board_mode = "dual"
        pm.assigned_left = REAL_PATH
        pm.assigned_right = REAL_PATH.replace(b"8&257e6876", b"8&257e6877")
        pm.balance_multiplier = [1.0, 1.0]
        pm.stance_width_mm = None

        pm._save_calibration(str(cal))

        on_disk = json.loads(cal.read_text())
        assert not on_disk["assigned_left"].startswith("b'"), (
            "calibration file still stores a Python bytes repr"
        )

        assert obs_server.board_id_to_bytes(on_disk["assigned_left"]) == REAL_PATH
        assert obs_server.board_id_to_bytes(
            on_disk["assigned_right"]) == pm.assigned_right

    def test_loaded_ids_are_not_placeholders(self, tmp_path):
        """A decoded path must still pass the placeholder check, or a restored
        dual setup would be silently downgraded to single."""
        text = obs_server.board_id_to_text(REAL_PATH)
        assert not obs_server._is_placeholder_board_id(text)
