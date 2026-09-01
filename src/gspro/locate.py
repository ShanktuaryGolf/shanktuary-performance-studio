"""Locate GSPro's driving-range SQLite database.

GSPro (Windows) stores range shots in a per-user SQLite file:
    %LOCALAPPDATA%\\..\\LocalLow\\GSPro\\GSPro\\GSPro.db
which resolves to ``~\\AppData\\LocalLow\\GSPro\\GSPro\\GSPro.db`` — the same
path SimRead's locateGsproDataDir() uses.

Override with the SPS_GSPRO_DB environment variable (absolute path) so a
machine can point at a synced copy or an unusual install location without
code changes. This is runtime configuration, never a repo default.
"""

import os


def _windows_default():
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        # %LOCALAPPDATA%\..\LocalLow\GSPro\GSPro  (SimRead's exact path)
        return os.path.normpath(
            os.path.join(local_app_data, "..", "LocalLow", "GSPro", "GSPro", "GSPro.db")
        )
    home = os.path.expanduser("~")
    return os.path.join(home, "AppData", "LocalLow", "GSPro", "GSPro", "GSPro.db")


def locate_gspro_database_path() -> str:
    """Return the path to GSPro.db.

    Resolution order (mirrors SPS's Nova discovery convention — env var
    first, then platform default):
      1. ``SPS_GSPRO_DB`` environment variable (explicit path)
      2. Windows per-user default under AppData\\LocalLow
      3. POSIX fallback: ``~/.local/share/GSPro/GSPro.db`` (synced copy)

    The returned path is NOT guaranteed to exist; callers check with
    os.path.exists and surface a friendly "GSPro not found" state.
    """
    override = os.environ.get("SPS_GSPRO_DB", "").strip()
    if override:
        return os.path.abspath(override)

    if os.name == "nt":
        return _windows_default()

    # POSIX fallback for a synced copy of the Windows database.
    return os.path.join(os.path.expanduser("~"), ".local", "share", "GSPro", "GSPro.db")


def gspro_db_exists(path: str | None = None) -> bool:
    """True when the GSPro database file is present and readable."""
    p = path or locate_gspro_database_path()
    return os.path.isfile(p)
