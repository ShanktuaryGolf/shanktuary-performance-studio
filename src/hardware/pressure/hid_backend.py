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
        return hid.enumerate(WBB_VID, WBB_PID)
    except Exception:
        return []


class HidBackend(BoardBackend):
    """Reads the Wii Balance Board as an HID device via hidapi."""

    def __init__(self, device_path: bytes | None = None) -> None:
        self._device: hid.device | None = None
        self._calibration: _BoardCalibration | None = None
        self._device_path = device_path
        self._temp_ref: float = 0.0

    def open(self) -> None:
        if hid is None:
            raise RuntimeError("hidapi is not installed. Run: pip install hidapi")
        self._device = hid.device()
        try:
            if self._device_path:
                self._device.open_path(self._device_path)
            else:
                self._device.open(WBB_VID, WBB_PID)
        except IOError as e:
            self._device = None
            raise RuntimeError(
                "Wii Balance Board not found via HID. "
                "Make sure it is paired and connected via Bluetooth. "
                f"({e})"
            ) from e

        # Use non-blocking / short-timeout mode
        self._device.set_nonblocking(1)

        # 1. Wake extension controller
        self._write_register(EXT_INIT_ADDR1, b"\x55")
        self._write_register(EXT_INIT_ADDR2, b"\x00")

        # 2. Try reading factory calibration (non-blocking, fallback to default)
        try:
            cal_data = self._read_register(EXT_CALIB_ADDR, 24)
            if cal_data and len(cal_data) >= 24:
                self._calibration = self._parse_calibration(cal_data)
        except Exception:
            pass

        if not self._calibration:
            self._calibration = DEFAULT_CALIBRATION

        # 3. Turn on LED 1 as visual feedback
        self._send_report(bytes([RPT_LED, 0x10]))

        # 4. Set reporting mode: continuous, buttons + extension
        self._send_report(bytes([RPT_DATA_REPORTING, 0x04, RPT_IN_BTN_EXT8]))

    def _send_report(self, data: bytes) -> None:
        """Send an output report to the Wiimote."""
        if self._device is None:
            return
        try:
            self._device.write(data)
        except Exception:
            pass

    def _write_register(self, address: int, data: bytes) -> None:
        """Write data to a Wiimote register address."""
        addr_bytes = address.to_bytes(3, "big")
        size = len(data)
        payload = bytes([RPT_WRITE_REG, 0x04]) + addr_bytes + bytes([size])
        payload += data + b"\x00" * (16 - len(data))
        self._send_report(payload)

    def _read_register(self, address: int, size: int) -> bytes | None:
        """Read data from a Wiimote register address with short timeout."""
        addr_bytes = address.to_bytes(3, "big")
        size_bytes = size.to_bytes(2, "big")
        payload = bytes([RPT_READ_REG, 0x04]) + addr_bytes + size_bytes
        self._send_report(payload)

        result = bytearray()
        remaining = size
        deadline = time.monotonic() + 0.3

        while remaining > 0 and time.monotonic() < deadline:
            report = self._wait_for_report(RPT_IN_READ_DATA, timeout=0.1)
            if report is None or len(report) < 22:
                break
            size_error = report[3]
            chunk_size = ((size_error >> 4) & 0x0F) + 1
            chunk = report[6:6 + chunk_size]
            result.extend(chunk)
            remaining -= chunk_size

        return bytes(result) if result else None

    def _wait_for_report(self, report_id: int, timeout: float = 0.1) -> bytes | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data = self._device.read(64)
            except Exception:
                return None
            if not data:
                time.sleep(0.005)
                continue
            if data[0] == report_id:
                return bytes(data)
        return None

    @staticmethod
    def _parse_calibration(data: bytes) -> _BoardCalibration:
        vals = struct.unpack(">12H", data[:24])
        return _BoardCalibration(
            top_right=_CalibrationData(vals[0], vals[4], vals[8]),
            bottom_right=_CalibrationData(vals[1], vals[5], vals[9]),
            top_left=_CalibrationData(vals[2], vals[6], vals[10]),
            bottom_left=_CalibrationData(vals[3], vals[7], vals[11]),
        )

    def shutdown(self) -> None:
        if self._device is None:
            return
        try:
            self._send_report(bytes([RPT_LED, 0x00]))
            self._send_report(bytes([RPT_DATA_REPORTING, 0x00, 0x30]))
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
            self._send_report(bytes([RPT_DATA_REPORTING, 0x04, RPT_IN_BTN_EXT8]))
            return None

        if report_id not in (RPT_IN_BTN_EXT8, RPT_IN_BTN_EXT19):
            return None

        if len(data) < 11:
            return None

        ext = data[3:11]
        tr, br, tl, bl = struct.unpack(">HHHH", bytes(ext))

        cal = self._calibration or DEFAULT_CALIBRATION
        kg_tl = _interpolate_kg(tl, cal.top_left)
        kg_tr = _interpolate_kg(tr, cal.top_right)
        kg_bl = _interpolate_kg(bl, cal.bottom_left)
        kg_br = _interpolate_kg(br, cal.bottom_right)

        return SensorReading(
            top_left=kg_tl,
            top_right=kg_tr,
            bottom_left=kg_bl,
            bottom_right=kg_br,
            timestamp=time.monotonic(),
        )
