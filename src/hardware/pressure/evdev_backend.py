"""Real Wii Balance Board backend using evdev."""

import time

from .base import BoardBackend, SensorReading

try:
    import evdev
    from evdev import ecodes
    # evdev ABS codes from hid-wiimote kernel driver
    SENSOR_MAP = {
        ecodes.ABS_HAT1X: "top_left",      # code 18
        ecodes.ABS_HAT0X: "top_right",     # code 16
        ecodes.ABS_HAT1Y: "bottom_left",   # code 19
        ecodes.ABS_HAT0Y: "bottom_right",  # code 17
    }
except ImportError:
    evdev = None
    ecodes = None
    SENSOR_MAP = {}

DEVICE_NAME = "Nintendo Wii Remote Balance Board"


def find_board_device() -> str | None:
    """Scan /dev/input/ for the Wii Balance Board. Returns device path or None."""
    if evdev is None:
        return None
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            if DEVICE_NAME in dev.name:
                dev.close()
                return path
            dev.close()
        except (PermissionError, OSError):
            continue
    return None


def enumerate_board_devices() -> list[str]:
    """Return device paths for ALL connected Wii Balance Boards."""
    if evdev is None:
        return []
    paths = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            if DEVICE_NAME in dev.name:
                paths.append(path)
            dev.close()
        except (PermissionError, OSError):
            continue
    return paths


class EvdevBackend(BoardBackend):
    """Reads the Wii Balance Board as a Linux input device via evdev."""

    def __init__(self, device_path: str | None = None) -> None:
        self._device_path = device_path
        self._device: evdev.InputDevice | None = None
        self._pending = {"top_left": 0.0, "top_right": 0.0,
                         "bottom_left": 0.0, "bottom_right": 0.0}

    def open(self) -> None:
        if evdev is None:
            raise RuntimeError("python-evdev is not installed (pip install evdev)")
        # A wizard placeholder is not a device node. Never let it degrade into
        # "auto-find the first board" -- in a dual setup that resolves to the
        # board the other handle already owns.
        if self._device_path in ("Board A", "Board B"):
            raise RuntimeError(
                f"{self._device_path!r} is a placeholder, not a real input device. "
                "Only one balance board was detected."
            )
        path = self._device_path or find_board_device()
        if path is None:
            raise RuntimeError(
                "Wii Balance Board not found in /dev/input/. "
                "Make sure it's paired via Bluetooth and hid-wiimote is loaded. "
                "You may need to be in the 'input' group: sudo usermod -a -G input $USER"
            )
        self._device = evdev.InputDevice(path)
        self._device.grab()  # exclusive access

    def shutdown(self) -> None:
        """Power off the balance board by disconnecting Bluetooth.

        On Linux the hid-wiimote kernel driver handles the board.
        Disconnecting the Bluetooth link causes the board to power
        down within a few seconds.
        """
        import subprocess
        # Grab the Bluetooth address from the device's phys path before closing
        bt_addr = None
        if self._device is not None:
            # evdev phys looks like "001f:0306 00:1e:35:xx:xx:xx"
            phys = getattr(self._device, "phys", "") or ""
            parts = phys.split()
            for p in parts:
                if p.count(":") == 5:
                    bt_addr = p.upper()
                    break
        self.close()
        if bt_addr:
            try:
                subprocess.run(
                    ["bluetoothctl", "disconnect", bt_addr],
                    timeout=5, capture_output=True,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass

    def close(self) -> None:
        if self._device:
            try:
                self._device.ungrab()
            except OSError:
                pass
            self._device.close()
            self._device = None

    @property
    def is_open(self) -> bool:
        return self._device is not None

    def read(self) -> SensorReading | None:
        """Non-blocking read. Returns a SensorReading on SYN_REPORT, else None."""
        if self._device is None:
            return None

        try:
            event = self._device.read_one()
        except BlockingIOError:
            return None
        except OSError:
            # Device disappeared (board powered off / BT drop) — mark closed
            # so PressureManager's reconnect logic can recreate the backend.
            self.close()
            return None

        while event is not None:
            if event.type == ecodes.EV_ABS and event.code in SENSOR_MAP:
                # hid-wiimote driver outputs ~centinewtons; convert to kg
                self._pending[SENSOR_MAP[event.code]] = float(event.value) / 100.0
            elif event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                return SensorReading(
                    top_left=self._pending["top_left"],
                    top_right=self._pending["top_right"],
                    bottom_left=self._pending["bottom_left"],
                    bottom_right=self._pending["bottom_right"],
                    timestamp=time.monotonic(),
                )
            try:
                event = self._device.read_one()
            except BlockingIOError:
                break
            except OSError:
                self.close()
                break

        return None
