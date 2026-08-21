# Project Status

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
