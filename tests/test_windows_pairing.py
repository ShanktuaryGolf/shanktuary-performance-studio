"""Tests for native Windows Bluetooth pairing of the Wii Balance Board.

These run on any platform. The structure layouts and the PIN byte packing are
the parts that must be exactly right -- they are what the Windows PIN text box
destroys -- so they are tested here rather than only on a Windows machine.

Structures containing c_wchar are deliberately NOT size-asserted: wchar_t is
2 bytes on Windows and 4 on Linux, so their sizeof differs off Windows. They
are only ever used at runtime on Windows, where ctypes sizes them correctly.
"""

import ctypes
import sys
import unittest

sys.path.insert(0, '/home/sean/sps')

from src.hardware.pressure import windows_pairing as wp


class TestStructureLayout(unittest.TestCase):
    """Windows validates several of these through their dwSize members, and a
    wrong layout means silent misbehaviour rather than a clean error."""

    def test_fixed_width_struct_sizes_match_windows_x64(self):
        # Verified against bluetoothapis.h on x64.
        self.assertEqual(ctypes.sizeof(wp.BLUETOOTH_ADDRESS), 8)
        self.assertEqual(ctypes.sizeof(wp.BLUETOOTH_PIN_INFO), 17)
        self.assertEqual(ctypes.sizeof(wp.BLUETOOTH_OOB_DATA_INFO), 32)
        self.assertEqual(ctypes.sizeof(wp.BLUETOOTH_DEVICE_SEARCH_PARAMS), 40)
        self.assertEqual(ctypes.sizeof(wp.GUID), 16)
        self.assertEqual(ctypes.sizeof(wp.SYSTEMTIME), 16)

    def test_pin_info_holds_16_bytes(self):
        self.assertEqual(wp.BTH_MAX_PIN_SIZE, 16)
        info = wp.BLUETOOTH_PIN_INFO()
        self.assertEqual(len(info.pin), 16)

    def test_hid_service_guid_value(self):
        # HumanInterfaceDeviceServiceClass_UUID 00001124-0000-1000-8000-00805F9B34FB
        g = wp.HID_SERVICE_GUID
        self.assertEqual(g.Data1, 0x00001124)
        self.assertEqual(g.Data2, 0x0000)
        self.assertEqual(g.Data3, 0x1000)
        self.assertEqual(bytes(g.Data4), b"\x80\x00\x00\x80\x5f\x9b\x34\xfb")


class TestAddressConversion(unittest.TestCase):
    def test_round_trip(self):
        for mac in ("001E35AABBCC", "38FC983BB4DC", "00E04C000001"):
            self.assertEqual(wp.address_to_hex(wp.hex_to_address(mac)), mac)

    def test_accepts_separators(self):
        self.assertEqual(
            wp.address_to_hex(wp.hex_to_address("00:1E:35:AA:BB:CC")),
            "001E35AABBCC")

    def test_byte_order_is_little_endian_in_rgbytes(self):
        """BLUETOOTH_ADDRESS.rgBytes[0] is the LAST byte of the printed MAC."""
        addr = wp.hex_to_address("001E35AABBCC")
        self.assertEqual(list(addr.rgBytes), [0xCC, 0xBB, 0xAA, 0x35, 0x1E, 0x00])

    def test_rejects_bad_length(self):
        for bad in ("", "001E35", "001E35AABBCCDD"):
            with self.assertRaises(ValueError):
                wp.hex_to_address(bad)


class TestPinDerivation(unittest.TestCase):
    def test_pin_is_host_address_reversed(self):
        self.assertEqual(wp.pin_bytes_for_host("38FC983BB4DC"),
                         bytes([0xDC, 0xB4, 0x3B, 0x98, 0xFC, 0x38]))

    def test_reported_failing_adapter(self):
        """The adapter from the user's bug report: 00:E0:4C:00:00:01.

        Three of its six PIN bytes are NUL -- this is the case that truncated
        to a single character on the Windows clipboard.
        """
        pin = wp.pin_bytes_for_host("00E04C000001")
        self.assertEqual(pin, bytes([0x01, 0x00, 0x00, 0x4C, 0xE0, 0x00]))
        self.assertEqual(len(pin), 6)
        self.assertEqual(pin.count(0), 3)

    def test_invalid_mac_gives_empty(self):
        self.assertEqual(wp.pin_bytes_for_host("nope"), b"")


class TestBuildPinResponse(unittest.TestCase):
    """The whole point of the native route: raw bytes survive intact."""

    def test_nul_bytes_survive(self):
        pin = bytes([0x01, 0x00, 0x00, 0x4C, 0xE0, 0x00])
        resp = wp.build_pin_response(wp.hex_to_address("001E35AABBCC"), pin)
        self.assertEqual(resp.u.pinInfo.pinLength, 6)
        self.assertEqual(bytes(resp.u.pinInfo.pin[:6]), pin)

    def test_high_bytes_survive_unencoded(self):
        """0xDC must stay one byte -- text entry would send UTF-8 C3 9C."""
        pin = bytes([0xDC, 0xB4, 0x3B, 0x98, 0xFC, 0x38])
        resp = wp.build_pin_response(wp.hex_to_address("001E35AABBCC"), pin)
        self.assertEqual(bytes(resp.u.pinInfo.pin[:6]), pin)
        self.assertEqual(resp.u.pinInfo.pinLength, 6)

    def test_uses_legacy_auth_method_and_positive_response(self):
        resp = wp.build_pin_response(wp.hex_to_address("001E35AABBCC"), b"\x01\x02")
        self.assertEqual(resp.authMethod, wp.AUTH_METHOD_LEGACY)
        self.assertEqual(resp.negativeResponse, 0)

    def test_address_is_carried_through(self):
        resp = wp.build_pin_response(wp.hex_to_address("001E35AABBCC"), b"\x01")
        self.assertEqual(wp.address_to_hex(resp.bthAddressRemote), "001E35AABBCC")

    def test_unused_pin_slots_stay_zero(self):
        resp = wp.build_pin_response(wp.hex_to_address("001E35AABBCC"), b"\xAA\xBB")
        self.assertEqual(bytes(resp.u.pinInfo.pin[2:]), b"\x00" * 14)

    def test_rejects_out_of_range_lengths(self):
        addr = wp.hex_to_address("001E35AABBCC")
        for bad in (b"", b"\x01" * 17):
            with self.assertRaises(ValueError):
                wp.build_pin_response(addr, bad)


class TestBoardIdentification(unittest.TestCase):
    def test_matches_by_name(self):
        self.assertTrue(wp.looks_like_balance_board("Nintendo RVL-WBC-01", ""))
        self.assertTrue(wp.looks_like_balance_board("Wii Balance Board", ""))

    def test_matches_by_nintendo_oui_when_name_is_blank(self):
        """Windows often reports an empty name for a freshly-synced board."""
        self.assertTrue(wp.looks_like_balance_board("", "001E35AABBCC"))

    def test_rejects_unrelated_devices(self):
        self.assertFalse(wp.looks_like_balance_board("Ultimarc BlueHID",
                                                     "AABBCCDDEEFF"))
        self.assertFalse(wp.looks_like_balance_board("", "AABBCCDDEEFF"))


class TestErrorText(unittest.TestCase):
    def test_known_codes_are_explained(self):
        self.assertIn("1244", wp.describe_error(wp.ERROR_NOT_AUTHENTICATED))
        self.assertIn("timed out", wp.describe_error(wp.WAIT_TIMEOUT))

    def test_unknown_code_still_readable(self):
        self.assertEqual(wp.describe_error(999999), "Win32 error 999999")


class TestPlatformGuards(unittest.TestCase):
    def test_non_windows_degrades_cleanly(self):
        """Every entry point must be safe to call on Linux/macOS -- the module
        is imported unconditionally by the pressure package."""
        if sys.platform == "win32":
            self.skipTest("Windows has the real API")
        self.assertFalse(wp.is_available())
        self.assertEqual(wp.list_radios(), [])
        self.assertIsNone(wp.get_live_radio_mac())
        self.assertEqual(wp.find_balance_boards(), [])

    def test_pair_returns_failure_dict_not_exception(self):
        if sys.platform == "win32":
            self.skipTest("Windows has the real API")
        result = wp.pair_balance_board(log=lambda *a: None)
        self.assertFalse(result["success"])
        self.assertTrue(result["message"])


if __name__ == "__main__":
    unittest.main()
