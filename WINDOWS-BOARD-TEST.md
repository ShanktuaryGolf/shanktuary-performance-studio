SHANKTUARY WINDOWS WII BOARD TEST - SOURCE WORKFLOW, NOT A RELEASE

This is an isolated source test run from your git checkout, not an installer.
Physical Windows hardware has NOT been tested here. Automated Linux tests
and Windows wheel availability checks cannot establish Bluetooth reliability.
ACCURACY WARNING: factory-calibration failure uses adaptive scaling, which is
NOT verified kg/force accuracy. Check console calibrated=yes/adaptive status.

REQUIREMENTS
Windows x64, Python 3.12 x64 from python.org with Tcl/Tk, internet for the
first setup, and one or two Wii Balance Boards. Reading requires them to be paired and
exposed as Windows HID devices. Close other software reading those same boards.
No administrator access, driver install, firewall change, execution-policy
change or security bypass is required or performed by this launcher.
Optional native pairing changes system-wide Bluetooth bonds/HID services only
after your explicit in-app confirmation.

START
1. In your existing source checkout, save/commit any local work before running
   git pull. Resolve any conflicts before launching. Do not copy this over an
   installed application directory.
2. Double-click Start-Board-Test.cmd. Approve the local first-run setup if
   wanted. It installs pinned Pillow, hidapi and setuptools in .venv-board-test here.
3. Choose one or two physical Wii boards in the startup window. Closing that
   chooser cancels before pressure hardware is opened.
4. The Boards setup screen opens. Use Scan to find already-paired boards.
   If needed, click Pair Board and read the system-wide pairing confirmation.
   Enter the number of NEW unpaired boards (not the total including existing
   bonds). Press red SYNC on only the prompted board, then confirm that step.
   Repeat if pairing a second new board. Keep the other board out of SYNC.
   For two boards, assign two DISTINCT devices left/right. Verify each board
   independently changes its own live reading; selecting dual mode alone is
   not proof that both devices connected. With only one available, underlying
   code can expose that one board while the second is missing.
5. With boards unloaded, tare; then test safe, stationary weight shifts.
   Confirm the UI reports hardware rather than demo and readings respond to
   physical loading. Do not use this unverified build for clinical decisions.

PAIRING LIMIT
Native Windows pairing is available only after you click Pair Board and accept
its explicit confirmation. This can alter OS Bluetooth bonds/services, including
removing and recreating a stale bond during recovery, so it affects other apps.
It does not install drivers or change security settings. Pair one/two NEW boards,
not already-bonded ones. The native flow uses Windows Bluetooth APIs; physical
Windows compatibility is not verified here. Canceling either prompt starts no
pairing. Bluetooth must already be enabled on the laptop.
Windows Add Device PIN text entry is not a dependable Wii solution: the Wii PIN
is six binary bytes. Do not install unofficial drivers, disable security, or
paste guessed PINs. If native pairing or Scan fails, stop and report Windows
version, Bluetooth adapter and pairing error. No physical result is claimed.

DATA HONESTY AND LIMITS
Every hardware launch creates a NEW empty isolated session under
board-test-state/run-... . Previous runs remain on disk. There is no imported
shot history or synthetic pressure fallback. Demo toggles are blocked in the
physical test. Browser overlay fictional shot placeholders are removed; no
launch-monitor connection is started by this board-only test.
For the separate, explicitly synthetic visual review, close hardware mode and
run Start-Demo-Only.cmd. Its state is in demo-only-state, and its window/session
are labeled SAMPLE DATA. Demo results are never physical hardware evidence.
Open-FP remains an experimental source in the underlying app UI; this bundle's
startup and instructions target Wii boards. Do not select simulator endpoints
and call those readings hardware evidence.

A live stream is not proof of calibrated accuracy. The current HID backend can
fall back to adaptive scaling if factory calibration cannot be read; check the
console for calibrated=yes versus calibrated=adaptive. Treat adaptive readings
as unverified. Two-board fallback and Windows Bluetooth compatibility still
need actual laptop testing. Launch-monitor synchronized shot capture is outside
this board-only package's scope.

ISOLATION
All app paths are redirected before importing the app. A new loopback-only
server selects a free port instead of taking installed Studio's port 9321.
The console prints its actual URL. Use only links opened by this test, not an
old localhost:9321 tab. .venv-board-test, board-test-state and demo-only-state are local to
the checkout folder; installed app data/settings are not read or overwritten.
Bluetooth devices are shared OS resources: reading a paired board can contend
with another app, and optional pairing changes system-wide bonds/services.
App data isolation is not a Bluetooth sandbox.
Run only the provided .cmd launchers, not the production entrypoints. Keep the
console open for errors and close the app normally to release hardware handles.
To remove test dependencies/data, delete only .venv-board-test, board-test-state
and demo-only-state after saving any results you need. Do not delete your repo.

VERIFICATION
Pinned Python 3.12 win_amd64 wheels downloaded successfully for Pillow 11.3.0,
hidapi 0.14.0.post4; setuptools 80.9.0 provides a universal wheel.
Automated launcher checks are in tests/test_windows_board_test_launcher.py.
No Windows runtime, real Wii
board stream, dual-board calibration or OS pairing test was performed here.
Use git rev-parse HEAD to identify the tested source revision.
