# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec pentru motorul Deadlock Helper (fara interfata).

Build:  pyinstaller engine.spec --noconfirm --clean   ->  dist/dlh-engine/

Interfata Electron (ui/) il ia din dist/dlh-engine si il pune in installer.
Onedir, nu onefile: nu se mai dezarhiveaza la fiecare pornire. Consola ramane
(console=True): vorbim cu interfata pe stdin/stdout; Electron il porneste cu
fereastra ascunsa.
"""

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[("icon.ico", ".")],
    hiddenimports=["engine.assets", "engine.stats", "engine.vision", "engine.game", "engine.bug_report"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["unittest", "pydoc", "doctest", "lib2to3", "sqlite3", "tkinter", "_tkinter",
              "PIL", "matplotlib", "scipy", "pandas"],
    noarchive=False,
)

# ffmpeg-ul din opencv (30 MB) e doar pentru video: noi citim imagini
a.binaries = [b for b in a.binaries if "opencv_videoio_ffmpeg" not in b[0]]
a.datas = [d for d in a.datas if "opencv_videoio_ffmpeg" not in d[0]]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dlh-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon="icon.ico",
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="dlh-engine")
