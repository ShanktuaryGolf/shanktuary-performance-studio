"""GUI tests own every Tk interpreter they create, including setup skips/errors."""
import pytest


@pytest.fixture(autouse=True)
def cleanup_tk_roots(monkeypatch):
    # A fixture that skips before its yield never runs its own teardown. A
    # leaked default root makes later PhotoImages belong to the wrong Tcl
    # interpreter, hiding the first failure behind dozens of unrelated errors.
    try:
        import tkinter as tk
    except ImportError:
        yield
        return
    roots = []
    original_init = tk.Tk.__init__

    def tracked_init(root, *args, **kwargs):
        original_init(root, *args, **kwargs)
        roots.append(root)
        # Match bare Xvfb: a desktop window manager must not silently shrink
        # a requested test viewport to the host monitor's work area.
        root.overrideredirect(True)

    monkeypatch.setattr(tk.Tk, '__init__', tracked_init)
    yield
    for root in reversed(roots):
        try:
            for callback in root.tk.call('after', 'info'):
                root.after_cancel(callback)
            root.destroy()
        except tk.TclError:
            # Tests are encouraged to destroy their roots themselves too.
            pass
