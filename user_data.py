"""Persistent user data, independent of source trees and read-only app bundles."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HISTORY_NAME = "shanktuary_session_history.json"
ANCILLARY_NAMES = ("shanktuary_index_history.json", "shanktuary_combine_history.json")


def get_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".local" / "share"
    return base / "shanktuary"


def legacy_data_dirs() -> list[Path]:
    if getattr(sys, "frozen", False):
        paths = [Path(sys.executable).parent]
        # An AppImage's executable lives on a temporary, read-only mount.
        if os.environ.get("APPIMAGE"):
            paths.insert(0, Path(os.environ["APPIMAGE"]).absolute().parent)
        return paths
    return [Path(__file__).resolve().parent]


def _copy_without_overwrite(source: Path, target: Path) -> None:
    """Publish a complete copy only if the destination is still absent."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".migrate-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as src:
            shutil.copyfileobj(src, out)
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(temp, target)
        except FileExistsError:
            pass
    finally:
        os.unlink(temp)


def prepare_data_dir(target: Path, legacy_dirs: list[Path]) -> None:
    """Copy old history/traces once; never move originals or replace user data.

    Traces are copied first, history last. A failed migration can safely retry
    without publishing a history file with missing traces. Errors propagate so
    the desktop can tell the user and avoid saving an empty replacement.
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for old in legacy_dirs:
        old = Path(old)
        if old.resolve() == target.resolve():
            continue
        history = old / HISTORY_NAME
        import_history = not (target / HISTORY_NAME).exists() and history.is_file()
        if import_history:
            # Validate before importing, while retaining the original bytes.
            with history.open(encoding="utf-8") as source:
                data = json.load(source)
            if not isinstance(data, (dict, list)):
                raise ValueError(f"Invalid legacy history: {history}")
        # Fill missing ancillary files on upgrades/retries even if the main
        # history already exists. Never replace current analytics or traces.
        for name in ANCILLARY_NAMES:
            source = old / name
            destination = target / name
            if source.is_file() and not destination.exists():
                _copy_without_overwrite(source, destination)
        traces = old / "pressure_traces"
        if traces.exists():
            for trace in traces.glob("*.json.gz"):
                destination = target / "pressure_traces" / trace.name
                if not destination.exists():
                    _copy_without_overwrite(trace, destination)
        if import_history:
            _copy_without_overwrite(history, target / HISTORY_NAME)


def atomic_write_json(path: str | Path, payload: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
