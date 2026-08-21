# Video Editor Tab Integration Plan

Current status: COMPLETED on 2026-08-21. E0-E7 and every machine-verifiable acceptance criterion below
passed; subjective UX, real-provider audio quality and diverse user-video evaluation remain outside the
machine acceptance boundary.

Reference UI: the two user-provided screenshots from 2026-08-21. Reference implementation inspected
read-only at `F:\CppClone\CapCap`.

## 1. Goal

Add a native `Video Editor` navigation tab immediately below `Kiểu phụ đề` and above request logs. The
tab must let a user load a video plus SRT, inspect and edit display/TTS text against a synchronized
timeline, regenerate selected voice, preview a short range, and export through the existing
VideoCaptioner subtitle/dubbing/synthesis engines.

SRT remains the canonical persisted subtitle artifact. ASS is generated only for an explicit Save as
ASS action or as a temporary render input that is removed after preview/export.

## 2. Evidence and constraints

- VideoCaptioner is PyQt5 + QFluentWidgets. Long work belongs in `videocaptioner/ui/thread/`.
- Its current `SubtitleInterface` already owns editable original/translated data and an explicit Save
  menu containing SRT/ASS/VTT/JSON/TXT, but active video-player hooks are commented out.
- CapCap uses PySide6, python-mpv, a large monolithic main window, and optional NumPy/SciPy/ONNX stacks.
  Importing its UI modules directly would mix Qt bindings and add unapproved dependencies.
- Useful CapCap design references are `ui/views/editor/timeline.py`, `track_labels.py`,
  `ui/views/preview_panel.py`, `app/layers/`, `app/core/state/project_state.py`, and the waveform/thumbnail
  workers in `ui/worker_adapters/processing_workers.py`.
- Port concepts and algorithms into VideoCaptioner-owned PyQt5 modules. Do not copy the CapCap main
  window, switch VideoCaptioner to PySide6, or add MPV/model dependencies without a separate approval and
  license/package-size checkpoint.

## 3. Target layout

Navigation order:

~~~text
Trang chủ
Xử lý hàng loạt
Kiểu phụ đề
Video Editor
Nhật ký yêu cầu
~~~

Editor workspace:

~~~text
Command bar: Open | Save project | Undo | Redo | Fast preview | Export
Horizontal splitter: video preview and transport | context inspector
Vertical splitter: preview/inspector above | timeline below
Timeline tracks: V1 Video | A1 Original Audio | TS1 Subtitle + TTS
~~~

The inspector shows start/end, source text, display subtitle, TTS text, fit status, warnings, speaker,
voice speed, and `Regenerate voice`. Controls follow QFluentWidgets; the reference screenshot guides
density and hierarchy, not colors copied pixel-for-pixel. ImageGen may be used later for a static visual
mockup, but the shipped UI must be native widgets and icons, not a generated bitmap.

## 4. Target architecture

Create a core editor domain independent of Qt:

- `videocaptioner/core/editor/models.py`: `EditorProject`, `EditorTrack`, `EditorClip`, `EditorCue`.
- `videocaptioner/core/editor/adapters.py`: lossless conversion to/from `ASRData`, `DubbingCue`, and
  `DubbingReport` without flattening display and TTS text together.
- `videocaptioner/core/editor/commands.py`: undoable edit commands for text, timing, split, delete, add,
  move, and per-cue voice settings.
- `videocaptioner/core/editor/project_store.py`: atomic versioned JSON state containing relative paths and
  stable cue IDs; never API keys or absolute prompt payloads.

Create PyQt5 presentation modules:

- `videocaptioner/ui/view/video_editor_interface.py`: navigation page and orchestration only.
- `videocaptioner/ui/components/editor/timeline_view.py`: virtualized `QGraphicsView` timeline.
- `videocaptioner/ui/components/editor/track_header.py`: fixed synchronized labels and mute/lock controls.
- `videocaptioner/ui/components/editor/subtitle_inspector.py`: selected-cue editor.
- `videocaptioner/ui/components/editor/video_preview.py`: playback surface and subtitle overlay.
- `videocaptioner/ui/thread/editor_media_thread.py`: ffprobe, waveform, thumbnails, and five-second preview.
- `videocaptioner/ui/thread/editor_voice_thread.py`: selected-group regeneration through
  `DubbingEngine`, with an explicit force-refresh for that cache key only.

`MainWindow` constructs the page and inserts it after `SubtitleStyleInterface`. Use an icon verified in
the installed QFluentWidgets version.

## 5. Delivery phases

### E0 - Contract and fixtures

- Freeze `editor-project-v1`, stable cue IDs, milliseconds as canonical timing, and SRT-only persistence.
- Add deterministic short video/SRT/WAV fixtures and a 1,000-cue performance fixture.
- Audit CapCap GPL/license compatibility and any code that is ported rather than rewritten.

### E1 - Navigation and shell

- Add the tab in the exact requested navigation position.
- Build responsive splitters, empty/open/loading/error states, command bar, and keyboard focus order.
- No nested decorative cards; preview and timeline are full working surfaces.

### E2 - Preview and canonical project state

- Load video metadata and SRT into `EditorProject`; preserve source/display/TTS fields independently.
- Start with PyQt5 QtMultimedia already available in the environment; make MPV a later dependency gate if
  codec/seek acceptance fails.
- Synchronize playback position, subtitle overlay, cue selection, and inspector without blocking Qt.

### E3 - Timeline MVP

- Implement V1/A1/TS1, ruler, playhead, horizontal zoom/scroll, waveform, thumbnails, cue selection,
  drag/resize, split/delete/add, track lock/mute, undo/redo, and selection range.
- Cache waveform/thumbnails by media fingerprint; workers discard stale request signatures.
- Paint only visible clips so a 60-minute/1,000-cue project remains responsive.

### E4 - Subtitle and dubbing inspector

- Edit source, display subtitle, TTS text, timing, voice speed, and optional speaker.
- Validate non-negative/non-overlapping timing before mutation; command stack is the single write path.
- `Regenerate voice` invalidates only the selected group's persistent cache key, measures the new WAV,
  updates fit/report state, and never mutates unrelated groups.
- Show `Removed repeated TTS boundary overlap` and allow the user to restore intentional repetition.

### E5 - Preview and export

- Fast Preview renders only the selected range or five seconds around the playhead through existing FFmpeg
  utilities and the live editor model.
- Export reuses existing Natural/Legacy dubbing and synthesis. It never reads stale pipeline SRT/ASS when
  the editor model is dirty.
- Save writes project JSON + SRT atomically. Explicit Save as ASS is the only persistent ASS route;
  temporary render ASS lives under a run temp directory and is cleaned.

### E6 - Optional visual layers

- Port Blur, Logo, Mask, and Text only after the V1/A1/TS1 editor passes acceptance.
- Each layer gets a core model, inspector, timeline clip, preview renderer, export renderer, undo command,
  serialization, and round-trip test. Do not expose placeholder buttons before these paths work.

### E7 - Integration and packaging

- Connect Home/Subtitle/Dubbing report actions to `Open in Video Editor` using structured project data.
- Add translations to source files, sync fallback resources, and update `VideoCaptioner.spec` only for new
  runtime assets/imports.
- Run targeted editor tests, full offline suite, Ruff, Pyright, translation sync, FFmpeg integration,
  labelled EXE build, and packaged startup/import/resource smoke.

## 6. Acceptance criteria

1. `Video Editor` appears directly below `Kiểu phụ đề` at desktop and minimum supported window size.
2. Opening video + SRT creates one V1, one A1, and one TS1 model without changing source files.
3. Selecting or seeking a cue synchronizes preview, timeline, inspector, and subtitle overlay.
4. Display subtitle and TTS text round-trip independently through save/reopen/export.
5. Undo/redo covers text, timing, split, delete, add, drag, resize, and voice-setting edits.
6. Regenerating one cue makes one TTS request/cache refresh and leaves every other audio file untouched.
7. Boundary-overlap normalization cannot produce duplicated spoken tokens; intentional full-cue repetition
   remains editable and is never silently deleted.
8. Normal completion persists SRT and project JSON only. No ASS appears unless explicitly requested.
9. Fast Preview and final export use the same current editor state and preserve video duration.
10. A 60-minute video with 1,000 cues can scroll/zoom/select without repainting every off-screen clip.
11. No UI worker touches widgets directly, no PySide6 import enters VideoCaptioner, and no new dependency is
    added without approval.
12. Full tests, quality gates, final EXE build, bundled-resource inspection, and packaged smoke pass.

## 7. Explicitly deferred

- Piper/Edge TTS, Sherpa-ONNX diarization, automatic per-speaker assignment, OCR range re-transcription,
  remote engine server, and bundled MPV remain separate dependency/license campaigns.
- ImageGen mockups do not count as editor implementation or runtime acceptance.

## 8. Delivery record — 2026-08-21

### Phase results

- **E0 pass:** `editor-project-v1`, stable IDs, millisecond timing, SRT-only contract, deterministic
  H.264/AAC/SRT/WAV fixtures and 60-minute/1,000-cue fixture. CapCap is Apache-2.0; implementation was
  rewritten as VideoCaptioner-owned GPL-3.0 code.
- **E1 pass:** exact navigation order, command bar, empty/loading/error states, responsive splitters and
  700-pixel page-width acceptance.
- **E2 pass:** QtMultimedia H.264/AAC playback + seek, SRT import, overlay/playhead/selection/inspector
  synchronization and independent source/display/TTS state.
- **E3 pass:** V1/A1/TS1 ruler, zoom/scroll, range, waveform, thumbnails, drag/resize, add/split/delete,
  mute/lock and undo/redo. Stale media results are discarded by request signature.
- **E4 pass:** timing/text/speaker/voice inspector and selected-group force refresh through
  `DubbingEngine`; unrelated cache entries remain byte-identical.
- **E5 pass:** Fast Preview and final export use the same live snapshot, mix regenerated WAV, reuse
  Natural/Legacy Dubbing and preserve duration. Normal completion writes SRT/project only.
- **E6 pass:** Blur/Logo/Mask/Text have models, UI editing, timeline clips, preview/export renderers,
  undo commands and round-trip tests; no placeholder controls are exposed.
- **E7 pass:** Subtitle/Dubbing handoff, translations/docs, full quality gates, labelled EXE archive
  inspection and exact packaged smoke.

### Acceptance evidence

1. Navigation order and 700 px layout: pass.
2. One V1/A1/TS1 model without source mutation: pass.
3. Preview/timeline/inspector/overlay synchronization: pass.
4. Independent display/TTS project and export round-trip: pass.
5. Undo/redo for text, timing, split/delete/add, move/resize and voice settings: pass.
6. One selected group regeneration/cache refresh; unrelated cache untouched: pass.
7. Boundary overlap repair and intentional full-cue repetition regression: pass.
8. SRT/project-only normal save; explicit ASS-only persistence: pass.
9. Shared current state and duration-preserving FFmpeg preview/export: pass (±120 ms fixture tolerance).
10. 60 minutes/1,000 cues: 3 visible cues painted; 0.220 ms average measured paint.
11. Worker/widget isolation, no PySide6/MPV/new dependency: pass.
12. Editor 23/23; full offline 419 passed/23 skipped; Ruff/Pyright/translations/build/archive/smoke:
    pass.

Final artifact: `dist/VideoCaptioner-VideoEditor-20260821.exe`, 113,104,947 bytes,
SHA-256 `23836F039A3C4E7CC2C2257352E2AC1A150901BFE8B8D707176A4BA486F119E7`, `NotSigned`.
