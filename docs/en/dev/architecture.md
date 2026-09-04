# VideoCaptioner Architecture

This page describes the system as it exists in the source tree: one Python core shared by the CLI
and the GUI, the subtitle pipeline, the Video Editor tab, and the managed VieNeu Local runtime.
Domain details live in [Natural Dubbing](../../dev/natural-dubbing.md),
[Video Editor](../../dev/video-editor.md) and [VieNeu One-App](../../dev/vieneu-one-app.md); the
current work log is `status.md` at the repository root.

## Overview

```
                ┌──────────── CLI (videocaptioner/cli) ────────────┐
   video/audio  │ transcribe · subtitle · synthesize · dub · process │
      ─────────►│ download · config · vieneu · style                │
                └───────────────┬───────────────────────────────────┘
                                │ direct calls
                ┌───────────────▼───────────────────────────────────┐
                │ core: asr → split/optimize → translate → subtitle │
                │       → dubbing (TTS + mix) → synthesis (FFmpeg)  │
                │ core/editor · core/tts/vieneu · core/llm · utils  │
                └───────────────▲───────────────────────────────────┘
                                │ via QThread workers in ui/thread
                ┌───────────────┴───────────────────────────────────┐
                │ GUI PyQt5 + QFluentWidgets (videocaptioner/ui)    │
                │ view · components · task_factory · signal_bus     │
                └───────────────────────────────────────────────────┘
```

Rule of thumb: `core/` never imports Qt; the UI orchestrates and presents. Long work (ASR, LLM,
FFmpeg, TTS, the sidecar) runs in `ui/thread/` workers and reports through signals; widgets are never
touched from a worker.

## Directory layout

```text
videocaptioner/config.py          Runtime paths for the three modes: source, pip-installed, PyInstaller
videocaptioner/core/entities.py   Shared entities: TranscribeConfig, SubtitleConfig, *Task, enums
videocaptioner/cli/               argparse, commands/, config.py (config layers), output, exit codes
videocaptioner/core/asr/          ASR engines, ASRData, chunked_asr
videocaptioner/core/split/        Sentence splitting (rules + LLM)
videocaptioner/core/optimize/     LLM subtitle optimization
videocaptioner/core/translate/    BaseTranslator, factory, LLM/Google/Bing/DeepLX
videocaptioner/core/subtitle/     Styles, ASS/rounded renderers, editing (subtitle table operations)
videocaptioner/core/dubbing/      engine, orchestrator, planner, cache, rewrite, audio_mixer, presets
videocaptioner/core/tts/          BaseTTS, OpenAI/MiniMax, vieneu/ (managed runtime + model)
videocaptioner/core/editor/       Video Editor domain: models, commands, project_store, media, voice
videocaptioner/core/llm/          OpenAI-compatible client, credentials, context, request logger
videocaptioner/core/prompts/      Prompt .md files (bundled into the EXE)
videocaptioner/core/utils/        FFmpeg/video_utils, subprocess_helper, installer, cache, logger
videocaptioner/ui/                main.py, view/, components/, thread/, task_factory.py, common/
resource/                         Assets, fonts, translations, subtitle styles (bundled copy)
videocaptioner/resources/         Fallback fonts/translations for the pip package
scripts/                          Launcher, sync_translations, VieNeu one-app builder, PyInstaller entry
installer/                        WiX sources for the MSI
tests/                            Tests per domain; integration/slow/llm markers for external services
```

## Paths and run modes

`videocaptioner/config.py` resolves `ROOT_PATH`, `RESOURCE_PATH`, `APPDATA_PATH` and `WORK_PATH` for
three modes: frozen (PyInstaller, `sys._MEIPASS`), dev (`resource/` beside the package) and pip
(`platformdirs`). It also prepends the managed bin directories (FFmpeg, Faster-Whisper, Deno) to
`PATH` when they exist. `core/utils/installer.py` downloads FFmpeg/Deno into `AppData/bin/` on Windows
when they are missing.

## Configuration

- GUI: `ui/common/config.py` is a qfluentwidgets `QConfig` persisted to `AppData/settings.json`;
  values are read via `cfg.<item>.value` and written via `cfg.set(...)`.
- CLI: `cli/config.py` merges `CLI arguments > env (OPENAI_*, VIDEOCAPTIONER_*) > config.toml
  (user_config_dir) > the GUI's settings.json > defaults`. The GUI layer only mirrors credentials and
  endpoints (`load_gui_settings()`), never behaviour toggles.
- `ui/task_factory.py` turns `cfg` into `SubtitleTask`, `TranscribeTask`, `DubbingTask` and
  `FullProcessTask`; the CLI builds the same entities from its config dict.

## Subtitle pipeline

1. **ASR** (`core/asr`): `transcribe(audio, TranscribeConfig)` picks the engine (Bijian, JianYing,
   Whisper API, whisper.cpp, Faster-Whisper). `chunked_asr` splits long audio and merges the overlapping
   results. The output is `ASRData` (a list of `ASRDataSeg` in milliseconds).
2. **Split/Optimize** (`core/split`, `core/optimize`): word-level subtitles are regrouped into sentences
   by rules and the LLM; the optimizer fixes ASR mistakes in batches through `call_llm`.
3. **Translate** (`core/translate`): `TranslatorFactory` builds a translator; `BaseTranslator` chunks the
   input, runs a `ThreadPoolExecutor` through `submit_with_context` (contextvars preserved) and caches
   results with diskcache. `LLMTranslator` builds a per-film "global context" once and puts a
   deterministic fingerprint of the source into the cache key (never random LLM output).
4. **Subtitle** (`core/subtitle`): `ASRData` exports SRT/ASS/TXT/JSON according to
   `SubtitleLayoutEnum`; ASS styles come from `style_manager`; `ass_renderer` and `rounded_renderer`
   burn subtitles with FFmpeg. `editing.py` holds the operations on the subtitle dict
   (`ASRData.to_json()`) used by the subtitle tab: merge/delete/select rows, search and replace,
   re-export of pipeline outputs.
5. **Synthesis** (`core/utils/video_utils.py`): muxes soft subtitles (mov_text) or burns hard ones
   (`subtitles=`/`ass=` filters), probes CUDA and reads progress from FFmpeg's stderr.

The GUI chains the steps in `SubtitlePipelineThread`; the CLI `process` command runs them in sequence.

## LLM

`core/llm/client.py` keeps one shared OpenAI-compatible client. Credentials are an `LLMCredentials`
dataclass (key hidden from repr) registered through `configure_llm_client()`; `get_llm_client()`
accepts explicit credentials or uses the registered ones, reads `OPENAI_*` from the environment only
as a fallback and never writes to `os.environ`. `call_llm()` is memoized with diskcache;
`request_logger` records requests/responses per `ContextVar` so parallel threads do not interleave.
`core/llm/context.py` carries `task_id`/stage for logging.

## Dubbing

`DubbingEngine` (`core/dubbing/engine.py`) is the API; `DubbingOrchestrator` runs a job: read the
subtitles, let the planner group cues and compute the available time, consult `PersistentTTSCache`,
synthesize the missing groups with the TTS provider, measure the real WAVs, rewrite over-long lines via
`TimingRewriteService` (LLM), apply the fit policy, build the voice track and mix it with the original
audio (`audio_mixer.py`, choosing a filter syntax that works on old and new FFmpeg). A JSON report
records every group. `presets.py` is the single source for the provider table, mix modes and text
sources shared by GUI and CLI. TTS providers: OpenAI, MiniMax, Local AI (self-hosted
OpenAI-compatible) and VieNeu Local (managed).

## VieNeu Local

`core/tts/vieneu/`: `runtime_locator` finds the Python runtime and bridge inside the one-app build;
`runtime_manager` owns the sidecar (loopback port, per-session bearer token, credential-scrubbed
environment, shutdown of exactly its own process tree); `model_updater` downloads/validates/activates
models pinned to a commit SHA with atomic state; `service.py` is the facade for GUI and CLI. VieNeu,
CUDA and FastAPI are never imported into the Qt process. A base build without `runtime/vieneu/` must
disable the actions instead of repeating errors.

## Video Editor

`core/editor/` is Qt-free: `models.py` (schema `editor-project-v1`, milliseconds canonical, stable cue
IDs), `commands.py` (`CommandStack` for every mutation, undo/redo), `project_store.py` (save JSON + SRT;
ASS only through "Save as ASS"), `media.py` (probe/thumbnail/waveform/render with FFmpeg, cancellable),
`adapters.py` and `voice.py` (bridges to dubbing/TTS). `ui/view/video_editor_interface.py` is the
PyQt5/QFluentWidgets page; preview and export share `build_visual_filter_graph`. No PySide6 or MPV.

## Subprocesses and environment

Every `subprocess.run/Popen` under `videocaptioner/` passes `env=child_environment()`
(`core/utils/subprocess_helper.py`): a copy of `os.environ` without `OPENAI_*`/`VIDEOCAPTIONER_*` that
keeps the prepended PATH. Windows uses `CREATE_NO_WINDOW`. Arguments are always lists, never
`shell=True`.

## Packaging and tests

- PyInstaller `onedir` with the single `VideoCaptioner.spec`; entry `scripts/pyinstaller_gui.py`;
  resources and prompts must be listed in the spec. `scripts/build_vieneu_one_app.py` merges the runtime
  and model seed into the onedir output.
- Gates: `ruff check videocaptioner/`, `pyright videocaptioner/` (0 errors), `pytest tests/test_cli`,
  `sync_translations.py --check`; CI (`.github/workflows/ci.yml`) also runs the offline suite
  `-m "not integration and not slow and not llm"` on Ubuntu with FFmpeg and offscreen Qt.
- Tests that need external services carry the `integration`/`llm` markers; tests that need FFmpeg skip
  when it is absent.

---

Related:
- [API](/en/dev/api)
- [Contributing](/en/dev/contributing)
