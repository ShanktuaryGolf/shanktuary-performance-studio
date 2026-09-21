"""Console output must land in a log file the user can find and send.

A --windowed build has no console, so when a user says "pairing doesn't
work" there is nothing to look at. Everything printed is mirrored into
~/.shanktuary/logs/shanktuary.log, and the Tools menu opens that folder.
"""

import importlib
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def session_log(tmp_path, monkeypatch):
    """A fresh session_log module pointed at a temp dir, with stdout/stderr
    restored afterwards so the tee never leaks into other tests."""
    import src.session_log as mod
    mod = importlib.reload(mod)
    monkeypatch.setattr(mod, "LOG_DIR", str(tmp_path / "logs"))
    saved_out, saved_err = sys.stdout, sys.stderr
    yield mod
    sys.stdout, sys.stderr = saved_out, saved_err
    mod._installed = False


def _read(mod):
    with open(mod.log_path(), encoding="utf-8") as f:
        return f.read()


class TestTee:
    def test_print_reaches_both_console_and_file(self, session_log, capsys):
        path = session_log.install()
        assert path and os.path.exists(path)

        print("[i] Scanning for a board")
        print("[!] Pairing failed: no PIN request", file=sys.stderr)

        body = _read(session_log)
        assert "[i] Scanning for a board" in body
        assert "[!] Pairing failed: no PIN request" in body, (
            "stderr was not mirrored"
        )
        # The console still gets it -- the tee must not swallow output, which
        # is the exact regression the pairing flow had earlier.
        captured = capsys.readouterr()
        assert "[i] Scanning for a board" in captured.out
        assert "Pairing failed" in captured.err

    def test_lines_are_timestamped(self, session_log):
        session_log.install()
        print("hello")
        body = _read(session_log)
        import re
        assert re.search(r"^\d\d:\d\d:\d\d hello$", body, re.M), (
            f"no HH:MM:SS stamp on the line: {body!r}"
        )

    def test_partial_writes_are_not_double_stamped(self, session_log):
        """print() with multiple args writes pieces; only a line START gets a
        stamp, or a log line reads 'HH:MM:SS a HH:MM:SS b'."""
        session_log.install()
        print("a", "b", "c")
        body = _read(session_log)
        assert body.count("\na") + body.count(" a ") >= 0  # sanity
        line = [ln for ln in body.splitlines() if ln.endswith("a b c")]
        assert line, f"line not found in {body!r}"
        assert line[0].count(":") == 2, f"double-stamped: {line[0]!r}"

    def test_session_header_marks_each_launch(self, session_log):
        session_log.install()
        body = _read(session_log)
        assert "Shanktuary session started" in body
        assert sys.platform in body

    def test_install_is_idempotent(self, session_log):
        a = session_log.install()
        b = session_log.install()
        assert a == b
        print("once")
        assert _read(session_log).count("once") == 1, "double tee"

    def test_unwritable_dir_does_not_break_startup(self, session_log,
                                                    monkeypatch):
        """A missing log must never stop the app from launching."""
        monkeypatch.setattr(session_log, "LOG_DIR", "/proc/nope/cannot")
        assert session_log.install() is None
        print("still works")  # must not raise


class TestRotation:
    def test_rotates_when_too_large(self, session_log, monkeypatch):
        monkeypatch.setattr(session_log, "MAX_BYTES", 50)
        os.makedirs(session_log.LOG_DIR, exist_ok=True)
        with open(session_log.log_path(), "w") as f:
            f.write("x" * 100)

        session_log.install()

        assert os.path.exists(session_log.log_path() + ".1")
        assert os.path.getsize(session_log.log_path()) < 100

    def test_keeps_a_bounded_number_of_old_logs(self, session_log,
                                                monkeypatch):
        monkeypatch.setattr(session_log, "MAX_BYTES", 10)
        monkeypatch.setattr(session_log, "KEEP", 2)
        os.makedirs(session_log.LOG_DIR, exist_ok=True)
        for _ in range(5):
            with open(session_log.log_path(), "w") as f:
                f.write("y" * 20)
            session_log._rotate()

        names = sorted(os.listdir(session_log.LOG_DIR))
        assert names == ["shanktuary.log.1", "shanktuary.log.2"], names


class TestToolsMenuEntry:
    def test_tools_menu_offers_the_log_folder(self):
        """The user has to be able to find the log without knowing about
        hidden dot-folders."""
        src = open(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "shanktuary_performance_studio.py"),
            encoding="utf-8").read()
        assert '"open_log_folder"' in src
        assert "Open Log Folder" in src
        assert 'action == "open_log_folder"' in src, "menu item has no handler"

    def test_open_log_folder_falls_back_to_clipboard(self, monkeypatch):
        """If the OS file browser cannot be launched, the path must still
        reach the user somehow."""
        import shanktuary_performance_studio as studio

        class _Root:
            def after(self, *a, **k):
                pass

        class _App:
            root = _Root()
            copy_feedback = None
            copied = None

            def copy_to_clipboard(self, text):
                self.copied = text

            def clear_copy_feedback(self):
                pass

            def draw_screen(self):
                pass

        app = _App()
        monkeypatch.setattr(studio.sys, "platform", "linux")
        import subprocess
        monkeypatch.setattr(subprocess, "Popen",
                            lambda *a, **k: (_ for _ in ()).throw(
                                OSError("no xdg-open")))
        studio.ShanktuaryApp.open_log_folder(app)

        assert app.copied and app.copied.endswith("shanktuary.log")
        assert "clipboard" in str(app.copy_feedback)
