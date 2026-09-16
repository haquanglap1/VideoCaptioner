# Prompt phiên tiếp theo — agent tự nghiệm thu sau bản GUI Lifetime

Tiếp tục ở checkout user chỉ định, worktree **VideoCaptioner-ASR-S3**, nhánh
**codex/asr-s3-native**. Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất của `status.md`,
phần S5.2 trong `docs/dev/asr-implementation-2026-09.md` và `docs/dev/asr-s52.md`.
Đọc thêm `asr-local-s5.md`, `asr-s41.md`, `architecture.md` khi cần đúng domain.

**Agent tự làm phần kiểm thử kỹ thuật và chuẩn bị kết quả.** User đã yêu cầu bỏ việc xác nhận
từng nút vì mất thời gian. Chỉ gom checkpoint khi cần người nghe/đọc đánh giá chất lượng, lựa chọn
dịch vụ có phí, nhập credential kín hoặc chọn media riêng. Không bắt user sửa lệnh placeholder.
Phân biệt rõ agent đo, user xác nhận, evidence kế thừa, chưa chạy và blocked.

Mục tiêu tiếp theo: nghiệm thu workflow **local/media trên binary Lifetime hiện tại**, quan sát
thêm vòng đời GUI, và xử lý lỗi có tái hiện thuộc các luồng này. **Chưa mở S6**, không benchmark
corpus, chọn engine mặc định mới, tự commit/push/tag/release. Quyền submit của phiên bàn giao
không tự áp dụng cho thay đổi mới. Lưu prompt không khởi chạy task hoặc automation.

## 1. Xác minh snapshot và giữ dữ liệu

- Code GUI Lifetime đã chốt tại **`e6c0074250df41b5da4b7eaa71b2e9f21e4adcab`**, parent
  **`7e2889527bc3293b5e1f5a484e53b34e99aa3290`**. Code ASR S5.2 **`073510d`** là ancestor.
  HEAD còn có commit tài liệu bàn giao sau code. Kiểm tra `git status --short --branch`, log,
  ancestry; giữ mọi thay đổi user, không reset/clean/stash hoặc đoán rằng checkout sạch.
- Manifest code commit gồm `videocaptioner/ui/main.py`,
  `tests/test_ui/test_gui_entry_lifetime.py`, `status.md`, `docs/dev/asr-implementation-2026-09.md`.
  Hai file code/test chỉ sửa lifetime GUI và thêm regression; phần tài liệu chứa kết quả nghiệm thu.
- Artifact mới: **`dist/VideoCaptioner-ASR-S52-Lifetime-20260907/`**, EXE cùng tên thư mục,
  **31.161.900 byte**, local **2026-09-07 22:39:32**, SHA-256
  **`b2dfe8692266fd08dc2471f54838385b975c6ebfe0839d8aa1d5436b38a75f78`**.
  Onedir **580 file / 237.667.204 byte**; **218 module** trong PYZ đã so khớp source.
  Build exit 0, 234,437 s; 6 optional/platform WARNING, 0 ERROR, 6 SyntaxWarning upstream.
- Giữ bản cũ **`dist/VideoCaptioner-ASR-S52-Review-20260907-Final/`**, SHA-256
  **`457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649`**.
  Giữ media, `.env`, cookies, AppData, work-dir, logs, runtime và mọi artifact khác.
- Tạo scratch mới chưa tồn tại. Copy **EXE + `_internal/`** sang bản test onedir mới, kiểm tra hash;
  không copy AppData/media/log của artifact và không dùng artifact gốc làm scratch.
- Python đã dùng **3.12.13**, interpreter/FFmpeg có sẵn; checkout này không có `.venv` riêng.
  Tìm interpreter phù hợp, xác minh import đúng checkout. Không dùng Python 3.14 trên PATH,
  uv sync/cài global/nâng pin Qt, sửa generated version/QM hoặc thêm GPU libraries vào venv Qt.

## 2. Trạng thái đã đo — không chạy lại chỉ để có thêm số pass

| Gate | Evidence và giới hạn |
| --- | --- |
| User A1–A6, B1 | User xác nhận GUI/settings, chọn runtime, health Community-1/aligner, đóng app và mở review trên Final cũ. Sau đó user giao agent tự kiểm thử |
| Lifetime regression | QApplication được giữ ở module scope; translator có parent application. Hai case VI/EN fail trên source cũ rồi pass sau sửa. Không tắt GC/SIP destructor hoặc đổi worker cleanup |
| Offline mới nhất | **1.119 passed / 5 skipped / 51 deselected / 145,95 s / exit 0**, gồm CLI106. Test gần 29 pass/6,89 s; ruff pass, pyright 0/0, translations/diff-check pass |
| Năm skip | QtMultimedia H.264 playback vì offscreen; bốn TTS/service. Không gọi đây là native playback hoặc online acceptance |
| Lifetime review GUI | Agent mở review, lưu bằng native picker, xác minh FLAC/FFmpeg, xuất JSON, reopen. Raw/IDs/edited/identity/pending giữ nguyên; reopen không tự báo nguồn đã verified |
| Lifetime editor GUI | Agent mở project tổng hợp riêng, đổi speaker A→B, Apply→undo→redo, Save JSON+SRT rồi reopen. Typed reload giữ timing/provenance/context confirmed/locked/pending, không ASS |
| Lifetime GUI exit | **966,328 s**, RSS snapshot **255.377.408 byte**, đóng X exit 0; không process con, log chỉ update-check, không traceback/InfoBar. Không phải bằng chứng mọi crash đã hết |
| Whisper API thật | **Final cũ**, một command được user chọn: videocaptioner / `https://api.videocaptioner.cn/v1` / `whisper-1` / public Chinese 4,204 s. Health trước upload exit 0/40,109 s; cache MISS, ASR→Community-1→JSON exit 0/22,141 s; 1 cue 0–4000 ms, 1 speaker, 67.263 sample/identity khớp, pending false; EXE xuất SRT exit 0 |
| GPT/Qwen local | GPT hybrid source/Final EXE và Qwen/Community-1 source/EXE ở các snapshot trước đã smoke thật. Chưa chạy job ASR mới trên Lifetime; không tự chuyển dấu pass giữa hai binary |
| Speaker/pending contract | Agent đã đo CLI/typed API và tone tổng hợp: mismatch trước runtime, raw/IDs/overrides/legacy/pending đúng; Community-1 thật xóa pending sau stage. Unknown/ambiguous/overlap/assigned và union span giữ nguyên. Không phải speaker accuracy |

**Whisper EXE không còn là gate đang fail 429 trong snapshot hiện tại:** một job mới đã pass trên
Final sau lượt 429 cũ. Không tự gọi lại API chỉ vì prompt cũ nói còn nợ, hoặc vì code GUI vừa đổi.
Scribe online, phồn thể strict, speaker accuracy và xưng hô do người đọc vẫn chưa nghiệm thu.

## 3. Việc ưu tiên agent tự làm

1. **Media local từ Lifetime.** Dùng audio Trung public ngắn đã có, chọn tường minh
   **Qwen 0.6B → strict alignment → Community-1 → JSON/SRT** trên bản copy Lifetime mới.
   Giữ model/policy/pin; không chuyển mặc định GUI hoặc đổi model khi lỗi. Kiểm tra config/root,
   readiness và audio trước job; phân biệt status, health và inference. Ghi cache hit/miss,
   stage/exit, counts, identity/timing/pending và cleanup. Một kết quả review phải được giữ nguyên
   để điều tra, không clamp/nội suy/bỏ token/cắt prefix để ép pass.
2. **Playback native còn thiếu.** Dùng video tổng hợp hoặc public đã chấp thuận; kiểm tra Play,
   seek, poster/timeline và đóng editor/app trên backend native. Không dùng screenshot offscreen
   làm bằng chứng layout/playback. Có thể dùng test native hiện có
   `tests/test_editor/test_ui_sync_performance.py::test_qtmultimedia_h264_preview_plays_and_seeks`
   với config/cache/media cô lập; không coi chỉ mở poster là video đã phát thành công.
3. **Quan sát shutdown trong workflow thật.** Kết hợp review/editor, save/reopen, đổi selection,
   cancel kiểm tra nguồn rồi đóng app. Dùng GUI tools khi callable, giữ đúng cửa sổ/PID bản test.
   Quan sát tối thiểu 25 s và đọc log/process sau đóng. Nếu công cụ UI timeout, kiểm tra process,
   exit và WER trước khi kết luận là lỗi công cụ hoặc lỗi app; tiếp tục gate độc lập bằng CLI/API
   và ghi rõ bằng chứng nào còn thiếu. Không chuyển việc bấm nút lại cho user một cách mặc định.
4. **Checkpoint chất lượng có ý nghĩa.** Trình bày output cùng đoạn audio/video ngắn để user
   nghe/xem, gom các điểm cần đánh giá text/timing/speaker. Chỉ dùng video riêng khi user chọn
   hoặc chấp thuận. Không tự chấm xưng hô, suy danh tính/giới/quan hệ hoặc mở corpus S6.

Runtime dùng nguyên tại chỗ, **không copy/move venv rồi gọi portable**:

- Qwen/ForcedAligner: **`build/S5-Qwen-Runtime-20260907-R2/`**; không chọn bản S5 đầu.
- Community-1: **`build/S51-Community1-Runtime-20260907/`**; không chọn thư mục chỉ có dependency.
  Revision **`3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`**, manifest SHA-256
  **`8af6543a4f173c8a3c19c84c802c57a4f4ded1ccf242ad23c2fee6b675068447`**.
  Đã cài và inference offline thật; không cần xin lại HF token hoặc chấp nhận điều kiện lại.

Audio public ưu tiên là `public-zh.wav` đã dùng ở scratch nghiệm thu; decode canonical cho
**67.263 sample**, khoảng **4,204 s**. Nếu thiếu, dùng đúng nguồn
[Qwen public Chinese](https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_zh.wav).
Agent phải resolve đường dẫn và chuẩn bị output chưa tồn tại trước lệnh, không giao placeholder
cho user. Các flag đã có: `transcribe --asr qwen-local --language zh --qwen-model qwen-0.6b`,
`--qwen-runtime`, `--local-diarize`, `--diarization-runtime`, `--local-timeout`, `-o`.
`local-diarize` dùng timed JSON/SRT và `--audio`, `--runtime`; **không nhận `--config`**.

## 4. Giữ đúng giới hạn crash SIP

- Final GUI PID 52400 đã crash exit **3221225477 / 0xc0000005**, SIP offset **0xe58e**;
  lỗi Settings trước đó có offset **0x13a26**. Dump main thread đi qua QApplication destruction,
  SIP wrapper visitor/get-address trong Python/SystemExit cleanup.
- **24 subprocess baseline/stress trước sửa đều exit 0.** Chỉ hai điều kiện lifetime được tái
  hiện tất định và có regression red→green. Không khẳng định nút Lưu, automation, InfoBar và
  lỗi Settings là cùng một nguyên nhân; không khẳng định mọi crash SIP đã hết.
- Nếu crash lại: giữ output/log riêng, ghi đúng binary hash/PID/thời điểm/exit, đọc bản ghi WER
  và dump đúng process ở máy. Không upload dump hoặc quét heap tìm dữ liệu riêng tư/credential.
  Không sửa framework/nâng pin, tắt GC/SIP destructor hay nới timeout để che lỗi. Chỉ sửa ứng dụng
  khi có bằng chứng về nguyên nhân/phạm vi và test hồi quy phù hợp.

Hai thư mục scratch cũ nằm cạnh checkout (tìm bằng basename, không tìm credential):

- **`VC-S52-Accept-20260907-204008`**: `reports/acceptance.md`, `reports/fixture-manifest.json`,
  `reports/whisper-one-job.json`, output Whisper và fixture tổng hợp. Các script owner cũ đã thoát;
  không chạy lại owner/script trả phí hoặc tìm key cũ.
- **`VC-S52-SIP-Diag-20260907-221507`**: `README.md`, `artifact-verification.json`,
  `gui-process.json`, `gui-output-verification.json`, `native-stack-unwind.txt` và test/build logs.
  `native-stack.txt` và `native-stack-with-images.txt` là thử nghiệm unwind chưa đúng, **không
  dùng làm bằng chứng**. Helper ignored chỉ hỗ trợ điều tra, không thay source test/manifest.

## 5. API, privacy và bàn giao

- Key gateway của phiên trước đã rời RAM khi owner thoát; không nằm trong argv/env/file.
  **Không tìm trong chat cũ, checkout khác, AppData, log/artifact hoặc environment chung.**
  Chỉ mở ô password/getpass khi user chọn job trả phí mới; không yêu cầu dán key vào chat.
- HF, gateway, Scribe/ElevenLabs và LLM dịch là credential/quyền riêng. Thiếu một key không chặn
  các gate local. Scribe chỉ chạy khi có lựa chọn và key đúng provider; không trộn Community-1
  lên native labels. Không resubmit Soniox hoặc đổi provider/model để vượt parser.
- Mỗi job tính phí phải nêu provider/endpoint/model/audio trước. Quyền chạy một job Whisper
  trước đó **đã dùng**, không tự cấp cho lần mới. Không chạy vòng lặp command sau 429; policy
  retry hữu hạn bên trong app vẫn giữ. Nếu dịch bằng `gpt-5.6-terra`, timeout tường minh 300 s,
  cần đúng endpoint/quyền LLM; không suy key STT dùng được cho dịch.
- Identity là hash toàn PCM16 mono 16 kHz + sample count; không tự gắn identity cho legacy.
  JSON/project giữ metadata; SRT không giữ identity/context. Pending chỉ xóa sau diarization.
  Unknown/ambiguous/overlap và coverage union ≥80% không phải xác suất acoustic.
- Test phải cô lập AppData/cache/config/lease. S2 vẫn có thể lưu cache values khi tắt cache reads:
  fixture alignment dùng cache RAM. QThread phải wait trước khi object ra khỏi scope. Không chạy
  full cùng build/GPU jobs; không rerun full/build chỉ để sửa tài liệu hoặc submit Git.
- Nếu sửa code: test gần lỗi và gate liên quan; thay lifetime/metadata/runtime thì full offline.
  Artifact mới dùng spec duy nhất và tên/output/work/cache/temp mới; báo đủ bốn gate build,
  source/bundle match và giới hạn runtime. Không ghi đè hoặc dọn artifact cũ.
- Cập nhật status/implementation và bảng gate theo bằng chứng thật, chỉ metadata không nhạy cảm
  vào Git. Kết thúc bằng kết quả, blocker cụ thể và việc còn lại; **dừng review, không tự S6/submit**.
