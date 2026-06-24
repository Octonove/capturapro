# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para CapturaPro (build onedir, ventana sin consola).

La ruta de ffmpeg.exe se pasa por la variable de entorno FFMPEG_SRC
(ver build.ps1). Si esta definida, ffmpeg.exe (y ffprobe.exe si existe) se
empaquetan junto a la aplicacion.
"""

import os

block_cipher = None

binaries = []
ffmpeg_src = os.environ.get("FFMPEG_SRC", "")
if ffmpeg_src and os.path.isfile(ffmpeg_src):
    # Solo ffmpeg.exe: la app no usa ffprobe en runtime (ahorra ~210 MB).
    binaries.append((ffmpeg_src, "."))

icon_path = os.environ.get("APP_ICON", "")
icon_arg = icon_path if (icon_path and os.path.isfile(icon_path)) else None

a = Analysis(
    ['..\\CapturaPro.py'],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=['PIL._tkinter_finder', 'soundcard', 'soundcard.mediafoundation',
                   '_cffi_backend'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'pandas', 'matplotlib', 'PyQt5', 'PyQt6', 'PySide6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CapturaPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CapturaPro',
)
