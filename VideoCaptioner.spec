# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for the VideoCaptioner Windows GUI build.

Single spec for every build. The exe name comes from the VC_BUILD_NAME env var,
so a dated/labelled build doesn't need its own copy of this file:

    set VC_BUILD_NAME=VideoCaptioner-YouTubeFix-20260630
    uv run pyinstaller VideoCaptioner.spec --clean --noconfirm

Without VC_BUILD_NAME the application directory is ``dist/VideoCaptioner``.
The installer presents it as one app/shortcut while avoiding onefile extraction
on every launch.
"""

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

BUILD_NAME = os.environ.get("VC_BUILD_NAME", "VideoCaptioner")

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
    # Reproducible alignment recipe only. GPU interpreter/model are installed separately.
    ("runtime\\alignment", "runtime\\alignment"),
]
binaries = []
hiddenimports = []
hiddenimports += collect_submodules("videocaptioner")
# Native settings/probe pages load lazily; explicitly retain their frozen entry points.
hiddenimports += ["videocaptioner.core.asr.native_api",
                  "videocaptioner.ui.components.NativeASRSettingWidget",
                  "videocaptioner.ui.thread.native_asr_thread"]
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
    excludes=["torch", "torchaudio", "qwen_asr"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=BUILD_NAME,
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
    icon="resource\\assets\\logo.png",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=BUILD_NAME,
)
