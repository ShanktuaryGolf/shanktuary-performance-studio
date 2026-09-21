"""Native Windows Bluetooth pairing for the Wii Balance Board.

Why this module exists
----------------------
The board's pairing PIN is **six raw binary bytes** (the host radio's address
in reverse), not text. Windows' "Add a device" PIN box is a text edit control:

  * it refuses control characters (0x00-0x1F), so any host MAC whose reversed
    bytes contain one -- e.g. ``00:E0:4C:00:00:01`` -> ``01 00 00 4C E0 00`` --
    is literally unenterable, and
  * whatever you do type is encoded to bytes before transmission, so a high
    byte such as 0xDC goes out as UTF-8 ``C3 9C`` and the PIN is wrong anyway.

So "copy the PIN and paste it into Bluetooth settings" cannot work in general;
it only succeeds by luck when all six bytes happen to be printable ASCII.
WiiBrew states the same: Wiimote/Balance Board PINs are binary and OS pairing
prompts that expect strings generally cannot be used.

The fix is to never involve the text box. ``BluetoothRegisterForAuthenticationEx``
hands us a callback and ``BLUETOOTH_AUTHENTICATE_RESPONSE.pinInfo`` carries the
PIN as ``UCHAR pin[16]`` plus an explicit length -- raw bytes, NULs and all.

Two strategies are implemented, tried in order:

  1. ``pair_via_callback``  -- Register-for-auth + AuthenticateDeviceEx, answer
     with raw PIN bytes. Byte-exact; the only correct route.
  2. ``pair_via_legacy``    -- ``BluetoothAuthenticateDevice`` with a WCHAR
     passkey buffer (what 32feet.NET / WiiBalanceWalker do). Kept as a fallback
     because it is widely reported to work on some stacks, but Windows narrows
     those WCHARs to bytes itself, which can mangle 0x80-0x9F. Never preferred.

Everything is ctypes -- no new dependency. Structures use explicit-width types
so the fixed-width ones (auth response, PIN info, search params) have
Windows-exact layout on any host and can be unit-tested from Linux. Structures
containing ``c_wchar`` are larger off Windows (4-byte wchar vs 2) and are only
size-correct at runtime on Windows, which is the only place they are used.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import (
    POINTER,
    byref,
    c_int,
    c_uint8,
    c_uint16,
    c_uint32,
    c_uint64,
    c_void_p,
    c_wchar,
    sizeof,
)

IS_WINDOWS = sys.platform == "win32"

BLUETOOTH_MAX_NAME_SIZE = 248
BTH_MAX_PIN_SIZE = 16

# BLUETOOTH_AUTHENTICATION_METHOD
AUTH_METHOD_LEGACY = 1
AUTH_METHOD_OOB = 2
AUTH_METHOD_NUMERIC_COMPARISON = 3
AUTH_METHOD_PASSKEY_NOTIFICATION = 4
AUTH_METHOD_PASSKEY = 5

# BLUETOOTH_AUTHENTICATION_REQUIREMENTS
MITM_PROTECTION_NOT_REQUIRED = 0

BLUETOOTH_SERVICE_DISABLE = 0x00
BLUETOOTH_SERVICE_ENABLE = 0x01

ERROR_SUCCESS = 0
ERROR_INVALID_PARAMETER = 87
ERROR_BUSY = 170
ERROR_NOT_AUTHENTICATED = 1244
ERROR_NO_MORE_ITEMS = 259
WAIT_TIMEOUT = 258
ERROR_DEVICE_NOT_CONNECTED = 1167
ERROR_NOT_FOUND = 1168

#: Nintendo's Bluetooth OUI for Wii accessories.
NINTENDO_OUI = (0x00, 0x1E, 0x35)
BOARD_NAME_HINTS = ("rvl-wbc", "balance")

_ERROR_TEXT = {
    ERROR_SUCCESS: "success",
    ERROR_INVALID_PARAMETER: "invalid parameter (87)",
    ERROR_BUSY: "the board is already paired to this PC (170)",
    ERROR_NOT_AUTHENTICATED: "authentication failed / wrong PIN (1244)",
    ERROR_NO_MORE_ITEMS: "no more items (259)",
    WAIT_TIMEOUT: "timed out waiting for the board (258)",
    ERROR_DEVICE_NOT_CONNECTED: "device not connected (1167)",
    ERROR_NOT_FOUND: "device not found (1168)",
}


def describe_error(code: int) -> str:
    """Human-readable text for a Win32 error code from the Bluetooth APIs."""
    if code in _ERROR_TEXT:
        return _ERROR_TEXT[code]
    return f"Win32 error {code}"


# --------------------------------------------------------------------------
# Structures. Explicit-width fields only -- c_long/c_ulong differ between
# Linux LP64 and Windows LLP64 and would silently change sizeof(), which
# Windows validates through the dwSize members.
# --------------------------------------------------------------------------

class BLUETOOTH_ADDRESS(ctypes.Union):
    _fields_ = [("ullLong", c_uint64), ("rgBytes", c_uint8 * 6)]


class SYSTEMTIME(ctypes.Structure):
    _fields_ = [
        ("wYear", c_uint16), ("wMonth", c_uint16), ("wDayOfWeek", c_uint16),
        ("wDay", c_uint16), ("wHour", c_uint16), ("wMinute", c_uint16),
        ("wSecond", c_uint16), ("wMilliseconds", c_uint16),
    ]


class BLUETOOTH_DEVICE_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", c_uint32),
        ("Address", BLUETOOTH_ADDRESS),
        ("ulClassofDevice", c_uint32),
        ("fConnected", c_uint32),
        ("fRemembered", c_uint32),
        ("fAuthenticated", c_uint32),
        ("stLastSeen", SYSTEMTIME),
        ("stLastUsed", SYSTEMTIME),
        ("szName", c_wchar * BLUETOOTH_MAX_NAME_SIZE),
    ]


class BLUETOOTH_DEVICE_SEARCH_PARAMS(ctypes.Structure):
    _fields_ = [
        ("dwSize", c_uint32),
        ("fReturnAuthenticated", c_uint32),
        ("fReturnRemembered", c_uint32),
        ("fReturnUnknown", c_uint32),
        ("fReturnConnected", c_uint32),
        ("fIssueInquiry", c_uint32),
        ("cTimeoutMultiplier", c_uint8),
        ("hRadio", c_void_p),
    ]


class BLUETOOTH_FIND_RADIO_PARAMS(ctypes.Structure):
    _fields_ = [("dwSize", c_uint32)]


class BLUETOOTH_RADIO_INFO(ctypes.Structure):
    _fields_ = [
        ("dwSize", c_uint32),
        ("address", BLUETOOTH_ADDRESS),
        ("szName", c_wchar * BLUETOOTH_MAX_NAME_SIZE),
        ("ulClassofDevice", c_uint32),
        ("lmpSubversion", c_uint16),
        ("manufacturer", c_uint16),
    ]


class BLUETOOTH_PIN_INFO(ctypes.Structure):
    _fields_ = [("pin", c_uint8 * BTH_MAX_PIN_SIZE), ("pinLength", c_uint8)]


class BLUETOOTH_OOB_DATA_INFO(ctypes.Structure):
    _fields_ = [("C", c_uint8 * 16), ("R", c_uint8 * 16)]


class BLUETOOTH_NUMERIC_COMPARISON_INFO(ctypes.Structure):
    _fields_ = [("NumericValue", c_uint32)]


class BLUETOOTH_PASSKEY_INFO(ctypes.Structure):
    _fields_ = [("passkey", c_uint32)]


class _AUTH_RESPONSE_UNION(ctypes.Union):
    _fields_ = [
        ("pinInfo", BLUETOOTH_PIN_INFO),
        ("oobInfo", BLUETOOTH_OOB_DATA_INFO),
        ("numericCompInfo", BLUETOOTH_NUMERIC_COMPARISON_INFO),
        ("passkeyInfo", BLUETOOTH_PASSKEY_INFO),
    ]


class BLUETOOTH_AUTHENTICATE_RESPONSE(ctypes.Structure):
    _fields_ = [
        ("bthAddressRemote", BLUETOOTH_ADDRESS),
        ("authMethod", c_uint32),
        ("u", _AUTH_RESPONSE_UNION),
        ("negativeResponse", c_uint8),
    ]


class _AUTH_PARAMS_UNION(ctypes.Union):
    _fields_ = [("Numeric_Value", c_uint32), ("Passkey", c_uint32)]


class BLUETOOTH_AUTHENTICATION_CALLBACK_PARAMS(ctypes.Structure):
    _fields_ = [
        ("deviceInfo", BLUETOOTH_DEVICE_INFO),
        ("authenticationMethod", c_uint32),
        ("ioCapability", c_uint32),
        ("authenticationRequirements", c_uint32),
        ("u", _AUTH_PARAMS_UNION),
    ]


class GUID(ctypes.Structure):
    # Data4 is c_uint8*8, not c_char*8: a c_char array reads back truncated at
    # its first NUL, and this GUID's Data4 starts 80 00 00 -- the stored bytes
    # would be right but every read of them would lie.
    _fields_ = [
        ("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16),
        ("Data4", c_uint8 * 8),
    ]


#: HumanInterfaceDeviceServiceClass_UUID -- enabling this is what makes the
#: paired board show up to hidapi as an HID device.
HID_SERVICE_GUID = GUID(0x00001124, 0x0000, 0x1000,
                        (c_uint8 * 8)(0x80, 0x00, 0x00, 0x80,
                                      0x5F, 0x9B, 0x34, 0xFB))


def _auth_callback_type():
    """BOOL CALLBACK(LPVOID, PBLUETOOTH_AUTHENTICATION_CALLBACK_PARAMS)."""
    factory = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
    return factory(c_int, c_void_p,
                   POINTER(BLUETOOTH_AUTHENTICATION_CALLBACK_PARAMS))


# --------------------------------------------------------------------------
# Windows-only bindings
# --------------------------------------------------------------------------

_bt = None


def _api():
    """Return the bound bthprops.cpl module, or None when unavailable."""
    global _bt
    if _bt is not None:
        return _bt
    if not IS_WINDOWS:
        return None
    # getattr, not ctypes.WinDLL directly: the attribute does not exist off
    # Windows and a bare reference trips static analysis on the dev machines.
    windll_factory = getattr(ctypes, "WinDLL", None)
    if windll_factory is None:
        return None
    try:
        lib = windll_factory("bthprops.cpl")
    except OSError:
        return None

    lib.BluetoothFindFirstRadio.argtypes = [
        POINTER(BLUETOOTH_FIND_RADIO_PARAMS), POINTER(c_void_p)]
    lib.BluetoothFindFirstRadio.restype = c_void_p
    lib.BluetoothFindNextRadio.argtypes = [c_void_p, POINTER(c_void_p)]
    lib.BluetoothFindNextRadio.restype = c_int
    lib.BluetoothFindRadioClose.argtypes = [c_void_p]
    lib.BluetoothFindRadioClose.restype = c_int

    lib.BluetoothGetRadioInfo.argtypes = [c_void_p, POINTER(BLUETOOTH_RADIO_INFO)]
    lib.BluetoothGetRadioInfo.restype = c_uint32

    lib.BluetoothFindFirstDevice.argtypes = [
        POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS), POINTER(BLUETOOTH_DEVICE_INFO)]
    lib.BluetoothFindFirstDevice.restype = c_void_p
    lib.BluetoothFindNextDevice.argtypes = [c_void_p, POINTER(BLUETOOTH_DEVICE_INFO)]
    lib.BluetoothFindNextDevice.restype = c_int
    lib.BluetoothFindDeviceClose.argtypes = [c_void_p]
    lib.BluetoothFindDeviceClose.restype = c_int

    lib.BluetoothRemoveDevice.argtypes = [POINTER(BLUETOOTH_ADDRESS)]
    lib.BluetoothRemoveDevice.restype = c_uint32

    lib.BluetoothSetServiceState.argtypes = [
        c_void_p, POINTER(BLUETOOTH_DEVICE_INFO), POINTER(GUID), c_uint32]
    lib.BluetoothSetServiceState.restype = c_uint32

    lib.BluetoothRegisterForAuthenticationEx.argtypes = [
        POINTER(BLUETOOTH_DEVICE_INFO), POINTER(c_void_p),
        _auth_callback_type(), c_void_p]
    lib.BluetoothRegisterForAuthenticationEx.restype = c_uint32
    lib.BluetoothUnregisterAuthentication.argtypes = [c_void_p]
    lib.BluetoothUnregisterAuthentication.restype = c_int

    lib.BluetoothSendAuthenticationResponseEx.argtypes = [
        c_void_p, POINTER(BLUETOOTH_AUTHENTICATE_RESPONSE)]
    lib.BluetoothSendAuthenticationResponseEx.restype = c_uint32

    lib.BluetoothAuthenticateDeviceEx.argtypes = [
        c_void_p, c_void_p, POINTER(BLUETOOTH_DEVICE_INFO),
        POINTER(BLUETOOTH_OOB_DATA_INFO), c_uint32]
    lib.BluetoothAuthenticateDeviceEx.restype = c_uint32

    lib.BluetoothAuthenticateDevice.argtypes = [
        c_void_p, c_void_p, POINTER(BLUETOOTH_DEVICE_INFO),
        POINTER(c_wchar), c_uint32]
    lib.BluetoothAuthenticateDevice.restype = c_uint32

    _bt = lib
    return _bt


def is_available() -> bool:
    """True when native pairing can be attempted on this machine."""
    return _api() is not None


# --------------------------------------------------------------------------
# Address helpers
# --------------------------------------------------------------------------

def address_to_hex(addr: BLUETOOTH_ADDRESS) -> str:
    """BLUETOOTH_ADDRESS -> 'AABBCCDDEEFF' (display order, high byte first)."""
    return "".join(f"{b:02X}" for b in reversed(list(addr.rgBytes)))


def hex_to_address(mac_hex: str) -> BLUETOOTH_ADDRESS:
    """'AABBCCDDEEFF' -> BLUETOOTH_ADDRESS."""
    raw = mac_hex.replace(":", "").replace("-", "").upper()
    if len(raw) != 12:
        raise ValueError(f"not a 12-hex-digit MAC: {mac_hex!r}")
    data = bytes.fromhex(raw)
    addr = BLUETOOTH_ADDRESS()
    for i, b in enumerate(reversed(data)):
        addr.rgBytes[i] = b
    return addr


def pin_bytes_for_host(host_mac_hex: str) -> bytes:
    """Host adapter MAC -> the board's 6-byte pairing PIN (address reversed)."""
    raw = host_mac_hex.replace(":", "").replace("-", "").upper()
    if len(raw) != 12:
        return b""
    return bytes(reversed(bytes.fromhex(raw)))


def looks_like_balance_board(name: str, addr_hex: str) -> bool:
    """Match by Nintendo OUI or product name -- either alone is enough."""
    lowered = (name or "").lower()
    if any(hint in lowered for hint in BOARD_NAME_HINTS):
        return True
    raw = (addr_hex or "").replace(":", "").upper()
    if len(raw) == 12:
        prefix = tuple(bytes.fromhex(raw[:6]))
        if prefix == NINTENDO_OUI:
            return True
    return False


# --------------------------------------------------------------------------
# Radios
# --------------------------------------------------------------------------

def _iter_radio_handles():
    """Yield every local Bluetooth radio handle, closing the finder after."""
    lib = _api()
    if lib is None:
        return
    params = BLUETOOTH_FIND_RADIO_PARAMS(sizeof(BLUETOOTH_FIND_RADIO_PARAMS))
    handle = c_void_p()
    finder = lib.BluetoothFindFirstRadio(byref(params), byref(handle))
    if not finder:
        return
    try:
        while True:
            yield handle.value
            nxt = c_void_p()
            if not lib.BluetoothFindNextRadio(finder, byref(nxt)):
                break
            handle = nxt
    finally:
        lib.BluetoothFindRadioClose(finder)


def list_radios() -> list[dict]:
    """Every *live* local Bluetooth radio: address, name, handle.

    The registry's ``BTHPORT\\Parameters\\LocalDeviceAddress`` can be stale
    from a radio that is no longer installed -- which yields a PIN that can
    never pair. This asks the driver stack what is actually present.
    """
    lib = _api()
    if lib is None:
        return []
    out = []
    for h in _iter_radio_handles():
        info = BLUETOOTH_RADIO_INFO()
        info.dwSize = sizeof(BLUETOOTH_RADIO_INFO)
        if lib.BluetoothGetRadioInfo(h, byref(info)) == ERROR_SUCCESS:
            out.append({
                "handle": h,
                "address": address_to_hex(info.address),
                "name": info.szName,
            })
    return out


def get_live_radio_mac() -> str | None:
    """Address of the first live radio as 12-char hex, or None."""
    radios = list_radios()
    return radios[0]["address"] if radios else None


# --------------------------------------------------------------------------
# Device discovery
# --------------------------------------------------------------------------

def find_balance_boards(timeout_mult: int = 4,
                        include_known: bool = True) -> list[dict]:
    """Inquire for Wii Balance Boards.

    ``timeout_mult`` is in units of 1.28 s (Windows caps it at 48). The board
    only answers an inquiry for ~20 s after SYNC is pressed, so the caller must
    prompt for SYNC immediately before this runs.
    """
    lib = _api()
    if lib is None:
        return []
    timeout_mult = max(1, min(48, int(timeout_mult)))

    found: dict[str, dict] = {}
    for radio in list_radios():
        sp = BLUETOOTH_DEVICE_SEARCH_PARAMS()
        sp.dwSize = sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS)
        sp.fReturnAuthenticated = 1 if include_known else 0
        sp.fReturnRemembered = 1 if include_known else 0
        sp.fReturnUnknown = 1
        sp.fReturnConnected = 1 if include_known else 0
        sp.fIssueInquiry = 1
        sp.cTimeoutMultiplier = timeout_mult
        sp.hRadio = radio["handle"]

        info = BLUETOOTH_DEVICE_INFO()
        info.dwSize = sizeof(BLUETOOTH_DEVICE_INFO)
        finder = lib.BluetoothFindFirstDevice(byref(sp), byref(info))
        if not finder:
            continue
        try:
            while True:
                addr_hex = address_to_hex(info.Address)
                if looks_like_balance_board(info.szName, addr_hex):
                    found.setdefault(addr_hex, {
                        "address": addr_hex,
                        "name": info.szName,
                        "authenticated": bool(info.fAuthenticated),
                        "remembered": bool(info.fRemembered),
                        "connected": bool(info.fConnected),
                        "radio_address": radio["address"],
                        "radio_handle": radio["handle"],
                    })
                nxt = BLUETOOTH_DEVICE_INFO()
                nxt.dwSize = sizeof(BLUETOOTH_DEVICE_INFO)
                if not lib.BluetoothFindNextDevice(finder, byref(nxt)):
                    break
                info = nxt
        finally:
            lib.BluetoothFindDeviceClose(finder)
    return list(found.values())


def remove_device(mac_hex: str) -> int:
    """Forget a bond. A stale/half-finished bond makes Windows refuse to
    re-pair with 'Try connecting your device again', so removing it first is
    part of a reliable retry."""
    lib = _api()
    if lib is None:
        return ERROR_NOT_FOUND
    addr = hex_to_address(mac_hex)
    return int(lib.BluetoothRemoveDevice(byref(addr)))


def enable_hid_service(radio_handle, device_info: BLUETOOTH_DEVICE_INFO) -> int:
    """Turn on the HID service so the board enumerates for hidapi."""
    lib = _api()
    if lib is None:
        return ERROR_NOT_FOUND
    return int(lib.BluetoothSetServiceState(
        radio_handle, byref(device_info), byref(HID_SERVICE_GUID),
        BLUETOOTH_SERVICE_ENABLE))


def _device_info_for(mac_hex: str, radio_handle) -> BLUETOOTH_DEVICE_INFO | None:
    """Re-read a device record straight from the cache (no inquiry)."""
    lib = _api()
    if lib is None:
        return None
    sp = BLUETOOTH_DEVICE_SEARCH_PARAMS()
    sp.dwSize = sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS)
    sp.fReturnAuthenticated = 1
    sp.fReturnRemembered = 1
    sp.fReturnUnknown = 1
    sp.fReturnConnected = 1
    sp.fIssueInquiry = 0
    sp.cTimeoutMultiplier = 0
    sp.hRadio = radio_handle

    info = BLUETOOTH_DEVICE_INFO()
    info.dwSize = sizeof(BLUETOOTH_DEVICE_INFO)
    finder = lib.BluetoothFindFirstDevice(byref(sp), byref(info))
    if not finder:
        return None
    try:
        target = mac_hex.replace(":", "").upper()
        while True:
            if address_to_hex(info.Address) == target:
                return info
            nxt = BLUETOOTH_DEVICE_INFO()
            nxt.dwSize = sizeof(BLUETOOTH_DEVICE_INFO)
            if not lib.BluetoothFindNextDevice(finder, byref(nxt)):
                return None
            info = nxt
    finally:
        lib.BluetoothFindDeviceClose(finder)


# --------------------------------------------------------------------------
# Pairing strategies
# --------------------------------------------------------------------------

def build_pin_response(device_addr: BLUETOOTH_ADDRESS,
                       pin: bytes) -> BLUETOOTH_AUTHENTICATE_RESPONSE:
    """Fill a legacy-PIN authentication response with raw PIN bytes.

    Split out from the callback so the byte packing -- the part that the
    Windows text box destroys -- is unit-testable off Windows.
    """
    if not 1 <= len(pin) <= BTH_MAX_PIN_SIZE:
        raise ValueError(f"PIN must be 1..{BTH_MAX_PIN_SIZE} bytes, got {len(pin)}")
    resp = BLUETOOTH_AUTHENTICATE_RESPONSE()
    resp.bthAddressRemote = device_addr
    resp.authMethod = AUTH_METHOD_LEGACY
    resp.negativeResponse = 0
    for i, b in enumerate(pin):
        resp.u.pinInfo.pin[i] = b
    resp.u.pinInfo.pinLength = len(pin)
    return resp


def pair_via_callback(device: dict, pin: bytes, log=print) -> tuple[bool, str]:
    """Preferred route: answer the auth request with raw PIN bytes.

    ``BLUETOOTH_PIN_INFO`` carries ``UCHAR pin[16]`` plus an explicit length,
    so NUL bytes and high bytes survive exactly -- unlike anything typed or
    pasted into the Windows PIN box.
    """
    lib = _api()
    if lib is None:
        return False, "Bluetooth API unavailable"

    radio_handle = device["radio_handle"]
    info = _device_info_for(device["address"], radio_handle)
    if info is None:
        return False, "board disappeared before pairing could start"

    state = {"answered": False, "send_result": None}
    target = device["address"].upper()

    def _callback(_param, params_ptr):
        try:
            params = params_ptr.contents
            addr_hex = address_to_hex(params.deviceInfo.Address)
            if addr_hex.upper() != target:
                return 0
            method = params.authenticationMethod
            if method != AUTH_METHOD_LEGACY:
                log(f"[!] Unexpected auth method {method} (expected legacy PIN)")
                return 0
            resp = build_pin_response(params.deviceInfo.Address, pin)
            res = lib.BluetoothSendAuthenticationResponseEx(radio_handle, byref(resp))
            state["answered"] = True
            state["send_result"] = int(res)
            log(f"[i] Sent {len(pin)}-byte PIN -> {describe_error(int(res))}")
            return 1
        except Exception as e:  # a crash here would take down the BT thread
            log(f"[!] Auth callback error: {e}")
            return 0

    cb = _auth_callback_type()(_callback)
    reg_handle = c_void_p()
    rc = lib.BluetoothRegisterForAuthenticationEx(
        byref(info), byref(reg_handle), cb, None)
    if rc != ERROR_SUCCESS:
        return False, f"could not register for authentication: {describe_error(rc)}"

    try:
        rc = lib.BluetoothAuthenticateDeviceEx(
            None, radio_handle, byref(info), None, MITM_PROTECTION_NOT_REQUIRED)
        if rc != ERROR_SUCCESS:
            # ERROR_BUSY means Windows already holds a bond for this device, so
            # it never asks us for a PIN. Note the device record from an
            # inquiry can still report fAuthenticated=0 while that bond exists
            # (the reported case), so do not trust that flag here: try to get
            # the HID service on, and if that fails drop the stale bond so the
            # caller can pair cleanly.
            if rc == ERROR_BUSY:
                fresh = _device_info_for(device["address"], radio_handle) or info
                svc = enable_hid_service(radio_handle, fresh)
                if svc == ERROR_SUCCESS:
                    return True, ("board was already paired; "
                                  "HID service re-enabled")
                log(f"[!] Board is bonded but HID enable failed: "
                    f"{describe_error(svc)}; clearing the stale bond.")
                rm = remove_device(device["address"])
                log(f"[i] Removed stale bond -> {describe_error(rm)}")
                return False, ("board held a stale Windows pairing, now "
                               "cleared — press SYNC and pair again")
            detail = describe_error(rc)
            if not state["answered"]:
                detail += " (Windows never asked us for the PIN)"
            return False, f"pairing failed: {detail}"
    finally:
        lib.BluetoothUnregisterAuthentication(reg_handle)

    fresh = _device_info_for(device["address"], radio_handle) or info
    if not fresh.fAuthenticated:
        return False, "Windows reported success but the board is not bonded"

    svc = enable_hid_service(radio_handle, fresh)
    if svc != ERROR_SUCCESS:
        return True, (f"paired, but enabling the HID service failed "
                      f"({describe_error(svc)}) — unplug/replug or re-run pairing")
    return True, "paired and HID service enabled"


def pair_via_legacy(device: dict, pin: bytes, log=print) -> tuple[bool, str]:
    """Fallback: ``BluetoothAuthenticateDevice`` with a WCHAR passkey buffer.

    This is what 32feet.NET and WiiBalanceWalker use. Windows narrows the
    WCHARs to PIN bytes itself, and that conversion is not guaranteed to be
    byte-identity for 0x80-0x9F, so it is only tried after the callback route.
    A fixed-size buffer (not c_wchar_p) is used deliberately: the length is
    passed explicitly, so embedded NULs are not treated as a terminator.
    """
    lib = _api()
    if lib is None:
        return False, "Bluetooth API unavailable"

    radio_handle = device["radio_handle"]
    info = _device_info_for(device["address"], radio_handle)
    if info is None:
        return False, "board disappeared before pairing could start"

    buf = (c_wchar * (BTH_MAX_PIN_SIZE + 1))()
    for i, b in enumerate(pin):
        buf[i] = chr(b)
    rc = lib.BluetoothAuthenticateDevice(None, radio_handle, byref(info),
                                         buf, len(pin))
    if rc != ERROR_SUCCESS:
        return False, f"legacy pairing failed: {describe_error(rc)}"

    fresh = _device_info_for(device["address"], radio_handle) or info
    svc = enable_hid_service(radio_handle, fresh)
    if svc != ERROR_SUCCESS:
        return True, (f"paired, but enabling the HID service failed "
                      f"({describe_error(svc)})")
    return True, "paired and HID service enabled (legacy route)"


def pair_balance_board(discovery_timeout_mult: int = 8,
                       forget_existing: bool = False,
                       log=print) -> dict:
    """Find a Wii Balance Board in SYNC mode and pair it end to end.

    ``forget_existing`` defaults to False: a board that is already bonded
    usually just needs its HID service re-enabled, and tearing down a working
    bond on every click is destructive. Pass True (the CLI's ``--forget``) to
    force a clean re-pair.

    The PIN is derived per radio from that radio's *live* address, so a stale
    registry value cannot poison it. Returns a result dict rather than raising
    so the UI can show something specific for every failure.
    """
    result = {
        "success": False,
        "message": "",
        "address": "",
        "radio_address": "",
        "method": "",
        "boards_seen": 0,
    }
    if not is_available():
        result["message"] = ("Native pairing needs the Windows Bluetooth API "
                             "(bthprops.cpl); not available on this system.")
        return result

    radios = list_radios()
    if not radios:
        result["message"] = "No Bluetooth radio found. Is Bluetooth switched on?"
        return result
    log(f"[i] Live Bluetooth radio(s): "
        f"{', '.join(r['address'] for r in radios)}")

    log("[i] Scanning for a Wii Balance Board — press the red SYNC button now.")
    boards = find_balance_boards(timeout_mult=discovery_timeout_mult)
    result["boards_seen"] = len(boards)
    if not boards:
        result["message"] = ("No balance board answered. Press SYNC inside the "
                             "battery compartment and retry within ~20s.")
        return result

    board = boards[0]
    result["address"] = board["address"]
    result["radio_address"] = board["radio_address"]
    log(f"[i] Found {board['name'] or 'board'} at {board['address']} "
        f"via radio {board['radio_address']}")

    # Already bonded? Then re-authenticating is the wrong move -- Windows
    # answers ERROR_BUSY (170) and never asks for a PIN, which looks like a
    # pairing failure but means the opposite. What such a board usually needs
    # is its HID service turned back on so hidapi can see it again.
    if board["authenticated"] and not forget_existing:
        log("[i] Board is already paired — enabling its HID service.")
        info = _device_info_for(board["address"], board["radio_handle"])
        if info is not None:
            svc = enable_hid_service(board["radio_handle"], info)
            if svc == ERROR_SUCCESS:
                result.update(
                    success=True, method="already_paired",
                    message="Board was already paired; HID service re-enabled.")
                return result
            log(f"[!] Enabling HID service failed: {describe_error(svc)}")
        log("[i] Clearing the existing bond and pairing from scratch.")
        forget_existing = True

    if forget_existing and (board["authenticated"] or board["remembered"]):
        rc = remove_device(board["address"])
        log(f"[i] Cleared previous bond -> {describe_error(rc)}")
        time.sleep(1.0)
        refreshed = find_balance_boards(timeout_mult=discovery_timeout_mult)
        match = [b for b in refreshed if b["address"] == board["address"]]
        if not match:
            result["message"] = ("Cleared the stale pairing, but the board "
                                 "stopped answering. Press SYNC and retry.")
            return result
        board = match[0]

    pin = pin_bytes_for_host(board["radio_address"])
    if len(pin) != 6:
        result["message"] = f"Could not derive a PIN from radio {board['radio_address']}"
        return result

    ok, message = pair_via_callback(board, pin, log=log)
    result["method"] = "callback"
    if not ok:
        log(f"[!] Raw-PIN route failed: {message}")
        # The legacy route drives the SAME BluetoothAuthenticateDevice stack,
        # so retrying it after an already-bonded refusal just reproduces the
        # error. Only fall back when the failure could plausibly differ.
        if "already paired" in message or "stale Windows pairing" in message:
            result["message"] = message
            return result
        log("[i] Trying the legacy AuthenticateDevice route...")
        ok2, message2 = pair_via_legacy(board, pin, log=log)
        if ok2:
            result.update(success=True, method="legacy", message=message2)
            return result
        result["message"] = f"{message}; legacy route also failed: {message2}"
        return result

    result.update(success=True, message=message)
    return result
