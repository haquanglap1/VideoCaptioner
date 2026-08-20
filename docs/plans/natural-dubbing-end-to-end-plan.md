# Natural Dubbing End-to-End Plan

Current status: MACHINE COMPLETE — P-1 through P8 implemented and verified; subjective/live-provider
acceptance remains with the user.

Last verified: 2026-08-21 at workspace F:\CppClone\VideoCaptioner.

Closeout evidence: targeted gates passed (dubbing 55, pipeline 1, CLI 58, translate 14 passed/7 skipped,
ASRData 46); full suite 379 passed/26 skipped/0 failed; Ruff pass; CLI Pyright 0 errors/0 warnings;
translation sync pass. PyInstaller artifact `dist/VideoCaptioner-NaturalDubbing-20260821.exe` is
112,995,075 bytes, SHA-256 `F1BC0254B73B06DF49E852762E6D028CE5E0C44C8C310D035C30A60FD3A89D4B`.
Packaged parent/child lived for 15 seconds, startup log had no exception match, and all created PIDs were
closed. This artifact also includes the later SRT-only pipeline, merged-TTS boundary-overlap fixes,
daily app/LLM log partitioning, in-memory default reports, and concrete failure reasons.
Authenticode status is `NotSigned`.

## 1. Goal

Deliver one complete VideoCaptioner release that:

- always dubs the intended target-language text;
- keeps display subtitles separate from TTS wording;
- plans voice groups against real timeline capacity;
- synthesizes at a natural provider speed, measures the real audio, and rewrites only timing outliers;
- never silently truncates speech in Natural mode;
- persists reusable TTS audio in a deterministic cache;
- keeps a machine-readable dubbing report in memory, optionally persists it with `--report`, and shows a
  GUI review summary;
- exposes the same workflow through a new CLI "dub" command and optional "process --dub";
- preserves Legacy timing for users who explicitly choose it;
- passes unit, integration, full-suite, packaging, and packaged-startup gates.

The user will perform subjective listening and real-provider acceptance after handoff. The implementation
session must complete all machine-verifiable work first and must not stop between phases to request
manual confirmation.

## 2. Execution contract for the next session

The next implementation session is authorized to:

1. Read AGENTS.md, this plan, README.md, the newest status.md section, and only the source/tests named
   by the active phase.
2. Implement every mandatory phase P-1 through P8 continuously.
3. Run targeted tests after each phase, then the full offline suite, FFmpeg integration tests, build
   the labelled EXE, and smoke-test that exact EXE.
4. Fix failures found by those gates and continue without waiting for phase-by-phase user approval.
5. Update this plan, README.md, status.md, and focused documentation with measured results.

Do not:

- commit, push, create a release, or modify Git history;
- install new packages or change configuration outside the workspace;
- overwrite or delete unrelated user artifacts;
- read or expose API keys, cookies, transcripts, or private media;
- claim live API, subjective listening, or real-video acceptance unless actually run.

Only stop for a real blocker that requires new authority, such as a missing package that is not already
locked, unavailable credentials required by an acceptance gate, a destructive action, or an external
service outage with no deterministic fallback. A missing live API key is not a blocker for this release:
use fake providers and deterministic fixtures, finish all machine gates, and mark live-provider acceptance
as pending for the user's later test.

## 3. Mandatory release scope

The mandatory release includes:

- P-1 baseline cleanup needed to make gates trustworthy;
- P0 correct target-text routing;
- P1 rich dubbing data model, stable report schema, and deterministic timing planner;
- P2 persistent TTS cache;
- P3 timing-aware LLM rewrite service with deterministic validation;
- P4 measured synthesize/rewrite/fit orchestration;
- P5 Natural versus Legacy audio policy;
- P6 GUI review summary and TTS-text separation;
- P7 CLI dubbing and process integration;
- P8 regression, documentation, EXE build, and packaged smoke test.

The following CapCap-inspired features are intentionally outside this mandatory release:

- Piper and Edge TTS;
- Sherpa-ONNX speaker diarization;
- per-speaker automatic voice assignment;
- OCR subtitle extraction and range re-transcription;
- MPV timeline, waveform, thumbnails, and general-purpose layer editor;
- bundled FFmpeg/MPV resource manager;
- remote engine server.

Reason: these require new dependencies, binary/model licensing audits, or a separate editor architecture.
They must not block the natural-dubbing release. Record them in Section 18 as the follow-up campaign.

## 4. Verified baseline and known defects

Verified from current source:

- SubtitleProcessData has index/original_text/translated_text/optimized_text but no timing.
- ASRDataSeg has text/translated_text/start_time/end_time but no TTS wording or speaker metadata.
- SubtitlePipelineThread passes subtitle_task.output_path into DubbingTask.
- ASRData.from_srt treats the first line of a detected bilingual cue as text and the second as
  translated_text.
- DubbingEngine._create_tts_data currently reads seg.text unconditionally.
- DubbingEngine._align_timeline may speed up to DubbingConfig.max_speed, currently 1.5 by default,
  and truncates speech that still exceeds the available window.
- Full-pipeline dubbing failure is currently treated as non-fatal and can silently continue with the
  original video.
- The TTS work directory is temporary and deleted at the end; generated segment audio is not reusable.
- There is no CLI "dub" command.
- The CLI config roundtrip test writes the global config directory even when config_path points to a
  temporary test file.
- Current Pyright baseline has one warning in cli/commands/synthesize.py around the preset Literal type.
- AGENTS.md is an intentional untracked file from the previous task; preserve it.

Baseline evidence to refresh at implementation start:

~~~powershell
git status --short --branch
.\.venv\Scripts\python.exe -m pytest tests\test_dubbing tests\test_thread\test_subtitle_pipeline_thread.py -q
.\.venv\Scripts\ruff.exe check videocaptioner\
.\.venv\Scripts\pyright.exe videocaptioner\cli\
~~~

If .venv is absent, stop before installing packages because package installation requires explicit
permission. It existed and used CPython 3.12.13 at the last verified session.

## 5. Target architecture

The final internal flow must be:

~~~text
ASRData with original and translated text
    -> explicit DubbingTextSource resolution
    -> DubbingCue list
    -> deterministic DubbingGroup planner
    -> optional pre-rewrite for predicted hard overruns
    -> persistent-cache lookup
    -> TTS at provider-native requested speed
    -> real WAV duration measurement
    -> rewrite and re-synthesize measured outliers only
    -> Natural or Legacy fit policy
    -> voice-track construction and media mix
    -> in-memory DubbingReport + optional JSON + GUI/CLI summary
~~~

Display subtitle generation remains independent:

~~~text
ASRData -> selected bilingual/monolingual layout -> SRT/ASS/render
~~~

Never use a formatted bilingual SRT as the canonical internal boundary between translation and dubbing.
SRT remains an import/export artifact, not the rich domain model.

## 6. Domain model and stable schema

Create videocaptioner/core/dubbing/models.py.

### 6.1 Enums

Define string-backed enums:

- DubbingTextSource: AUTO, TRANSLATED, ORIGINAL
- DubbingTimingMode: NATURAL, LEGACY
- UnresolvedFitPolicy: REVIEW, ALLOW_OVERLAP
- DubbingFitStatus: PENDING, CACHED, FIT, REWRITTEN, SPEED_ADJUSTED, NEEDS_REVIEW, FAILED

Keep serialized values stable and English.

### 6.2 DubbingCue

Required fields:

- cue_id: stable integer or deterministic string
- start_time: seconds
- end_time: seconds
- source_text
- subtitle_text
- tts_text
- speaker: optional string, empty for this release
- voice: optional per-cue override, empty for this release
- group_id
- original_index
- metadata: dict for forward compatibility

### 6.3 DubbingGroup

Required fields:

- group_id
- cue_ids
- start_time
- subtitle_end_time
- available_end_time
- available_duration
- source_text
- subtitle_text
- tts_text
- predicted_duration
- measured_duration
- fit_ratio
- attempt_count
- action_taken
- fit_status
- needs_review
- cache_key
- audio_path
- warnings

### 6.4 DubbingPlan

Required fields:

- schema_version: "dubbing-plan-v1"
- source_path basename only
- target_language
- provider
- model
- voice
- timing_mode
- created_at
- groups
- summary

Do not serialize API keys, base paths containing credentials, absolute input paths, or raw provider
responses. Absolute cache audio paths may be used internally but the exported report should store
paths relative to the report or cache root when practical.

### 6.5 DubbingReport

Keep a versioned report in memory for every run. Persist JSON only when an explicit report path is
requested:

~~~text
videocaptioner dub ... --report <path>.json
~~~

Summary fields:

- total_groups
- cache_hits
- rewritten_groups
- speed_adjusted_groups
- fit_groups
- review_groups
- failed_groups
- maximum_fit_ratio
- p95_fit_ratio
- total_tts_attempts
- output_created

Write JSON atomically through a temporary sibling file followed by replace.

## 7. Configuration contract

Extend videocaptioner/core/dubbing/config.py without removing current keys.

Add:

~~~python
text_source = DubbingTextSource.AUTO
timing_mode = DubbingTimingMode.NATURAL
natural_max_speed = 1.08
fit_ratio_limit = 1.05
borrow_gap_ms = 350
silence_guard_ms = 80
max_group_duration = 8.0
max_rewrite_attempts = 2
rewrite_enabled = True
cache_enabled = True
unresolved_policy = UnresolvedFitPolicy.REVIEW
~~~

Rules:

- max_speed remains the Legacy-mode ceiling and stays backward compatible.
- Natural mode must ignore max_speed and use natural_max_speed.
- Natural mode must never call the truncation path.
- Existing global TTS speed remains a user-requested provider speed. Default remains 1.0.
- A user-requested provider speed above natural_max_speed is explicit user input; record it in the
  report rather than silently lowering it.
- Fresh/missing timing-mode settings default to Natural because this release intentionally changes the
  quality default. Legacy remains selectable.

Add matching GUI config items in videocaptioner/ui/common/config.py and CLI defaults in
videocaptioner/cli/config.py.

## 8. Phase P-1 — trustworthy baseline — COMPLETE

Goal: eliminate known unrelated gate noise before feature implementation.

### Work

1. Fix save_config_value in videocaptioner/cli/config.py:
   - create path.parent for the effective config_path;
   - do not call ensure_config_dir for an unrelated global directory when a custom path is supplied;
   - retain chmod protection on the actual file.
2. Add/adjust the existing roundtrip test to assert no global config directory is touched.
3. Fix the existing Pyright preset warning in cli/commands/synthesize.py using a narrow Literal type,
   validation, or cast consistent with surrounding code.
4. Run CLI tests, Ruff, and Pyright.

### Done criteria

- tests/test_cli passes inside the workspace sandbox;
- Ruff passes;
- Pyright reports 0 errors and 0 warnings for videocaptioner/cli;
- no behavior change outside the effective custom config path.

## 9. Phase P0 — correct dubbing text source — COMPLETE

Goal: eliminate target-language routing ambiguity before changing timing.

### Work

1. Add resolve_dubbing_text(segment, source_mode) in the dubbing domain:
   - TRANSLATED requires non-empty translated_text or returns a clear validation error;
   - ORIGINAL uses text;
   - AUTO prefers translated_text, then text.
2. Change DubbingEngine._create_tts_data to use the resolver and preserve both source and subtitle text
   in DubbingCue rather than immediately reducing to TTSDataSeg.
3. Add optional dubbing_subtitle_path to SubtitleTask for file-based compatibility.
4. In SubtitleThread, when need_next_task is true:
   - emit one dedicated target-only dubbing SRT;
   - use translation when available;
   - otherwise use original text;
   - store the path on the task.
5. In SubtitlePipelineThread, pass dubbing_subtitle_path to DubbingTask instead of the display-layout
   subtitle path.
6. Manual dubbing import must expose Auto/Translated/Original in the GUI.
7. Do not change the user's display subtitle layout or rendered subtitle path.
8. Make natural-mode dubbing validation errors fatal to the enabled dubbing stage; do not silently
   continue with the original video. Legacy/provider failure handling may remain configurable, but the
   final status must never say dubbed when the dubbed artifact was not created.

### Tests

- target-only SRT
- source-only SRT
- bilingual source-above
- bilingual target-above
- AUTO preference
- TRANSLATED missing-text error
- CJK keep/strip behavior
- full pipeline passes dedicated target-only artifact
- enabled dubbing failure cannot be reported as successful dubbing

### Done criteria

- when translated_text exists, zero generated TTS segments use original text;
- display subtitle output is byte-for-byte unaffected in targeted regression fixtures.

## 10. Phase P1 — deterministic grouping and timing planner — COMPLETE

Create videocaptioner/core/dubbing/planner.py.

### Grouping rules

Process cues in stable timeline order.

Merge adjacent cues into one group only when all conditions pass:

1. gap is non-negative and <= borrow_gap_ms;
2. speaker is equal, or both speakers are empty;
3. combined span is <= max_group_duration;
4. cues do not overlap;
5. the previous cue does not end a strong sentence followed by a gap larger than 120 ms.

Strong sentence ending includes ".", "!", "?", and target-language equivalents. Commas and incomplete
phrases do not force a boundary.

For each final group:

- start_time is the first cue start;
- subtitle_end_time is the last cue end;
- available_end_time is the next group start minus silence_guard_ms, or video duration for the last group;
- available_end_time cannot be earlier than subtitle_end_time;
- available_duration is available_end_time minus start_time;
- source_text and subtitle_text join cues with natural spaces without altering individual display cues.

### Prediction

Prediction is routing only; it must not be the final acceptance gate.

- normalize text using the provider's existing TTS normalization;
- count spoken units after normalization;
- add pause cost for punctuation;
- add cost for numbers, years, alphanumeric model names, acronyms, URLs, and symbols;
- use a conservative default rate profile for the target language;
- record predicted_duration and predicted fit ratio;
- real synthesized duration always overrides prediction.

Do not copy CapCap's fixed 4.0/4.5 words-per-second heuristic as truth.

### Tests

- stable IDs
- small-gap merge
- large-gap split
- speaker boundary
- overlap boundary
- strong-punctuation boundary
- group-duration boundary
- last-group video capacity
- silence guard
- prediction costs for numbers/acronyms/punctuation
- original cue text/timestamps unchanged

### Done criteria

- planner is deterministic and pure for the same input/config;
- no network, FFmpeg, filesystem write, or TTS dependency in planner unit tests.

## 11. Phase P2 — persistent TTS cache — COMPLETE

Create videocaptioner/core/dubbing/cache.py.

Cache root:

~~~text
CACHE_PATH/dubbing_tts/v1/
~~~

Key inputs:

- schema version
- normalized tts_text
- provider enum
- API base host only if it changes provider behavior; never store credentials
- model
- voice
- provider-native speed
- sample rate
- text normalization version

Use SHA-256. Cache filenames must not contain transcript text.

Store:

- WAV
- small metadata JSON with key, duration, provider/model/voice, sample rate, created timestamp
- no API key and no raw response

Behavior:

- validate cached WAV exists and has positive measurable duration;
- invalid entries become misses without deleting unrelated cache data;
- synthesize only misses;
- reuse a cached entry across segment indices and across runs;
- update report counters;
- temporary adjusted WAVs stay in the per-run work directory;
- do not add an automatic cache deletion policy in this release.

Tests:

- deterministic key
- credential exclusion
- hit/miss
- corrupt/missing WAV fallback
- same text with different voice/model/speed is a miss
- duplicate text within one job synthesizes once
- cache disabled bypasses reads and writes

## 12. Phase P3 — timing-aware rewrite service — COMPLETE

Create:

~~~text
videocaptioner/core/dubbing/rewrite_service.py
videocaptioner/core/prompts/dubbing/initial.md
videocaptioner/core/prompts/dubbing/rescue.md
tests/test_dubbing/test_dubbing_rewrite.py
~~~

Use the existing OpenAI-compatible call_llm path and context logging. Do not create a second client stack.

### Input contract

Each group request contains:

- group_id
- source language
- target language
- source text
- existing subtitle translation
- available duration
- measured duration when this is a rescue
- measured fit ratio
- target spoken-unit budget
- attempt number
- custom user style prompt if supplied

### Output contract

Strict JSON:

~~~json
{
  "group_id": "g-...",
  "tts_text": "...",
  "preserved_terms": ["..."]
}
~~~

Validate:

- exact group_id;
- non-empty string;
- no extra prose/markdown;
- all digits, percentages, currencies, units, and alphanumeric product tokens preserved;
- negation is not removed or inverted by obvious target-language markers;
- output is not identical after a rescue unless no safer shortening exists;
- no unsupported content is added according to deterministic token/entity checks where possible.

Names and semantic fidelity still require the prompt and later user listening; do not claim that a
deterministic validator proves perfect translation.

### Request policy

- use subtitle_text unchanged for predicted-fit groups;
- optionally pre-rewrite only predicted hard overruns above 1.15;
- after real TTS, rewrite only measured groups above fit_ratio_limit;
- maximum max_rewrite_attempts;
- batch outliers conservatively while preserving group IDs;
- keep contextvars through worker submission;
- cache rewrite results with source signature, subtitle text, timing budget, model, style, and prompt
  version;
- if no LLM is configured, skip semantic rewrite and continue to Natural fit/review policy.

Tests:

- valid response
- wrong/missing group_id
- malformed JSON
- missing number/unit/model token
- empty rewrite
- cache-key stability
- retry limit
- no-LLM fallback
- context propagation

## 13. Phase P4 — measured synthesize/rewrite loop — COMPLETE

Refactor DubbingEngine into explicit internal stages while preserving public dub() compatibility.

Suggested private stages:

- _load_dubbing_source
- _build_dubbing_plan
- _resolve_cache_hits
- _synthesize_missing_groups
- _measure_groups
- _rewrite_outliers
- _apply_fit_policy
- _build_voice_track
- _write_report
- _mix_output

### Loop

1. Plan groups.
2. Pre-rewrite predicted hard overruns only when enabled and configured.
3. Resolve persistent cache.
4. Synthesize misses at the configured provider-native speed.
5. Measure real WAV duration.
6. Compute fit_ratio = measured_duration / available_duration.
7. Accept <= fit_ratio_limit.
8. Rewrite measured outliers and synthesize only changed text.
9. Repeat until fit or max_rewrite_attempts.
10. Send unresolved groups to the selected fit policy.

Candidate acceptance:

- prefer a candidate inside 0.85 to fit_ratio_limit;
- otherwise accept only if it is closer to 1.0 than the prior candidate;
- reject candidates below 0.75 unless the original group is extremely short and content validation passes;
- retain the best valid candidate across attempts, not merely the last response.

TTS failure:

- record FAILED with the provider error summary;
- do not substitute silent audio and call the group successful;
- preserve other cache results;
- report the failed group;
- enabled Natural dubbing cannot be marked complete with failed groups.

Tests use a FakeTTS whose WAV duration is deterministic from normalized text. No live API is required.

## 14. Phase P5 — Natural and Legacy fit policies — COMPLETE

Refactor alignment without deleting current Legacy behavior.

### Natural mode

- never truncate;
- never slow short speech merely to fill the window;
- borrow already-planned silence;
- allow speed adjustment only up to natural_max_speed;
- measure duration again after speed adjustment;
- if the group remains above fit_ratio_limit:
  - REVIEW: mark NEEDS_REVIEW and stop final dubbing completion before mix;
  - ALLOW_OVERLAP: keep full uncut speech, record the overlap and warning.

No hidden fallback from Natural to Legacy.

### Legacy mode

- preserve current max_speed and truncation behavior;
- label truncation in report as action_taken="legacy_truncate";
- retain existing tests and add explicit mode tests.

### Voice track

- schedule groups at group start times;
- ensure duplicate group/split cues do not synthesize the same text twice;
- preserve total video duration;
- do not overlap groups in REVIEW-successful output;
- use current FFmpeg 8 compatibility and no-audio-stream fallback.

Tests:

- Natural never invokes truncation
- Natural speed ceiling
- Natural review outlier
- Natural allow-overlap keeps full duration
- Legacy truncation regression
- short audio retains silence
- group borrowing prevents unnecessary speed
- FFmpeg voice-track duration
- silent source video mix

## 15. Phase P6 — GUI and review report — COMPLETE

### Dubbing settings

Update DubbingInterface:

- Text source: Auto / Translation / Original
- Timing mode: Natural / Legacy
- Natural max speed, enabled only for Natural
- Legacy max speed, enabled only for Legacy
- Rewrite for natural timing toggle
- Cache toggle
- Unresolved policy: Review / Allow overlap
- Existing provider/model/voice/mix/volume/concurrency controls remain

Use current QFluentWidgets style and PyQt5. Do not introduce PySide6.

### Read-only review dialog

Create videocaptioner/ui/components/DubbingReportDialog.py.

Display:

- summary counters;
- group ID and timestamp;
- subtitle text;
- TTS text;
- available duration;
- measured duration;
- fit ratio;
- attempt count;
- action;
- status/warnings;
- report path, only when the user explicitly requested persistence.

This release's dialog is read-only. Per-cue inline editing and re-run UI are explicitly follow-up work.
The user can correct the subtitle/TTS source and run again. Keeping it read-only prevents a second,
unverified editor state model from entering this release.

Behavior:

- show report summary after success;
- show the same dialog when REVIEW blocks completion;
- do not display API keys or absolute private input paths;
- error messages distinguish translation routing, TTS provider failure, and timing review requirement.

### Translation resources

Add every new visible string to resource/translations and synchronize the package fallback with:

~~~powershell
.\.venv\Scripts\python.exe scripts\sync_translations.py
.\.venv\Scripts\python.exe scripts\sync_translations.py --check
~~~

Do not edit compiled QM files directly.

## 16. Phase P7 — CLI dub and process integration — COMPLETE

Create videocaptioner/cli/commands/dub.py.

Add parser:

~~~text
videocaptioner dub VIDEO --subtitle FILE [options]
~~~

Required options:

- video
- --subtitle

Core options:

- --output
- --tts-provider
- --tts-api-key
- --tts-api-base
- --tts-model
- --voice
- --tts-speed
- --tts-concurrency
- --text-source auto|translated|original
- --timing-mode natural|legacy
- --natural-max-speed
- --legacy-max-speed
- --fit-ratio-limit
- --borrow-gap-ms
- --max-rewrite-attempts
- --no-timing-rewrite
- --no-tts-cache
- --unresolved review|allow-overlap
- --mix-mode keep|reduce|mute
- --original-volume
- --voice-volume
- --report
- common quiet/verbose/config options

Never print API keys. Quiet mode prints only the successful output path. Review-required and provider
failures return a non-zero documented exit code and print the concrete cause to stderr. Print a report
path only when `--report` was explicitly supplied.

Add "process --dub" and the minimum shared dubbing options so CLI full pipeline can run:

~~~text
transcribe -> subtitle/translate -> dedicated target text -> dub -> synthesize
~~~

The process command must not reuse a display-layout bilingual SRT for dubbing.

Tests:

- parser help
- required args
- invalid enums/ranges
- config versus CLI priority
- command builds DubbingConfig correctly
- quiet output
- review-required exit
- process --dub target-text routing

Update CLI docs and README examples.

## 17. Phase P8 — full validation, packaging, and closeout — COMPLETE

### Targeted gates

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests\test_dubbing -q
.\.venv\Scripts\python.exe -m pytest tests\test_thread\test_subtitle_pipeline_thread.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_cli -q
.\.venv\Scripts\python.exe -m pytest tests\test_translate -q
.\.venv\Scripts\python.exe -m pytest tests\test_asr\test_asr_data.py -q
~~~

### Quality gates

~~~powershell
.\.venv\Scripts\ruff.exe check videocaptioner\
.\.venv\Scripts\pyright.exe videocaptioner\cli\
.\.venv\Scripts\python.exe scripts\sync_translations.py --check
~~~

### Full offline suite

~~~powershell
$env:LOCALAPPDATA = Join-Path (Get-Location) 'AppData\CodexTest'
.\.venv\Scripts\python.exe -m pytest tests\ -q
~~~

Report pass/fail/skip counts. Integration tests requiring live third-party services may skip only for
their documented missing credential/service reason. Do not convert deterministic failures into skips.

### Deterministic end-to-end fixture

Add a short generated media fixture or test helper that:

- creates a video with FFmpeg;
- uses bilingual subtitle input with known target text;
- uses FakeTTS WAVs with controlled durations;
- exercises cache miss then cache hit;
- exercises one rewrite success and one review outlier;
- proves Natural mode never truncates;
- proves the report schema and summary.

Run real FFmpeg. No network.

### Build

Preserve the prior default EXE by using a labelled name:

~~~powershell
$env:PYINSTALLER_CONFIG_DIR = Join-Path $env:TEMP 'VideoCaptioner-PyInstaller'
$env:VC_BUILD_NAME = 'VideoCaptioner-NaturalDubbing-20260821'
.\.venv\Scripts\pyinstaller.exe VideoCaptioner.spec --clean --noconfirm
Remove-Item Env:VC_BUILD_NAME
~~~

Expected artifact:

~~~text
dist/VideoCaptioner-NaturalDubbing-20260821.exe
~~~

Record:

- PyInstaller exit code;
- warning-file count and noteworthy missing modules;
- artifact bytes/MiB;
- timestamp;
- SHA-256;
- signature status if checked.

### Packaged smoke test

Launch the exact labelled EXE hidden for at least 15 seconds, verify the PyInstaller parent/child
processes remain alive, then stop only the process IDs created by the test and verify zero remain.

Also verify:

- app.log contains no startup exception;
- bundled dubbing prompts/resources are available;
- report dialog module imports in frozen mode;
- CLI help for dub works from source; the windowed EXE itself is GUI-only unless the existing packaging
  contract is deliberately changed.

Do not call GUI startup proof an end-to-end TTS/API acceptance.

### Documentation closeout

Update:

- README.md feature list, GUI behavior, CLI dub examples, and EXE notes;
- docs/MODULE_USAGE.md or a focused docs/dev/natural-dubbing.md;
- status.md with only measured facts and remaining user tests;
- this plan: mark every completed phase and record exact gate counts/artifact hash.

Final git status must show only intentional source/docs/test changes plus ignored build artifacts.
Do not commit.

## 18. Acceptance criteria

Machine acceptance result on 2026-08-21: all 18 mandatory criteria below are complete. Subjective
naturalness and real-provider acceptance remain explicitly postponed as originally scoped.

The mandatory release is machine-complete only when all are true:

1. Translation exists -> generated TTS uses target text, not original text.
2. Display subtitle text and TTS text are separate fields.
3. Group planner is deterministic and uses borrowable silence safely.
4. Natural mode never truncates speech.
5. Natural alignment never exceeds configured natural_max_speed unless the user explicitly requested
   a faster provider-native voice speed, which is reported.
6. Real WAV duration, not word count alone, determines fit.
7. Only measured outliers are rewritten/re-synthesized.
8. Numbers, units, percentages, currencies, and alphanumeric product tokens survive accepted rewrites.
9. Unresolved outliers become explicit review or explicit allow-overlap; there is no silent fallback.
10. TTS cache is deterministic, credential-free, and reusable across runs.
11. Provider failure cannot be mislabeled as successful dubbing.
12. CLI dub and process --dub use the same core engine as GUI.
13. Targeted and full offline test gates pass.
14. Ruff passes and CLI Pyright has zero error/warning.
15. Translation resource sync passes.
16. Labelled EXE builds and packaged startup smoke passes.
17. No new dependency was installed.
18. No commit/push was performed.

User-postponed acceptance, explicitly not required before machine completion:

- subjective Vietnamese naturalness;
- real OpenAI/MiniMax/local provider quality;
- long-form movie/podcast listening;
- provider rate-limit behavior;
- final UX preference for review thresholds.

## 19. Hard-stop and recovery policy

Do not pause merely because a phase is large or a test initially fails. Diagnose, patch, and rerun.

Hard stop only when:

- completing mandatory scope requires installing a package not already in uv.lock;
- a required source file is user-modified in a conflicting way that cannot be preserved;
- the filesystem blocks required writes after safe retries;
- a destructive action becomes necessary;
- a mandatory result depends on unavailable secrets with no fake/deterministic acceptance route;
- build rollback or output integrity is uncertain.

On hard stop:

- preserve all work;
- do not mark the active phase complete;
- report the exact command/error and the smallest required user decision.

## 20. Follow-up CapCap-inspired campaign

After this release and user listening test, open a separate plan in this order:

1. Piper/Edge TTS provider adapters and voice catalog.
2. Downloadable Resource Manager for FFmpeg/models/runtime packs.
3. Fast five-second media preview.
4. Sherpa-ONNX speaker diarization.
5. Per-speaker voice assignment.
6. Persistent project/resume state.
7. OCR subtitle extraction and selected-range re-transcription.
8. Timeline/waveform/thumbnails only if the product is intentionally becoming an editor.

Each item requires its own dependency/license/package-size acceptance. Do not silently absorb PySide6
or CapCap's monolithic UI architecture into this PyQt5 project.

## 21. Paste-ready prompt for the next session

Use the following as the next-session request:

~~~text
Work in F:\CppClone\VideoCaptioner.

Read AGENTS.md in full, then README.md, the newest status.md section, and
docs/plans/natural-dubbing-end-to-end-plan.md in full.

Implement the mandatory Natural Dubbing release P-1 through P8 from that plan from start to finish in
this single session. Do not stop for phase confirmations or manual user testing. The user will test
subjective audio quality after handoff. Continue through targeted tests, full offline tests, FFmpeg
integration, documentation, labelled PyInstaller EXE build, SHA-256, and packaged GUI smoke test.

Preserve unrelated work and the existing untracked AGENTS.md. Do not commit/push. Do not install new
packages or change configuration outside the workspace. If a test fails, diagnose/fix/rerun and continue.
Only stop for a real hard blocker defined by the plan. Report machine evidence separately from pending
live-provider and subjective user acceptance.
~~~
