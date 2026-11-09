"""Wii Balance Board backend using hidapi (cross-platform, primarily for Windows).

Implements the Wiimote Bluetooth HID protocol for the Balance Board extension:
1. Initialize the extension controller (register writes)
2. Read factory calibration data (0kg, 17kg, 34kg per sensor)
3. Set continuous data reporting mode
4. Parse and calibrate sensor readings to kilograms

This replicates the approach used by WiimoteLib / WiiBalanceWalker.
"""

import struct
import sys
import time
from collections import deque
from copy import deepcopy
from dataclasses import dataclass

try:
    import hid
except ImportError:
    hid = None

from .base import BoardBackend, SensorReading

# Nintendo Wii Balance Board USB HID identifiers
WBB_VID = 0x057E
WBB_PID = 0x0306

# Handles whose outstanding read never completed. Freeing one would let
# Windows finish the read into freed memory, so they are deliberately kept
# alive for the life of the process instead.
_UNSETTLED_HANDLES: list = []


def _settle_pending_read(dev, attempts: int = 20, timeout_ms: int = 100) -> bool:
    """Complete hidapi's outstanding overlapped read before the handle closes.

    On Windows a non-blocking hid_read() that finds no data returns 0 but
    LEAVES its ReadFile pending (the normal state between polls). hid_close()
    then calls CancelIo(), which only cancels I/O issued by the CALLING
    thread -- the read was issued by the pressure worker, the close comes
    from the UI thread -- and immediately frees the read buffer and
    OVERLAPPED. Windows later completes the read into freed memory: heap
    corruption, reported as fatal exception 0xc0000374 at some unrelated
    allocation (the Setup -> step-on wizard crash).

    A timed read waits on that same pending request, so a read that returns
    data (or errors) means nothing is outstanding. The board streams
    continuously, so this normally returns on the first call.
    """
    for _ in range(attempts):
        try:
            if dev.read(64, timeout_ms):
                return True
        except Exception:
            return True   # read failed -> hidapi cleared the pending flag
    return False

# Set once if HID enumeration itself fails, so the 2s reconnect loop doesn't
# reprint the same error forever.
_ENUM_ERROR_LOGGED = False

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

CALIBRATION_TIMEOUT = 2.0
CALIBRATION_MAX_READS = 256
INVALID_ZERO_PAYLOAD = "Invalid sensor payload: all four raw ADC values are zero."


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
            prod = str(d.get("product_string", "")).lower()
            path = str(d.get("path", "")).lower()
            if vid == WBB_VID or "rvl-wbc" in prod or "balance" in prod or "rvl-wbc" in path:
                matched.append(d)
        return matched
    except Exception as e:
        # Enumeration failing is usually a missing/broken hidapi rather than a
        # per-call problem, so it would repeat on every 2s reconnect attempt.
        # Log once per process.
        global _ENUM_ERROR_LOGGED
        if not _ENUM_ERROR_LOGGED:
            _ENUM_ERROR_LOGGED = True
            print(f"[!] Error enumerating HID boards: {e} (further errors suppressed)")
        return []


class HidBackend(BoardBackend):
    """Reads the Wii Balance Board as an HID device via hidapi."""

    def __init__(self, device_path: bytes | None = None) -> None:
        self._device: hid.device | None = None
        self._calibration: _BoardCalibration | None = None
        self._device_path = device_path
        self._temp_ref: float = 0.0
        self._last_packet_timestamp: float | None = None
        self._last_sample_timestamp: float | None = None
        self._raw_cells: dict[str, int] | None = None
        self._last_error: str | None = None
        self._reset_packet_diagnostics()

    def open(self) -> None:
        if self.is_open:
            return
        self._calibration = None
        self._last_packet_timestamp = None
        self._last_sample_timestamp = None
        self._raw_cells = None
        self._last_error = None
        self._reset_packet_diagnostics()
        try:
            self._open_device()
        except Exception as exc:
            self._last_error = f"HID initialization failed: {exc}"
            self.close()
            raise

    def _open_device(self) -> None:
        if hid is None:
            raise RuntimeError("hidapi is not installed. Run: pip install hidapi")

        # A caller that names a device MEANS that device. Falling back to
        # open-by-VID/PID would hand back "the first WBB found", so in a
        # two-board setup both handles could land on the same physical board
        # -- the app would report dual while reading one board twice, and the
        # unopened board would sit there blinking. Explicit path => explicit
        # failure.
        explicit = bool(
            self._device_path
            and self._device_path not in (b"Board A", b"Board B", "Board A", "Board B")
        )

        self._device = hid.device()
        opened = False

        # 1. Try specified path if valid (not placeholder)
        if explicit:
            try:
                p = self._device_path.encode("utf-8") if isinstance(self._device_path, str) else self._device_path
                self._device.open_path(p)
                opened = True
            except Exception:
                opened = False
            if not opened:
                self._device = None
                raise RuntimeError(
                    f"Wii Balance Board at {self._device_path!r} could not be opened. "
                    "It may be disconnected, or already held by another handle."
                )

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
        self._write(bytes([0x16, 0x04, 0xA4, 0x00, 0xF0, 0x01, 0x55] + [0x00] * 15))
        time.sleep(0.05)
        self._write(bytes([0x16, 0x04, 0xA4, 0x00, 0xFB, 0x01, 0x00] + [0x00] * 15))
        time.sleep(0.05)

        # 2. Read factory calibration data from 0xA40024 (24 bytes)
        self._collect_calibration()

        # 3. Turn on LED 1 (solid blue)
        self._write(bytes([0x11, 0x10]))
        time.sleep(0.05)

        # 4. Set reporting mode: continuous, buttons + extension
        self._write(bytes([0x12, 0x04, 0x32]))
        time.sleep(0.05)

        # Switch to non-blocking for normal streaming operation
        self._device.set_nonblocking(1)
        print(f"[+] Wii Balance Board opened via HID "
              f"(calibration={'factory' if self._calibration else 'unavailable'}); "
              "awaiting sensor samples")

    def _reset_packet_diagnostics(self) -> None:
        self._packet_count = 0
        self._report_counts: dict[int, int] = {}
        self._recent_packets: deque = deque(maxlen=8)
        self._last_packets_by_report: dict[int, dict] = {}
        self._recent_writes: deque = deque(maxlen=8)
        self._first_writes: list[dict] = []
        self._first_acks: list[dict] = []
        self._recent_acks: deque = deque(maxlen=8)
        self._last_status: dict | None = None
        self._zero_extension_count = 0
        self._zero_extension_streak = 0
        self._last_nonzero_extension_timestamp: float | None = None

    def _write(self, data):
        """Record the result of an existing write, without retries or new I/O."""
        entry = dict(timestamp=time.monotonic(), hex=bytes(data[:64]).hex(),
                     requested_length=len(data), return_count=None, error=None)
        try:
            result = self._device.write(data)
            entry["return_count"] = result
            return result
        except Exception as exc:
            entry["error"] = str(exc)[:512]
            raise
        finally:
            self._recent_writes.append(entry)
            if len(self._first_writes) < 8:
                self._first_writes.append(entry)

    def _observe_packet(self, data) -> float:
        timestamp = time.monotonic()
        self._last_packet_timestamp = timestamp
        report_id = data[0]
        entry = dict(timestamp=timestamp, report_id=report_id, length=len(data),
                     hex=bytes(data[:64]).hex())
        self._packet_count += 1
        self._report_counts[report_id] = self._report_counts.get(report_id, 0) + 1
        self._recent_packets.append(entry)
        self._last_packets_by_report[report_id] = entry
        if report_id == RPT_IN_ACK and len(data) >= 5:
            # ACKs name only the output command ID, not its memory address.
            ack = dict(timestamp=timestamp, report_id=data[3], error=data[4])
            self._recent_acks.append(ack)
            if len(self._first_acks) < 8:
                self._first_acks.append(ack)
        if report_id == RPT_IN_STATUS and len(data) >= 7:
            self._last_status = dict(timestamp=timestamp, flags=data[3],
                                     extension_present=bool(data[3] & 0x02),
                                     battery=data[6])
        if report_id in (RPT_IN_BTN_EXT8, RPT_IN_BTN_EXT19) and len(data) >= 11:
            tr, br, tl, bl = struct.unpack(">HHHH", bytes(data[3:11]))
            self._raw_cells = dict(top_left=tl, top_right=tr,
                                   bottom_left=bl, bottom_right=br)
            if not any((tr, br, tl, bl)):
                self._zero_extension_count += 1
                self._zero_extension_streak += 1
            else:
                self._zero_extension_streak = 0
                self._last_nonzero_extension_timestamp = timestamp
        return timestamp

    def _collect_calibration(self) -> None:
        """Assemble only the requested EEPROM bytes, regardless of arrival order.

        Unrelated input reports do not consume a small fixed packet budget.
        Both time and read count are bounded even for a continuously busy device.
        """
        received: dict[int, int] = {}
        start = EXT_CALIB_ADDR & 0xFFFF
        deadline = time.monotonic() + CALIBRATION_TIMEOUT
        self._last_error = "Factory calibration unavailable: incomplete response"
        self._write(bytes([0x17, 0x04, 0xA4, 0x00, 0x24, 0x00, 0x18]))
        for _ in range(CALIBRATION_MAX_READS):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            # Never use zero (an infinite wait in blocking hidapi mode).
            data = self._device.read(64, max(1, min(100, int(remaining * 1000))))
            if not data:
                continue
            self._observe_packet(data)
            if data[0] != RPT_IN_READ_DATA:
                continue
            if len(data) < 6 or data[3] & 0x0F:
                self._last_error = "Factory calibration unavailable: invalid/error memory report"
                continue
            size = (data[3] >> 4) + 1
            address = (data[4] << 8) | data[5]
            offset = address - start
            if len(data) < 6 + size or not (0 <= offset and offset + size <= 24):
                self._last_error = "Factory calibration unavailable: invalid size/address"
                continue
            chunk = dict(enumerate(data[6:6 + size], offset))
            if any(i in received and received[i] != value for i, value in chunk.items()):
                self._last_error = "Factory calibration unavailable: conflicting response bytes"
                return
            received.update(chunk)
            if len(received) == 24:
                try:
                    self._calibration = self._parse_calibration(
                        bytes(received[i] for i in range(24)))
                except ValueError as exc:
                    self._last_error = f"Factory calibration unavailable: {exc}"
                else:
                    self._last_error = None
                return

    def get_diagnostics(self) -> dict:
        """Connection and observed data, without claiming uncalibrated kg.

        is_open describes the usable backend, not quarantined OS handles.
        Timestamps are monotonic and remain None until actually observed.
        """
        sensor_status = (
            "waiting" if self._raw_cells is None else
            "invalid_zero_payload" if not any(self._raw_cells.values()) else
            "valid" if self._calibration else "uncalibrated"
        )
        return {
            "sensor_data_status": sensor_status,
            "recovery_blocked": sensor_status == "invalid_zero_payload",
            "packet_count": self._packet_count,
            "report_counts": dict(self._report_counts),
            "last_packet": deepcopy(self._recent_packets[-1]) if self._recent_packets else None,
            "recent_packets": deepcopy(list(self._recent_packets)),
            "last_packets_by_report": deepcopy(self._last_packets_by_report),
            "recent_writes": deepcopy(list(self._recent_writes)),
            "first_writes": deepcopy(self._first_writes),
            "first_acks": deepcopy(self._first_acks),
            "recent_acks": deepcopy(list(self._recent_acks)),
            "last_status": deepcopy(self._last_status),
            "zero_extension_count": self._zero_extension_count,
            "zero_extension_streak": self._zero_extension_streak,
            "last_nonzero_extension_timestamp": self._last_nonzero_extension_timestamp,
            "calibration_status": "factory" if self._calibration else "unavailable",
            "last_packet_timestamp": self._last_packet_timestamp,
            "last_sample_timestamp": self._last_sample_timestamp,
            "raw_cells": dict(self._raw_cells) if self._raw_cells is not None else None,
            "last_error": INVALID_ZERO_PAYLOAD if sensor_status == "invalid_zero_payload" else self._last_error,
            "is_open": self.is_open,
        }

    def shutdown(self) -> None:
        if self._device is None:
            return
        try:
            self._write(bytes([0x11, 0x00]))
            self._write(bytes([0x12, 0x00, 0x30]))
        except Exception:
            pass
        self.close()

    def close(self) -> None:
        dev = self._device
        if dev is None:
            return
        self._device = None
        if sys.platform == "win32" and not _settle_pending_read(dev):
            # Still pending after ~2s: closing now would corrupt the heap.
            # Leak the handle rather than crash the app.
            _UNSETTLED_HANDLES.append(dev)
            self._last_error = "HID close incomplete: pending read; handle quarantined"
            print("[!] Balance board read did not finish; handle left open "
                  "to avoid a crash")
            return
        try:
            dev.close()
        except Exception as exc:
            self._last_error = f"HID close failed: {exc}"
            _UNSETTLED_HANDLES.append(dev)

    @property
    def is_open(self) -> bool:
        return self._device is not None

    def read(self) -> SensorReading | None:
        """Non-blocking read. Drains the OS HID queue and returns a calibrated
        SensorReading (kg) from the MOST RECENT extension report, so displayed
        CoP never lags behind real time when the board streams faster than the
        manager polls."""
        if self._device is None:
            return None

        latest = None
        latest_timestamp = None
        # Drain everything queued; keep only the newest data report.
        for _ in range(64):  # hard cap to bound one poll cycle
            try:
                data = self._device.read(64)
            except Exception as exc:
                self._last_error = f"HID read failed: {exc}"
                # Read failure = device gone (power off / BT drop). Mark the
                # backend closed so PressureManager's reconnect logic fires.
                self.close()
                return None
            if not data:
                break

            timestamp = self._observe_packet(data)
            report_id = data[0]

            # Re-enable continuous reporting if status report received
            if report_id == RPT_IN_STATUS:
                try:
                    self._write(bytes([0x12, 0x04, 0x32]))
                except Exception as exc:
                    self._last_error = f"HID reporting request failed: {exc}"
                    self.close()
                    return None
                continue

            if report_id not in (RPT_IN_BTN_EXT8, RPT_IN_BTN_EXT19):
                continue

            if len(data) < 11:
                continue

            latest = data
            latest_timestamp = timestamp

        if latest is None or self._calibration is None or not any(latest[3:11]):
            return None

        ext = latest[3:11]
        tr, br, tl, bl = struct.unpack(">HHHH", bytes(ext))

        kg_tl = _interpolate_kg(tl, self._calibration.top_left)
        kg_tr = _interpolate_kg(tr, self._calibration.top_right)
        kg_bl = _interpolate_kg(bl, self._calibration.bottom_left)
        kg_br = _interpolate_kg(br, self._calibration.bottom_right)
        self._last_sample_timestamp = latest_timestamp

        return SensorReading(
            top_left=kg_tl,
            top_right=kg_tr,
            bottom_left=kg_bl,
            bottom_right=kg_br,
            timestamp=latest_timestamp,
        )

    @staticmethod
    def _parse_calibration(data: bytes) -> _BoardCalibration:
        if len(data) != 24:
            raise ValueError("expected all 24 calibration bytes")
        vals = struct.unpack(">12H", data)
        if any(not (0 < vals[i] < vals[i + 4] < vals[i + 8]) for i in range(4)):
            raise ValueError("reference values must be positive and strictly increasing")
        return _BoardCalibration(
            top_right=_CalibrationData(vals[0], vals[4], vals[8]),
            bottom_right=_CalibrationData(vals[1], vals[5], vals[9]),
            top_left=_CalibrationData(vals[2], vals[6], vals[10]),
            bottom_left=_CalibrationData(vals[3], vals[7], vals[11]),
        )
