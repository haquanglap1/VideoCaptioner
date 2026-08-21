# VieNeu-TTS One-App Integration and Model Auto-Update Plan

Current status: IMPLEMENTED AND MACHINE-VALIDATED on 2026-08-21. V0-V5 are included in the feature-branch
delivery. The read-only `F:\CppClone\VieNeu-TTS` checkout was used only as the pinned build source;
production source/package defaults have no dependency on that path.

## 1. Goal

Ship VideoCaptioner and VieNeu-TTS as one user-facing Windows application:

- one installer, one shortcut, and one VideoCaptioner UI;
- no server window, manual batch file, API Base, or fake API key required;
- VieNeu starts lazily in a hidden child process, stays warm for the app session, and stops with the app;
- the first successful model download supports later offline use;
- on every app launch, a background check can stage the latest compatible VieNeu model revision;
- a model revision is activated only after validation and never changes during an active dubbing job;
- the last known-good revision remains available for automatic rollback.

"One app" is a distribution and UX contract, not a single OS process. VieNeu remains an isolated child
process so a CUDA, ONNX, native-library, or out-of-memory failure cannot take down the Qt UI. The installed
layout may contain runtime/model files, but the user only operates `VideoCaptioner.exe`.

## 2. Evidence and constraints

- `DubbingEngine._create_tts_provider()` already maps `TTSProviderEnum.LOCAL_AI` to `OpenAITTS`.
- `OpenAITTS` already sends OpenAI-style `POST /audio/speech`; GUI dubbing requests WAV output.
- The current VieNeu bridge exposes `/audio/speech`, `/models`, `/voices`, and `/health` under ``, `/v1`,
  and `/api/v1`. It serializes non-batch inference and dynamically batches supported GPU requests.
- VieNeu v3 Turbo defaults to `pnnbao-ump/VieNeu-TTS-v3-Turbo`, uses the `update` model subfolder for
  PyTorch/GPU, reports 48 kHz, and uses separate MOSS tokenizer/codec repositories.
- The installed `huggingface_hub` exposes both `HfApi.model_info()` and `snapshot_download()` with an
  explicit revision. Current VieNeu loaders call `from_pretrained()`/`hf_hub_download()` without pinning a
  revision, so merely relying on the default Hugging Face cache is not an atomic update policy.
- VideoCaptioner is Python 3.10-3.12; the inspected VieNeu environment is Python 3.12.13 and imports
  `vieneu`, FastAPI, and Uvicorn successfully.
- The current bridge, launcher, and Vietnamese usage guide are untracked files in the VieNeu checkout.
  Production integration must not depend on an unversioned absolute checkout path.
- VideoCaptioner's current PyInstaller output is one-file. Bundling a large mutable model into that EXE
  would cause repeated extraction and make model-only updates impractical. The integrated distribution
  should be a versioned runtime directory wrapped by one installer.
- Long startup, download, health polling, and model validation work must run outside the Qt main thread.
- Existing generic Local AI behavior, CLI flags, persistent WAV cache, and unrelated dirty work must be
  preserved.

## 3. Product contract

Add a distinct managed provider named `VieNeu Local` while retaining `Local AI` for arbitrary external
OpenAI-compatible servers.

When `VieNeu Local` is selected:

- hide or make read-only API Base/API Key/Model fields;
- choose the managed loopback endpoint and a per-session credential internally;
- show runtime state: `Stopped`, `Starting`, `Ready`, `Busy`, `Updating`, or `Failed`;
- show backend, active model revision, update status, and download progress;
- provide `Check for model update`, `Start/Stop`, and `Open model folder` actions;
- enable `Automatically update model`, default on;
- keep voice selection and Natural/Legacy controls unchanged.

Automatic update policy:

1. Perform a lightweight remote revision check in the background on every app launch.
2. If offline, rate-limited, or Hugging Face is unavailable, silently keep the active model and expose a
   non-blocking status; dubbing must remain usable offline.
3. If the remote commit SHA differs, download a complete candidate snapshot in the background with resume.
4. Do not stop or replace a server that is serving an active job.
5. Validate and activate the candidate on the next clean server start (or immediately only while stopped).
6. Keep one previous known-good revision. Never delete additional user/model data as part of activation.
7. If validation fails, mark that SHA rejected, restart the previous revision, and do not retry the same
   rejected SHA on every launch. A manual retry remains available.

"Latest" means the latest revision that passes the installed runtime's compatibility and audio smoke
checks. VieNeu Python/runtime code is updated with a VideoCaptioner app update, not by treating model files
as executable code. If a new model requires newer runtime code, retain the working model and report that an
app/runtime update is required.

## 4. Installed layout and state

Target installed layout:

~~~text
VideoCaptioner/
  VideoCaptioner.exe
  runtime/vieneu/
    python.exe
    bridge/vieneu_bridge.py
    Lib/site-packages/...
  resource/...
  AppData/
    models/vieneu/
      state.json
      hf/                       # managed Hugging Face cache/snapshots
      candidates/
      rejected/
    logs/
      vieneu-YYYY-MM-DD.log
~~~

`state.json` uses an atomic, versioned `vieneu-model-state-v1` schema containing only stable IDs and
relative/cache references:

- model channel and repository ID;
- active, previous, candidate, and rejected commit SHA;
- active backend and model subfolder;
- bundled VieNeu runtime version;
- dependent tokenizer/codec revisions;
- last check, download, validation, and activation timestamps;
- last sanitized error summary.

Do not store credentials, transcript text, raw provider responses, or machine-specific source checkout
paths in the state file. A model snapshot is immutable by commit SHA; `active` changes only through an
atomic state-file replacement after acceptance.

## 5. Target architecture

### 5.1 Managed runtime domain

Create VideoCaptioner-owned, Qt-independent modules under `videocaptioner/core/tts/vieneu/`:

- `models.py`: runtime states, model manifest/state dataclasses, schema validation, and sanitized errors;
- `runtime_locator.py`: source, installed, and explicitly configured runtime discovery;
- `runtime_manager.py`: start, health wait, ownership, retry, and graceful/forced shutdown;
- `model_updater.py`: remote SHA check, resumable snapshot staging, validation decision, and rollback;
- `client_identity.py`: resolved endpoint, active revision, backend, runtime version, and cache identity.

The runtime manager must:

- start the runtime Python directly with an argument list, never `shell=True` or a batch file;
- bind only to `127.0.0.1` on an app-selected free loopback port;
- pass a random per-session bearer token without logging it;
- use `CREATE_NO_WINDOW` and drain/route stdout and stderr so pipes cannot deadlock;
- verify a service ID, protocol version, and session identity from `/health`, not just any HTTP 200;
- track the exact owned PID/process tree and never kill an unrelated process occupying a port;
- expose cancellation and bounded timeouts while allowing the first model load to take longer;
- retry one unexpected startup failure, then return a useful sanitized error;
- pin one model revision for the complete lifetime of a dubbing job.

### 5.2 Versioned bridge

Move the useful behavior from the untracked prototype into a versioned bridge shipped with the app. Add:

- CLI arguments for model snapshot path/revision, dependent tokenizer/codec paths, backend, port, batch
  size, wait window, and session token;
- `/health` fields for service/protocol version, runtime version, model repository/revision, backend,
  sample rate, and readiness;
- bearer-token validation on managed endpoints;
- graceful scheduler shutdown and request rejection while stopping;
- no raw TTS text in normal logs;
- a startup failure exit code and machine-readable final error line for the manager.

Keep the OpenAI-compatible endpoints so `OpenAITTS` remains the audio transport. Do not import VieNeu into
the Qt process.

### 5.3 Model update service

Use Hugging Face commit SHA as the model version:

1. `HfApi.model_info(repo_id).sha` discovers the candidate revision.
2. `snapshot_download(repo_id, revision=sha, cache_dir=managed_hf_dir)` stages immutable files and resumes
   interrupted downloads.
3. Download the whole VieNeu model snapshot because distribution size is not a constraint and this avoids
   fragile per-backend file allowlists.
4. Pin the MOSS tokenizer and ONNX codec revisions in the runtime manifest. Update those dependencies only
   with a compatible runtime/app release unless a future signed compatibility manifest explicitly links
   new revisions.
5. Launch the candidate from its local snapshot path. Runtime inference must not follow mutable `main`.
6. Require `/health`, a voice-list request, and a deterministic short WAV synthesis. Verify non-empty,
   decodable audio, expected sample rate, finite samples, and a reasonable duration.
7. Promote candidate to active atomically on success. On failure, record the sanitized reason and launch
   the previous revision.

The updater may download while the active server is busy, but activation is a clean-start operation. It
must support pause/cancel on app exit and leave partial Hugging Face downloads resumable.

### 5.4 Dubbing/cache integration

- Add `vieneu-local` as a provider/config value without removing `local-ai`.
- Resolve the managed endpoint before constructing `OpenAITTS`.
- Use `sk-local` only for legacy external bridges; managed mode uses the ephemeral session token.
- Set managed audio/sample-rate metadata to the bridge's `/health` value (currently 48 kHz).
- Include model commit SHA, runtime/protocol version, backend, model/voice/speed, and sample rate in the
  persistent TTS cache identity. A model update must create a new cache namespace without deleting the old
  WAV cache.
- If the sidecar crashes during a group, fail that group with the existing provider-failure path. Never
  report the original video as successfully dubbed.
- Do not switch revisions during cache lookup, synthesis, rewrite/resynthesis, or mix for one job.

### 5.5 GUI and CLI

Create `videocaptioner/ui/thread/vieneu_runtime_thread.py` for start/update/validation work. UI code only
orchestrates signals and presentation; it never performs network, download, subprocess, or model work.

GUI integration points:

- selecting `VieNeu Local` presents the managed controls and current state;
- `Tải danh sách` lazily ensures the runtime is ready before fetching voices;
- manual dubbing and full pipeline use the same readiness gate;
- closing the app cancels pending update work and terminates only the owned sidecar;
- update errors are non-blocking when a known-good offline model exists, but startup/provider failures are
  sticky and actionable.

CLI integration:

- accept `--tts-provider vieneu-local`;
- auto-start and stop the managed runtime for that CLI process;
- default to the active model without forcing a network check for every headless command;
- provide explicit `vieneu model status`, `vieneu model update`, and `vieneu model rollback` commands, or
  equivalent subcommands finalized in Phase V0;
- preserve existing `local-ai` behavior for user-managed endpoints.

## 6. Delivery phases

### V0 - Contract, fixtures, and dependency/license audit — COMPLETE

- Freeze `vieneu-runtime-protocol-v1` and `vieneu-model-state-v1`.
- Freeze managed provider/config names and CLI semantics.
- Add fake bridge/model-repository fixtures, a tiny deterministic WAV fixture, and interrupted-download
  state fixtures.
- Inventory runtime/model licenses and required notices. Record model repository terms separately from
  the Apache-2.0 VieNeu code license and GPL-3.0 VideoCaptioner license.
- Decide the exact runtime build source and dependency lock; do not package the mutable developer `.venv`.

### V1 - Versioned bridge and source-mode runtime manager — COMPLETE

- Check in the bridge under VideoCaptioner ownership and add protocol/auth/health metadata.
- Implement locator, process ownership, hidden startup, log draining, readiness polling, and shutdown.
- In source mode, allow an explicit developer runtime path; never hardcode
  `F:\CppClone\VieNeu-TTS` in source or packaged defaults.
- Test port collision, wrong service on port, slow startup, crash, retry, cancellation, and no-orphan exit.

### V2 - Managed provider and UI/CLI integration — COMPLETE

- Add `VieNeu Local` provider while preserving generic `Local AI`.
- Add managed status/update controls and lazy readiness to voice loading and every dubbing entry point.
- Populate API endpoint/token/sample rate internally and include sidecar identity in errors/reports.
- Add CLI managed-provider lifecycle and offline active-model behavior.

### V3 - Model staging, activation, and rollback — COMPLETE

- Implement remote SHA checks, resumable snapshot download, atomic state, candidate validation, rejection,
  activation, and rollback.
- Add app-launch background checks and manual update/status/rollback actions.
- Pin dependent tokenizer/codec revisions and make all active inference use local immutable paths.
- Version persistent TTS cache identity by model/runtime/backend revision.
- Test update while idle, download while busy, activation after job, offline launch, corrupt/incomplete
  candidate, incompatible model, failed smoke, and successful rollback.

### V4 - Bundled runtime and one-app distribution — COMPLETE

- Build a clean VieNeu runtime from the approved lock into `runtime/vieneu/`; do not install globally.
- Update the single supported `VideoCaptioner.spec` and distribution script as needed without creating
  duplicate spec files.
- Produce one installer/portable package with one shortcut. The installed directory may contain multiple
  files; no console/server shortcut is exposed.
- Keep mutable model snapshots under `AppData/models/vieneu`, not inside the immutable EXE payload.
- Optionally seed the current known-good model in the installer; if not seeded, make first-run download
  size, progress, resume, and offline limitation explicit.

### V5 - Runtime and packaged acceptance — COMPLETE (machine gates)

- Run unit/integration gates with fake bridge/Hugging Face endpoints first.
- Run a real VieNeu GPU acceptance on the target RTX machine: cold start, warm start, voices, WAV request,
  concurrency/dynamic batching, Natural Dubbing, and audible Vietnamese review.
- Run model-update acceptance between two controlled revisions, including cache namespace change and
  forced candidate failure/rollback.
- Build the labelled package, inspect bundled runtime/native libraries, smoke exact installed EXE, verify
  the hidden sidecar and model paths, close the app, and confirm zero owned processes remain.
- Run one real video/FFmpeg workflow from the packaged app. Startup and unit tests alone do not prove TTS,
  CUDA, audio quality, or model-update behavior.

## 7. Acceptance criteria

1. A fresh user installs/opens one VideoCaptioner app and can use VieNeu without launching a batch file,
   server window, terminal, or editing API settings.
2. VieNeu starts only when needed, reports readiness without blocking Qt, remains warm during the session,
   and closes with the owning GUI/CLI process.
3. The manager never kills or adopts an unrelated process and never binds beyond loopback by default.
4. The same managed path works for manual dubbing, full pipeline, batch flow, and CLI.
5. The first completed model download can synthesize while fully offline on a later launch.
6. Each online app launch checks for a newer model commit without blocking normal app startup.
7. A different remote SHA downloads resumably in the background and cannot replace an active job's model.
8. Candidate health, voices, and WAV smoke must pass before atomic activation.
9. A corrupt or incompatible latest model automatically falls back to the last known-good revision and
   exposes a sanitized, actionable status.
10. Model revision changes invalidate only the relevant TTS cache namespace; old cached WAVs and model
    snapshots are not silently deleted.
11. Health/report/cache identity records the exact runtime, backend, model commit, voice, speed, and sample
    rate used for a job.
12. Server logs contain no API token or transcript text, and app configuration contains no hardcoded local
    developer path.
13. Concurrent GPU requests use the bridge's safe batching/serialization path; no model object is shared
    unsafely across Qt worker threads.
14. Offline tests, real GPU/TTS acceptance, packaged startup, packaged real-video workflow, and process
    cleanup are reported as separate gates.
15. Ruff, targeted Pyright, translation sync, relevant unit/integration tests, final package build, artifact
    fingerprint, and packaged smoke all pass before delivery is called complete.

## 8. Explicitly deferred

- A physically single giant one-file EXE. The supported result is one installer/shortcut/application with
  an internal runtime directory.
- Hot-swapping model weights inside an active process or dubbing job.
- Automatically executing arbitrary latest VieNeu Python code from a model repository.
- Automatic deletion of old snapshots, user voice clones, or TTS cache. Cleanup needs a separate,
  size-aware and recoverable retention feature.
- LAN/public serving. Managed mode is loopback-only; generic `Local AI` remains available for external
  servers.

## 9. Delivery record (2026-08-21)

- V0: froze the protocol/state/provider/CLI contracts; added fake bridge/update fixtures and license
  notices. Runtime source is pinned to VieNeu commit
  `36c4b501b0634a8f59805e6b529a058fbd30190b`; the GPU dependency lock SHA-256 is
  `079E23501EF943E355F411F18094992D1E9A25E7FEFD7022F37DA5DFAEF171AE`.
- V1: shipped the bridge and Qt-independent manager with loopback/authenticated health identity, hidden
  process ownership, bounded startup, retry, cancellation, pipe draining and owned-tree cleanup. Fake
  acceptance covers collision, wrong service, slow start, crash/retry and orphan cleanup.
- V2: added `VieNeu Local` without changing `Local AI`; GUI/full/manual/batch/editor and CLI all resolve
  one managed service. QThread work owns network/subprocess operations, while reports/cache metadata carry
  sanitized runtime identity.
- V3: implemented SHA discovery, resumable snapshot staging, atomic activation, rejected revision records,
  previous revision rollback and offline reuse. Real controlled update ran
  `d0c7ea3951eaaca27bdcf53ff9fa9eaf8ed5893a -> 2da0efab622a1722125991736524f080b751ef5b`;
  revision `760c29661f7ae65c6a6e55abd9691d05613f82ec` was deliberately rejected and the known-good revision
  restarted with zero owned process left.
- V4: built a clean uv-managed Python 3.12 runtime, installed only the hash-pinned lock, built VieNeu from
  the pinned source archive and removed only the unused 2+ GiB static development library `dnnl.lib`.
  The portable package seeds the active model/tokenizer/codec under managed AppData. The supported
  installer output is one MSI entry point plus external CAB payloads and one Start Menu shortcut; a giant
  physically single self-extracting EXE remains explicitly deferred.
- V5: real RTX/CUDA acceptance passed cold/warm start, 20 voices, WAV 48 kHz, concurrency/dynamic batch,
  Natural Dubbing and owned-process cleanup. The exact packaged EXE produced a 6.000-second H.264/AAC
  video whose audio is mono 48 kHz and left no EXE/sidecar process. Automated audio structure/content
  gates passed; final subjective listening remains a human release sign-off, not a machine claim.
