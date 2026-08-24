"""Windows & Cross-Platform Bluetooth helper for Wii Balance Board pairing.

The Wii Balance Board requires a specific PIN during Bluetooth pairing.
The PIN is the HOST Bluetooth adapter's MAC address with the bytes reversed,
where each byte is converted to its Latin-1 character value.

This matches the algorithm used by WiiBalanceWalker (32Feet.NET / WiimoteLib).

Example:
    Host MAC:       38:FC:98:3B:B4:DC
    Reversed bytes: DC B4 3B 98 FC 38 (0xDC, 0xB4, 0x3B, 0x98, 0xFC, 0x38)
    PIN characters: Ü ´ ; ˜ ü 8
"""

import subprocess
import re
import sys
import os


def get_host_bluetooth_mac() -> str | None:
    """Return the local Bluetooth adapter MAC address as 12-char uppercase hex 'AABBCCDDEEFF'.

    Tries multiple detection methods across Windows and Linux.
    """
    if sys.platform == "win32":
        # Method 1: PowerShell — Get-PnpDevice Bluetooth radio address
        mac = _try_powershell_pnp()
        if mac:
            return mac

        # Method 2: PowerShell NetAdapter
        mac = _try_powershell_netadapter()
        if mac:
            return mac

        # Method 3: Registry — BTHPORT parameters
        mac = _try_registry()
        if mac:
            return mac

    elif sys.platform.startswith("linux"):
        # Linux detection via sysfs or bluetoothctl
        mac = _try_linux_sysfs()
        if mac:
            return mac
        mac = _try_linux_bluetoothctl()
        if mac:
            return mac

    return None


def _try_powershell_pnp() -> str | None:
    """Query the Bluetooth radio MAC via PowerShell Get-PnpDevice."""
    try:
        ps_script = (
            "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
            "Where-Object { $_.InstanceId -like 'BTHUSB*' -or $_.InstanceId -like 'USB*' } | "
            "ForEach-Object { $_.InstanceId } | Select-Object -First 1"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=6,
        )
        if result.returncode == 0 and result.stdout.strip():
            instance_id = result.stdout.strip()
            mac = _extract_mac_from_id(instance_id)
            if mac:
                return mac
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _try_powershell_netadapter() -> str | None:
    """Query the Bluetooth radio MAC via Get-NetAdapter."""
    try:
        ps_script = (
            "$adapter = Get-NetAdapter -InterfaceDescription '*Bluetooth*' "
            "-ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($adapter) { $adapter.MacAddress -replace '-','' }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=6,
        )
        if result.returncode == 0 and result.stdout.strip():
            mac = result.stdout.strip().replace("-", "").replace(":", "")
            if len(mac) == 12 and all(c in "0123456789ABCDEFabcdef" for c in mac):
                return mac.upper()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _try_registry() -> str | None:
    """Read the Bluetooth adapter MAC from the Windows registry."""
    try:
        import winreg
        key_path = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            val, _ = winreg.QueryValueEx(key, "LocalDeviceAddress")
            if isinstance(val, bytes) and len(val) >= 6:
                mac = val[:6][::-1].hex().upper()
                return mac
    except (OSError, FileNotFoundError, ImportError):
        pass
    return None


def _try_linux_sysfs() -> str | None:
    """Read host Bluetooth adapter address from Linux /sys/class/bluetooth/hci0/address."""
    try:
        base_dir = "/sys/class/bluetooth"
        if os.path.exists(base_dir):
            for hci in os.listdir(base_dir):
                addr_path = os.path.join(base_dir, hci, "address")
                if os.path.exists(addr_path):
                    with open(addr_path, "r", encoding="utf-8") as f:
                        raw = f.read().strip().replace(":", "").replace("-", "")
                        if len(raw) == 12:
                            return raw.upper()
    except Exception:
        pass
    return None


def _try_linux_bluetoothctl() -> str | None:
    """Read host Bluetooth adapter address using bluetoothctl list."""
    try:
        res = subprocess.run(["bluetoothctl", "list"], capture_output=True, text=True, timeout=4)
        if res.returncode == 0 and res.stdout:
            match = re.search(r"Controller\s+([0-9A-Fa-f:]{17})", res.stdout)
            if match:
                return match.group(1).replace(":", "").upper()
    except Exception:
        pass
    return None


def _extract_mac_from_id(instance_id: str) -> str | None:
    """Try to extract a 12-hex-digit MAC from a PnP instance ID."""
    match = re.search(r'[0-9A-Fa-f]{12}', instance_id)
    if match:
        return match.group(0).upper()
    return None


def mac_to_wii_pin(mac_hex: str) -> str:
    """Convert a MAC address to the Wii Balance Board pairing PIN string (Latin-1).

    The PIN is each byte of the MAC in reverse order, converted to its
    character value. This matches WiiBalanceWalker's AddressToWiiPin().

    Args:
        mac_hex: 12-character hex string, e.g. "38FC983BB4DC"

    Returns:
        The PIN as a character string, e.g. "Ü´;\x98ü8"
    """
    mac_hex = mac_hex.replace(":", "").replace("-", "").upper()
    if len(mac_hex) != 12 or not all(c in "0123456789ABCDEF" for c in mac_hex):
        return ""
    pairs = [mac_hex[i:i + 2] for i in range(0, 12, 2)]
    return "".join(chr(int(pair, 16)) for pair in reversed(pairs))


def mac_has_zero_byte(mac_hex: str) -> bool:
    """Check if the MAC contains a 00 byte."""
    mac_hex = mac_hex.replace(":", "").replace("-", "").upper()
    if len(mac_hex) != 12:
        return False
    pairs = [mac_hex[i:i + 2] for i in range(0, 12, 2)]
    return "00" in pairs


def mac_to_wii_pin_bytes(mac_hex: str) -> bytes:
    """Convert a MAC address to the Wii Balance Board pairing PIN as raw bytes.

    Returns the PIN as 6 bytes (MAC in reversed byte order).
    """
    mac_hex = mac_hex.replace(":", "").replace("-", "").upper()
    if len(mac_hex) != 12 or not all(c in "0123456789ABCDEF" for c in mac_hex):
        return b""
    pairs = [mac_hex[i:i + 2] for i in range(0, 12, 2)]
    return bytes(int(pair, 16) for pair in reversed(pairs))


def mac_to_wii_pin_display(mac_hex: str) -> str:
    """Format the PIN for display, showing the actual characters with non-printable placeholders."""
    pin_bytes = mac_to_wii_pin_bytes(mac_hex)
    if not pin_bytes:
        return ""
    chars = []
    for b in pin_bytes:
        if b == 0:
            chars.append("\u2400")  # Unicode SYMBOL FOR NULL '␀'
        elif b < 0x20 or b == 0x7F:
            chars.append(f"\\x{b:02X}")
        else:
            chars.append(chr(b))
    return "".join(chars)


def format_mac_display(mac_hex: str) -> str:
    """Format a MAC hex string for display: '38:FC:98:3B:B4:DC'."""
    raw = mac_hex.replace(":", "").replace("-", "").upper()
    if len(raw) != 12:
        return mac_hex
    return ":".join(raw[i:i + 2] for i in range(0, 12, 2))


def open_windows_bluetooth_settings() -> bool:
    """Open the Windows Bluetooth settings page or control panel."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["explorer", "ms-settings:bluetooth"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return True
        elif sys.platform.startswith("linux"):
            # Try available Linux Bluetooth GUI tools
            import shutil
            for cmd in ["blueman-manager", "gnome-control-center", "kcmshell5"]:
                if shutil.which(cmd):
                    subprocess.Popen([cmd, "bluetooth"] if cmd == "gnome-control-center" else [cmd])
                    return True
            return True
    except Exception as e:
        print(f"[!] Unable to launch Bluetooth settings: {e}")
    return False
