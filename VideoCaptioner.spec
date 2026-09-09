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
hiddenimports += ["videocaptioner.core.dubbing.scheduling", "videocaptioner.core.dubbing.review",
                  "videocaptioner.ui.components.dubbing_review_dialog",
                  "videocaptioner.core.subtitle.synthesis"]
hiddenimports += ["videocaptioner.core.tts.omnivoice.provider", "videocaptioner.core.tts.omnivoice.runtime",
                  "videocaptioner.ui.components.omnivoice_panel"]
# S5 recipes/current bridge are data, including reuse of compatible old runtimes.
# GPU imports stay in the separate worker interpreter.
hiddenimports += ["videocaptioner.core.asr.local.pipeline", "videocaptioner.core.asr.local.review",
                  "videocaptioner.core.asr.local.prepare", "videocaptioner.core.asr.local.sentence_timing",
                  "videocaptioner.core.asr.local.sentence_fallback",
                  "videocaptioner.core.asr.audio_identity",
                  "videocaptioner.ui.thread.audio_identity_thread",
                  "videocaptioner.cli.commands.local_asr", "videocaptioner.ui.thread.local_asr_thread"]
# S4 context schema and editor form; translate/conversation.md is included by the prompt tree above.
hiddenimports += ["videocaptioner.core.translate.conversation",
                  "videocaptioner.ui.components.conversation_dialog"]
# Local ASR review/resume and cooperative subtitle worker lifecycle (S4.1).
hiddenimports += ["videocaptioner.core.asr.review",
                  "videocaptioner.ui.components.asr_review_dialog",
                  "videocaptioner.ui.thread.worker_lifecycle"]
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
    excludes=["torch", "torchaudio", "qwen_asr", "pyannote", "torchcodec"],
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
