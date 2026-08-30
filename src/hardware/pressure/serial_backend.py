"""Serial backend for DIY dual force plates (ESP32 + ADS1256 + HX711)."""

import struct
import time
import threading
from dataclasses import dataclass

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

from .base import BoardBackend, BoardOrientation, SensorReading, remap_for_orientation


# Frame protocol constants
SYNC = b"\xAA\x55"
FRAME_SIZE = 47
HEADER_SIZE = 2
TIMESTAMP_SIZE = 4
BAR_CHANNELS = 8
BEAM_CHANNELS = 2
CHECKSUM_SIZE = 1

# Struct format: header already consumed, then:
#   uint32 timestamp + 8x int32 bar + 2x int32 beam = 4 + 32 + 8 = 44 bytes
PAYLOAD_FMT = "<I8i2i"
PAYLOAD_SIZE = struct.calcsize(PAYLOAD_FMT)  # 44 bytes


@dataclass
class DualPlateReading:
    """Raw reading from both force plates plus beam cells."""
    left: SensorReading       # 4 bar cells, left foot
    right: SensorReading      # 4 bar cells, right foot
    left_beam_raw: int        # HX711 raw count, left foot
    right_beam_raw: int       # HX711 raw count, right foot
    timestamp: float          # time.monotonic()
    device_timestamp_us: int  # ESP32 micros()


@dataclass
class CalibrationData:
    """Per-channel tare offsets and scale factors."""
    bar_offsets: list[int]     # 8 raw count offsets (tare)
    bar_scales: list[float]   # 8 raw counts → kg conversion factors
    beam_offsets: list[int]   # 2 raw count offsets
    beam_scales: list[float]  # 2 raw counts → kg conversion factors

    @classmethod
    def default(cls) -> "CalibrationData":
        """Identity calibration — no offset, 1:1 scale."""
        return cls(
            bar_offsets=[0] * 8,
            bar_scales=[1.0] * 8,
            beam_offsets=[0] * 2,
            beam_scales=[1.0] * 2,
        )


def find_esp32_port() -> str | None:
    """Auto-detect ESP32 serial port."""
    for port in serial.tools.list_ports.comports():
        desc = (port.description or "").lower()
        vid = port.vid or 0
        # Common ESP32 USB-UART chips: CP210x (10C4:EA60), CH340 (1A86:7523)
        if vid in (0x10C4, 0x1A86) or "cp210" in desc or "ch340" in desc:
            return port.device
        # Espressif native USB (303A)
        if vid == 0x303A:
            return port.device
    return None


class SerialBackend(BoardBackend):
    """Reads dual force plate data from ESP32 over USB serial.

    The ESP32 sends 47-byte binary frames at ~80 Hz containing:
    - 8 bar cell readings (ADS1256, 4 per foot for CoP)
    - 2 beam cell readings (HX711, 1 per foot for accurate Fz)

    This backend produces SensorReading objects compatible with the
    existing CoPCalculator pipeline. The 4 bar cell values per foot
    are mapped to top_left, top_right, bottom_left, bottom_right.

    For the combined (single-board) view, left foot sensors become
    TL/BL and right foot sensors become TR/BR, preserving the
    left-right CoP axis that the existing pipeline expects.
    """

    BAUD_RATE = 921600

    def __init__(self, port: str | None = None,
                 calibration: CalibrationData | None = None,
                 plate_width_mm: float = 250.0,
                 plate_length_mm: float = 200.0) -> None:
        self._port = port
        self._serial: serial.Serial | None = None
        self._cal = calibration or CalibrationData.default()
        self._buf = bytearray()
        self._is_open = False
        self._last_dual: DualPlateReading | None = None
        self._orientation = BoardOrientation.LANDSCAPE
        # Guards _read_dual()'s shared parser state (self._buf) and self._cal
        # against concurrent read() (PressureManager loop thread) vs
        # tare()/calibrate_with_known_weight() (HTTP handler threads).
        self._lock = threading.Lock()
        # Physical plate dimensions (per foot)
        self.plate_width_mm = plate_width_mm
        self.plate_length_mm = plate_length_mm

    @property
    def orientation(self) -> BoardOrientation:
        return self._orientation

    @orientation.setter
    def orientation(self, value: BoardOrientation) -> None:
        self._orientation = value

    def open(self) -> None:
        port = self._port or find_esp32_port()
        if port is None:
            raise RuntimeError(
                "ESP32 force plate not found. Check USB connection. "
                "Expected CP210x, CH340, or Espressif USB device."
            )
        self._serial = serial.Serial(
            port=port,
            baudrate=self.BAUD_RATE,
            timeout=0,  # non-blocking
        )
        # Flush any stale data
        self._serial.reset_input_buffer()
        self._buf.clear()
        self._is_open = True

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None
        self._is_open = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    def read(self) -> SensorReading | None:
        """Non-blocking read. Returns a combined SensorReading if a frame is available.

        The combined reading maps both plates onto the standard 4-sensor layout:
            top_left     = left foot front total
            bottom_left  = left foot back total
            top_right    = right foot front total
            bottom_right = right foot back total

        This preserves left-right and front-back axes for the existing
        CoPCalculator, SwingDetector, and all downstream processing.
        """
        with self._lock:
            dual = self._read_dual()
        if dual is None:
            return None

        self._last_dual = dual
        left = dual.left
        right = dual.right

        # Remap each plate individually for orientation BEFORE combining.
        # This is critical for portrait mode — the single-board remap
        # applied to the combined view would scramble the left/right
        # foot axis into front/back.
        if self._orientation != BoardOrientation.LANDSCAPE:
            left = remap_for_orientation(left, self._orientation)
            right = remap_for_orientation(right, self._orientation)

        # Combine per-foot 4-corner into the standard 4-sensor layout:
        # Left foot front (TL+TR of left plate) → combined TL
        # Left foot back (BL+BR of left plate) → combined BL
        # Right foot front (TL+TR of right plate) → combined TR
        # Right foot back (BL+BR of right plate) → combined BR
        return SensorReading(
            top_left=left.top_left + left.top_right,
            bottom_left=left.bottom_left + left.bottom_right,
            top_right=right.top_left + right.top_right,
            bottom_right=right.bottom_left + right.bottom_right,
            timestamp=dual.timestamp,
        )

    def _read_dual(self) -> DualPlateReading | None:
        """Parse the next complete frame from the serial buffer."""
        if self._serial is None:
            return None

        # Read available bytes
        try:
            avail = self._serial.in_waiting
            if avail > 0:
                self._buf.extend(self._serial.read(avail))
        except (serial.SerialException, OSError):
            self._is_open = False
            return None

        # Find sync header and parse frame
        while len(self._buf) >= FRAME_SIZE:
            idx = self._buf.find(SYNC)
            if idx < 0:
                # No sync found — discard all but last byte (might be partial sync)
                self._buf = self._buf[-1:]
                return None
            if idx > 0:
                # Discard bytes before sync
                self._buf = self._buf[idx:]
            if len(self._buf) < FRAME_SIZE:
                return None

            frame = bytes(self._buf[:FRAME_SIZE])
            self._buf = self._buf[FRAME_SIZE:]

            # Verify checksum
            chk = 0
            for b in frame[:-1]:
                chk ^= b
            if chk != frame[-1]:
                continue  # bad checksum, try next sync

            return self._parse_frame(frame)

        return None

    def _parse_frame(self, frame: bytes) -> DualPlateReading:
        """Decode a verified 47-byte frame into a DualPlateReading."""
        payload = frame[HEADER_SIZE:HEADER_SIZE + PAYLOAD_SIZE]
        values = struct.unpack(PAYLOAD_FMT, payload)

        device_ts = values[0]
        bar_raw = list(values[1:9])
        beam_raw = [values[9], values[10]]

        now = time.monotonic()

        # Apply calibration: kg = (raw - offset) * scale
        bar_kg = [
            (bar_raw[i] - self._cal.bar_offsets[i]) * self._cal.bar_scales[i]
            for i in range(8)
        ]
        # NOTE: HX711 beam-cell calibration path is currently unconsumed —
        # left_beam_raw/right_beam_raw are captured below and fed only into the
        # tare/calibrate loops, whose results (beam_offsets/beam_scales) were
        # used solely by a dead beam_kg computation. Filed as its own issue:
        # decide whether to wire the beam cells in or rip the path out.

        # Clamp negatives to zero (noise below tare)
        bar_kg = [max(0.0, v) for v in bar_kg]

        left = SensorReading(
            top_left=bar_kg[0],
            top_right=bar_kg[1],
            bottom_left=bar_kg[2],
            bottom_right=bar_kg[3],
            timestamp=now,
        )
        right = SensorReading(
            top_left=bar_kg[4],
            top_right=bar_kg[5],
            bottom_left=bar_kg[6],
            bottom_right=bar_kg[7],
            timestamp=now,
        )

        return DualPlateReading(
            left=left,
            right=right,
            left_beam_raw=beam_raw[0],
            right_beam_raw=beam_raw[1],
            timestamp=now,
            device_timestamp_us=device_ts,
        )

    @property
    def last_dual_reading(self) -> DualPlateReading | None:
        """Access the most recent per-foot reading for advanced UI."""
        return self._last_dual

    # ---- Calibration helpers ----

    def tare(self, num_samples: int = 50, timeout_s: float = 10.0) -> None:
        """Zero out all channels by averaging readings with no load.

        Call this with the platforms empty and stationary.
        Blocks until enough samples are collected, the device disconnects,
        or timeout_s elapses. On failure the previous offsets are restored
        (never left zeroed) and RuntimeError is raised.
        """
        sums_bar = [0] * 8
        sums_beam = [0] * 2
        count = 0

        with self._lock:
            # Temporarily read raw frames
            old_offsets = self._cal.bar_offsets[:]
            old_beam_offsets = self._cal.beam_offsets[:]
            self._cal.bar_offsets = [0] * 8
            self._cal.beam_offsets = [0] * 2

            deadline = time.monotonic() + timeout_s
            try:
                while count < num_samples:
                    if not self._is_open or time.monotonic() > deadline:
                        raise RuntimeError(
                            "tare aborted: device disconnected or timed out "
                            f"after {count}/{num_samples} samples"
                        )
                    dual = self._read_dual()
                    if dual is None:
                        time.sleep(0.005)
                        continue
                    # Accumulate raw bar values from the SensorReading fields
                    left = dual.left
                    right = dual.right
                    raw_bars = [
                        left.top_left, left.top_right,
                        left.bottom_left, left.bottom_right,
                        right.top_left, right.top_right,
                        right.bottom_left, right.bottom_right,
                    ]
                    for i in range(8):
                        scale = self._cal.bar_scales[i]
                        if scale == 0:
                            scale = 1.0
                        sums_bar[i] += int(raw_bars[i] / scale)
                    sums_beam[0] += dual.left_beam_raw
                    sums_beam[1] += dual.right_beam_raw
                    count += 1

                self._cal.bar_offsets = [s // num_samples for s in sums_bar]
                self._cal.beam_offsets = [s // num_samples for s in sums_beam]
            except BaseException:
                # Restore prior calibration — never leave offsets zeroed.
                self._cal.bar_offsets = old_offsets
                self._cal.beam_offsets = old_beam_offsets
                raise

    def calibrate_with_known_weight(self, weight_kg: float,
                                     num_samples: int = 50,
                                     timeout_s: float = 10.0) -> None:
        """Calibrate scale factors using a known weight placed at center of each plate.

        Call tare() first, then place the known weight centered on BOTH plates
        (half on each), then call this method. Aborts with RuntimeError on
        disconnect or timeout (scales untouched).
        """
        sums_bar = [0.0] * 8
        sums_beam = [0.0] * 2
        count = 0

        with self._lock:
            deadline = time.monotonic() + timeout_s
            while count < num_samples:
                if not self._is_open or time.monotonic() > deadline:
                    raise RuntimeError(
                        "calibration aborted: device disconnected or timed out "
                        f"after {count}/{num_samples} samples"
                    )
                dual = self._read_dual()
                if dual is None:
                    time.sleep(0.005)
                    continue
                left = dual.left
                right = dual.right
                raw_bars = [
                    left.top_left, left.top_right,
                    left.bottom_left, left.bottom_right,
                    right.top_left, right.top_right,
                    right.bottom_left, right.bottom_right,
                ]
                for i in range(8):
                    sums_bar[i] += raw_bars[i]
                sums_beam[0] += dual.left_beam_raw - self._cal.beam_offsets[0]
                sums_beam[1] += dual.right_beam_raw - self._cal.beam_offsets[1]
                count += 1

            # Each plate should read ~weight_kg/2
            half_weight = weight_kg / 2.0
            # Each of the 4 bar cells per plate should read ~weight_kg/8
            per_cell = weight_kg / 8.0

            for i in range(8):
                avg_raw = sums_bar[i] / num_samples
                if abs(avg_raw) > 1:
                    self._cal.bar_scales[i] = per_cell / avg_raw
                else:
                    self._cal.bar_scales[i] = 1.0

            for i in range(2):
                avg_raw = sums_beam[i] / num_samples
                if abs(avg_raw) > 1:
                    self._cal.beam_scales[i] = half_weight / avg_raw
                else:
                    self._cal.beam_scales[i] = 1.0
