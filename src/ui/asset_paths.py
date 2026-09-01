"""Resolve desktop UI assets in both source checkouts and PyInstaller bundles."""

from __future__ import annotations

import sys
from pathlib import Path


def asset_dir() -> Path:
    """Return the shared ``assets`` directory for this running app.

    PyInstaller's layout differs by platform. Windows/Linux usually expose
    bundled data directly under ``sys._MEIPASS``; macOS app bundles place data
    under ``Contents/Resources``. Check both explicitly before falling back to
    a source checkout.
    """
    candidates = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        candidates.extend([
            base / "assets",
            base.parent / "Resources" / "assets",
            base.parent.parent / "Resources" / "assets",
        ])

    # macOS .app: .../Contents/MacOS/<executable> -> Contents/Resources/assets
    try:
        exe = Path(sys.executable).resolve()
        candidates.append(exe.parent.parent / "Resources" / "assets")
    except Exception:
        pass

    here = Path(__file__).resolve()
    # src/ui/asset_paths.py -> repository root
    source = here.parents[2] / "assets"
    candidates.append(source)

    # Defensive fallback for unusual editable/install layouts.
    candidates.extend(parent / "assets" for parent in here.parents)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return source


def asset_path(name: str) -> str:
    return str(asset_dir() / name)
