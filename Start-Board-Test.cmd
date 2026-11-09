@echo off
setlocal
cd /d "%~dp0"
echo Shanktuary physical-board source test. No administrator access is needed.
echo Requires Windows x64 and Python 3.12 x64 with Tcl/Tk.
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  py -3.12 "%~dp0windows_review_setup.py" %*
  goto finished
)
python -c "import sys; assert sys.version_info[:2] == (3,12)" >nul 2>&1
if not errorlevel 1 (
  python "%~dp0windows_review_setup.py" %*
  goto finished
)
echo Python 3.12 was not found. Install Python 3.12 x64 from python.org
echo with Tcl/Tk enabled, then run this file again. See WINDOWS-BOARD-TEST.md.
:finished
echo.
pause
endlocal
