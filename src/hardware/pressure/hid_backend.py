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
from dataclasses import dataclass

import hid

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


def _interpolate_kg(raw: int, cal: _CalibrationData) -> float:
    """Convert a raw sensor value to kg using 2-point linear interpolation.

    Uses the calibration curve: 0kg → 17kg → 34kg.
    """
    if raw < cal.kg0:
        return 0.0
    elif raw < cal.kg17:
        # Interpolate between 0kg and 17kg
        if cal.kg17 == cal.kg0:
            return 0.0
        return 17.0 * (raw - cal.kg0) / (cal.kg17 - cal.kg0)
    else:
        # Interpolate between 17kg and 34kg (and extrapolate beyond)
        if cal.kg34 == cal.kg17:
            return 17.0
        return 17.0 + 17.0 * (raw - cal.kg17) / (cal.kg34 - cal.kg17)


def enumerate_boards() -> list[dict]:
    """Return info dicts for all connected Wii Balance Boards via HID."""
    return hid.enumerate(WBB_VID, WBB_PID)


class HidBackend(BoardBackend):
    """Reads the Wii Balance Board as an HID device via hidapi.

    Properly initializes the Wiimote extension controller, reads
    calibration data, and returns sensor values in kilograms.
    """

    def __init__(self, device_path: bytes | None = None) -> None:
        self._device: hid.device | None = None
        self._calibration: _BoardCalibration | None = None
        self._device_path = device_path
        self._temp_ref: float = 0.0  # Factory reference temperature

    def open(self) -> None:
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

        # Use blocking reads during init (with timeout)
        self._device.set_nonblocking(0)

        # --- Initialize extension controller ---
        self._write_register(EXT_INIT_ADDR1, b"\x55")
        time.sleep(0.1)
        self._write_register(EXT_INIT_ADDR2, b"\x00")
        time.sleep(0.1)

        # --- Verify it's a balance board (non-fatal) ---
        ext_type = self._read_register(EXT_TYPE_ADDR, 6)
        if ext_type and len(ext_type) == 6 and ext_type != BB_EXT_TYPE:
            self.close()
            raise RuntimeError(
                "Connected Wiimote device is not a Balance Board. "
                f"Extension type: {ext_type.hex()}"
            )

        # --- Read calibration data ---
        cal_data = self._read_register(EXT_CALIB_ADDR, 24)
        if cal_data and len(cal_data) >= 24:
            self._calibration = self._parse_calibration(cal_data)

        # --- Read factory temperature reference ---
        temp_data = self._read_register(EXT_TEMP_ADDR, 2)
        if temp_data and len(temp_data) >= 2:
            self._temp_ref = struct.unpack(">H", temp_data[:2])[0]

        # Switch to non-blocking for normal operation
        self._device.set_nonblocking(1)

        # Turn on LED 1 as visual feedback
        self._send_report(bytes([RPT_LED, 0x10]))

        # Set reporting mode: continuous, buttons + 8 extension bytes
        self._send_report(bytes([RPT_DATA_REPORTING, 0x04, RPT_IN_BTN_EXT8]))

    def _send_report(self, data: bytes) -> None:
        """Send an output report to the Wiimote.

        The first byte of data must be the Wiimote report ID (e.g. 0x11, 0x12).
        The Wiimote uses numbered HID reports, so hidapi expects the report ID
        as the first byte — no 0x00 prefix.
        """
        if self._device is None:
            return
        self._device.write(data)

    def _write_register(self, address: int, data: bytes) -> None:
        """Write data to a Wiimote register address."""
        # Output report 0x16: [0x16] [0x04] [addr_hi] [addr_mid] [addr_lo] [size] [data...]
        addr_bytes = address.to_bytes(3, "big")
        size = len(data)
        payload = bytes([RPT_WRITE_REG, 0x04]) + addr_bytes + bytes([size])
        # Pad data to 16 bytes (required by protocol)
        payload += data + b"\x00" * (16 - len(data))
        self._send_report(payload)
        # Wait for ACK
        self._wait_for_report(RPT_IN_ACK, timeout=1.0)

    def _read_register(self, address: int, size: int) -> bytes | None:
        """Read data from a Wiimote register address."""
        addr_bytes = address.to_bytes(3, "big")
        size_bytes = size.to_bytes(2, "big")
        payload = bytes([RPT_READ_REG, 0x04]) + addr_bytes + size_bytes
        self._send_report(payload)

        # Collect response packets (data comes in 16-byte chunks)
        result = bytearray()
        remaining = size
        deadline = time.monotonic() + 2.0

        while remaining > 0 and time.monotonic() < deadline:
            report = self._wait_for_report(RPT_IN_READ_DATA, timeout=1.0)
            if report is None:
                break

            # Report 0x21 layout (with report ID from hidapi):
            # [0x21] [buttons(2)] [size_error(1)] [addr(2)] [data(16)]
            if len(report) < 22:
                break

            size_error = report[3]
            chunk_size = ((size_error >> 4) & 0x0F) + 1
            error_flag = size_error & 0x0F
            if error_flag != 0:
                break

            chunk = report[6:6 + chunk_size]
            result.extend(chunk)
            remaining -= chunk_size

        return bytes(result) if result else None

    def _wait_for_report(self, report_id: int, timeout: float = 1.0) -> bytes | None:
        """Block-read HID reports until we get the expected report ID."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = self._device.read(64, timeout_ms=int(timeout * 1000))
            if not data:
                return None
            if data[0] == report_id:
                return bytes(data)
        return None

    @staticmethod
    def _parse_calibration(data: bytes) -> _BoardCalibration:
        """Parse 24 bytes of calibration data into _BoardCalibration.

        Layout (big-endian uint16, 3 calibration points × 4 sensors):
            Bytes 0-7:   0kg  — TR, BR, TL, BL
            Bytes 8-15:  17kg — TR, BR, TL, BL
            Bytes 16-23: 34kg — TR, BR, TL, BL
        """
        vals = struct.unpack(">12H", data[:24])
        # vals[0..3] = 0kg:  TR, BR, TL, BL
        # vals[4..7] = 17kg: TR, BR, TL, BL
        # vals[8..11] = 34kg: TR, BR, TL, BL
        return _BoardCalibration(
            top_right=_CalibrationData(vals[0], vals[4], vals[8]),
            bottom_right=_CalibrationData(vals[1], vals[5], vals[9]),
            top_left=_CalibrationData(vals[2], vals[6], vals[10]),
            bottom_left=_CalibrationData(vals[3], vals[7], vals[11]),
        )

    def shutdown(self) -> None:
        """Power off the balance board by turning off LEDs, stopping
        data reporting, and closing the HID connection.

        The board powers down within a few seconds after losing its
        active connection with all LEDs off.
        """
        if self._device is None:
            return
        try:
            # Turn off all LEDs
            self._send_report(bytes([RPT_LED, 0x00]))
            # Stop data reporting (report mode 0x30 = buttons only, non-continuous)
            self._send_report(bytes([RPT_DATA_REPORTING, 0x00, 0x30]))
        except (IOError, OSError):
            pass
        self.close()

    def close(self) -> None:
        if self._device:
            self._device.close()
            self._device = None

    @property
    def is_open(self) -> bool:
        return self._device is not None

    def read(self) -> SensorReading | None:
        """Non-blocking read. Returns a calibrated SensorReading in kg."""
        if self._device is None:
            return None

        data = self._device.read(64)
        if not data:
            return None

        report_id = data[0]
        if report_id != RPT_IN_BTN_EXT8:
            return None

        # Report 0x32: [report_id] [buttons(2)] [extension(8)]
        if len(data) < 11:
            return None

        ext = data[3:11]
        tr, br, tl, bl = struct.unpack(">HHHH", bytes(ext))

        if self._calibration:
            kg_tl = _interpolate_kg(tl, self._calibration.top_left)
            kg_tr = _interpolate_kg(tr, self._calibration.top_right)
            kg_bl = _interpolate_kg(bl, self._calibration.bottom_left)
            kg_br = _interpolate_kg(br, self._calibration.bottom_right)

            # Temperature compensation: correct for drift from factory reference.
            # The board stores a reference temp at 0xA40060. Current board temp
            # is embedded in the raw sensor report byte 2 (extension offset).
            # Correction: ~0.07% per °C deviation from reference.
            if self._temp_ref > 0:
                board_temp = ext[7]  # Current temp from extension data
                delta = board_temp - self._temp_ref
                correction = 1.0 - 0.0007 * delta
                correction = max(0.98, min(1.02, correction))  # clamp ±2%
                kg_tl *= correction
                kg_tr *= correction
                kg_bl *= correction
                kg_br *= correction

            return SensorReading(
                top_left=kg_tl, top_right=kg_tr,
                bottom_left=kg_bl, bottom_right=kg_br,
                timestamp=time.monotonic(),
            )
        else:
            # Fallback: return raw values if calibration wasn't read
            return SensorReading(
                top_left=float(tl),
                top_right=float(tr),
                bottom_left=float(bl),
                bottom_right=float(br),
                timestamp=time.monotonic(),
            )
