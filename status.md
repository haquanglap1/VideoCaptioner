# Project Status

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
