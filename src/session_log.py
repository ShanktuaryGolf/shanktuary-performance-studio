"""Mirror console output to a log file the user can find and send.

The app prints its diagnostics with plain print(). That is fine in a
terminal and useless in a --windowed build, where there is no console at
all -- so when a user reports "pairing doesn't work" there is nothing to look
at. This tees stdout and stderr into ~/.shanktuary/logs/ (next to the
calibration file users already know about), rotating so it cannot grow
without bound.

Deliberately simple: no logging framework, no reformatting. Whatever the
console would have shown is what lands in the file, byte for byte, so a
pasted log reads exactly like a pasted terminal.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime

LOG_DIR = os.path.normpath(os.path.expanduser("~/.shanktuary/logs"))
LOG_NAME = "shanktuary.log"
#: Rotate when the current file passes this size, keep this many old ones.
MAX_BYTES = 2 * 1024 * 1024
KEEP = 3


def log_path() -> str:
    # normpath so Windows users see C:\Users\x\.shanktuary\logs\shanktuary.log
    # rather than a mix of both slash styles they cannot paste anywhere.
    return os.path.normpath(os.path.join(LOG_DIR, LOG_NAME))


class _Tee:
    """A file-like that writes to the original stream AND the log file.

    Writes are line-stamped so a log from a user shows *when* things happened,
    which is what distinguishes "it hung for 25s" from "it failed instantly".
    """

    def __init__(self, original, log_file, lock):
        self._orig = original
        self._log = log_file
        self._lock = lock
        self._at_line_start = True

    def write(self, text):
        if not text:
            return 0
        try:
            if self._orig is not None:
                self._orig.write(text)
        except Exception:
            pass
        try:
            with self._lock:
                out = []
                for piece in text.splitlines(keepends=True):
                    if self._at_line_start:
                        out.append(time.strftime("%H:%M:%S ") + piece)
                    else:
                        out.append(piece)
                    self._at_line_start = piece.endswith("\n")
                self._log.write("".join(out))
                self._log.flush()
        except Exception:
            pass
        return len(text)

    def flush(self):
        for s in (self._orig, self._log):
            try:
                if s is not None:
                    s.flush()
            except Exception:
                pass

    # Anything else (isatty, encoding, fileno...) comes from the original so
    # libraries that inspect sys.stdout keep working.
    def __getattr__(self, name):
        if self._orig is None:
            raise AttributeError(name)
        return getattr(self._orig, name)


def _rotate():
    path = log_path()
    try:
        if os.path.exists(path) and os.path.getsize(path) >= MAX_BYTES:
            for i in range(KEEP - 1, 0, -1):
                src = f"{path}.{i}"
                dst = f"{path}.{i + 1}"
                if os.path.exists(src):
                    os.replace(src, dst)
            os.replace(path, f"{path}.1")
    except OSError:
        pass


_installed = False


def install() -> str | None:
    """Start mirroring stdout/stderr to the log file. Idempotent.

    Returns the log path, or None if the file could not be opened (the app
    keeps running either way -- a missing log must never block a launch).
    """
    global _installed
    if _installed:
        return log_path()
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        _rotate()
        f = open(log_path(), "a", encoding="utf-8", errors="replace")
    except OSError:
        return None

    lock = threading.Lock()
    f.write(f"\n===== Shanktuary session started "
            f"{datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    f.write(f"python {sys.version.split()[0]} on {sys.platform}\n")
    f.flush()

    sys.stdout = _Tee(sys.stdout, f, lock)
    sys.stderr = _Tee(sys.stderr, f, lock)
    _installed = True
    return log_path()
