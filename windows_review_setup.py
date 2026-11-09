"""Explicit, bundle-local setup for a isolated Windows physical-board source test."""
import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def main():
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64') or sys.maxsize <= 2**32:
        raise RuntimeError('This launcher requires Windows x64. ARM and other systems are not validated.')
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Use Python 3.12 x64 from python.org, with Tcl/Tk enabled.')
    import tkinter
    state = ROOT / 'board-test-state'
    state.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
               TEMP=str(state), TMP=str(state), PIP_CONFIG_FILE=os.devnull)
    # Ignore inherited Python import overrides and package index credentials/settings.
    for key in list(env):
        if key.startswith('PIP_') and key != 'PIP_CONFIG_FILE':
            env.pop(key)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    python = ROOT / '.venv-board-test' / 'Scripts' / 'python.exe'
    requirements = ROOT / 'requirements-review.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = ROOT / '.venv-board-test' / '.review-dependencies'
    ready = python.exists() and marker.exists() and marker.read_text() == fingerprint
    if not ready:
        print('First-run setup creates .venv-board-test and board-test-state ONLY in this extracted folder.')
        print('It downloads Pillow 11.3.0, hidapi 0.14.0.post4 and setuptools 80.9.0 from https://pypi.org using the internet.')
        print('No global packages, administrator access, firewall changes or installed Studio changes.')
        if input('Continue with this local setup? [y/N] ').strip().lower() != 'y':
            print('Setup cancelled.'); return
        if not python.exists():
            subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv-board-test')], check=True, env=env)
        subprocess.run([str(python), '-m', 'pip', '--isolated', 'install', '--index-url',
                        'https://pypi.org/simple', '--no-cache-dir', '--disable-pip-version-check',
                        '--only-binary=:all:', '--no-deps', '-r', str(requirements)], check=True, env=env)
        marker.write_text(fingerprint)
    subprocess.run([str(python), '-c', 'import tkinter; import hid; from PIL import Image, ImageTk'], check=True, env=env)
    subprocess.run([str(python), str(ROOT / 'scripts' / ('review_desktop.py' if '--demo' in sys.argv else 'hardware_review.py')),
                    '--state-dir', str(ROOT / 'demo-only-state' if '--demo' in sys.argv else state)], cwd=ROOT, env=env, check=True)

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ImportError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Cannot start review: {exc}')
        print('See WINDOWS-BOARD-TEST.md. Do not run as administrator or change security settings.')
        sys.exit(1)
