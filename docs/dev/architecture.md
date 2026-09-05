# Kiến trúc VideoCaptioner

Tài liệu này mô tả hệ thống như đang có trong mã nguồn: một core Python dùng chung cho CLI và GUI,
pipeline phụ đề, tab Video Editor, và runtime VieNeu Local được quản lý. Chi tiết từng domain nằm ở
[Natural Dubbing](natural-dubbing.md), [Video Editor](video-editor.md) và
[VieNeu One-App](vieneu-one-app.md); trạng thái công việc hiện tại nằm trong `status.md` ở gốc repo.

## Tổng quan

```
                ┌──────────── CLI (videocaptioner/cli) ────────────┐
   video/audio  │ transcribe · subtitle · synthesize · dub · process │
      ─────────►│ download · config · vieneu · style                │
                └───────────────┬───────────────────────────────────┘
                                │ gọi trực tiếp
                ┌───────────────▼───────────────────────────────────┐
                │ core: asr → split/optimize → translate → subtitle │
                │       → dubbing (TTS + mix) → synthesis (FFmpeg)  │
                │ core/editor · core/tts/vieneu · core/llm · utils  │
                └───────────────▲───────────────────────────────────┘
                                │ qua QThread trong ui/thread
                ┌───────────────┴───────────────────────────────────┐
                │ GUI PyQt5 + QFluentWidgets (videocaptioner/ui)    │
                │ view · components · task_factory · signal_bus     │
                └───────────────────────────────────────────────────┘
```

Nguyên tắc: `core/` không import Qt; UI chỉ điều phối và trình bày. Việc dài (ASR, LLM, FFmpeg, TTS,
sidecar) chạy trong worker của `ui/thread/` và báo về bằng signal; không cập nhật widget từ worker.

## Cấu trúc thư mục

```text
videocaptioner/config.py          Đường dẫn runtime cho 3 chế độ: source, pip-installed, PyInstaller
videocaptioner/core/entities.py   Entity dùng chung: TranscribeConfig, SubtitleConfig, *Task, enum, enum_from_display
videocaptioner/cli/               argparse, commands/, config.py (lớp cấu hình), output, exit codes
videocaptioner/core/asr/          Engine ASR, ASRData, chunked_asr
videocaptioner/core/split/        Tách câu (rule + LLM)
videocaptioner/core/optimize/     Tối ưu phụ đề bằng LLM
videocaptioner/core/translate/    BaseTranslator, factory, LLM/Google/Bing/DeepLX
videocaptioner/core/subtitle/     Style, ASS/rounded renderer, editing (bảng phụ đề), style_presenter (tab kiểu phụ đề)
videocaptioner/core/dubbing/      engine, orchestrator, planner, cache, rewrite, audio_mixer, presets
videocaptioner/core/tts/          BaseTTS, OpenAI/MiniMax, vieneu/ (runtime + model quản lý)
videocaptioner/core/editor/       Domain Video Editor: models, commands, project_store, media, voice, presenter
videocaptioner/core/llm/          Client OpenAI-compatible, credentials, context, request logger, services
videocaptioner/core/prompts/      Prompt .md (được bundle vào EXE)
videocaptioner/core/utils/        FFmpeg/video_utils, subprocess_helper, installer, cache, logger
videocaptioner/ui/                main.py, view/, components/, thread/, task_factory.py, common/
resource/                         Assets, fonts, translations, subtitle styles (bản bundle)
videocaptioner/resources/         Fallback fonts/translations cho package pip
scripts/                          Launcher, sync_translations, VieNeu one-app builder, PyInstaller entry
installer/                        WiX source cho MSI
tests/                            Test theo domain; marker integration/slow/llm cho test cần dịch vụ ngoài
```

## Đường dẫn và chế độ chạy

`videocaptioner/config.py` quyết định `ROOT_PATH`, `RESOURCE_PATH`, `APPDATA_PATH`, `WORK_PATH` theo
ba chế độ: frozen (PyInstaller, `sys._MEIPASS`), dev (có `resource/` cạnh package) và pip
(`platformdirs`). Nó cũng prepend các thư mục bin quản lý (FFmpeg, Faster-Whisper, Deno) vào `PATH`
khi tồn tại. `core/utils/installer.py` tải FFmpeg/Deno vào `AppData/bin/` trên Windows khi thiếu.

## Cấu hình

- GUI: `ui/common/config.py` là `QConfig` (qfluentwidgets) lưu `AppData/settings.json`; mọi giá trị
  đọc qua `cfg.<item>.value` và ghi qua `cfg.set(...)`.
- CLI: `cli/config.py` gộp theo thứ tự `tham số CLI > env (OPENAI_*, VIDEOCAPTIONER_*) > config.toml
  (user_config_dir) > settings.json của GUI > mặc định`. Lớp GUI chỉ mirror credential/endpoint
  (`load_gui_settings()`), không mirror công tắc hành vi.
- `ui/task_factory.py` dịch `cfg` thành `SubtitleTask`, `TranscribeTask`, `DubbingTask`,
  `FullProcessTask`; CLI dựng cùng các entity đó từ dict cấu hình.
- `core/llm/services.py` giữ `LLM_SERVICE_PRESETS` (prefix trong `settings.json`, attribute trên `cfg`,
  base URL/model gợi ý, key mặc định cho Ollama/LM Studio) cho từng dịch vụ LLM; `SettingInterface` dựng
  card theo bảng này và CLI suy `GUI_LLM_SERVICE_PREFIX` từ cùng bảng nên provider chỉ khai báo một chỗ.
  `core/entities.enum_from_display` đổi nhãn hiển thị về enum cho cả GUI và CLI.

## Pipeline phụ đề

1. **ASR** (`core/asr`): `transcribe(audio, TranscribeConfig)` chọn engine (Bijian, JianYing, Whisper
   API, whisper.cpp, Faster-Whisper). `chunked_asr` cắt audio dài và ghép lại có overlap. Kết quả là
   `ASRData` (danh sách `ASRDataSeg` với millisecond).
2. **Split/Optimize** (`core/split`, `core/optimize`): phụ đề word-level được gộp câu theo rule và LLM;
   optimizer sửa lỗi ASR theo batch qua `call_llm`.
3. **Translate** (`core/translate`): `TranslatorFactory` tạo translator; `BaseTranslator` chia chunk,
   chạy `ThreadPoolExecutor` qua `submit_with_context` (giữ contextvars), cache kết quả bằng diskcache.
   `LLMTranslator` dựng "global context" một lần cho cả phim và đưa fingerprint tất định của nguồn vào
   cache key (không đưa output LLM ngẫu nhiên).
4. **Subtitle** (`core/subtitle`): `ASRData` xuất SRT/ASS/TXT/JSON theo `SubtitleLayoutEnum`; style ASS
   từ `style_manager`; `ass_renderer` và `rounded_renderer` burn phụ đề bằng FFmpeg. `editing.py` chứa
   thao tác trên dict phụ đề (`ASRData.to_json()`) mà tab phụ đề dùng: gộp/xóa/chọn hàng, tìm-thay,
   xuất lại output của pipeline. `style_presenter.py` là phần không-Qt của tab kiểu phụ đề (font PIL
   nạp được, danh sách/đường dẫn style, màu RGBA, ảnh xem trước theo `StyleMode`); view chỉ ánh xạ
   widget ↔ `SubtitleStyle`.
5. **Synthesis** (`core/utils/video_utils.py`): ghép phụ đề mềm (mov_text) hoặc cứng (filter
   `subtitles=`/`ass=`), probe CUDA, đọc tiến độ từ stderr của FFmpeg.

GUI nối các bước qua `SubtitlePipelineThread`; CLI `process` chạy tuần tự các command.

## LLM

`core/llm/client.py` giữ một client OpenAI-compatible dùng chung. Credential là `LLMCredentials`
(dataclass, key ẩn khỏi repr) đăng ký qua `configure_llm_client()`; `get_llm_client()` nhận credential
tường minh hoặc dùng bộ đã đăng ký, chỉ đọc `OPENAI_*` từ môi trường như fallback và không bao giờ ghi
vào `os.environ`. `call_llm()` memoize theo diskcache; `request_logger` ghi request/response theo
`ContextVar` để các thread song song không lẫn log. `core/llm/context.py` giữ `task_id`/stage cho log.

## Dubbing

`DubbingEngine` (`core/dubbing/engine.py`) là API; `DubbingOrchestrator` chạy job: đọc phụ đề, planner
nhóm cue và tính sức chứa, tra `PersistentTTSCache`, tổng hợp phần thiếu bằng provider TTS, đo WAV
thật, rewrite câu vượt khung qua `TimingRewriteService` (LLM), áp chính sách fit, ghép voice track và
mix với audio gốc (`audio_mixer.py`, tự chọn cú pháp filter tương thích FFmpeg cũ/mới). Report JSON ghi
từng group. `presets.py` là nguồn duy nhất cho bảng provider, mix mode, text source dùng chung GUI/CLI.
Provider TTS: OpenAI, MiniMax, Local AI (OpenAI-compatible tự quản), VieNeu Local (được quản lý).

## VieNeu Local

`core/tts/vieneu/`: `runtime_locator` tìm runtime Python + bridge trong bản one-app; `runtime_manager`
sở hữu sidecar (loopback port, bearer token theo session, môi trường đã lọc credential, đóng đúng
process tree); `model_updater` tải/validate/activate model theo commit SHA với state atomic;
`service.py` là facade cho GUI/CLI. Không import VieNeu/CUDA/FastAPI vào process Qt. Base build không có
`runtime/vieneu/` phải disable action thay vì báo lỗi lặp.

Ở chế độ source, locator chỉ tìm `<ROOT>/runtime/vieneu/`; để chạy với runtime đã build bằng
`scripts/build_vieneu_runtime.py`, đặt `VIDEOCAPTIONER_VIENEU_RUNTIME` (và `VIDEOCAPTIONER_VIENEU_BRIDGE`
nếu bridge nằm chỗ khác). `HuggingFaceVieNeuClient` ép `HF_HUB_DISABLE_SYMLINKS` trên Windows và dùng
lớp tqdm riêng (không monitor thread, có sink ghi khi EXE windowed không có stderr). Trong GUI, mọi
action VieNeu của tab Lồng tiếng đi qua một hàng đợi (mới nhất thắng); lúc khởi động app chỉ kiểm tra
revision rồi đề nghị tải, xem [VieNeu One-App](vieneu-one-app.md).

## Video Editor

`core/editor/` độc lập Qt: `models.py` (schema `editor-project-v1`, millisecond canonical, cue ID ổn
định), `commands.py` (`CommandStack` cho mọi mutation, undo/redo), `project_store.py` (save JSON + SRT;
ASS chỉ qua "Save as ASS"), `media.py` (probe/thumbnail/waveform/render bằng FFmpeg, hủy được),
`adapters.py` và `voice.py` (nối với dubbing/TTS), `presenter.py` (đặt cue mới, vị trí tách, lệnh
inspector, thuộc tính/tên layer, đường dẫn gợi ý). `ui/view/video_editor_interface.py` là page
PyQt5/QFluentWidgets; preview và export dùng chung `build_visual_filter_graph`. Không thêm PySide6/MPV.

## Subprocess và môi trường

Mọi `subprocess.run/Popen` trong `videocaptioner/` truyền `env=child_environment()`
(`core/utils/subprocess_helper.py`): bản sao `os.environ` bỏ `OPENAI_*`/`VIDEOCAPTIONER_*` nhưng giữ
PATH đã prepend. Trên Windows dùng `CREATE_NO_WINDOW`. Argument luôn là list, không `shell=True`.

## Đóng gói và kiểm thử

- PyInstaller `onedir` với duy nhất `VideoCaptioner.spec`; entry `scripts/pyinstaller_gui.py`; resource
  và prompt phải nằm trong spec. `scripts/build_vieneu_one_app.py` ghép runtime + model seed vào onedir.
- Gate: `ruff check videocaptioner/`, `pyright videocaptioner/` (0 lỗi), `pytest tests/test_cli`,
  `sync_translations.py --check`; CI (`.github/workflows/ci.yml`) chạy thêm bộ offline
  `-m "not integration and not slow and not llm"` trên Ubuntu có FFmpeg và Qt offscreen.
- Test cần dịch vụ ngoài mang marker `integration`/`llm`; test cần FFmpeg tự skip khi thiếu.
- Test điều khiển QThread qua `QEventLoop` phải `thread.wait()` sau khi loop thoát (xem helper trong
  `tests/test_thread/conftest.py`); thả QThread còn chạy khiến Qt abort interpreter trên CI.
- `scripts/pyinstaller_gui.py` thay `sys.stdout`/`sys.stderr` None của EXE windowed bằng devnull trước
  khi import GUI, vì thư viện ghi thẳng ra stderr (tqdm) từng làm app treo khi thoát.
- `scripts/build_vieneu_runtime.py` cài dependency bằng `uv pip install --no-config --require-hashes`
  để `[tool.uv] override-dependencies` của workspace không lọt vào runtime.

---

Tài liệu liên quan:
- [API](/dev/api)
- [Đóng góp](/dev/contributing)
- [Natural Dubbing](/dev/natural-dubbing)
- [Video Editor](/dev/video-editor)
- [VieNeu One-App](/dev/vieneu-one-app)
