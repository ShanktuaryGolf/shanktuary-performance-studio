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
import time
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

    def test_busy_is_explained_as_already_paired(self):
        """Reported from a real run: error 170 with 'Windows never asked us for
        the PIN'. That reads like a failure but means the bond already exists."""
        self.assertEqual(wp.ERROR_BUSY, 170)
        self.assertIn("already paired", wp.describe_error(wp.ERROR_BUSY))

    def test_unknown_code_still_readable(self):
        self.assertEqual(wp.describe_error(999999), "Win32 error 999999")


class TestAlreadyPairedBoard(unittest.TestCase):
    """A board that is already bonded must not be re-authenticated. Windows
    answers ERROR_BUSY and never asks for a PIN; what the board actually needs
    is its HID service enabled so hidapi can see it."""

    def _board(self, **over):
        b = {"address": "CC9E004CE1F9", "name": "Nintendo RVL-WBC-01",
             "authenticated": True, "remembered": True, "connected": False,
             "radio_address": "38FC983BB4DC", "radio_handle": 1}
        b.update(over)
        return b

    def test_already_paired_board_skips_authentication(self):
        from unittest import mock
        calls = {"hid": 0}

        def _fake_enable(_h, _i):
            calls["hid"] += 1
            return wp.ERROR_SUCCESS

        with mock.patch.object(wp, "is_available", return_value=True), \
                mock.patch.object(wp, "list_radios",
                                  return_value=[{"handle": 1,
                                                 "address": "38FC983BB4DC",
                                                 "name": "r"}]), \
                mock.patch.object(wp, "find_balance_boards",
                                  return_value=[self._board()]), \
                mock.patch.object(wp, "_device_info_for",
                                  return_value=wp.BLUETOOTH_DEVICE_INFO()), \
                mock.patch.object(wp, "enable_hid_service", _fake_enable), \
                mock.patch.object(wp, "pair_via_callback") as auth:
            result = wp.pair_balance_board(log=lambda *a: None)

        self.assertTrue(result["success"], result["message"])
        self.assertEqual(result["method"], "already_paired")
        self.assertEqual(calls["hid"], 1, "HID service was not enabled")
        auth.assert_not_called()

    def test_unpaired_board_still_authenticates(self):
        """The shortcut must not swallow the normal first-time pairing path."""
        from unittest import mock
        with mock.patch.object(wp, "is_available", return_value=True), \
                mock.patch.object(wp, "list_radios",
                                  return_value=[{"handle": 1,
                                                 "address": "38FC983BB4DC",
                                                 "name": "r"}]), \
                mock.patch.object(wp, "find_balance_boards",
                                  return_value=[self._board(authenticated=False,
                                                            remembered=False)]), \
                mock.patch.object(wp, "pair_via_callback",
                                  return_value=(True, "paired")) as auth:
            result = wp.pair_balance_board(log=lambda *a: None)

        self.assertTrue(result["success"])
        auth.assert_called_once()

    def test_already_paired_failure_does_not_retry_legacy_route(self):
        """The legacy route drives the same stack, so retrying an 'already
        paired' refusal just reproduces it and doubles the log noise."""
        from unittest import mock
        with mock.patch.object(wp, "is_available", return_value=True), \
                mock.patch.object(wp, "list_radios",
                                  return_value=[{"handle": 1,
                                                 "address": "38FC983BB4DC",
                                                 "name": "r"}]), \
                mock.patch.object(wp, "find_balance_boards",
                                  return_value=[self._board(authenticated=False)]), \
                mock.patch.object(
                    wp, "pair_via_callback",
                    return_value=(False, "board is already paired but ...")), \
                mock.patch.object(wp, "pair_via_legacy") as legacy:
            result = wp.pair_balance_board(log=lambda *a: None)

        self.assertFalse(result["success"])
        legacy.assert_not_called()

    def test_forget_existing_defaults_to_false(self):
        """Tearing down a working bond on every button click is destructive,
        and it also skipped the already-paired shortcut entirely."""
        import inspect
        sig = inspect.signature(wp.pair_balance_board)
        self.assertIs(sig.parameters["forget_existing"].default, False)


class TestBusyRecovery(unittest.TestCase):
    """The reported failure: ERROR_BUSY (170) with 'Windows never asked us for
    the PIN', on a board the inquiry reported as NOT authenticated. Windows was
    holding a bond the device record did not admit to."""

    def _setup(self, hid_result):
        from unittest import mock
        lib = mock.MagicMock()
        lib.BluetoothRegisterForAuthenticationEx.return_value = wp.ERROR_SUCCESS
        lib.BluetoothAuthenticateDeviceEx.return_value = wp.ERROR_BUSY
        device = {"address": "CC9E004CE1F9", "radio_handle": 1,
                  "radio_address": "38FC983BB4DC"}
        info = wp.BLUETOOTH_DEVICE_INFO()
        info.fAuthenticated = 0      # exactly what the reported run saw
        return lib, device, info, hid_result

    def test_busy_enables_hid_without_trusting_the_authenticated_flag(self):
        from unittest import mock
        lib, device, info, _ = self._setup(wp.ERROR_SUCCESS)
        with mock.patch.object(wp, "_api", return_value=lib), \
                mock.patch.object(wp, "_device_info_for", return_value=info), \
                mock.patch.object(wp, "enable_hid_service",
                                  return_value=wp.ERROR_SUCCESS):
            ok, msg = wp.pair_via_callback(device, b"\x01\x02\x03\x04\x05\x06",
                                           log=lambda *a: None)
        self.assertTrue(ok, msg)
        self.assertIn("already paired", msg)

    def test_busy_with_failed_hid_enable_clears_the_stale_bond(self):
        """Self-healing: leaving the user with an unusable bond and no way
        forward is how this bug stayed stuck across restarts."""
        from unittest import mock
        lib, device, info, _ = self._setup(wp.ERROR_NOT_FOUND)
        with mock.patch.object(wp, "_api", return_value=lib), \
                mock.patch.object(wp, "_device_info_for", return_value=info), \
                mock.patch.object(wp, "enable_hid_service",
                                  return_value=wp.ERROR_NOT_FOUND), \
                mock.patch.object(wp, "remove_device",
                                  return_value=wp.ERROR_SUCCESS) as rm:
            ok, msg = wp.pair_via_callback(device, b"\x01\x02\x03\x04\x05\x06",
                                           log=lambda *a: None)
        self.assertFalse(ok)
        rm.assert_called_once_with("CC9E004CE1F9")
        self.assertIn("press SYNC", msg)


class TestAuthTimeout(unittest.TestCase):
    """Reported: the console stopped dead after 'Found Nintendo RVL-WBC-01'
    and the board never paired.

    BluetoothAuthenticateDeviceEx blocks with no timeout of its own and logs
    nothing while it waits, so a stall there is indistinguishable from a crash
    -- and it can outlast the ~20s the board stays awake after SYNC.
    """

    def _lib(self, block_for):
        from unittest import mock
        lib = mock.MagicMock()
        lib.BluetoothRegisterForAuthenticationEx.return_value = wp.ERROR_SUCCESS

        def _slow_auth(*a, **k):
            time.sleep(block_for)
            return wp.ERROR_SUCCESS

        lib.BluetoothAuthenticateDeviceEx.side_effect = _slow_auth
        return lib

    def test_blocking_call_is_bounded(self):
        from unittest import mock
        lib = self._lib(block_for=5.0)
        device = {"address": "0024446AEBFC", "radio_handle": 1,
                  "radio_address": "38FC983BB4DC"}
        started = time.time()
        with mock.patch.object(wp, "_api", return_value=lib), \
                mock.patch.object(wp, "_device_info_for",
                                  return_value=wp.BLUETOOTH_DEVICE_INFO()):
            ok, msg = wp.pair_via_callback(device, b"\x01\x02\x03\x04\x05\x06",
                                           log=lambda *a: None,
                                           auth_timeout=0.5)
        elapsed = time.time() - started

        self.assertFalse(ok)
        self.assertLess(elapsed, 3.0,
                        "pairing hung past its timeout; the UI would freeze")
        self.assertIn("SYNC again", msg,
                      "timeout message should tell the user what to do")

    def test_timeout_keeps_the_callback_alive(self):
        """Unregistering while Windows may still call back would hand it a
        dangling pointer."""
        from unittest import mock
        lib = self._lib(block_for=3.0)
        device = {"address": "0024446AEBFC", "radio_handle": 1,
                  "radio_address": "38FC983BB4DC"}
        before = len(wp._ORPHANED_AUTH)
        with mock.patch.object(wp, "_api", return_value=lib), \
                mock.patch.object(wp, "_device_info_for",
                                  return_value=wp.BLUETOOTH_DEVICE_INFO()):
            wp.pair_via_callback(device, b"\x01\x02\x03\x04\x05\x06",
                                 log=lambda *a: None, auth_timeout=0.3)

        self.assertEqual(len(wp._ORPHANED_AUTH), before + 1)
        lib.BluetoothUnregisterAuthentication.assert_not_called()

    def test_progress_is_logged_while_waiting(self):
        """A silent stall is what made this impossible to diagnose."""
        from unittest import mock
        lines = []
        lib = self._lib(block_for=0.05)
        device = {"address": "0024446AEBFC", "radio_handle": 1,
                  "radio_address": "38FC983BB4DC"}
        info = wp.BLUETOOTH_DEVICE_INFO()
        info.fAuthenticated = 1
        with mock.patch.object(wp, "_api", return_value=lib), \
                mock.patch.object(wp, "_device_info_for", return_value=info), \
                mock.patch.object(wp, "enable_hid_service",
                                  return_value=wp.ERROR_SUCCESS):
            wp.pair_via_callback(device, b"\x01\x02\x03\x04\x05\x06",
                                 log=lines.append, auth_timeout=5.0)

        blob = " ".join(lines)
        self.assertIn("Authenticating with the board", blob,
                      "no log line before the blocking call")
        self.assertIn("Authentication returned", blob,
                      "no log line after the blocking call")


class TestDiscoveryOrder(unittest.TestCase):
    """The board answers for only ~20s after SYNC. A 10s inquiry before
    authentication can spend most of that window, so the cached device list is
    checked first."""

    def test_cached_lookup_is_tried_before_inquiry(self):
        from unittest import mock
        calls = []

        def _find(timeout_mult=4, include_known=True, issue_inquiry=True):
            calls.append(issue_inquiry)
            return [{"address": "0024446AEBFC", "name": "Nintendo RVL-WBC-01",
                     "authenticated": False, "remembered": False,
                     "connected": False, "radio_address": "38FC983BB4DC",
                     "radio_handle": 1}]

        with mock.patch.object(wp, "is_available", return_value=True), \
                mock.patch.object(wp, "list_radios",
                                  return_value=[{"handle": 1,
                                                 "address": "38FC983BB4DC",
                                                 "name": "r"}]), \
                mock.patch.object(wp, "find_balance_boards", _find), \
                mock.patch.object(wp, "pair_via_callback",
                                  return_value=(True, "paired")):
            wp.pair_balance_board(log=lambda *a: None)

        self.assertEqual(calls[0], False,
                         "first lookup should be the instant cached one")
        self.assertEqual(len(calls), 1,
                         "an unpaired board was cached; no inquiry needed")

    def test_falls_back_to_inquiry_when_cache_has_nothing_new(self):
        from unittest import mock
        calls = []

        def _find(timeout_mult=4, include_known=True, issue_inquiry=True):
            calls.append(issue_inquiry)
            if issue_inquiry:
                return [{"address": "0024446AEBFC", "name": "b",
                         "authenticated": False, "remembered": False,
                         "connected": False, "radio_address": "38FC983BB4DC",
                         "radio_handle": 1}]
            return []          # nothing cached

        with mock.patch.object(wp, "is_available", return_value=True), \
                mock.patch.object(wp, "list_radios",
                                  return_value=[{"handle": 1,
                                                 "address": "38FC983BB4DC",
                                                 "name": "r"}]), \
                mock.patch.object(wp, "find_balance_boards", _find), \
                mock.patch.object(wp, "pair_via_callback",
                                  return_value=(True, "paired")):
            result = wp.pair_balance_board(log=lambda *a: None)

        self.assertEqual(calls, [False, True])
        self.assertTrue(result["success"])


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
