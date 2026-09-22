"""Closing a board on Windows must not free a still-pending overlapped read.

Regression for the Setup -> step-on wizard crash (Windows fatal exception
0xc0000374, heap corruption). hidapi's Windows hid_read() in non-blocking
mode leaves a ReadFile pending whenever no report is waiting; hid_close()
cancels only the CALLING thread's I/O and frees the buffer, so the kernel
later writes a report into freed memory.

FakeWinHid models exactly that: an empty non-blocking read leaves a request
pending, a timed read waits on it, and close() while pending is corruption.
"""
import src.hardware.pressure.hid_backend as hb


class FakeWinHid:
    def __init__(self, reports_after_wait=True, dead=False):
        self.pending = False
        self.corrupted = False
        self.closed = False
        self.reports_after_wait = reports_after_wait
        self.dead = dead

    def read(self, length, timeout_ms=0):
        if self.dead:
            self.pending = False
            raise OSError("read error")
        if timeout_ms == 0:
            # Non-blocking with no data: returns empty, ReadFile stays pending.
            self.pending = True
            return []
        # Timed read waits on the (possibly already pending) request.
        self.pending = True
        if self.reports_after_wait:
            self.pending = False
            return [0x32] + [0] * 21
        return []

    def close(self):
        if self.pending:
            self.corrupted = True
        self.closed = True


def _backend(dev):
    b = hb.HidBackend.__new__(hb.HidBackend)
    b._device = dev
    return b


def test_close_waits_out_the_pending_read_on_windows(monkeypatch):
    monkeypatch.setattr(hb.sys, "platform", "win32")
    dev = FakeWinHid()
    b = _backend(dev)
    dev.read(64)                       # worker's last poll: request pending
    assert dev.pending

    b.close()
    assert dev.closed
    assert not dev.corrupted, "handle freed with a read still pending"
    assert not b.is_open


def test_a_read_that_never_completes_leaks_instead_of_corrupting(monkeypatch):
    monkeypatch.setattr(hb.sys, "platform", "win32")
    monkeypatch.setattr(hb, "_UNSETTLED_HANDLES", [])
    dev = FakeWinHid(reports_after_wait=False)
    b = _backend(dev)
    dev.read(64)

    b.close()
    assert not dev.corrupted
    assert not dev.closed, "closed a handle whose read never finished"
    assert hb._UNSETTLED_HANDLES == [dev]
    assert not b.is_open


def test_a_dead_board_closes_immediately(monkeypatch):
    monkeypatch.setattr(hb.sys, "platform", "win32")
    dev = FakeWinHid(dead=True)
    b = _backend(dev)
    b.close()
    assert dev.closed and not dev.corrupted
