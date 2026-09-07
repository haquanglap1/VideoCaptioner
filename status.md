# Project Status

## 2026-09-07 (ASR S2: JSON → alignment tiếng Trung, dừng để review)

- Baseline đúng `origin/codex/asr-s1-api-profiles`, commit
  `43bb76f45d8dc12cd107fbcbd92c7e21ab811cc3`. Làm trong worktree/nhánh
  `codex/asr-s2-alignment`; giữ nguyên master và ba tài liệu untracked của checkout nguồn.
- `AlignedAPI` nối JSON S1 qua runtime Qwen riêng vào ASRData/SRT cho CLI/GUI; preflight
  Chinese + runtime/model/CUDA trước upload. Chunk lossless <=240 s, cắt ở silence, không overlap,
  không bỏ tail. Model limit 300 s; không dùng chunk ASR 10 phút.
- Contract ms strict giữ nguyên text/dấu câu, kiểm tra coverage/bounds/overlap/silence; tắt
  nội suy `fix_timestamp` của upstream Qwen. Thiếu/trùng chữ, zero-length, lệch timing hoặc
  không có ranh cắt an toàn dừng review cả job, không tạo SRT một phần/timestamp giả.
- Runtime Windows Python 3.12 CUDA riêng, lock có hash (Qwen 0.0.6, Torch 2.8.0+cu128), model pin
  `c7cbfc2048c462b0d63a45797104fc9db3ad62b7`; tải chỉ qua builder tường minh. Job/probe offline,
  process ẩn, lọc credential env, timeout/cancel/đóng cả Windows venv process tree. Qt không import
  Torch/Qwen; worker probe giữ contextvars và `wait()`. S2 HTTP async hủy socket được, giữ retry S1.
- Cache nhận dạng và alignment tách riêng; key hash theo audio/text/config/model/revision/policy.
  Preset, key theo endpoint, model/base/prompt/language và engine mặc định S1 được giữ.
- Alignment thật: clip Qwen Trung công khai 4.204 s → 13 span 400–3680 ms và SRT; warm ~0.10 s,
  peak Torch allocation ~1.76 GiB. Câu lệch audio và silence bị chặn; bản phồn thể cũng bị strict
  validator chặn, **chưa đạt acceptance phồn thể**. Không suy chất lượng cả corpus từ clip này.
- Gateway thật/GPT→SRT chưa nghiệm thu: worktree không có settings ASR hay env ASR key, không lấy
  credential/media từ checkout khác. Không triển khai S3–S6, không commit/push/tag/GitHub.
- Gate cuối: ruff/sync translations/diff-check pass; pyright 0 errors/0 warnings; full offline
  **768 passed, 5 skipped, 51 deselected** (83.74 s). EXE review PyInstaller exit 0, 6 warnings
  optional/platform (chi tiết trong bàn giao); EXE 30,985,630 byte, SHA-256 `133d04bb…55d5cb6`.
  Cửa sổ chính từ artifact sống qua 25 s, đóng sạch. Bytecode/recipe S2 đã đối chiếu source;
  workflow media/API từ EXE chưa nghiệm thu, base artifact không chứa GPU runtime/model.
- Chi tiết contract, cài runtime, giới hạn và số đo: [ASR alignment S2](docs/dev/asr-alignment-s2.md).
  Gate cuối và danh sách file: [bàn giao S2](docs/dev/asr-implementation-2026-09.md#bàn-giao-s2--2026-09-07).

## 2026-09-07 (ASR S1: request profile, preset gateway/Groq và gate offline)

- Hoàn tất S1 offline: registry provider/model/profile nhẹ; request/parser chung WhisperAPI/probe;
  Whisper/Groq giữ timing, GPT JSON probe được và subtitle preflight báo cần alignment S2 trước upload.
- Cache v2 SHA-256 cách ly endpoint/request/timing, prompt được hash; MIME theo bytes, cap upload,
  timeout/retry hữu hạn, lỗi/log không echo key/prompt/raw provider response. Không giả timestamp.
- Settings hai mặt có preset VideoCaptioner API/Groq/OpenAI/Custom và model nhập tay; giữ cấu hình
  preset, key theo endpoint và ngôn ngữ user. CLI thêm provider/profile theo precedence cũ; đổi endpoint
  không tự thừa kế key. Probe chạy worker chung giữ contextvars; không network khi mở settings.
- Validation: ruff toàn source/tests pass; pyright 0 error/0 warning; CLI và tests gần thay đổi pass;
  full offline **720 passed, 5 skipped, 51 deselected** (76,48 s); sync translations pass. Đã sửa
  startup guard bị kéo theo SDK OpenAI trong lượt test đầu. Dùng Python 3.12.13/môi trường project có
  sẵn, xác nhận import worktree; FFmpeg có sẵn, Qt offscreen, settings/cache/basetemp test cô lập.
- Online/EXE chưa nghiệm thu; không có key ASR trong worktree/env, không đọc/copy key checkout nguồn.
  Docs OpenAI/Groq đã đọc lại; trang docs gateway không tải được bằng web tool ở lượt này, giữ hợp đồng
  đã chấp nhận trong nghiên cứu. Không cài dependency, không build/phát hành, không triển khai S2–S6.
- Chi tiết hành vi, giới hạn, từng gate, manifest file và đầu vào S2:
  [bàn giao S1](docs/dev/asr-implementation-2026-09.md#bàn-giao-s1--2026-09-07).

## 2026-09-05 (Nghiệm thu VieNeu qua GUI one-app, sửa treo EXE, cập nhật model theo đề nghị, tài liệu, CI Node 24)

### Lỗi phát hiện từ log one-app trước khi nghiệm thu (mục 1)
- Log `dist/VideoCaptioner-VieNeu-OneApp-20260905/AppData/logs/app-2026-09-05.log` của hai lần user chạy (10:51 và
  11:12): `VieNeu auto-update failed: 'NoneType' object has no attribute 'write'` ngay khi mở tab Lồng tiếng, và hai
  process one-app còn sống không cửa sổ (PID 27060/28060, working set 3.8/6.7 MB). py-spy: main thread kẹt ở
  `tqdm._monitor.TMonitor.exit` → `join()`, thread monitor của tqdm kẹt chờ lock. Nguyên nhân: EXE windowed khởi động
  với `sys.stderr = None`; `tqdm.refresh()` (tqdm 4.67.1) giữ lock rồi `display()` ném AttributeError, lock không được
  nhả, atexit của tqdm join monitor vô hạn → mọi update model fail và app treo khi thoát. Sửa `5fc914a`:
  `ProgressTqdm` không tạo monitor thread và dùng sink ghi khi thiếu stderr; `scripts/pyinstaller_gui.py` thay
  stdout/stderr None bằng devnull cho cả đường GUI; test `test_hub_client_progress_bar_works_without_stderr` dò lock
  của đúng lớp bar (`tqdm.auto` và `tqdm.std` có lock riêng nên dò `tqdm.std` là vô nghĩa).
- Cùng log: `Dubbing thất bại: cannot schedule new futures after interpreter shutdown` lúc 11:56 khi user đóng app
  giữa job. Sửa `4111c6b`: `DubbingThread._progress_callback` ném `DubbingCancelled` khi thread bị
  `requestInterruption()` (callback chạy cả trong worker TTS nên job unwind mà core không cần cancel token);
  `MainWindow.closeEvent` yêu cầu dừng sớm, tắt sidecar/child process như cũ rồi `wait_for_dubbing_job(10 s)`; job bị
  hủy không hiện popup/report. Test mới `tests/test_thread/test_dubbing_thread.py`.
- Hai process treo được dừng thủ công sau khi lấy stack.

### Auto-update VieNeu: chỉ kiểm tra rồi đề nghị (mục 3, `6055687`)
- Trước: mở tab Lồng tiếng là tải ~1.7 GB và validate GPU âm thầm, tiến độ ghi vào widget đang ẩn, action của user
  xếp hàng sau. Nay `Auto update` bật → khởi động chỉ `check`; có bản mới → InfoBar "Có bản cập nhật mô hình VieNeu"
  với nút "Tải và kích hoạt"; nút "Kiểm tra cập nhật mô hình" cũng check rồi đề nghị; tắt `Auto update` → không kết
  nối mạng lúc khởi động. Khi tải: progress bar + status label của tab hiện "Downloading VieNeu model: Downloading
  bytes 799/1678 MB" (`describe_download_progress` gom ba bar của huggingface_hub: số file, bytes tải, bytes ghi; giữ
  phần trăm đơn điệu), rồi "Validating VieNeu candidate on the GPU..."; kết quả tách bạch: đã kích hoạt / đã tải nhưng
  hoãn vì có job giữ lease / đã mới nhất / offline. Action `auto-update` của thread bị bỏ; label trạng thái thêm
  "có bản <sha12>". Test GUI với hub giả: launch check không tải gì, bấm nút mới tải + kích hoạt qua fake bridge
  (+2 test trong `test_ui_thread.py`), test `describe_download_progress`; 11 chuỗi dịch vi_VN mới.

### Nghiệm thu VieNeu qua chính GUI one-app (mục 1)
- One-app build lại từ `6055687` (dời `AppData`/`work-dir` của bản cũ ra ngoài rồi trả lại, vì PyInstaller
  `--noconfirm` xóa cả `dist/<name>`), rồi điều khiển bằng UI Automation: pywinauto backend uia qua
  `uv run --frozen --with pywinauto` (không đổi dependency), nút tìm theo text tiếng Việt, `invoke()` cho InfoBar nằm
  ngoài màn hình (tab cao hơn 1440 px ở 125 %), `set_edit_text` cho LineEdit đường dẫn.
- Kết quả (104.7 s tổng): mở tab → 1.1 s sau có InfoBar đề nghị `8b7e9cff` (HF main đã qua `19dd1cc`); Start → Ready
  sau 32 s (cold), tự nạp 20 giọng, combo giữ "Ngọc Huyền"; lồng tiếng thủ công clip 14.32 s (3 câu, `allow-overlap`)
  xong sau 8.7 s → `smoke_dubbed.mp4` h264 + aac 12.99 s, report 3 group (2 fit, 1 speed_adjust 1.15x + allow_overlap);
  bấm "Tải và kích hoạt": tải 1678 MB trong ~20 s, validate GPU (Stopping → Starting → Ready `8b7e9cff`) ~11 s, InfoBar
  "Đã cập nhật mô hình VieNeu / Bản 8b7e9cffb4b4 đang hoạt động."; `state.json` active `8b7e9cff…14a6`, previous
  `2da0efab…ef5b`, `rejected_revisions` rỗng (không cần rollback); "Tải danh sách" lại 20 giọng từ model mới; lồng
  tiếng lần 2 OK (8.8 s); Stop → Stopped, python runtime tắt; đóng cửa sổ exit 0, 0 process sót.
- Log app sau đó chỉ còn 2 traceback cosmetic lúc teardown (`wrapped C/C++ object of type BottomInfoBarManager has
  been deleted` từ event filter của qfluentwidgets). Sửa `8b47447`: `closeEvent` gỡ các InfoBarManager khỏi event
  filter của cửa sổ; smoke lại trên bản build cuối (mở tab, kiểm tra cập nhật → InfoBar "Mô hình VieNeu đã mới nhất",
  đóng): exit 0, log không traceback.
- Chưa làm: installer WiX, nghe thủ công chất lượng giọng, workflow LLM thật và TTS OpenAI/MiniMax thật.

### Tài liệu (mục 2, `1e0a98c`)
- `docs/dev/architecture.md` + `docs/en/dev/architecture.md`: style_presenter, core/llm/services, core/editor/presenter,
  `entities.enum_from_display`, env `VIDEOCAPTIONER_VIENEU_RUNTIME`, guard stderr trong entry EXE, quy tắc
  `thread.wait()`, builder `--no-config`; `docs/dev/vieneu-one-app.md`: hàng đợi action, luồng check → đề nghị, flag
  builder, guard symlink, ví dụ `--source` không còn đường dẫn tuyệt đối; `docs/dev/view-structure.md` viết lại theo
  view hiện tại; AGENTS.md/CLAUDE.md thêm quy tắc `thread.wait()` cho test QThread qua QEventLoop và gate
  `ruff check videocaptioner/ tests/`.

### CI (mục 5, `e6b81ad`)
- actions/checkout v7, setup-python v7, astral-sh/setup-uv v10.0.1 (ghim tag đầy đủ: từ v8 setup-uv không còn tag
  major floating nên `@v10` làm CI fail ở Set up job; `enable-cache: true` vẫn tường minh nên đổi mặc định của v10 không
  ảnh hưởng), setup-node v7 (+ cache npm theo `docs/package-lock.json`), upload-artifact v7,
  download-artifact v8, upload-pages-artifact v5, deploy-pages v5; các input đang dùng không đổi ở các major này.
  Job quality thêm `ruff check tests/` (sửa 1 lỗi I001 ở `tests/test_editor/test_architecture_contract.py`). Chưa
  push nên CI chưa chạy với các workflow mới.

### Comment CJK đợt 3 (mục 4, `66d29f0`)
- 429 mục trong `ui/view/setting_interface.py` (101), `ui/components/FasterWhisperSettingWidget.py` (101),
  `core/split/split.py` (85), `core/entities.py` (76), `ui/components/WhisperCppSettingWidget.py` (66); thay đúng token
  (file, dòng), giữ CRLF. Còn **838 mục / 55 file**; nhiều nhất: `ui/view/batch_process_interface.py` 49,
  `ui/view/transcription_interface.py` 46, `ui/view/subtitle_style_interface.py` 44, `ui/thread/batch_process_thread.py`
  43, `ui/view/llm_logs_interface.py` 35. Bốn view ~1000 dòng vẫn chủ yếu là layout, không tách thêm.

### Build lại từ HEAD `8b47447` (mục 6)
- Base (`python -m PyInstaller VideoCaptioner.spec --clean --noconfirm` bằng `.venv`): exit 0, 0 error, 6 warning quen
  thuộc (js/emscripten, curl_cffi, yt_dlp_ejs, AppKit, tzdata, sip). `dist/VideoCaptioner/VideoCaptioner.exe`
  30,946,521 byte, 2026-09-05 13:23, SHA-256 `953f5f9f195ce826a3e52f098f19bbe66f859e9cfddfa26ceb5bdd5da22cf77a`;
  524 file / 234.5 MB, đủ prompts/resources/assets/fonts/translations/subtitle_style. Smoke: cửa sổ sau 5.8 s, đóng
  exit 0, không process sót, log chỉ có dòng version check.
- One-app (`scripts/build_vieneu_one_app.py --overwrite`, giữ AppData): exit 0, 6 warning như trên. EXE 30,946,521
  byte, SHA-256 `A8EFD5F85763D977563900F189609C5AD26E6070406AA3F3C50F534F7B6F2FDC`, runtime 29,256 file / 5.91 GB,
  seed 42 file / 1.77 GB (`2da0efab` từ repo AppData); AppData thật của bản one-app (settings, tool 4.9 GB, cache,
  model state active `8b7e9cff`) đã trả lại. Smoke `dubtab`: exit 0, không process sót, log không traceback.
- Nghiệm thu GUI ở mục 1 chạy trên bản build từ `6055687`; các commit sau chỉ đổi comment, docs, CI và
  `_detach_info_bar_managers`, đã smoke lại trên bản cuối.

### Gate
- ruff `videocaptioner/ tests/` pass; pyright `videocaptioner/` 0 errors / 0 warnings sau mỗi commit code;
  `sync_translations --check` in sync; test theo commit: test_vieneu + test_thread + test_ui (54 passed),
  test_cli + test_ui + test_split (190 passed); full suite offline (`-m "not integration and not slow and not llm"`,
  basetemp ngắn): **645 passed, 4 skipped (TTS cần API key), 51 deselected** trong 1:19, 1 warning.
- Phát hiện thêm khi so mtime: `tests/test_editor/test_startup_responsiveness.py` chạy GUI trong process con nên
  fixture cô lập `cfg.file` của root conftest không áp dụng; child ghi lại `AppData/settings.json` thật (hôm nay nội
  dung y nguyên, hash không đổi, nhưng `cfg.transcribe_model.value = BIJIAN` trong script có thể lọt vào file thật).
  Sửa: helper `_run_script` chèn preamble trỏ `cfg.file` sang thư mục tạm; chạy lại file test, mtime không đổi.
- Sự cố phiên: một script debug chạy ngoài pytest lúc 12:57 dựng `DubbingInterface` với `cfg` thật và đổi provider
  combo, nên có thể đã ghi `Dubbing/TTSProvider = vieneu-local` vào `AppData/settings.json` của repo (khóa khác không
  đổi; không có backup để so). Nếu trước đó dùng OpenAI thì đổi lại trong tab Lồng tiếng.
- 9 commit local `5fc914a..HEAD`, chưa push theo yêu cầu.

## 2026-09-04 (Sau roadmap: build EXE nghiệm thu, tách view đợt 2, dịch comment, pyright sạch, layout test)

### Build EXE onedir, smoke và workflow thật (mục 1)
- `uv run --frozen pyinstaller VideoCaptioner.spec --clean --noconfirm` tại HEAD `176ca84` (trước các thay đổi
  mục 2–5): exit code 0, 0 error, 6 warning không đáng chú ý (`urllib3.contrib.emscripten` thiếu module `js`,
  `curl_cffi`/`yt_dlp_ejs` không phải package nên bỏ qua data, `darkdetect` import AppKit chỉ có trên macOS).
- Artifact `dist/VideoCaptioner/VideoCaptioner.exe`: 30,934,673 byte, 2026-09-04 22:53, SHA-256
  `f4a00cc16f6830a2363d75a77ed9d386d9df13a0178df3f3606aa376135c86c6`; thư mục onedir 225 MB / 524 file, đã có
  `videocaptioner/core/prompts`, `videocaptioner/resources`, `resource/{assets,fonts,translations,subtitle_style}`.
- Smoke: khởi động EXE từ `dist/VideoCaptioner`, sau 20 s process vẫn sống (working set 139 MB), cửa sổ chính
  "Trợ lý phụ đề Kaka -- VideoCaptioner" hiện, EXE tự tạo `AppData/` riêng dưới `dist/` (cache DB + log ngày),
  dừng đúng PID do test tạo. Không đụng `AppData/settings.json` của repo (hash không đổi).
- Theo yêu cầu, tải công cụ bằng chính cơ chế của app để test dễ hơn: FFmpeg (BtbN qua
  `installer.ensure_ffmpeg()` → `AppData/bin/ffmpeg`), Faster-Whisper-XXL r245.2 bản GPU (ModelScope, giải nén
  bằng 7-Zip vào `AppData/bin/Faster-Whisper-XXL`), model `faster-whisper-large-v3` (3.09 GB, ModelScope vào
  `AppData/models`). Máy có RTX 5070 12 GB, driver 616.56. `config.py` tự prepend các thư mục này vào PATH của
  process nên test pydub/`silent_video` nay chạy thật; shell ngoài vẫn không có `ffmpeg` trên PATH.
- Workflow thật chạy từ source (EXE chỉ có GUI): clip 14 s giọng SAPI ghép FFmpeg → `video2audio` → `transcribe()`
  FasterWhisper large-v3 trên CUDA: 28 segment word-level đúng nội dung trong 49.6 s (gồm nạp model), 5 sự kiện
  progress; CLI `synthesize` hard (CRF 32) và soft: exit 0, output h264+aac 14.32 s, bản soft có stream
  `mov_text`. Các subprocess ffmpeg/ffprobe/faster-whisper-xxl đều chạy qua `env=child_environment()`.
- Chưa nghiệm thu: LLM thật (không có API key hay local server), dubbing/TTS thật, auto-update, và workflow
  chạy trực tiếp qua EXE. EXE này build từ `176ca84` nên chưa chứa các thay đổi mục 2–5.

### Tách logic khỏi view đợt 2: style, settings, editor (mục 2)
- `core/subtitle/style_presenter.py` (không import Qt): `PREVIEW_TEXTS`/`PREVIEW_ORIENTATIONS`,
  `preview_text_pair`, `default_background`/`preview_background`, `parse_rgba_hex`/`format_rgba_hex`,
  `font_choices` + `pil_can_load_font`, `style_file_path`/`resolve_style_path`/`list_style_ids`/`choose_style_id`/
  `save_style`, `rounded_bg_style`, `render_style_preview` (chọn renderer theo `StyleMode`), `first_image_path`.
  `SubtitleStyleInterface` (1281 → 967 dòng) chỉ còn snapshot widget ↔ `SubtitleStyle` (`_ass_style`,
  `_rounded_style`, `_apply_style`); hai QThread preview gộp thành `StylePreviewThread`; `generateAssStyles`
  thay bằng `SubtitleStyle.to_ass_string()` (cùng chuỗi ASS, bold=-1); load/save rounded đi qua
  `SubtitleStyle.from_file`/`to_json_dict` thay vì dict thủ công.
- `core/llm/services.py`: `LLM_SERVICE_PRESETS` (prefix trong settings.json, attr trên `cfg`, base mặc định, model
  gợi ý, base có sửa được hay không, key mặc định cho Ollama/LM Studio, placeholder), `settings_prefix_for`,
  `fill_default_api_key`, `missing_whisper_api_fields`; `core/entities.enum_from_display` thay
  `_enum_from_display`. `SettingInterface` (1120 → 1006) dựng card theo bảng; CLI `GUI_LLM_SERVICE_PREFIX` suy
  ra từ cùng bảng nên không còn hai bản map provider.
- `core/editor/presenter.py`: `new_cue_span`/`new_cue` (`CuePlacementError.reason` = `inside_cue`/`no_space`),
  `split_position`, `inspector_commands`, `track_state_command`/`track_locked`, `layer_range`,
  `unique_layer_name`, `layer_properties`, `new_layer`, `layer_index`, `layer_pending_changes`,
  `layer_list_label`, đường dẫn gợi ý và `preview_output_path`. `VideoEditorInterface` (1117 → 1043) giữ dialog
  trong `_ask_layer_value`; `CommandStack` và các command hiện có không đổi.
- Test mới: `tests/test_subtitle/test_style_presenter.py` (26), `tests/test_ui/test_subtitle_style_interface.py`
  (5, offscreen, `SUBTITLE_STYLE_PATH` trỏ tmp, preview stub, cfg.file đã cô lập), `tests/test_llm/test_services.py`
  (6, gồm đối chiếu với CLI), `tests/test_ui/test_setting_interface.py` (5), `tests/test_editor/test_presenter.py`
  (15).
- Validation: ruff `videocaptioner/` pass; pyright 0 errors; test_ui/test_subtitle/test_llm/test_cli/test_editor/
  test_thread/test_dubbing/test_translate/test_utils offline: **393 passed, 26 deselected**.

### Dịch comment/docstring tiếng Trung đợt 2 (mục 3)
- 163 mục trong 6 file: `core/asr/faster_whisper.py` (34), `core/subtitle/rounded_renderer.py` (43),
  `core/subtitle/ass_renderer.py` (36), `ui/thread/video_download_thread.py` (33),
  `ui/thread/file_download_thread.py` (13), `core/asr/whisper_cpp.py` (4). Chỉ token COMMENT và docstring
  theo `tokenize`, thay đúng (file, dòng); chuỗi `tr()` và message log giữ nguyên. ruff pass, import được.
- Còn lại theo cùng thống kê: **1267 mục / 60 file**. Nhiều nhất: `ui/view/setting_interface.py` 101,
  `ui/components/FasterWhisperSettingWidget.py` 101, `core/split/split.py` 85, `core/entities.py` 76,
  `ui/components/WhisperCppSettingWidget.py` 66, `ui/view/batch_process_interface.py` 49,
  `ui/view/transcription_interface.py` 46, `ui/view/subtitle_style_interface.py` 44,
  `ui/thread/batch_process_thread.py` 43, `ui/view/llm_logs_interface.py` 35, `core/asr/chunk_merger.py` 34,
  `core/optimize/optimize.py` 33, `core/asr/chunked_asr.py` 32; 47 file còn lại mỗi file ≤ 31.

### Dọn 9 warning pyright còn lại (mục 4)
- `ui/thread/video_download_thread.py`: typeshed gõ `YoutubeDL(params)` bằng TypedDict riêng `_Params` (không có
  trong package yt-dlp 2026.7.4) còn dict option được dựng động, nên `cast(Any, ...)` ở hai điểm gọi kèm comment.
- `ui/thread/subtitle_pipeline_thread.py`: `file_path`/`output_path` của `FullProcessTask` là Optional; thu hẹp
  trước khi dựng đường dẫn video lồng tiếng, thiếu thì báo qua `handle_error` (TaskFactory luôn đặt hai giá trị).
- `ui/view/batch_process_interface.py`: `_current_task_type()` thu hẹp `currentData()` (chỉ None trước init) về
  `FULL_PROCESS` mặc định, dùng ở 5 chỗ đọc task type.
- Validation: pyright `videocaptioner/` **0 errors, 0 warnings**; ruff pass.

### Test layout editor ổn định dưới offscreen trên Windows (mục 5)
- Nguyên nhân: offscreen Qt trên máy Windows dùng font Helvetica 12pt (native là MS Shell Dlg 2 7pt) nên hàng bốn
  nút Blur/Logo/Mask/Text trong `QHBoxLayout` đẩy `minimumSizeHint` của tab Layers lên 356 px; `QSplitter` tôn
  trọng min đó nên preview chỉ còn 306 px. Sửa: hàng nút dùng `FlowLayout` của qfluentwidgets (min bằng một nút,
  tự xuống dòng khi hẹp hoặc font lớn); test giữ nguyên ngưỡng 320/290/300. Đo lại offscreen: preview 372,
  tabs 294.
- Validation: `test_ui_sync_performance.py` offscreen 6 passed 1 skipped (QtMultimedia); native
  `test_ui_sync_performance` + `test_visual_layers` 26 passed. Full suite offline cuối cùng
  (`-m "not integration and not slow and not llm"`, basetemp ngắn) với FFmpeg/Whisper thật: **636 passed,
  4 skipped (TTS cần API key), 51 deselected** trong 1:15; hash `AppData/settings.json` không đổi.

### VieNeu Local: dựng runtime, kích hoạt model và one-app (2026-09-05)
- Yêu cầu: máy chưa có model lồng tiếng VieNeu. Clone `pnnbao97/VieNeu-TTS` vào `D:\AI-Work\VieNeu-TTS` đúng commit
  pin `36c4b501`, build runtime bằng `scripts/build_vieneu_runtime.py` → `build/vieneu-runtime-20260904` (5.6 GB,
  Python 3.12 + torch 2.8.0+cu128, smoke `ok 2.8.0+cu128 True`).
- Lỗi 1: `uv pip install --require-hashes` trong builder (uv 0.11.6) kéo `[tool.uv] override-dependencies`
  PyQt5-Qt5 của workspace vào và fail vì thiếu hash. Builder nay truyền `--no-config` cho cả hai lần `uv pip install`.
- Lỗi 2: huggingface_hub 1.28 dò symlink theo thư mục cache một cách lười và không khóa; với nhiều thread tải,
  thread thứ hai qua mặt probe và `os.symlink` ném WinError 1314 trên máy không có quyền symlink (Developer
  Mode tắt). `HuggingFaceVieNeuClient.snapshot_download` nay ép `HF_HUB_DISABLE_SYMLINKS` (env + `constants`)
  trên win32 để cache luôn là file thường; 2 test mới trong `tests/test_vieneu/test_model_updater.py`.
- Model: tokenizer/codec MOSS `6aa02b01` và `pnnbao-ump/VieNeu-TTS-v3-Turbo` revision pin `2da0efab` (HF main đã
  là `19dd1cc`) tải vào `AppData/models/vieneu/hf` (1.7 GB); `videocaptioner vieneu update --revision 2da0efab…`
  với `VIDEOCAPTIONER_VIENEU_RUNTIME` trỏ runtime vừa build: sidecar khởi động trên RTX 5070, health/voices/WAV
  pass, active revision `2da0efab`, sidecar tắt sạch (0 process sót).
- Lồng tiếng thật từ source: `dub smoke.mp4 --subtitle smoke_vi.srt --tts-provider vieneu-local --voice "Minh Đức"
  --timing-mode natural --mix-mode mute`: 3 nhóm TTS thành công (0 failed). Lần 1 dừng đúng policy `review`
  (exit 6: câu 1 audio 4.75 s / khung 3.22 s, tỷ lệ 1.48); lần 2 `--unresolved allow-overlap` ra
  `smoke_dubbed.mp4` h264 + AAC 48 kHz 14.32 s, report `output_created: true`.
- One-app: `scripts/build_vieneu_one_app.py --name VideoCaptioner-VieNeu-OneApp-20260905` từ HEAD `ed2c3a4` + hai
  fix trên: EXE 30,941,586 byte SHA-256 `3822ED7E…B600FC`, runtime 29,256 file / 5.91 GB, model seed 42 file /
  1.77 GB (tổng 7.7 GB), `distribution-manifest.json` ghi đủ revision. Locator/store của app đọc được runtime và
  ba snapshot trong gói. Smoke EXE one-app 30 s: cửa sổ chính hiện, không spawn process con, không lỗi log.
- Chưa nghiệm thu: bấm Start/Update/lồng tiếng từ chính GUI one-app, auto-update nền lên `19dd1cc` (chưa chạy
  vì smoke chỉ 30 s), installer WiX, nghe thủ công chất lượng giọng.

### VieNeu GUI: không tải được danh sách giọng (2026-09-05)
- Báo cáo từ bản one-app: bấm "Tải danh sách" với VieNeu Local không ra giọng. Log one-app cho thấy sidecar đã
  khởi động và báo `voices=20`, nên lỗi nằm ở tầng GUI. Nguyên nhân: `main_window` chạy action `auto-update`
  (mặc định) bằng một `VieNeuRuntimeThread` riêng không nằm trong `_vieneu_threads` của tab Lồng tiếng, còn
  `_start_vieneu_action` bỏ qua im lặng mọi action khi đã có thread đang chạy; `_fetch_voices` lại đổi nút thành
  "Đang tải..." và disable trước khi gọi, nên nút kẹt vĩnh viễn khi bấm trong lúc check/update hoặc ngay sau Start.
  Hai luồng dùng chung một sidecar còn có thể chạy song song (launch update + Start của user).
- Sửa `dubbing_interface.py`: action đến khi bận được xếp vào `_vieneu_pending_action` (mới nhất thắng) và chạy
  khi thread hiện tại `finished`; status label báo "VieNeu: busy, {action} queued"; sau `start` thành công tự
  gọi `_fetch_voices` để combo có ngay giọng VieNeu (không còn để "alloy" của OpenAI); kết quả `voices` cũng
  refresh nút Start/Stop; `_on_vieneu_error` ghi `logger.warning` để log app có dấu vết; `shutdown_vieneu_threads()`
  dùng chung cho `closeEvent` và lúc thoát app. `main_window.py` gọi launch action qua cùng hàng đợi của tab và
  chờ bằng `shutdown_vieneu_threads(11_000)` khi đóng.
- Test: `tests/test_vieneu/test_ui_thread.py` +2 (fake bridge): bấm tải giọng khi Start đang chạy → được xếp hàng,
  nút bật lại, combo nhận `fake-voice`; Start một mình cũng điền danh sách. Tái hiện với runtime thật qua
  offscreen: `check` → Start → tải giọng liên tiếp: 20 giọng trong 8.1 s, chọn "Minh Đức", trạng thái Ready.
- Validation: ruff pass, pyright 0/0, `tests/test_vieneu` + `test_startup_responsiveness` + `test_dubbing`
  **106 passed**; `test_ui` + `test_ui_thread` 23 passed. One-app build lại cùng tên với `--overwrite`.
- CI của `2d1f2c2`: job offline abort (exit 134, `Fatal Python error: Aborted`) tại
  `test_subtitle_thread.py::TestSubtitleThreadError::test_missing_file`, không liên quan thay đổi: helper
  `run_thread_with_timeout` thoát event loop ngay khi nhận signal `error` rồi thả `SubtitleThread` còn đang chạy,
  Qt `qFatal` "Destroyed while thread is still running" tùy thời điểm (local 6/6 pass, CI dính). Helper nay
  `thread.wait()` sau event loop.

## 2026-09-04 (Nhóm trung hạn: hợp nhất config GUI/CLI, credentials không qua os.environ)

### Nguyên nhân và thay đổi
- CLI và GUI giữ hai bộ cấu hình riêng (`config.toml` trong `user_config_dir` và `AppData/settings.json`)
  nên LLM key phải nhập hai lần. `build_config()` thêm lớp `load_gui_settings()` nằm dưới `config.toml`:
  chỉ mirror credentials/endpoint (key/base/model của dịch vụ LLM đang chọn trong GUI, Whisper API, DeepLX
  endpoint, TTS lồng tiếng; `local_ai` chuẩn hóa thành `local-ai`), bỏ qua giá trị rỗng, không đổi tên key.
  Thứ tự ưu tiên vẫn CLI > env > file > GUI > default; `config path` in thêm file GUI đang làm fallback.
  Test CLI nay cô lập `CONFIG_FILE`, `settings.json` và biến `OPENAI_*`/`VIDEOCAPTIONER_*` của máy dev.
- 10 điểm ghi `OPENAI_API_KEY`/`OPENAI_BASE_URL` (và `DEEPLX_ENDPOINT`) vào `os.environ` làm key rò sang
  mọi child process. `get_llm_client()` nay nhận `LLMCredentials` (dataclass frozen, key ẩn khỏi repr,
  base URL chuẩn hóa) hoặc dùng bộ đã đăng ký qua `configure_llm_client()`; env `OPENAI_*` chỉ còn là
  fallback đọc. CLI subtitle, dubbing orchestrator, `SubtitleThread`/`RetranslateThread` đăng ký object;
  CLI transcribe bỏ hẳn vì Whisper API đã nhận key qua `TranscribeConfig`; DeepLX endpoint đi qua
  `TranslatorFactory.create_translator(deeplx_endpoint=...)`.
- Thêm `child_environment()` trong `subprocess_helper`: copy `os.environ` bỏ prefix `OPENAI_`/
  `VIDEOCAPTIONER_` (không phân biệt hoa thường), giữ PATH đã prepend ffmpeg/whisper/deno. Áp cho 44 call
  site `subprocess.run/Popen` trong `videocaptioner/` (ffmpeg/ffprobe, faster-whisper, whisper.cpp, yt-dlp,
  editor render, 7z/tar, updater, explorer/open), default của `run_process_with_stream_reader` và
  `_environment()` của sidecar VieNeu (token session đặt sau khi lọc).

### Validation
- Test CLI **70 passed** (10 test GUI fallback, regression key không vào env). Mới: `test_llm/test_client.py`
  (8), `test_utils/test_subprocess_helper.py` (5, gồm child process Python thật qua `env=` và qua
  `run_process_with_stream_reader`), test VieNeu `_environment`. Bộ offline test_llm/test_utils/test_cli/
  test_translate/test_subtitle/test_dubbing/test_thread/test_editor/test_ui: **227 passed, 12 skipped,
  9 errors**; 9 error là fixture `silent_video` của `test_natural_dubbing_integration` gọi ffmpeg không có
  trên PATH máy này. Ruff `videocaptioner/`: pass. Pyright `cli/` + 10 module đã sửa: **0 errors**.
- Chưa nghiệm thu: ffmpeg/whisper/yt-dlp thật với `env=child_environment()` (máy không có FFmpeg), sidecar
  VieNeu thật, và gọi LLM thật qua `LLMCredentials`.

### Test cho core/utils (mục 3)
- `tests/test_utils/` trước chỉ có 5 test layout PyInstaller. Thêm `conftest.py` với fixture `ffmpeg`
  (skip khi `shutil.which` không thấy hoặc binary không chạy được `-version`, ví dụ file ngoại lai trên
  PATH gây WinError 216) và `silent_video` sinh clip 1 giây bằng lavfi.
- `test_video_utils.py`: `plan_video_chunks`, `temporary_subtitle_file`, parser banner `ffmpeg -i` (video
  + nhiều audio stream có tag ngôn ngữ, audio-only, không stream, lỗi subprocess), `video2audio`,
  `check_cuda_available`, `add_subtitles` soft/hard (progress từ `time=` giả, lỗi return code) qua module
  `subprocess` giả ghi lại lệnh và kiểm `env=` đã lọc key; 4 test chạy FFmpeg thật (skip ở máy này).
- `test_installer.py`: tra cứu managed dir > PATH, `_prepend_to_path` idempotent, `_validate_archive`,
  giải nén ffmpeg zip chỉ lấy file trong `bin/`, `ensure_ffmpeg`/`ensure_deno` với `_download` giả và
  không network. Fixture khôi phục PATH vì `ensure_*` prepend thư mục tmp, nếu không `ffmpeg.exe` giả rò
  sang test sau.
- `test_platform_utils.py` mở rộng: predicate hệ điều hành, `get_subprocess_kwargs`, lọc FasterWhisper
  trên macOS, `open_folder/open_file/reveal_in_explorer` với Popen giả (đúng launcher, env đã lọc,
  `os.startfile` ưu tiên trên Windows). `test_subprocess_helper.py` thêm `StreamReader` và
  `run_process_with_stream_reader` với child Python thật (hai stream, override `env`).
- Validation: `tests/test_utils` **71 passed, 4 skipped** (4 skip là nhóm FFmpeg thật). Ruff pass.

### Pyright toàn package và gate CI (mục 4)
- Khảo sát bằng `pyright --outputjson` trên 170 file: chỉ còn **10 lỗi** ngoài `cli/` (8 ở
  `ui/view/dubbing_interface.py` do `Qt.Horizontal`/`Qt.AlignCenter` không có trong stub PyQt5, 2
  `reportReturnType` ở `core/translate/base.py` và `llm_translator.py`) cùng 21 warning.
- Sửa: dùng enum có scope `Qt.Orientation.Horizontal`/`Qt.AlignmentFlag.AlignCenter` (bằng nhau ở
  runtime PyQt5 5.15, không cần `type: ignore`); `_safe_translate_chunk` cast kết quả cache về
  `Optional[List[SubtitleProcessData]]`, `_agent_loop` cast dict đã validate; `_parallel_translate` raise
  rõ khi executor đã shutdown thay vì đưa `None` vào `submit_with_context`. Dọn 12 warning biến không dùng
  và `title` có thể `None` trong `video_download_thread`; 9 warning còn lại là stub yt-dlp `_Params`,
  `output_path`/`task_type` Optional trong pipeline/batch UI, để lại vì cần đổi logic.
- Gate CI `.github/workflows/ci.yml` đổi từ `pyright videocaptioner/cli/` sang `pyright videocaptioner/`;
  AGENTS.md, CLAUDE.md và README cập nhật lệnh gate.
- Validation: pyright `videocaptioner/` **0 errors, 9 warnings**. Ruff pass. Test translate/subtitle/
  thread/ui/dubbing engine: pass; 20 fail trong `tests/test_asr/test_chunk*` là pydub gọi ffmpeg không có
  trên máy (đã ghi từ đợt trước), không liên quan thay đổi này.

### Tách logic khỏi view lớn: subtitle_interface và dubbing_interface (mục 5, đợt 1)
- `core/subtitle/editing.py` (không import Qt) nhận toàn bộ thao tác trên dict phụ đề dạng
  `ASRData.to_json()`: `merge_rows`, `delete_rows`, `select_rows`, `replace_text`, `playback_range`,
  `find_supported_subtitle`, `export_subtitle`, `pipeline_reexport_targets`/`reexport_pipeline_outputs`,
  `task_folder`, `write_editor_handoff`. `SubtitleInterface` giữ nguyên `SubtitleTableModel`, chỉ gọi vào
  các hàm này; thêm `_selected_rows()` dùng chung cho menu chuột phải và phím tắt.
- Hành vi đổi có chủ đích: gộp hàng khi chọn cách quãng (Ctrl+click) nay gộp cả các hàng nằm giữa; code cũ
  âm thầm xóa những hàng không được chọn trong khoảng đó.
- `core/dubbing/presets.py` gom bảng provider (thứ tự combo, voice gợi ý, API base/model mặc định), key
  mix mode/text source/timing/unresolved, sample rate, `provider_from_key` (nhận cả `local_ai`/`local-ai`),
  `mix_mode_from_key`, `fill_provider_defaults` (chỉ điền ô trống), `merged_output_path`.
  `DubbingInterface` và CLI `dub.py` dùng chung, bỏ hai bản map trùng.
- Test: `tests/test_subtitle/test_editing.py` (20), `tests/test_dubbing/test_presets.py` (6),
  `tests/test_ui/test_subtitle_interface.py` (4, view offscreen: load, merge, delete, click hàng phát
  trước cue end 50 ms). Dubbing view kiểm offscreen: đổi provider điền preset, giữ voice đã gõ, ẩn/hiện
  khối VieNeu, `_save_settings` lưu đúng key.
- Fixture autouse mới ở root conftest trỏ `cfg.file` sang tmp: trước đó dựng `DubbingInterface` trong test
  (`test_vieneu/test_ui_thread.py`) và smoke thủ công ghi thẳng vào `AppData/settings.json` của máy dev;
  trong phiên này smoke đã ghi đè TTSApiBase/TTSModel/Voice và được trả về mặc định (`alloy`,
  `https://api.openai.com/v1`, `tts-1`), TTSProvider hiện là `vieneu-local` do test cũ đặt.
- Còn lại của mục 5: `subtitle_style_interface.py` (1281 dòng), `setting_interface.py` (1120),
  `video_editor_interface.py` (1117) chưa tách; `subtitle_interface.py` còn ~1000 dòng chủ yếu là dựng
  layout.
- Validation: ruff pass; pyright `videocaptioner/` 0 errors; test_ui + test_vieneu UI thread + test_cli +
  editing + presets: **pass**, hash `settings.json` không đổi sau khi chạy.

### Comment/docstring tiếng Trung sang English trong file đã chạm (mục 6, đợt 1)
- 198 comment và docstring CJK trong 10 file đã sửa logic ở đợt này được dịch sang English:
  `core/utils/subprocess_helper.py`, `platform_utils.py`, `video_utils.py`, `ui/thread/subtitle_thread.py`,
  `core/translate/base.py`, `llm_translator.py`, `deeplx_translator.py`, `factory.py`,
  `core/llm/client.py`, `ui/view/subtitle_interface.py`. Chuỗi `self.tr(...)` và message log giữ nguyên
  vì là key bản dịch/UI. Cách làm: tokenize để liệt kê đúng COMMENT/docstring có CJK, thay theo
  (file, dòng, nội dung) nên không đụng string literal.
- Còn lại theo thống kê `tokenize`: ~160 mục trong `faster_whisper.py`, `rounded_renderer.py`,
  `ass_renderer.py`, `video_download_thread.py`, `file_download_thread.py`, `whisper_cpp.py`; các file
  chưa chạm khác chưa đếm.
- Validation: ruff pass, pyright 0 errors, test translate/subtitle/utils/ui/llm/cli **210 passed**.

### CI: job offline fail từ run đầu tiên vì thiếu libpulse cho QtMultimedia
- Sau khi push 7 commit lên `origin/master`, job "Lint, type check, CLI tests" pass (gate
  `pyright videocaptioner/` xanh trên Linux) nhưng "Offline test suite" fail với pytest exit code 2, giống
  run của `a893800` trước đó. Log job cần đăng nhập nên không đọc được từ máy dev; soi wheel
  `PyQt5_Qt5-5.15.2 manylinux2014` cho thấy `libQt5Multimedia.so.5` cần `libpulse.so.0` và
  `libpulse-mainloop-glib.so.0`, trong khi job chỉ cài libGL/xkb/dbus. Hai file `tests/test_editor/`
  import `PyQt5.QtMultimedia` nên collection fail.
- Sửa `.github/workflows/ci.yml`: cài thêm `libpulse0 libpulse-mainloop-glib0` và gstreamer
  (base/good/libav) cho backend playback; giữ log pytest qua `tee` và thêm bước `Annotate failures` phát
  dòng `FAILED/ERROR` thành annotation `::error` để API public đọc được nguyên nhân mà không cần token.
- Run `0051b2b` sau khi cài libpulse chạy hết bộ test trên Ubuntu: **576 passed, 3 failed** — annotation
  chỉ đúng ba test đặc thù Linux: `validate_relative_reference` không chặn `C:/...` trên POSIX (nay kiểm
  cả `PurePosixPath`/`PureWindowsPath`), test locator so sánh `sys.executable` chưa resolve (trên Linux
  `.venv/bin/python` là symlink), và test `get_subprocess_kwargs` mới thêm giả định có `CREATE_NO_WINDOW`.
  Sửa ở `9fca48a`.
- Run `9fca48a` abort SIGABRT (exit 134) không có tóm tắt pytest: test playback QtMultimedia dùng backend
  gstreamer trên runner không có sink. `555e406` skip test đó khi `QT_QPA_PLATFORM=offscreen` và bước
  annotate in thêm 10 dòng cuối log + dòng faulthandler. Run `555e406`: **cả hai job pass**, CI trên
  `master` xanh lần đầu kể từ khi thêm workflow.
- Test layout editor (`test_editor_layout_remains_usable_at_700_pixel_page_width`) pass trên Ubuntu
  offscreen; chỉ fail khi chạy offscreen trên máy Windows dev (preview 306 px < 320), pass ở platform
  native. Chưa sửa.

### Tài liệu kiến trúc, gộp snapshot cũ, đồng bộ AGENTS/CLAUDE (mục 7)
- `docs/dev/architecture.md` viết lại theo hiện trạng (tiếng Việt như các dev doc mới): sơ đồ CLI/core/GUI,
  cấu trúc thư mục, chế độ đường dẫn, lớp cấu hình, pipeline phụ đề, LLM client, dubbing, VieNeu Local,
  Video Editor, subprocess env, đóng gói và gate. `docs/en/dev/architecture.md` (trước đây rỗng) có bản
  tiếng Anh tương đương; sidebar VitePress đã trỏ sẵn tới hai đường dẫn này.
- `docs/TRANG_THAI_DU_AN.md` (snapshot 2026-05-01) được rút gọn thành mục "Lịch sử cũ" ở cuối
  `status.md` rồi xóa; `docs/README.md` trỏ sang architecture thay cho link cũ.
- `AGENTS.md` và `CLAUDE.md` hợp nhất: cùng nội dung, chỉ khác mục "Đặc thù Claude Code". Sửa claim sai
  rằng `CLAUDE.md` bị gitignore (file được track, chỉ `.claude/` bị ignore), bỏ tham chiếu tới snapshot
  đã xóa, guard Bing ghi đúng là "từng hỏng, chưa đo lại", bổ sung cấu trúc `core/editor`, `core/tts/vieneu`,
  `core/llm`, `installer/`, quy tắc test không ghi vào `AppData/settings.json`, ghi chú môi trường
  (basetemp ngắn, FFmpeg thiếu) và bài học mojibake khi patch file qua stdin trên Windows.

## 2026-09-04 (Nhóm sửa ngắn hạn: CI, test hermetic, timeout, auto-update onedir, LLM log race)

### Nguyên nhân và thay đổi
- Trước đây chỉ `publish-pypi.yml` chạy gate khi push tag. Thêm `.github/workflows/ci.yml` chạy trên
  push `master/main/dev` và mọi PR: ruff, pyright `cli/`, translation sync, test CLI, và job riêng cho
  bộ offline `-m "not integration and not slow and not llm"` trên Ubuntu có FFmpeg + Qt offscreen.
- `tests/test_cli/test_dub.py` fail trên máy không có FFmpeg vì `dub.run` gọi `validate_ffmpeg()` trước
  mọi mock. Thêm `tests/test_cli/conftest.py` autouse patch validator này.
- `test_daily_logs::test_log_interface_loads_only_selected_day` chỉ đúng vào ngày 2026-08-21 vì
  `available_llm_log_days` luôn chèn hôm nay; nay pin `local_day`. Cùng test giữ `QApplication` trong
  biến cục bộ nên bị GC sau khi pass và kéo `qconfig` của qfluentwidgets chết theo, làm mọi test Qt chạy
  sau báo `wrapped C/C++ object ... has been deleted`; nay giữ tham chiếu ở module.
- 14 lời gọi `requests` ở Bcut, JianYing và tải phụ đề YouTube không có timeout nên worker có thể treo
  vô hạn. Thêm `REQUEST_TIMEOUT = (10, 120)` cho hai ASR và `timeout=30` cho phụ đề; kiểm bằng AST:
  không còn `requests.*` nào thiếu timeout trong `videocaptioner/`.
- `UpdateDialog.__onYesButtonClicked` bị name-mangling theo lớp cha nên nút "Cập nhật ngay" thực tế
  chỉ đóng dialog; nay override `validate()` và giữ dialog mở. `_apply_update` copy exe đè
  `sys.executable` sẽ làm hỏng bản onedir; thêm `is_onedir_frozen_build()` trong `platform_utils`,
  với onedir chỉ giữ file đã tải, hướng dẫn chạy thủ công và nút mở thư mục. Bỏ `shell=True`, chạy
  `cmd /c` với list args.
- `request_logger` dùng dict toàn cục không lock và ghép response với entry "completed đầu tiên", nên
  log request/response lẫn giữa các thread translator; entry lỗi không bao giờ bị xóa. Nay ghép qua
  `ContextVar` một slot theo thread/context; thêm test 4 thread song song và retry.

### Validation
- Targeted `test_cli` + `test_llm` + `test_utils` + `test_ui`: **85 passed**. Ruff `videocaptioner/`
  và test mới: pass. Pyright `cli/` và 5 module đã sửa: **0 errors, 0 warnings** (6 warning sẵn có của
  `video_download_thread.py` không đổi). Translation sync: pass.
- Full offline cùng filter CI: **416 passed, 17 skipped, 21 failed, 9 errors**. Toàn bộ fail/error là
  môi trường máy này: FFmpeg không có trên PATH (pydub trong `test_asr/test_chunk*`, fixture của
  `test_natural_dubbing_integration`) và `test_one_app_builder` vượt MAX_PATH khi basetemp dài; chạy
  lại với basetemp ngắn: pass.
- Chưa nghiệm thu: workflow CI chưa chạy thật trên GitHub (job `offline-tests` trên Linux chưa được
  kiểm chứng), UpdateDialog chưa click-through trên EXE thật, Bcut/JianYing chưa gọi thật sau khi thêm
  timeout.

## 2026-08-22 (Nghiệm thu Video Editor trên EXE và sửa lỗi phát hiện khi chạy thật)

### Nguyên nhân và thay đổi
- `Thoát xem trước` làm hỏng playback: `setMedia` rồi `setPosition` ngay lập tức nên backend Windows
  báo `QtMultimedia playback failed` và `QVideoWidget` rơi về surface trắng. Nay seek được hoãn tới
  `LoadedMedia`, position tạm thời trong lúc chờ bị bỏ qua, và poster được hiện lại thay cho surface rỗng.
- Danh sách layer rỗng render trắng vì app stylesheet của QFluentWidgets thắng selector cũ. Dùng ID
  selector `QListWidget#EditorLayerList` cộng palette `Base`; không dùng viewport translucent vì nó để
  lộ nội dung tab bên cạnh.
- Status bar kẹt ở `Loading editor media...` sau khi worker xong; nay khôi phục thành số cue đã tải khi
  không còn media request nào đang chạy.
- Bổ sung 22 chuỗi dịch Việt còn thiếu của editor (`TTS text`, placeholder preview, các thông báo
  render/lưu/xuất và tiêu đề hộp thoại).

### Validation và artifact
- Editor suite: **54 passed** (thêm regression cho exit-preview deferred seek và status label). Ruff
  `videocaptioner/`: pass. Pyright module editor: **0 errors, 0 warnings**. Translation sync: pass.
- PyInstaller 6.22.2 exit 0 với `--workpath` riêng: `build/VideoCaptioner/` cũ thuộc account sandbox
  `CodexSandboxOffline` nên `--clean` không xóa được (WinError 5); đây là ACL của máy, không phải lỗi spec.
- Artifact cuối `dist/VideoCaptioner-EditorLayers-20260822c/`: 585 file / 236.713.006 bytes; EXE
  **30.921.908 bytes**, SHA-256
  `BA400A39D2C82DF3D9410669D4EFBF1687DEA5CAFC1EA96F570AF67DE27537B6`, `NotSigned`. Warning file 614
  dòng, 0 match module editor. `resource/fonts` có trong bundle nên `drawtext` dùng đúng font đã ghim.
  Ba lần build vì hai lỗi chỉ lộ ra khi chạy thật; bản `-20260822` và `-20260822b` là bước trung gian.
- Chạy thật trên EXE (click-through + screenshot từng bước): mở video 12 giây + SRT tiếng Việt qua hộp
  thoại thật, V1 có thumbnail, A1 có waveform, TS1 có 3 cue, thêm layer Văn bản và Mặt nạ, `Xem trước
  nhanh` render và phát với playhead giữ đúng `00:05.023 / 00:12.000` theo timeline dự án, `Thoát xem
  trước` trả về video gốc đúng vị trí và không còn báo lỗi.
- Chưa nghiệm thu: export video đầy đủ, dubbing với provider thật, và các codec ngoài H.264/AAC.

## 2026-08-22 (Video Editor: sửa lỗi visual layer, preview và render)

### Nguyên nhân và thay đổi
- Fast Preview trước đây `setMedia` clip đã render vào chính player, nên vị trí local của clip bị ghi
  thẳng vào `playhead_ms`: playhead nhảy về đầu range, inspector tự chọn nhầm cue và không có đường về
  video gốc. Preview nay chạy ở mode riêng có offset, cộng lại về timeline project, kèm action
  `Exit preview`.
- Mở `.vceditor.json` không gán `project_path` nên Ctrl+S luôn hỏi lại chỗ lưu; nay giữ đúng file đã mở.
- `_refresh_layer_list()` clear list ở mỗi command nên selection về -1 và nút Chỉnh sửa/Xóa im lặng
  không làm gì. Selection nay theo layer id và list được rebuild có block signal.
- Thumbnail đến muộn gọi `set_poster` vô điều kiện, ẩn `QVideoWidget` giữa lúc đang phát. Poster nay chỉ
  áp khi playback chưa bắt đầu.
- Không có cảnh báo mất dữ liệu: `is_dirty` có trong model nhưng UI không đọc. Mở project khác nay hỏi
  trước khi bỏ thay đổi.
- Render không hủy được và `closeEvent` không chạy cho navigation page. `_run` đổi sang `Popen` + poll
  cancel, kill FFmpeg child; có action `Cancel render`, và page dừng worker qua `aboutToQuit`.
- `AppData/cache/editor_preview/` không bao giờ được dọn; nay xóa bản render cũ trước mỗi lần preview.
- Asset khác ổ đĩa (logo, WAV cache) làm hỏng toàn bộ `save()`; path vệ tinh nay fallback absolute, còn
  video/subtitle vẫn bắt buộc relative.
- Visual layer chỉ chỉnh được một thuộc tính qua `QInputDialog` và không đổi được vị trí/kích thước.
  Thêm `LayerInspector` (geometry, timing, opacity, visible/lock, property theo kind) trong cùng tab
  `Layers` với nút add và danh sách; layer chọn/kéo/resize được trên track FX1; track header có nút V
  cho TS1 và FX1.
- Parity preview/export: `drawtext` ghim `fontfile` từ `resource/fonts/` và canh giữa trong box layer,
  logo scale theo frame width thật lấy từ probe, opacity áp cho blur/mask qua `colorchannelmixer`, box
  clamp trong khung, overlay preview dùng rect video đã letterbox và scale font theo tỉ lệ video/widget.
- `boxblur` radius clamp theo `min(w,h)/4 - 1`: giới hạn thật đến từ plane chroma 4:2:0, và render thật
  đã bắt được lỗi `Invalid chroma_param radius value 35` mà assert chuỗi không thấy.

### Validation và artifact
- Editor suite: **52 passed** (thêm `tests/test_editor/test_visual_layers.py`, 17 test). Dubbing +
  thread suite: **69 passed, 2 skipped**. Ruff `videocaptioner/`: pass. Pyright bốn module editor:
  **0 errors, 0 warnings**. Translation sync: pass.
- Có render FFmpeg thật cho blur translucent + text tiếng Việt, và test hủy `_run` bằng FFmpeg đang chạy.
- Kiểm tra layout bằng ảnh render offscreen của page: hai tab vừa khung 1050 px, không còn ô nhập bị cắt.
- Chưa build EXE, chưa click-through GUI thủ công và chưa nghiệm thu video/provider thật cho các thay đổi
  này.

## 2026-08-22 (VieNeu base-build guard và khôi phục one-app onedir)

### Nguyên nhân và thay đổi
- Ảnh lỗi `runtime manifest is unavailable` đến từ việc chạy base onedir ~236 MB; build này không có
  `runtime/vieneu/python.exe`, bridge, runtime manifest hoặc model seed. Lỗi `no active model` là hệ quả.
- Base build nay không tự chạy VieNeu auto-update, không cho lặp action/thread khi runtime vắng, disable
  Start/Update/Fetch và hiển thị hướng dẫn dùng VieNeu One-App thay vì spam InfoBar có đường dẫn lỗi.
- `build_vieneu_one_app.py` trước đó vẫn giả định PyInstaller onefile rồi xóa nhầm output onedir mới tạo.
  Builder nay chạy PyInstaller bằng Python environment hiện tại, giữ toàn bộ `_internal`, ghép runtime +
  model seed vào đúng thư mục onedir và chỉ replace managed VieNeu data khi có `--overwrite`.
- Thêm regression cho base build thiếu runtime và builder augment onedir; đồng bộ bản dịch Việt.

### Validation và artifact
- VieNeu suite: **26 passed**. Startup/UI regression: **10 passed**. Ruff phạm vi source/scripts/tests:
  pass. Pyright service/main-window/builder: **0 errors, 0 warnings**. Translation sync: pass.
- Sáu MSI/CAB input đều khớp SHA-256 ledger. Admin-extract đích dài fail/rollback do MAX_PATH; đích ngắn
  `build/v22` hoàn tất với MSI status 0: runtime **29.245 file / 5.906.443.598 bytes**, model seed
  **42 file / 1.765.957.812 bytes** và active revision `2da0efab622a1722125991736524f080b751ef5b`.
- Exact EXE `vieneu status` exit 0; `vieneu update` exit 0 và báo `current`. Exact packaged Natural Dubbing
  cold-start PyTorch/CUDA, load 20 voices, tạo video 4 giây H.264/AAC mono 48 kHz và exit 0; zero process.
- Computer Use lần đầu phát hiện thêm ACL sandbox làm GUI auto-update gặp WinError 5. Chỉ `AppData` của
  artifact được cấp Modify cho user `Lap-4090`; atomic state replace nay có đúng quyền. Không dùng lại
  Computer Use sau khi binding nhầm sang Codex; hậu-ACL được kiểm bằng ACE/state và test, không gọi là
  visual acceptance lần hai.
- Artifact sạch: `dist/VideoCaptioner-VieNeu-Fixed-20260822/`, **29.853 file / 7.908.872.539 bytes**;
  EXE **30.899.994 bytes**, SHA-256
  `06FC34FA34931E65986EA5B21DBB1D916F120501167788C44276A90E3247DC44`, `NotSigned`. Runtime/model khớp
  distribution manifest; không còn cache/log/work-dir test. Artifact chưa deploy, commit hoặc push.

## 2026-08-21 (Cài đặt và màn tải model không còn nền trắng)

### Đã sửa
- `SettingInterface` nay áp transparent-background contract cho cả `ScrollArea`, native viewport và
  content widget. Dark theme không còn render viewport Windows màu `#efefef` che gần hết chữ/card.
- Hai trang cấu hình FasterWhisper/WhisperCpp cũng đánh dấu native viewport và container là translucent,
  tránh model settings/download flow rơi về palette sáng trên Windows.
- Khi chọn FasterWhisper trong Cài đặt, một card `Quản lý mô hình` hiện ngay bên dưới và mở trực tiếp
  `FasterWhisperDownloadDialog`; dialog vẫn được import lazy. Chọn lại provider đang active không còn là
  ngõ cụt UX vì user có action riêng để tải chương trình/model.
- Thêm regression offscreen cho pixel nền Cài đặt, thuộc tính transparent của cả hai model page, click
  Qt thật từ card mới tới callback mở manager và cả hai nút tải chương trình/model trong dialog.

### Validation và artifact
- Startup/UI targeted: **10 passed**. Ruff các file sửa: pass. Pyright ba module UI: **0 errors, 0
  warnings**. Pixel probe Cài đặt đổi từ `#efefef` sang `#202020` tại toàn bộ điểm nền đã đo.
- PyInstaller 6.22.2 exit 0: `dist/VideoCaptioner-FasterWhisperClickFix-20260821/`, 565 file /
  236,468,546 bytes; EXE **30,898,675 bytes**, SHA-256
  `C89176C89693BA69221EA64FA788644A1F90FE8281445F35A9268FEB70DA4D5D`, `NotSigned`. Warning file
  614 dòng optional/transitive và 0 match ba module sửa.
- Computer Use mở đúng EXE mới và click xuyên suốt Cài đặt → FasterWhisper → Quản lý mô hình → dialog
  tải; toàn bộ flow nhận click và giữ dark surface. Không bắt đầu download thật; đã đóng đúng bản test và
  xác nhận zero process. Artifact chưa được deploy đè lên bản user.

## 2026-08-21 (Video Editor dark UI và visual acceptance)

### Đã sửa
- Sửa nguyên nhân page trắng: `QVideoWidget`, `QTabWidget`, `QScrollArea` và spinbox Qt chuẩn trước đó
  fallback về Windows light palette dù navigation QFluent đang dark. Editor giờ có local dark surfaces
  cho command bar, preview, inspector, splitter, timeline shell, layer list, status/progress và scrollbar.
- Empty state ẩn native video surface trắng và hiện dark placeholder. Loaded state dùng thumbnail đầu làm
  poster trước khi Play; khi bắt đầu playback mới đưa `QVideoWidget` lên để giữ QtMultimedia behavior.
- Thay command bar bọc trong `QScrollArea` (làm width không co và action chồng chữ) bằng responsive shell.
  Chỉ giữ Open/Save/Undo/Redo/Fast Preview/Export trên hàng chính; Save as ASS và visual layers vào More.
- Page đặt window title `Video Editor`; dark hierarchy giữ nguyên tại page width 700 px, không thay engine,
  project schema, timeline model hoặc worker boundary.

### Validation đã đo
- Computer Use chụp ba trạng thái thật: packaged-before có preview/inspector trắng; source empty-state sau
  patch; source loaded-state với video poster, V1 thumbnails, A1 waveform, 5 TS1 cues và inspector; exact
  packaged-after không còn white surface hay toolbar overlap.
- Editor suite: **25 passed, 0 failed**. Ruff toàn `videocaptioner/`: pass. Targeted Pyright editor:
  **0 errors, 0 warnings**. Translation sync: pass.
- PyInstaller 6.22.2 exit 0: EXE **119,560,723 bytes**, SHA-256
  `7F9FBC771E8D41E9E71D31B64D27F6CA49EA40A538491B7155664B4D7399DD08`, 614 warning lines và
  0 editor-warning match, `NotSigned`.
- Web bundle/base bump `1.2.0`; setup SHA-256
  `FFA45AE9072BF692C71786ECB934D4702D2DD6C08D91008426C748D5C53D8F04`. Upgrade apply `0x0`;
  VieNeu runtime detect `Present / execute None`, không tải lại payload. Installed EXE hash khớp build và
  settings hash trước/sau upgrade byte-identical.

## 2026-08-21 (Thin web installer VieNeu)

### Đã triển khai
- Tách distribution thành base MSI chỉ chứa EXE và remote VieNeu MSI chứa runtime GPU + model seed.
  WiX Burn `VideoCaptioner Web Setup` nhúng base nhưng lấy runtime MSI + 5 CAB qua `DownloadUrl`; Burn tự
  tính/kiểm SHA-256 cho từng payload trước khi apply.
- Web setup `1.1.0` dùng cùng base UpgradeCode với offline MSI `1.0.0`, nên đường migration là Windows
  Installer major upgrade thay vì xóa/ghi đè file thô. Runtime là package riêng để bundle uninstall theo
  thứ tự ngược và không trùng component ownership với base.
- Source mới: `installer/VideoCaptioner-Base.wxs`, `VideoCaptioner-VieNeu-Runtime.wxs` và
  `VideoCaptioner-Web-Bundle.wxs`. `PayloadBaseUrl` là build variable; build test hiện trỏ loopback
  `http://127.0.0.1:8765`, cần đổi thành HTTPS CDN/object storage trước khi phát hành cho máy khác.

### Validation đã đo
- Setup EXE **119,974,725 bytes** (114.42 MiB), nhỏ hơn bộ offline nén khoảng 3.8 GiB. Base MSI nhúng
  **118,919,168 bytes**; remote payload gồm runtime MSI + 5 CAB.
- Đã xóa các payload copy cạnh setup để buộc remote path. Burn log xác nhận HTTP `HEAD/GET`,
  `download from http://127.0.0.1:8765/...` và `Verified acquired payload` cho runtime MSI + đủ 5 CAB.
- Quiet install pass: base apply `0x0`, runtime apply `0x0`, bundle apply/cleanup `0x0`. Installed EXE
  SHA-256 `2CEC54842FD78FE34407C97E5E235DC632EAC5318B735140ACD29263D9CCBCCD`; runtime
  `vieneu-3.3.0-bridge-1.0.0`, active model
  `2da0efab622a1722125991736524f080b751ef5b`, `torch_cuda.dll` tồn tại và đúng một shortcut.
- Runtime Burn cache dùng `Cache=remove` và đã được dọn sau install. Bản offline `1.0.0` user cài trước
  đó được gỡ qua registered ProductCode với removal status 0 trước khi nghiệm thu web setup.

## 2026-08-21 (VieNeu Local one-app V0-V5)

### Đã triển khai
- Thêm provider `VieNeu Local` riêng, giữ nguyên generic `Local AI`. GUI/manual/full/batch/editor và CLI
  cùng dùng một managed service; app tự điền loopback endpoint, session token, model và sample rate.
- Thêm domain Qt-independent `core/tts/vieneu`: protocol/state schema có version, locator không hardcode
  checkout developer, hidden sidecar ownership, health identity/auth, timeout/retry/cancel, job lease pin
  revision, graceful/forced owned-tree shutdown và cache/report identity đã sanitize.
- Ship bridge FastAPI/OpenAI-compatible riêng trong runtime, bind `127.0.0.1`, không import CUDA/VieNeu vào
  Qt, không log transcript/token; health báo runtime/backend/revision/48 kHz và scheduler batch an toàn.
- Thêm updater theo Hugging Face commit SHA: resumable full snapshot, atomic state, pinned tokenizer/codec,
  health + voices + WAV validation, deferred activation khi busy, rejected record, offline reuse và rollback.
- GUI có status/start-stop/check-update/rollback/model folder/auto-update qua QThread. CLI có
  `vieneu status|update|rollback` và `--tts-provider vieneu-local`; EXE windowed attach stdout/stderr vào
  console/redirected pipe khi chạy CLI nhưng không mở console ở GUI mode.
- Runtime build dùng uv-managed Python 3.12, pinned VieNeu source commit
  `36c4b501b0634a8f59805e6b529a058fbd30190b`, hash-locked dependencies và notices/license. Builder bỏ
  đúng static development `torch/lib/dnnl.lib`; `torch_cuda.dll` và inference runtime vẫn được giữ.

### Validation đã đo
- Full offline suite: **447 passed, 19 skipped, 0 failed** / 466 collected, 127.06 giây. VieNeu + CLI +
  dubbing regression cuối: **142 passed, 0 failed**. Ruff toàn `videocaptioner/` và các script VieNeu:
  pass; targeted Pyright: **0 errors, 0 warnings**; translation sync/parse và `git diff --check`: pass.
- Real RTX/CUDA: cold **7.7161 s**, warm **0.001295 s**, 20 voices, 4 concurrent WAV mono 48 kHz,
  dynamic batch observed, zero owned process sau shutdown. Clean pruned runtime chạy lại cold
  **13.8077 s**, warm **0.001596 s**, 2 concurrent và dynamic batch pass.
- Real update/rollback: activate `d0c7ea3951eaaca27bdcf53ff9fa9eaf8ed5893a`, update/activate
  `2da0efab622a1722125991736524f080b751ef5b`, offline rollback chạy TTS thật, rồi trả lại latest. Forced
  candidate `760c29661f7ae65c6a6e55abd9691d05613f82ec` bị reject; previous restart, snapshot giữ lại, lỗi
  được sanitize và zero process.
- Exact packaged EXE CLI `vieneu status`: stdout JSON 1.310 byte, stderr rỗng, exit 0. Real packaged
  Natural Dubbing: exit 0, sidecar observed, video H.264/AAC **6.000 s**, mono **48 kHz**, zero EXE/sidecar.
  GUI smoke có parent + child sống sau 15 giây, không eager-start sidecar, log không có startup exception;
  sau đóng còn zero process.

### Runtime, portable và installer
- Clean runtime: **5,906,443,598 bytes / 29,245 files**; lock SHA-256
  `079E23501EF943E355F411F18094992D1E9A25E7FEFD7022F37DA5DFAEF171AE`, VieNeu wheel SHA-256
  `8D4CE3EEB6B645EC1AD03CDCA4AA5BE81906896DE16D531E50AF7387234C8424`.
- Portable `dist/VideoCaptioner-VieNeu-OneApp-20260821/`: EXE **119,559,584 bytes**, SHA-256
  `2CEC54842FD78FE34407C97E5E235DC632EAC5318B735140ACD29263D9CCBCCD`; model seed
  **1,765,957,812 bytes / 42 files**, active latest + pinned MOSS dependency. Release tree được tái tạo
  sau acceptance và xác nhận không chứa cache/log/work-dir/acceptance data.
- WiX MSI entry point `dist/installer-wix6-release-final/VideoCaptioner-VieNeu-OneApp-20260821.msi`:
  **5,345,404 bytes**, SHA-256 `0E64C755A1345F139817163EA8AB47310B4A52CD59215D02239EF3B81E5515DD`,
  đi cùng 5 external CAB dưới giới hạn media và tạo đúng một Start Menu shortcut. MSI install status 0;
  installed EXE hash/model/runtime khớp, installed `vieneu status` exit 0; uninstall status 0, shortcut,
  registry, install dir và owned process đều về zero. EXE/MSI hiện `NotSigned`.

### Acceptance boundary
- Machine audio/container/content gates đã pass nhưng cảm nhận giọng tiếng Việt vẫn cần người nghe ký
  duyệt; artifact là `AppData/vieneu-final-packaged-output.mp4` (không nằm trong release package).
- Giant physically single self-extracting EXE không được hỗ trợ; distribution contract là một MSI entry
  point + external CAB payload, một shortcut/app, với sidecar nội bộ. Publication đi qua feature branch
  để không ghi trực tiếp thêm một payload lớn lên `master`.
## 2026-08-21 (Lazy tabs và Subtitle Style packaged closeout)

### Đã sửa
- `SegmentedWidget.clicked(bool)` trước đó đẩy `bool` vào tham số mặc định của lazy callback, làm mọi
  Home tab sau tab đầu ném `TypeError` và giữ nguyên nội dung Task Creation. Callback nay nhận riêng
  `_checked` và giữ đúng `route_key`.
- Subtitle Style gọi transparent-background contract của QFluentWidgets cho ScrollArea/viewport/widget,
  nên text dark-theme không còn trắng trên panel trắng.
- ASS preview đặt temp `.ass` dưới `AppData/cache` của app và quote/escape đúng đường dẫn FFmpeg filter
  có drive letter, khoảng trắng và dấu nháy; preview không còn fail `original_size` trên Windows.

### Validation
- Regression mới dùng click Qt thật, pixel render dark thật và FFmpeg thật: **8 passed**. Post-merge full
  suite với VieNeu + Video Editor + startup/UI: **453 passed, 23 skipped, 0 failed** / 476 collected,
  113.49 giây. Ruff pass; Pyright CLI + các module tích hợp: **0 errors, 0 warnings**; translation sync pass.
- Computer Use click trực tiếp trên EXE ở `E:\Game\Translate video`: Transcription, Optimize/Translate,
  Dubbing và Synthesis đều hiện đúng page riêng. Subtitle Style có panel dark và preview ASS hiển thị sau
  4 giây; app đóng sạch, zero window/process. Settings giữ nguyên SHA-256
  `DD880B4DFC002DAD90BB91B01E00E7B0E6D7FC868BE45B1ED29E78B320F97384`; log không có error mới sau
  các marker cũ lúc 16:25, preview mới 3,801,434 bytes lúc 16:42:45.

### Artifact cuối
- Onedir EXE **30,883,355 bytes**, 565 file / 236,449,303 bytes; SHA-256
  `23963B0B24D8E6FA8B578B62DD8204B22651DDD59BFB2C997D7118EAB28BEEEE`, `NotSigned`.
- MSI **95,940,948 bytes**, SHA-256
  `CFD055858C02BF99EB488A77A66B1B3CBC45ADD6E48ED0866D9BBF9D8DF4EC10`, `NotSigned`; filtered ICE
  validation exit 0 với ba warning ICE60 TTF app-private như trước.
- Deploy E dùng staged swap; backup runtime/EXE/settings timestamp `20260821-163844` được giữ nguyên.

## 2026-08-21 (Startup responsiveness và Transcription UI không còn khóa)

### Đã sửa
- Đổi PyInstaller mặc định từ `onefile` sang `onedir`; EXE được gắn `logo.png`, installer source nhận
  cả thư mục app và vẫn tạo một shortcut. Mỗi lần mở không còn giải nén hơn 100 MB vào `_MEI...`.
- `MainWindow` và các page Home/Batch/Subtitle Style/Video Editor/Logs/Settings được tạo lazy. Trong
  Home chỉ Task Creation được tạo ban đầu; Transcription/Subtitle/Dubbing/Synthesis chỉ load khi mở.
- `core.asr`, `core.translate` và `core.llm` giữ nguyên public API nhưng chuyển sang lazy exports.
  `yt_dlp` và ModelScope chỉ import trong worker khi thật sự tải video/model.
- Transcription không còn dựng cả ba provider setting widget lúc mở. Kiểm tra FasterWhisper chạy trong
  `QThread`; scan model/bin có giới hạn depth/entry, chịu lỗi permission và không còn tự xóa executable
  nhỏ/hỏng trong một phép kiểm tra trạng thái.

### Validation và số đo
- Fresh-process import `MainWindow`: khoảng **3.300 ms -> 422 ms**. Constructor: **1.618 ms -> 106 ms**.
  First frame + Home: **1.042 ms -> 217 ms**. Mở Transcription lần đầu: **920 ms -> 106 ms**.
- Startup/ASR/thread/CLI/translate targeted: **186 passed, 14 skipped**. Offline suite trong phạm vi sạch:
  **421 passed, 26 skipped, 1 deselected** / 448 collected, 90.94 giây. Ruff toàn source: pass; Pyright
  startup/Transcription: **0 errors, 0 warnings**; translation sync: pass.
- Sau khi merge `origin/master`, targeted VieNeu UI/CLI + lazy tabs + ASS preview đạt **12 passed**;
  full merged suite đạt **453 passed, 23 skipped, 0 failed** trước publication.

### Packaged artifact
- PyInstaller 6.22.2 exit 0:
  `dist/startup-fix/VideoCaptioner-StartupFix-20260821/VideoCaptioner-StartupFix-20260821.exe`,
  **30,883,014 bytes**; toàn onedir **565 file / 236,448,962 bytes (225.50 MiB)**; SHA-256
  `FE0235C18ED9A1BF33D30CE41280D4DD160025D9F5242C3999012F29B749BBEE`; `NotSigned`.
- Warning file 614 dòng optional/transitive, 0 match startup/Transcription/VieNeu. Cold start đầu sau build
  và Windows scan: **11.042 ms**; ba warm start: **863 / 828 / 905 ms**. Mỗi run đúng 1 process,
  `CloseMainWindow` exit 0, zero process còn lại và app log không có exception/error.
- WiX CLI **5.0.2** được cài project-local tại `.tools/wix`; Dotnet home, NuGet cache, temp và
  intermediate đều nằm dưới repo trên ổ F (`.tools` được gitignore, 19.48 MiB). WiX 7 không được dùng
  vì yêu cầu chấp nhận OSMF EULA; không có tool/app project nào được cài global hoặc vào ổ C.
- MSI onedir: `dist/startup-fix/VideoCaptioner-StartupFix-20260821.msi`, **95,936,852 bytes**, SHA-256
  `15B1F1DAD90154E896B4CCE939BEE851F3555509F8F13AACB2F73CE10EE59E19`, `NotSigned`. Decompile xác nhận
  565 File rows và một Start Menu shortcut trỏ đúng EXE. ICE validation còn lại pass sau khi suppress
  `ICE38/64/91` là ba rule WiX không tương thích với wildcard harvesting trong package per-user; chỉ còn
  3 warning ICE60 đã map tới ba TTF app-private. MSI không được chạy cài và registry product vẫn bằng 0.
- Portable onedir được deploy trực tiếp tới `E:\Game\Translate video` mà không chạy MSI; EXE cũ,
  `AppData` và `work-dir` được giữ nguyên. Settings đích giữ đúng SHA-256
  `DD880B4DFC002DAD90BB91B01E00E7B0E6D7FC868BE45B1ED29E78B320F97384` và có backup timestamp trước
  test. Smoke từ E: cold Windows scan **13.096 ms**, warm **1.008 ms**, đúng 1 process, exit 0, zero
  leftover, app log append 55 bytes và 0 error match.

## 2026-08-21 (Video Editor E0-E7)

### Đã triển khai
- Thêm tab `Video Editor` native PyQt5/QFluentWidgets ngay dưới `Kiểu phụ đề` và trên `Nhật ký yêu
  cầu`; page co được tới 700 px, command bar overflow vào More thay vì overlap.
- Thêm domain `editor-project-v1` với stable cue/layer IDs, milliseconds canonical, relative paths,
  atomic project + SRT save và ba trường riêng `source_text` / `display_text` / `tts_text`. Normal save
  không persist ASS; chỉ explicit `Save as ASS` tạo ASS.
- Preview QtMultimedia, inspector và timeline V1/A1/TS1 đồng bộ playhead/selection/overlay. Timeline có
  zoom/scroll/range, add/split/delete, drag/resize, track mute/lock và undo/redo; waveform/thumbnails chạy
  QThread, cache theo media fingerprint và bỏ kết quả stale.
- `Regenerate voice` dùng `DubbingEngine`, force-refresh đúng cache key của selected group, đo WAV và
  giữ nguyên cache/audio group khác. Fast Preview dùng WAV live đã regenerate; final export dùng cùng
  editor snapshot và Natural/Legacy config hiện có, không tạo report JSON mặc định.
- Blur/Logo/Mask/Text có core model, layer panel, timeline clip, preview, FFmpeg export, command undo,
  serialization và round-trip. Không thêm PySide6, MPV hay dependency mới.
- Thêm `Open in Video Editor` từ Subtitle và Dubbing workflow; cập nhật translation sources/fallback,
  README, tài liệu dev và plan. `VideoCaptioner.spec` không cần đổi vì đã collect toàn bộ submodule.

### Validation đã đo
- Editor targeted: **23 passed, 0 failed**. Dubbing/thread/CLI/subtitle/translate regression:
  **151 passed, 10 skipped, 0 failed**. Full offline suite cuối với AppData/cache cô lập:
  **419 passed, 23 skipped, 0 failed** / 442 collected, 107.01 giây.
- Real FFmpeg H.264/AAC + SRT/WAV fixtures pass Fast Preview 1.5 giây, live display/TTS routing,
  regenerated voice mix, Blur/Logo/Mask/Text render và final export giữ duration trong ±120 ms. Không
  có ASS ngoài explicit export.
- QtMultimedia H.264/AAC playback tiến được và seek 1.7 giây trong tolerance. Layout 700 px, stale-result
  discard, preview/inspector/timeline sync và worker isolation đều pass.
- Timeline 60 phút/1.000 cue tại viewport giữa chỉ paint **3 cue**; 100 paint = **21.958 ms**
  (**0.220 ms/frame**), 5.000 query = **1.801 ms** (**0.360 µs/query**).
- Ruff toàn `videocaptioner/`: pass. Pyright CLI + toàn bộ editor module: **0 errors, 0 warnings**.
  Translation JSON/TS parse và sync `--check`: pass.

### Packaged artifact
- PyInstaller 6.22.2 exit 0: `dist/VideoCaptioner-VideoEditor-20260821.exe`, **113,104,947 bytes**,
  timestamp `2026-08-21 04:08:23 +07:00`, SHA-256
  `23836F039A3C4E7CC2C2257352E2AC1A150901BFE8B8D707176A4BA486F119E7`, `NotSigned`.
- Warning file có 569 dòng optional/transitive; 0 match editor/QtMultimedia. Archive chứa QtMultimedia,
  toàn bộ `core.editor`, UI components, media/voice thread, interface và Vietnamese translation.
- Exact packaged smoke: parent PID 52244 + child PID 79816 sống sau 15 giây; daily log append 55 bytes,
  0 startup exception match; đã đóng đúng owned tree và xác nhận 0 process còn lại.

### Còn chờ user/provider thật
- Chưa nghiệm thu cảm nhận UX, codec/video thực tế đa dạng, chất lượng nghe tiếng Việt, provider TTS thật,
  rate-limit hoặc video thật dài. Machine acceptance không dùng API key/live provider.

## 2026-08-21 (Dubbing report in-memory và lỗi có nguyên nhân)

### Đã sửa
- GUI và full pipeline không còn tự ghi `<output>-dubbing-report.json`. `dubbing-report-v1` được giữ trong
  RAM để dialog hiển thị; CLI chỉ persist JSON khi user chủ động truyền `--report PATH`.
- Provider failure nêu số group, group ID và lỗi provider đã sanitize; API key/Bearer token bị redaction.
- Natural review nêu số group, group tệ nhất, audio duration, available duration và fit ratio, kèm hướng
  xử lý. GUI giữ lỗi trên status label và InfoBar sticky thay vì biến mất sau 5 giây.
- CLI exit 6/7 in nguyên nhân ra stderr; chỉ in report path khi report thực sự được yêu cầu.

### Validation và package
- Dubbing + TTS + CLI targeted: **139 passed**. Ruff: pass. CLI Pyright: **0 errors, 0 warnings**.
- PyInstaller exit 0: `dist/VideoCaptioner-NaturalDubbing-20260821.exe`, 112,995,075 bytes
  (107.76 MiB), timestamp `2026-08-21 02:43:56 +07:00`, SHA-256
  `F1BC0254B73B06DF49E852762E6D028CE5E0C44C8C310D035C30A60FD3A89D4B`, `NotSigned`.
- Packaged smoke: parent PID 21468 + child PID 34896 sống sau 15 giây; daily app log append 55 bytes,
  0 startup exception match; đã đóng đúng hai PID và xác nhận 0 process test còn lại.
- Không chạy lại full suite; full gate gần nhất vẫn **379 passed, 26 skipped, 0 failed**.

## 2026-08-21 (Chia log theo ngày)

### Đã sửa
- Application log ghi vào `AppData/logs/app-YYYY-MM-DD.log`; mỗi ngày vẫn size-rotate 10 MiB với tối đa
  5 backup trong ngày. Tất cả named logger dùng chung một handler để không tranh chấp rollover.
- LLM request log ghi vào `llm_requests-YYYY-MM-DD.jsonl`; quá 10 MiB sẽ giữ tối đa 2 backup trong ngày.
- Màn `Nhật ký yêu cầu` có bộ chọn ngày, chỉ nạp file của ngày đang xem và nút xóa chỉ xóa ngày đã chọn.
  `llm_requests.jsonl` / `.old` cũ vẫn xuất hiện dưới mục `Cũ`, nhưng writer không ghi thêm vào đó.
- `LogWindow` theo dõi file app-log của ngày hiện tại, tự chuyển ngày/rotation và chỉ đọc tail 20 KiB thay
  vì nạp toàn bộ file. Không tự xóa hoặc migrate log cũ của user.

### Validation và package
- Daily-log + context/UI tests: **15 passed**; riêng daily contract: **6 passed**.
- Ruff: pass. CLI Pyright: **0 errors, 0 warnings**. Translation sync/source validation: pass.
- PyInstaller exit 0: `dist/VideoCaptioner-NaturalDubbing-20260821.exe`, 112,995,075 bytes
  (107.76 MiB), timestamp `2026-08-21 02:43:56 +07:00`, SHA-256
  `F1BC0254B73B06DF49E852762E6D028CE5E0C44C8C310D035C30A60FD3A89D4B`, `NotSigned`.
- Packaged smoke tạo đúng `app-2026-08-21.log`; parent PID 21468 + child PID 34896 sống sau 15 giây,
  0 startup exception match; đã đóng đúng hai PID và xác nhận 0 process test còn lại.
- Không chạy lại full suite; full gate gần nhất vẫn **379 passed, 26 skipped, 0 failed**.

## 2026-08-21 (SRT-only pipeline, TTS boundary dedup và kế hoạch Video Editor)

### Đã sửa
- Full subtitle pipeline nay dùng output `【字幕】*.srt` và chỉ persist SRT cạnh video; không còn tự tạo
  `【样式字幕】*.ass` hoặc `<video>.ass`. Menu Save trong `SubtitleInterface` vẫn giữ lựa chọn ASS khi user
  chủ động cần export.
- Layout re-export chỉ cập nhật các SRT pipeline đã tạo, không tự ghi lại ASS cũ.
- Natural planner nay loại overlap 1-4 spoken token ở biên giữa các cue được merge, ví dụ
  `"... bạn" + "bạn khỏe ..."`. Chỉ `tts_text` thay đổi; `subtitle_text`/cue display giữ nguyên. Report
  ghi warning `Removed repeated TTS boundary overlap`. Một cue lặp hoàn toàn vẫn được giữ để không xóa
  lời lặp có chủ ý.
- Thêm kế hoạch tích hợp tab `Video Editor` dựa trên khảo sát read-only `F:\CppClone\CapCap`, port theo
  kiến trúc PyQt5/QFluentWidgets thay vì import trực tiếp PySide6.

### Validation
- Dubbing: **58 passed**. Thread: **10 passed, 2 skipped**. CLI: **58 passed**.
- Regression riêng output/dedup: **18 passed**. Ruff: pass. CLI Pyright: **0 errors, 0 warnings**.
- Không chạy lại full suite vì thay đổi hẹp; full gate gần nhất vẫn là **379 passed, 26 skipped, 0 failed**.
- PyInstaller exit 0: `dist/VideoCaptioner-NaturalDubbing-20260821.exe`, 112,995,075 bytes
  (107.76 MiB), timestamp `2026-08-21 02:43:56 +07:00`, SHA-256
  `F1BC0254B73B06DF49E852762E6D028CE5E0C44C8C310D035C30A60FD3A89D4B`, `NotSigned`.
- Packaged smoke: parent PID 21468 + child PID 34896 sống sau 15 giây; 0 startup exception match;
  đã đóng đúng hai PID và xác nhận 0 process test còn lại.

## 2026-08-21 (Natural Dubbing P-1 đến P8)

### Đã triển khai
- Tách `source_text`, `subtitle_text`, `tts_text`; `AUTO` ưu tiên bản dịch và full pipeline dùng artifact
  target-only riêng, không tái sử dụng SRT display song ngữ cho TTS.
- Thêm domain schema `dubbing-plan-v1` / `dubbing-report-v1`, deterministic grouping planner, dự đoán
  duration chỉ để routing và sức chứa timeline có borrowable silence + guard.
- Thêm persistent WAV cache `AppData/cache/dubbing_tts/v1` với key SHA-256 theo text đã normalize,
  provider host, model, voice, speed và sample rate; metadata không chứa credential/raw response.
- Thêm timing rewrite qua `call_llm` hiện có với strict JSON validator giữ số, phần trăm, tiền tệ, unit,
  product token và negation. Không có LLM config thì bỏ rewrite và đi thẳng fit/review policy.
- Natural mode đo WAV thật, chỉ re-synthesize outlier, giới hạn speed mặc định 1.08x và không truncate.
  Outlier chưa giải quyết sẽ `review` (dừng trước mix) hoặc `allow-overlap` có warning. Legacy vẫn có
  max-speed/truncate và ghi action `legacy_truncate`.
- GUI có Auto/Translation/Original, Natural/Legacy, rewrite/cache/unresolved controls và report dialog
  read-only. Provider failure/review không còn bị báo thành công bằng video gốc.
- CLI có `dub` và `process --dub`; exit code 6 = review, 7 = provider failure. Quiet `dub` chỉ in output
  path khi thành công.

### Validation đã đo
- Targeted: dubbing **55 passed**; subtitle pipeline **1 passed**; CLI **58 passed**; translate
  **14 passed, 7 skipped**; ASRData **46 passed**.
- Full suite với `LOCALAPPDATA=AppData/CodexTest`: **379 passed, 26 skipped, 0 failed** / 405 collected,
  76.62 giây. Skip thuộc live credential/service markers, Bcut HTTP 412, JianYing rate-limit và Bing 404.
- Ruff `videocaptioner/`: pass. Pyright `videocaptioner/cli/`: **0 errors, 0 warnings**. Translation sync:
  pass.
- FFmpeg integration tạo video fixture thật và WAV FakeTTS deterministic: cache miss→hit, target routing,
  measured rewrite, Natural review không truncate, allow-overlap, Legacy truncate, voice-track/mix và
  video không audio stream đều pass.

### Packaged artifact
- PyInstaller 6.22.2 exit 0: `dist/VideoCaptioner-NaturalDubbing-20260821.exe`, 112,995,075 bytes
  (107.76 MiB), timestamp `2026-08-21 02:43:56 +07:00`.
- SHA-256: `F1BC0254B73B06DF49E852762E6D028CE5E0C44C8C310D035C30A60FD3A89D4B`; Authenticode:
  `NotSigned`.
- Archive có `dubbing/initial.md`, `dubbing/rescue.md` và `DubbingReportDialog`. Warning file có 555
  missing-module lines, chủ yếu optional/transitive từ ModelScope, yt-dlp, urllib3; không có match Natural
  Dubbing. Noteworthy: `tzdata`, `sip`, `js`, `curl_cffi`, `yt_dlp_ejs` không được bundle.
- Smoke exact EXE: parent PID 21468 + child PID 34896 cùng sống sau 15 giây; log append 55 bytes, 0 startup
  exception match; đã đóng đúng hai PID và xác nhận 0 process test còn lại.

### Còn chờ user/provider thật
- Chưa nghiệm thu chất lượng nghe tiếng Việt, OpenAI/MiniMax/local provider thật, rate-limit hay video dài.
- Không có live API/key nào được dùng trong machine acceptance. EXE GUI đã startup pass nhưng workflow
  media/TTS thật trong packaged app vẫn chờ user thử.

## 2026-08-18 (Sửa lỗi theo review code)

### Sửa lỗi chặn tính năng
- **Dubbing hỏng hoàn toàn với ffmpeg 8.x**: `-filter_complex_script` đã bị ffmpeg 8.0 loại bỏ →
  bước ghép voice track fail 100%. Nay probe một lần rồi chọn `-filter_complex_script` (ffmpeg cũ)
  hoặc `-/filter_complex` (ffmpeg mới). Đã verify end-to-end với ffmpeg N-126188 (2026-08-17).
- **Không lồng tiếng được sang Trung/Nhật/Quảng**: `_strip_cjk` lọc ký tự CJK vô điều kiện làm mọi
  câu rỗng. Nay có `DubbingConfig.strip_cjk`, `task_factory` tự tắt khi ngôn ngữ đích là CJK; nếu
  toàn bộ câu bị lọc thì báo lỗi nêu rõ nguyên nhân thay vì "TTS thất bại cho tất cả segments".
- **Mix audio fail trên video không tiếng**: filter `[0:a]` không có stream. Nay probe bằng ffprobe
  và tự rơi về chế độ "tắt audio gốc".
- **Search & Replace chưa được nối vào UI**: dialog chỉ được import, không có nút nào gọi. Nay có
  action trong command bar của `SubtitleInterface`, thay thế hàng loạt trên cả cột gốc và cột dịch.
- **`uv.lock` lệch `pyproject.toml`** (`yt-dlp>=2026.6.9` vs lock `2025.12.8`) làm `uv sync --frozen`
  của CI fail. Đã `uv lock` (yt-dlp 2026.7.4) và verify `remote_components: ["ejs:github"]` là option
  thật của yt-dlp → bản fix YouTube HD mới thực sự có hiệu lực.
- **ASR chunking sinh chunk rác**: mp3 padding làm audio dài hơn vài chục ms so với yêu cầu, khiến
  `_split_audio` cắt thêm một chunk ~48ms và gửi thêm một request ASR cho mỗi file. Nay bỏ qua phần
  đuôi ngắn hơn 1s.
- **`logger` chưa định nghĩa** trong `FasterWhisperSettingWidget._extract_7z` → NameError khi giải
  nén bằng tar thất bại.

### Sửa chất lượng dịch / cache
- Cache key của translator dùng chỉ số nội dung tất định (`source_signature`) thay cho ngữ cảnh toàn
  cục do LLM sinh ở temperature=1 — trước đó cache 7 ngày mất hiệu lực sau 1 giờ.
- Không build ngữ cảnh toàn cục khi số dòng < 10 (dịch lại vài dòng đã chọn không còn tốn thêm một
  lần gọi LLM cho một bản brief vô nghĩa).
- Reflect mode không còn ghi raw dict (`{'initial_translation': ...}`) vào phụ đề khi LLM trả sai
  schema — điều kiện nào không hợp lệ thì giữ nguyên bản gốc.
- Progress bar không còn đứng khi hit cache (`update_callback` được gọi cả trên nhánh cache).
- Chỉ gửi **tên file** thay vì đường dẫn tuyệt đối vào prompt LLM.
- `core/llm/context.py` chuyển sang `contextvars` + `submit_with_context` ở mọi ThreadPool → batch
  chạy song song không còn lẫn nhãn `task_id`/`stage` trong `llm_requests.jsonl`.

### Dọn dẹp
- Lint: `ruff check videocaptioner/` từ 58 lỗi → **0**. Gỡ dead config `speed_range[0]`, `gap_ms`,
  `output_format` (`speed_range` → `max_speed`), bỏ tham số không dùng của `_align_timeline`.
- Test suite: **21 failed + 16 errors → 0** (325 passed, 23 skipped). Nguyên nhân đã sửa: module
  `tests/test_tts` không collect được (`SiliconFlowTTS` đã bị gỡ trong refactor), thiếu fixture
  `mock_llm_client`, fixture cache rò trạng thái sang test khác, `MockTTS` ghi file không encoding.
  Test phụ thuộc service miễn phí bên thứ ba nay **skip** khi outage/rate-limit thay vì fail.
- Gộp 4 file `.spec` trùng nhau thành `VideoCaptioner.spec` (đặt tên exe qua `VC_BUILD_NAME`).
- Thêm `scripts/sync_translations.py` (có `--check`) thay cho bước copy tay 2 bản translations.
- `pyproject.toml`: `[tool.uv] dev-dependencies` → `[dependency-groups] dev` (bỏ deprecation warning).
- Docs: sửa đường dẫn `app/core/...` → `videocaptioner/...`, bỏ link chết `docs/CI_SETUP.md` và
  `docs/TESTING.md`.

### Còn tồn (chưa sửa)
- **Bing translator hỏng phía Microsoft**: `https://edge.microsoft.com/translate/auth` trả 404 (đã
  verify độc lập bằng curl, có và không có User-Agent). Cần tìm endpoint mới của Edge translate —
  không đoán. Trong lúc đó `--translator google` vẫn chạy tốt.
- CLI vẫn chưa có lệnh `dub`.

## 2026-06-30 (Nâng cấp dịch thuật)
- Thêm pha "ngữ cảnh toàn cục": đọc toàn bộ phụ đề một lần để sinh brief (chủ đề/tông giọng/glossary), nhồi vào mọi khối dịch giúp nhất quán thuật ngữ và mạch văn (áp dụng cho cả chế độ thường và phản tư).
- Sửa lỗi cache key: nay phân biệt theo chế độ phản tư, custom prompt và ngữ cảnh — tránh nhận nhầm kết quả cache cũ khi đổi thiết lập.
- Dịch phản tư có chọn lọc: chỉ phân tích sâu các dòng "có mùi dịch máy" để tiết kiệm token/thời gian.
- Ghi log phần phản tư (initial/reflection) thay vì bỏ đi; thêm nhãn tiến trình riêng cho chế độ phản tư.

## 2026-06-30
- Hoàn thiện engine lồng tiếng (Dubbing): tích hợp MiniMax TTS và mở rộng nhiều nhà cung cấp TTS khác nhau.
- Cải thiện chất lượng, tốc độ xử lý âm thanh và bổ sung chức năng trộn/ghép (merge) audio.
- Giữ giọng lồng tiếng ở âm lượng đầy đủ khi trộn với audio gốc.
- Thêm tùy chọn lồng tiếng hàng loạt (batch dubbing) và cho phép nhập thủ công số luồng TTS (thread count).
- Tăng tốc bước trộn âm thanh.

## 2026-05-01
- Thêm tính năng "Tìm kiếm & Thay thế" (Search & Replace) trong giao diện `SubtitleInterface` (Tab Tối ưu và Dịch phụ đề).
- Tính năng này hiển thị một popup nhập liệu, cho phép người dùng thay thế hàng loạt những từ bị dịch sai trong dữ liệu phụ đề hiện tại.
- Cập nhật tài liệu `README.md` tương ứng.


## Lịch sử cũ (gộp từ `docs/TRANG_THAI_DU_AN.md`, snapshot ngày 2026-05-01)

File snapshot đã bị xóa; nội dung dưới đây là bản rút gọn để giữ lịch sử. Mọi mục mới hơn ở trên
mới là trạng thái hiện tại.

- Build lúc đó: `dist/VideoCaptioner-PhaseD-20260501.exe` (~107 MB, onefile), Python 3.12.13,
  PyInstaller 6.20.0, tên EXE đặt qua `VC_BUILD_NAME`. Từ 2026-08 spec đã chuyển sang onedir.
- Phase D lồng tiếng bằng TTS API: thêm `core/dubbing/` (config, audio_mixer, engine), `DubbingThread`,
  tab "Lồng tiếng" (pipeline + thủ công), `DubbingTask` trong entities, 9 config item dubbing, dubbing
  step tùy chọn trong `subtitle_pipeline_thread`. Tái dùng `core/tts` (OpenAI TTS, SiliconFlow, voice
  clone + cache); ba chế độ audio gốc (giữ/giảm 40%/tắt); căn timeline bằng atempo 0.75x–1.5x, truncate
  khi vượt. Sau này Natural timing, planner, rewrite và VieNeu Local thay thế phần lớn logic này.
- Dọn UI: xóa card "Trợ giúp", "Gửi phản hồi" ở Cài đặt và icon GitHub trên sidebar.
- Tự cập nhật phiên bản: `auto_update_thread.py` tải EXE mới, `UpdateDialog` với progress + batch script
  thay thế và restart; `main_window.onNewVersion()` và `setting_interface.checkUpdate()` dùng dialog này.
  (2026-09-04: dialog từ chối thay EXE trên bản onedir và chỉ giữ file đã tải.)
- Bản dịch Việt: `resource/translations/VideoCaptioner_vi_VN.json` 698 entry, đồng bộ sang
  `videocaptioner/resources/translations/`.
- Kế hoạch còn dang dở khi đó: dubbing trong batch FULL_PROCESS, CLI `videocaptioner dub` (đã có),
  test end-to-end với TTS key thật, tối ưu build (UPX/exclude module).
