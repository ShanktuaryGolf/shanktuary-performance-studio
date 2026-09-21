"""Unit tests for Windows Bluetooth MAC reverse-PIN calculations."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, '/home/sean/sps')
from src.hardware.pressure import bluetooth_windows
from src.hardware.pressure.bluetooth_windows import (
    _normalize_mac,
    describe_pin_entry,
    format_mac_display,
    get_manual_mac_override,
    mac_has_zero_byte,
    mac_to_wii_pin,
    mac_to_wii_pin_bytes,
    mac_to_wii_pin_display,
    pin_is_typeable,
)


class TestManualMacOverride(unittest.TestCase):
    """Auto-detection can fail or be wrong; there must always be a manual way
    to supply the host MAC, or the board simply cannot be paired."""

    def setUp(self):
        bluetooth_windows.get_host_bluetooth_mac.cache_clear()

    def tearDown(self):
        bluetooth_windows.get_host_bluetooth_mac.cache_clear()

    def test_normalize_accepts_common_formats(self):
        for raw in ("38:FC:98:3B:B4:DC", "38-FC-98-3B-B4-DC",
                    "38FC983BB4DC", "38fc983bb4dc"):
            self.assertEqual(_normalize_mac(raw), "38FC983BB4DC", raw)

    def test_normalize_rejects_junk(self):
        for raw in (None, "", "not-a-mac", "38FC98", "38FC983BB4DCFF", "ZZ:..."):
            self.assertIsNone(_normalize_mac(raw), raw)

    def test_env_override_wins(self):
        with mock.patch.dict(os.environ,
                             {"SHANKTUARY_BT_MAC": "38:FC:98:3B:B4:DC"}):
            self.assertEqual(get_manual_mac_override(), "38FC983BB4DC")
            self.assertEqual(bluetooth_windows.get_host_bluetooth_mac(),
                             "38FC983BB4DC")

    def test_env_override_produces_expected_pin(self):
        with mock.patch.dict(os.environ,
                             {"SHANKTUARY_BT_MAC": "38FC983BB4DC"}):
            mac = bluetooth_windows.get_host_bluetooth_mac()
        assert mac is not None
        self.assertEqual(mac_to_wii_pin(mac), "\xdc\xb4\x3b\x98\xfc\x38")

    def test_bad_env_override_is_ignored(self):
        with mock.patch.dict(os.environ, {"SHANKTUARY_BT_MAC": "garbage"}):
            self.assertIsNone(get_manual_mac_override())

    def test_registry_is_preferred_over_pnp_on_windows(self):
        """The PnP path scrapes any 12 hex digits out of a device id, and a
        BTHENUM id embeds the REMOTE address -- so it must never outrank the
        authoritative registry value."""
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(bluetooth_windows.sys, "platform", "win32"), \
                mock.patch.object(bluetooth_windows, "_try_registry",
                                  return_value="AAAAAAAAAAAA") as reg, \
                mock.patch.object(bluetooth_windows, "_try_powershell_pnp",
                                  return_value="BBBBBBBBBBBB") as pnp:
            bluetooth_windows.get_host_bluetooth_mac.cache_clear()
            self.assertEqual(bluetooth_windows.get_host_bluetooth_mac(),
                             "AAAAAAAAAAAA")
            reg.assert_called_once()
            pnp.assert_not_called()


class TestBluetoothPIN(unittest.TestCase):
    def test_known_mac_reversal(self):
        # Known test vector 1: 38:FC:98:3B:B4:DC
        # Bytes: 0x38, 0xFC, 0x98, 0x3B, 0xB4, 0xDC
        # Reversed: 0xDC, 0xB4, 0x3B, 0x98, 0xFC, 0x38
        mac = "38:FC:98:3B:B4:DC"
        raw_bytes = mac_to_wii_pin_bytes(mac)
        self.assertEqual(raw_bytes, bytes([0xDC, 0xB4, 0x3B, 0x98, 0xFC, 0x38]))

        pin_str = mac_to_wii_pin(mac)
        self.assertEqual(len(pin_str), 6)
        self.assertEqual(pin_str[0], chr(0xDC))
        self.assertEqual(pin_str[1], chr(0xB4))
        self.assertEqual(pin_str[2], ';')
        self.assertEqual(pin_str[3], chr(0x98))
        self.assertEqual(pin_str[4], chr(0xFC))
        self.assertEqual(pin_str[5], '8')

        self.assertFalse(mac_has_zero_byte(mac))

    def test_mac_with_zero_byte(self):
        # Known test vector 2: 00:11:22:33:44:55
        mac = "00:11:22:33:44:55"
        self.assertTrue(mac_has_zero_byte(mac))
        raw_bytes = mac_to_wii_pin_bytes(mac)
        self.assertEqual(raw_bytes[-1], 0x00)

        display = mac_to_wii_pin_display(mac)
        self.assertTrue(display.endswith("\u2400"))

    def test_format_mac_display(self):
        self.assertEqual(format_mac_display("AABBCCDDEEFF"), "AA:BB:CC:DD:EE:FF")
        self.assertEqual(format_mac_display("38-fc-98-3b-b4-dc"), "38:FC:98:3B:B4:DC")

    def test_invalid_mac_handling(self):
        self.assertEqual(mac_to_wii_pin("INVALID"), "")
        self.assertEqual(mac_to_wii_pin_bytes("123"), b"")
        self.assertEqual(mac_to_wii_pin_display(""), "")


class TestPinTypeability(unittest.TestCase):
    """The Windows 'Add a device' PIN box is a text control: it rejects control
    characters and re-encodes non-ASCII before transmitting. Telling a user to
    paste a PIN that cannot survive that is worse than useless, so the app has
    to know which PINs are actually enterable."""

    def test_control_bytes_are_not_typeable(self):
        # The adapter from the bug report: 00:E0:4C:00:00:01 -> 01 00 00 4C E0 00
        self.assertFalse(pin_is_typeable("00E04C000001"))

    def test_high_bytes_are_not_typeable(self):
        # 0xDC etc. would be re-encoded as UTF-8 and arrive wrong.
        self.assertFalse(pin_is_typeable("38FC983BB4DC"))

    def test_all_printable_ascii_is_typeable(self):
        # Reverses to 'ABCDEF' -- the lucky case that made this bug look
        # intermittent rather than systematic.
        self.assertTrue(pin_is_typeable("464544434241"))

    def test_space_and_tilde_boundaries(self):
        self.assertTrue(pin_is_typeable("7E7E7E202020"))   # 0x20..0x7E
        self.assertFalse(pin_is_typeable("7F7E7E202020"))  # 0x7F is DEL

    def test_no_mac_is_not_typeable(self):
        self.assertFalse(pin_is_typeable(""))
        self.assertFalse(pin_is_typeable("garbage"))

    def test_description_names_the_native_route_when_untypeable(self):
        note = describe_pin_entry("00E04C000001")
        self.assertIn("Pair Board", note)

    def test_description_is_reassuring_when_typeable(self):
        note = describe_pin_entry("464544434241")
        self.assertIn("ASCII", note)


class TestClipboardTruncationRule(unittest.TestCase):
    """The Windows clipboard carries text as NUL-terminated CF_UNICODETEXT, so
    a PIN containing 0x00 is cut short on paste -- the user in the bug report
    got a single character. The UI must detect that, not paste silently."""

    @staticmethod
    def _clipboard_payload(pin: str) -> tuple[str, bool]:
        """Mirror of the UI's rule in shanktuary_performance_studio.py."""
        safe = pin.split("\x00")[0]
        return safe, safe != pin

    def test_reported_pin_is_detected_as_truncated(self):
        pin = mac_to_wii_pin("00E04C000001")
        safe, truncated = self._clipboard_payload(pin)
        self.assertTrue(truncated)
        self.assertEqual(safe, "\x01")  # exactly the one glyph users saw

    def test_ascii_pin_is_not_truncated(self):
        pin = mac_to_wii_pin("464544434241")
        safe, truncated = self._clipboard_payload(pin)
        self.assertFalse(truncated)
        self.assertEqual(len(safe), 6)

    def test_nul_free_high_byte_pin_survives_the_clipboard(self):
        """Not truncated -- but still not *correct* to type, which is why
        pin_is_typeable is a separate, stricter check."""
        pin = mac_to_wii_pin("38FC983BB4DC")
        safe, truncated = self._clipboard_payload(pin)
        self.assertFalse(truncated)
        self.assertFalse(pin_is_typeable("38FC983BB4DC"))


class TestLiveRadioPreferredOverRegistry(unittest.TestCase):
    """BTHPORT's LocalDeviceAddress can be left over from a radio that is no
    longer installed, which yields a PIN that can never pair."""

    def setUp(self):
        bluetooth_windows.get_host_bluetooth_mac.cache_clear()

    def tearDown(self):
        bluetooth_windows.get_host_bluetooth_mac.cache_clear()

    def test_live_radio_wins(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(bluetooth_windows.sys, "platform", "win32"), \
                mock.patch.object(bluetooth_windows, "_try_live_radio",
                                  return_value="CCCCCCCCCCCC") as live, \
                mock.patch.object(bluetooth_windows, "_try_registry",
                                  return_value="AAAAAAAAAAAA") as reg:
            self.assertEqual(bluetooth_windows.get_host_bluetooth_mac(),
                             "CCCCCCCCCCCC")
            live.assert_called_once()
            reg.assert_not_called()

    def test_registry_still_used_when_no_live_radio(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(bluetooth_windows.sys, "platform", "win32"), \
                mock.patch.object(bluetooth_windows, "_try_live_radio",
                                  return_value=None), \
                mock.patch.object(bluetooth_windows, "_try_registry",
                                  return_value="AAAAAAAAAAAA"):
            self.assertEqual(bluetooth_windows.get_host_bluetooth_mac(),
                             "AAAAAAAAAAAA")

    def test_manual_override_still_beats_everything(self):
        with mock.patch.dict(os.environ,
                             {"SHANKTUARY_BT_MAC": "38FC983BB4DC"}), \
                mock.patch.object(bluetooth_windows, "_try_live_radio",
                                  return_value="CCCCCCCCCCCC") as live:
            self.assertEqual(bluetooth_windows.get_host_bluetooth_mac(),
                             "38FC983BB4DC")
            live.assert_not_called()

if __name__ == "__main__":
    unittest.main()
