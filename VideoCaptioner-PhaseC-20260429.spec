# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ("resource\\assets", "resource\\assets"),
    ("resource\\fonts", "resource\\fonts"),
    ("resource\\translations", "resource\\translations"),
    ("resource\\subtitle_style", "resource\\subtitle_style"),
    # Package-level non-Python resources required at runtime.
    # collect_submodules() only picks up .py files, so .md prompts and
    # fallback fonts/translations must be added explicitly.
    ("videocaptioner\\core\\prompts", "videocaptioner\\core\\prompts"),
    ("videocaptioner\\resources", "videocaptioner\\resources"),
]
binaries = []
hiddenimports = []
hiddenimports += collect_submodules("videocaptioner")
tmp_ret = collect_all("qfluentwidgets")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]
tmp_ret = collect_all("py7zr")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]


a = Analysis(
    ["scripts\\pyinstaller_gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
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
    a.binaries,
    a.datas,
    [],
    name="VideoCaptioner-PhaseC-20260429",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
