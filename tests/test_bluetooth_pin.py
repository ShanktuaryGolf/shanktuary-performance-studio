"""Unit tests for Windows Bluetooth MAC reverse-PIN calculations."""

import sys
import unittest

sys.path.insert(0, '/home/sean/sps')
from src.hardware.pressure.bluetooth_windows import (
    format_mac_display,
    mac_has_zero_byte,
    mac_to_wii_pin,
    mac_to_wii_pin_bytes,
    mac_to_wii_pin_display,
)


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
