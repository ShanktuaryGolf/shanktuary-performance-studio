"""Persisted shot-source configuration.

Qwen's original port selected the shot source with the ``SPS_SHOT_SOURCE``
environment variable only. That is fine for a developer, but SPS ships to
other people: a GSPro user who has never owned a Nova cannot be asked to set
an environment variable before the app will read their shots. This module
gives the choice a real home on disk so the UI can own it.

Resolution order (env var stays as an escape hatch, exactly like
locate_gspro_database_path does for the database path):

  1. ``SPS_SHOT_SOURCE`` / ``SPS_GSPRO_DB`` environment variables — when set
     they win and the UI shows the setting as locked by the environment.
  2. The persisted user file, ``shanktuary_shot_source.json`` next to the
     other per-user runtime state.
  3. Defaults: source "nova", database path auto-located.

Per project convention this file is per-user runtime state written beside
the session history — never a repo default, and never a hard-coded path
belonging to one machine.
"""

import json
import os
import threading

#: Valid shot sources.
#:   nova  -- OpenLaunch Nova WebSocket only (default; unchanged behaviour)
#:   gspro -- poll GSPro.db only; Nova shots are dropped so a launch monitor
#:            feeding GSPro never double-ingests one physical shot
#:   both  -- ingest from both (only correct for genuinely separate bays)
VALID_SOURCES = ("nova", "gspro", "both", "open_connect", "cgp")
DEFAULT_SOURCE = "nova"
DEFAULT_OPEN_CONNECT_PORT = 921

SETTINGS_FILENAME = "shanktuary_shot_source.json"

_lock = threading.Lock()
_cache = None


def _user_settings_path():
    """Per-user fallback location.

    A frozen install can sit in a read-only directory (Program Files), where
    writing beside the executable fails silently and the splash would reappear
    on every launch. ``~/.shanktuary/`` is already used for balance-board
    calibration, so it is the established per-user home.
    """
    return os.path.join(
        os.path.expanduser("~"), ".shanktuary", SETTINGS_FILENAME
    )


def _settings_path():
    """Path to the persisted settings file.

    Imported lazily from the studio module so this package stays importable
    on its own (the tests build a poller without a Tk app).
    """
    override = os.environ.get("SPS_SHOT_SOURCE_FILE", "").strip()
    if override:
        return os.path.abspath(override)

    user_path = _user_settings_path()
    if os.path.isfile(user_path):
        # An existing per-user file always wins; it is where a read-only
        # install will have landed.
        return user_path

    try:
        import shanktuary_performance_studio as studio

        base = studio.DATA_DIR
    except Exception:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, SETTINGS_FILENAME)


def _normalise_source(value):
    """Coerce any input to a valid source name, else None."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    return v if v in VALID_SOURCES else None


def _valid_port(value):
    return type(value) is int and 1 <= value <= 65535


def _read_file():
    path = _settings_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path, data):
    """Atomically write JSON. Returns True on success, False if unwritable."""
    tmp = path + ".tmp"
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def load_settings(refresh=False):
    """Return the effective settings dict.

    Keys:
      source          -- one of VALID_SOURCES (effective value)
      db_path         -- explicit GSPro.db override, or "" for auto-locate
      source_locked   -- True when SPS_SHOT_SOURCE forces the source
      db_path_locked  -- True when SPS_GSPRO_DB forces the database path
      onboarded       -- True once the user has completed the source picker
      open_connect_port -- receiver port, integer 1..65535 (default 921)
      open_connect_lan -- explicit LAN opt-in (default False)
      cgp_device      -- discovered service name, or ""
      ogc_enrichment  -- opt-in local model calculations (default False)
      ogc_club_estimates -- independent speculative club opt-in (default False)

    Only preferences persist, never a running listener or connection state.
    """
    global _cache
    with _lock:
        if _cache is not None and not refresh:
            return dict(_cache)

        stored = _read_file()
        source = _normalise_source(stored.get("source")) or DEFAULT_SOURCE
        db_path = stored.get("db_path") if isinstance(stored.get("db_path"), str) else ""
        onboarded = bool(stored.get("onboarded", False))
        always_show = bool(stored.get("always_show_splash", False))
        port = stored.get("open_connect_port")
        if not _valid_port(port):
            port = DEFAULT_OPEN_CONNECT_PORT
        cgp_device = stored.get("cgp_device")
        if not isinstance(cgp_device, str):
            cgp_device = ""

        env_source = _normalise_source(os.environ.get("SPS_SHOT_SOURCE"))
        source_locked = env_source is not None
        if source_locked:
            source = env_source

        env_db = os.environ.get("SPS_GSPRO_DB", "").strip()
        db_path_locked = bool(env_db)
        if db_path_locked:
            db_path = os.path.abspath(env_db)

        _cache = {
            "source": source,
            "db_path": db_path,
            "source_locked": source_locked,
            "db_path_locked": db_path_locked,
            "onboarded": onboarded,
            "always_show_splash": always_show,
            "open_connect_port": port,
            "open_connect_lan": stored.get("open_connect_lan") is True,
            "cgp_device": cgp_device,
            "ogc_enrichment": stored.get("ogc_enrichment") is True,
            "ogc_club_estimates": stored.get("ogc_club_estimates") is True,
        }
        return dict(_cache)


def save_settings(source=None, db_path=None, onboarded=None,
                  always_show_splash=None, open_connect_port=None,
                  open_connect_lan=None, cgp_device=None, ogc_enrichment=None,
                  ogc_club_estimates=None):
    """Persist user choices and refresh the cache.

    Environment overrides are never written to disk — the stored value keeps
    the user's own choice so unsetting the variable restores it. Returns the
    new effective settings.
    """
    stored = _read_file()

    if source is not None:
        norm = _normalise_source(source)
        if norm is None:
            raise ValueError(f"invalid shot source {source!r}; expected one of {VALID_SOURCES}")
        stored["source"] = norm
    if db_path is not None:
        stored["db_path"] = os.path.abspath(db_path.strip()) if db_path.strip() else ""
    if onboarded is not None:
        stored["onboarded"] = bool(onboarded)
    if always_show_splash is not None:
        stored["always_show_splash"] = bool(always_show_splash)

    if open_connect_port is not None:
        if not _valid_port(open_connect_port):
            raise ValueError("Open Connect port must be an integer from 1 to 65535")
        stored["open_connect_port"] = open_connect_port
    if cgp_device is not None:
        if not isinstance(cgp_device, str):
            raise ValueError("CGP device must be a discovered service name string")
        stored["cgp_device"] = cgp_device
    for key, value in (("open_connect_lan", open_connect_lan),
                       ("ogc_enrichment", ogc_enrichment),
                       ("ogc_club_estimates", ogc_club_estimates)):
        if value is not None:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be a boolean")
            stored[key] = value

    path = _settings_path()
    if not _write_json(path, stored):
        # The install directory is read-only (Program Files). Fall back to
        # the per-user home so the choice actually survives a restart.
        fallback = _user_settings_path()
        if fallback != path and not _write_json(fallback, stored):
            print(f"[gspro] could not persist shot-source settings to {path}"
                  f" or {fallback}; the choice will not survive a restart")

    global _cache
    with _lock:
        _cache = None
    return load_settings(refresh=True)


def effective_source():
    """The shot source in force right now."""
    return load_settings()["source"]


def effective_db_path():
    """The GSPro database path in force right now (explicit or auto-located)."""
    settings = load_settings()
    if settings["db_path"]:
        return settings["db_path"]
    from .locate import locate_gspro_database_path

    return locate_gspro_database_path()


def gspro_enabled():
    """True when the current source ingests GSPro shots."""
    return effective_source() in ("gspro", "both")


def nova_enabled():
    """True when the current source ingests Nova shots."""
    return effective_source() in ("nova", "both")
