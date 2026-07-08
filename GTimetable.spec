# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Testy Timetables — offline desktop build.
#
# Build with:  pyinstaller GTimetable.spec
# Run this on EACH target OS separately (Windows -> .exe, macOS -> .app/binary,
# Linux -> ELF binary). PyInstaller cannot cross-compile.

a = Analysis(
    ['run_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
    ],
    hiddenimports=[
        'reportlab.graphics.barcode.common',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['psycopg2', 'psycopg2-binary'],  # not needed offline (SQLite only)
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GTimetable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no terminal window; errors go to app.log instead (see run_desktop.py)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,
)
