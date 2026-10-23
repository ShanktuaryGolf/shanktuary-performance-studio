# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['shanktuary_app.py'],
    pathex=['src/ui/_legacy'],
    binaries=[],
    datas=[('assets', 'assets'), ('src/analytics/data', 'src/analytics/data')],
    hiddenimports=[
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageDraw',
        'PIL.ImageOps',
        'zeroconf',
        'obs_server',
        'tkinter',
        'http.server',
        'socketserver',
        'urllib.parse',
        'json',
        'threading'
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShanktuaryPerformanceStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ShanktuaryPerformanceStudio',
)
