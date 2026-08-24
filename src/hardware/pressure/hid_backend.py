"""Wii Balance Board backend using hidapi (cross-platform, primarily for Windows).

Implements the Wiimote Bluetooth HID protocol for the Balance Board extension:
1. Initialize the extension controller (register writes)
2. Read factory calibration data (0kg, 17kg, 34kg per sensor)
3. Set continuous data reporting mode
4. Parse and calibrate sensor readings to kilograms

This replicates the approach used by WiimoteLib / WiiBalanceWalker.
"""

import struct
import time
try:
    import hid
except ImportError:
    hid = None

from .base import BoardBackend, SensorReading

# Nintendo Wii Balance Board USB HID identifiers
WBB_VID = 0x057E
WBB_PID = 0x0306

# --- Wiimote output report IDs ---
RPT_LED = 0x11
RPT_DATA_REPORTING = 0x12
RPT_WRITE_REG = 0x16
RPT_READ_REG = 0x17
RPT_STATUS_REQUEST = 0x15

# --- Wiimote input report IDs ---
RPT_IN_STATUS = 0x20
RPT_IN_READ_DATA = 0x21
RPT_IN_ACK = 0x22
RPT_IN_BTN_EXT8 = 0x32   # Buttons + 8 extension bytes
RPT_IN_BTN_EXT19 = 0x34  # Buttons + 19 extension bytes

# Extension register addresses
EXT_INIT_ADDR1 = 0xA400F0
EXT_INIT_ADDR2 = 0xA400FB
EXT_TYPE_ADDR = 0xA400FA    # 6 bytes — extension type identifier
EXT_CALIB_ADDR = 0xA40024   # 24 bytes — calibration data
EXT_TEMP_ADDR = 0xA40060    # 2 bytes — factory temperature reference

# Balance Board extension type identifier
BB_EXT_TYPE = bytes([0x00, 0x00, 0xA4, 0x20, 0x04, 0x02])


@dataclass
class _CalibrationData:
    """Factory calibration for one sensor at 3 reference weights."""
    kg0: int    # raw value at 0 kg
    kg17: int   # raw value at 17 kg
    kg34: int   # raw value at 34 kg


@dataclass
class _BoardCalibration:
    """Full calibration for all 4 sensors."""
    top_right: _CalibrationData
    bottom_right: _CalibrationData
    top_left: _CalibrationData
    bottom_left: _CalibrationData


DEFAULT_CALIBRATION = _BoardCalibration(
    top_right=_CalibrationData(2400, 2800, 3200),
    bottom_right=_CalibrationData(2400, 2800, 3200),
    top_left=_CalibrationData(2400, 2800, 3200),
    bottom_left=_CalibrationData(2400, 2800, 3200),
)


def _interpolate_kg(raw: int, cal: _CalibrationData) -> float:
    """Convert a raw sensor value to kg using 2-point linear interpolation."""
    if raw <= cal.kg0:
        return 0.0
    elif raw < cal.kg17:
        if cal.kg17 == cal.kg0:
            return 0.0
        return 17.0 * (raw - cal.kg0) / (cal.kg17 - cal.kg0)
    else:
        if cal.kg34 == cal.kg17:
            return 17.0
        return 17.0 + 17.0 * (raw - cal.kg17) / (cal.kg34 - cal.kg17)


def enumerate_boards() -> list[dict]:
    """Return info dicts for all connected Wii Balance Boards via HID."""
    if hid is None:
        return []
    try:
        boards = hid.enumerate(WBB_VID, WBB_PID)
        if boards:
            return boards
        all_devs = hid.enumerate()
        matched = []
        for d in all_devs:
            vid = d.get("vendor_id", 0)
            pid = d.get("product_id", 0)
            prod = str(d.get("product_string", "")).lower()
            path = str(d.get("path", "")).lower()
            if vid == WBB_VID or "rvl-wbc" in prod or "balance" in prod or "rvl-wbc" in path:
                matched.append(d)
        return matched
    except Exception as e:
        print(f"[!] Error enumerating HID boards: {e}")
        return []


class HidBackend(BoardBackend):
    """Reads the Wii Balance Board as an HID device via hidapi."""

    def __init__(self, device_path: bytes | None = None) -> None:
        self._device: hid.device | None = None
        self._calibration: _BoardCalibration | None = None
        self._device_path = device_path
        self._temp_ref: float = 0.0
        self._baseline_raw: tuple[int, int, int, int] | None = None

    def open(self) -> None:
        if hid is None:
            raise RuntimeError("hidapi is not installed. Run: pip install hidapi")
        self._device = hid.device()
        opened = False

        # 1. Try specified path if valid (not placeholder)
        if self._device_path and self._device_path not in (b"Board A", b"Board B", "Board A", "Board B"):
            try:
                p = self._device_path.encode("utf-8") if isinstance(self._device_path, str) else self._device_path
                self._device.open_path(p)
                opened = True
            except Exception:
                opened = False

        # 2. Try default VID/PID
        if not opened:
            try:
                self._device.open(WBB_VID, WBB_PID)
                opened = True
            except Exception:
                opened = False

        # 3. Try enumerating matched devices
        if not opened:
            devs = enumerate_boards()
            if devs and "path" in devs[0]:
                try:
                    self._device.open_path(devs[0]["path"])
                    opened = True
                except Exception:
                    opened = False

        if not opened:
            self._device = None
            raise RuntimeError("Wii Balance Board not found via HID. Please verify Bluetooth connection.")

        # Match exact working sequence from diagnose_wbb.py
        self._device.set_nonblocking(0)

        # 1. Initialize extension controller
        self._device.write(bytes([0x16, 0x04, 0xA4, 0x00, 0xF0, 0x01, 0x55] + [0x00] * 15))
        time.sleep(0.05)
        self._device.write(bytes([0x16, 0x04, 0xA4, 0x00, 0xFB, 0x01, 0x00] + [0x00] * 15))
        time.sleep(0.05)

        # 2. Read factory calibration data from 0xA40024 (24 bytes)
        try:
            self._device.write(bytes([0x17, 0x04, 0xA4, 0x00, 0x24, 0x00, 0x18]))
            time.sleep(0.05)
            cal_bytes = bytearray()
            for _ in range(5):
                d = self._device.read(64, 250)
                if d and d[0] == 0x21 and len(d) >= 22:
                    sz = ((d[3] >> 4) & 0x0F) + 1
                    cal_bytes.extend(d[6:6+sz])
                    if len(cal_bytes) >= 24:
                        break
            if len(cal_bytes) >= 24:
                self._calibration = self._parse_calibration(bytes(cal_bytes[:24]))
            else:
                self._calibration = None
        except Exception:
            self._calibration = None

        # 3. Turn on LED 1 (solid blue)
        self._device.write(bytes([0x11, 0x10]))
        time.sleep(0.05)

        # 4. Set reporting mode: continuous, buttons + extension
        self._device.write(bytes([0x12, 0x04, 0x32]))
        time.sleep(0.05)

        # Switch to non-blocking for normal streaming operation
        self._device.set_nonblocking(1)
        print(f"[+] Wii Balance Board connected and streaming via HID (calibrated={'yes' if self._calibration else 'adaptive'})!")

    def shutdown(self) -> None:
        if self._device is None:
            return
        try:
            self._device.write(bytes([0x11, 0x00]))
            self._device.write(bytes([0x12, 0x00, 0x30]))
        except Exception:
            pass
        self.close()

    def close(self) -> None:
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    @property
    def is_open(self) -> bool:
        return self._device is not None

    def read(self) -> SensorReading | None:
        """Non-blocking read. Returns a calibrated SensorReading in kg."""
        if self._device is None:
            return None

        try:
            data = self._device.read(64)
        except Exception:
            return None

        if not data:
            return None

        report_id = data[0]

        # Re-enable continuous reporting if status report received
        if report_id == RPT_IN_STATUS:
            try:
                self._device.write(bytes([0x12, 0x04, 0x32]))
            except Exception:
                pass
            return None

        if report_id not in (RPT_IN_BTN_EXT8, RPT_IN_BTN_EXT19):
            return None

        if len(data) < 11:
            return None

        ext = data[3:11]
        tr, br, tl, bl = struct.unpack(">HHHH", bytes(ext))

        if self._baseline_raw is None:
            self._baseline_raw = (tr, br, tl, bl)

        if self._calibration:
            kg_tl = _interpolate_kg(tl, self._calibration.top_left)
            kg_tr = _interpolate_kg(tr, self._calibration.top_right)
            kg_bl = _interpolate_kg(bl, self._calibration.bottom_left)
            kg_br = _interpolate_kg(br, self._calibration.bottom_right)
        else:
            # Adaptive baseline delta if factory EEPROM was not readable
            kg_tr = max(0.0, (tr - self._baseline_raw[0]) / 25.0)
            kg_br = max(0.0, (br - self._baseline_raw[1]) / 25.0)
            kg_tl = max(0.0, (tl - self._baseline_raw[2]) / 25.0)
            kg_bl = max(0.0, (bl - self._baseline_raw[3]) / 25.0)

        return SensorReading(
            top_left=kg_tl,
            top_right=kg_tr,
            bottom_left=kg_bl,
            bottom_right=kg_br,
            timestamp=time.monotonic(),
        )

    @staticmethod
    def _parse_calibration(data: bytes) -> _BoardCalibration:
        vals = struct.unpack(">12H", data[:24])
        return _BoardCalibration(
            top_right=_CalibrationData(vals[0], vals[4], vals[8]),
            bottom_right=_CalibrationData(vals[1], vals[5], vals[9]),
            top_left=_CalibrationData(vals[2], vals[6], vals[10]),
            bottom_left=_CalibrationData(vals[3], vals[7], vals[11]),
        )
