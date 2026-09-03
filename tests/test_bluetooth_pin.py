"""Unit tests for Windows Bluetooth MAC reverse-PIN calculations."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, '/home/sean/sps')
from src.hardware.pressure import bluetooth_windows
from src.hardware.pressure.bluetooth_windows import (
    _normalize_mac,
    format_mac_display,
    get_manual_mac_override,
    mac_has_zero_byte,
    mac_to_wii_pin,
    mac_to_wii_pin_bytes,
    mac_to_wii_pin_display,
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

if __name__ == "__main__":
    unittest.main()
