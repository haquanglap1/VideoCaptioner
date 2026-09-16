# Qwen câu thực dụng và Whisper dự phòng — 2026-09-09

User đồng ý giữ Qwen 1.7B làm chính, chấp nhận sai số nhận dạng/timing thông thường
và dùng Whisper cho vùng không xuất được phụ đề. Thay đổi này tiếp tục `b102ae9`
trên ASR-S3, giữ các tài liệu chưa commit từ trước; không commit/push.

## Hành vi đã triển khai

- Policy mới `qwen-sentence-practical-v1`: chia câu theo text như trước, lấy start
  đầu/end cuối; yêu cầu interval dương, trong audio, không chồng câu, giới hạn
  thời lượng câu. Lỗi duration của token biên và outlier nội bộ không tự chặn câu.
  Kiểm tra năng lượng trong toàn cue, không ép từng onset. Raw không bị sửa.
- Policy `qwen-sentence-anchors-v1` của review cũ và strict word vẫn giữ nguyên
  semantics. Cache validated tách theo policy; raw alignment dùng lại được.
- Alignment đi tiếp qua các chunk lỗi trong chế độ câu; sau khi đóng runtime
  Qwen/aligner, gọi Faster-Whisper trên vùng chưa dùng được. Các chunk liên tiếp
  được gom để giảm lần nạp model; đuôi dưới 3 s dùng kèm đoạn trước để có ngữ cảnh.
  Whisper thay cả chữ và timing trong vùng, không ghép giờ vào
  transcript Qwen khác chữ. Không tự tải model dự phòng.
- Whisper dùng executable/model đã chọn ở cấu hình Faster-Whisper và nhận tên
  model + model directory đúng contract XXL. Process có deadline, kiểm tra hủy
  khi im lặng, cleanup process tree và GPU lease. Chỉ cache kết quả có cue hợp lệ;
  key phụ thuộc audio, cấu hình, fingerprint executable/model và policy.
- JSON giữ recognition provider/policy riêng từng cue; original Qwen/raw được
  lưu trong review. CLI/GUI báo số cue Whisper dự phòng. TXT-only không đổi;
  word mode không tự fallback. Dự phòng thất bại vẫn giữ TXT/review, không báo
  timed export thành công khi chưa tạo được file.

## Bài giảng thật

Evidence nằm trong `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/practical-sentences-20260909/`.
Nguồn video được resolve từ receipt cũ, xác minh hash; 29 recognition và 29 raw
alignment được phục hồi vào cache thử nghiệm riêng sau khi đối chiếu WAV/hash,
interval và provenance. Cache/raw/media cũ được giữ nguyên.

- Policy câu mới dùng được 27/29 chunk; còn overlap ở index 26 và zero-duration
  ở index 28. Đuôi 28 quá ngắn nên thêm index 27 làm ngữ cảnh; Whisper xử lý một
  vùng **713.100–771.029 ms** (57,929 s), giữ Qwen ở 26 chunk đầu.
- Public source CLI: **exit 0**, tạo `lecture.zh.srt` và `lecture.provenance.json`:
  **180 cue = 164 Qwen + 16 Whisper**. **0 Qwen recognition / 0 alignment mới**;
  một lượt Whisper inference thành công **26,234 s**, bao gồm khởi động worker.
- SRT SHA-256: `db52c8bfb8288644d1254c5f656ececcad103d30cb70f77fa904be84fda3f38c`.
  Đọc lại SRT/JSON giữ nguyên chữ/mốc, tất cả interval dương, trong recording và
  không chồng. Editor adapter nhập đủ 180 cue với ID duy nhất. Mốc cuối 767.150 ms.
- Lỗi helper đầu là stub cấu hình sai signature; hai lần startup Whisper đầu
  truyền model path vào tham số tên model, chưa recognition, đã sửa adapter và
  thêm regression. Lượt CLI thành công bị helper assertion whitespace sai sau
  khi đã ghi output; validator độc lập xác nhận file nguyên chữ. Giữ các log lỗi,
  không lặp inference đã thành công; không thay chúng thành pass.
- Đây là phụ đề dùng thử theo tiêu chí mới, chưa có reference/CER cho bài giảng
  hoặc nghe thủ công kiểm tra độ khớp lời nói. Không tuyên bố độ chính xác 80–90%.

## Validation

- Local ASR/sentence/review/identity: 112 pass; sau fix tham số model chạy lại
  suite fallback 13 pass (10 case cũ + 3 case mới). Tổng 115 test ASR khác nhau.
- CLI, local-ASR UI và transcript thread: 139 pass / 2 skip (workflow Faster-Whisper
  của fixture riêng không có cấu hình model). Tổng các suite: **254 pass / 2 skip**.
- Rà cuối giữ nguyên semantics word review: lỗi geometry không bị ghi nhầm thành
  lỗi acoustic cho mọi token. Bổ sung assert vào test cũ; 36 case word/sentence/
  fallback pass sau chỉnh này, không cộng lặp vào tổng test khác nhau.
- Ruff app/tests pass; pyright app **0 error / 0 warning** với `--venvpath` trỏ
  môi trường project chính đã có. Lần đầu pyright dùng nhầm đường `.venv` checkout
  báo missing imports; không cài/sync dependency. Translations in sync.
- Không full corpus, sweep, model download, dịch hoặc lồng tiếng mới.

## EXE

1. Spec duy nhất, bản cuối `VideoCaptioner-ASR-Practical-20260909-R2`: PyInstaller
   **exit 0**, khoảng **124,3 s** trong log; **6 WARNING / 0 ERROR** (js/emscripten,
   curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit). Có thêm cảnh báo Python từ thư viện
   modelscope/pydub trong build; không gây build failure.
2. EXE **31.194.113 byte**, timestamp local **2026-09-09 11:25:05**; SHA-256
   `ef4edc3af17f0e3fbef2575001e37a6abf34c561cfbb487ce079818565f2046e`.
   Phân phối nguyên onedir trong `dist/VideoCaptioner-ASR-Practical-20260909-R2/`.
3. GUI sống **25 s**, cửa sổ chính tồn tại, đóng đúng PID **exit 0**, không force.
   Lượt smoke R2 không có traceback/ERROR trong log; startup không lỗi import/resource.
4. Public CLI từ EXE: **exit 0 / 10,875 s**, SRT byte-identical bản source.
   Dùng 86 cache entries riêng đã verify; giữ GPU lease suốt lượt để cấm inference
   ngoài dự kiến. Chỉ thấy ffmpeg/ffprobe/nvidia-smi/conhost, không child sót;
   media giữ hash. Đây là frozen cached workflow, không phải đo tốc độ model.
   Chưa bấm workflow nhận dạng qua GUI hoặc inference mới từ EXE, tải model qua
   GUI, dịch, synthesis hay lồng tiếng end-to-end.

Bản Practical đầu (trước chỉnh review word cuối) vẫn giữ nguyên: build exit 0 /
185,6 s, SHA-256 `c19fad6fc7328623e74abb84e1c4f0a21289887430fb9c9035f66ee75d0bfb0e`.
Lượt GUI bản đầu có lỗi QFluentWidgets `BottomInfoBarManager has been deleted`
lúc đóng sau thông báo version, vẫn exit 0; lỗi này không xuất hiện trong smoke R2.
R2 chỉ thay semantics ghi lý do review khi word timing lỗi geometry, không thay
kết quả câu đã xuất hoặc chạy lại model. Dùng R2 cho source cuối của lượt này.

## Bổ sung: dịch bài giảng để user kiểm tra

User yêu cầu dùng LLM dịch bản phụ đề đã xuất. Lượt riêng trong
`practical-sentences-20260909/translation-vi/` dùng **gpt-5.6-terra** tại
`https://api.videocaptioner.cn/v1`, timeout **300 s/request**. Key được nhập qua
ô password, chỉ giữ trong RAM của job; không ghi settings/chat/argv/env/file.

- Dịch đủ **180/180 cue**, **7 request thành công** (một brief ngữ cảnh + sáu
  batch 30 câu), model trả về đúng `gpt-5.6-terra`, tổng **155,844 s**. Không
  recognition/alignment/GPU, không upload audio, không optimize hoặc split lại.
- `lecture.vi.srt`: bản tiếng Việt; `lecture.vi-zh.srt`: Việt trên/Trung dưới;
  `lecture.vi.txt`: bản đọc nhanh; `lecture.translated.json`: giữ nguồn/metadata.
- Validation độc lập: đủ 180 bản dịch không rỗng, 180 mốc SRT giống bản gốc,
  original text/cue ID/provenance giữ nguyên, source hash không đổi. Worker đã
  `wait()` và process exit 0; không benchmark/test/build app thêm.
- Đã đọc mẫu đầu/giữa/cuối. Một số tên công cụ được LLM diễn giải theo ngữ cảnh
  từ ASR chưa rõ; chưa đối chiếu lời nói thật hoặc chấm chất lượng dịch. User
  dùng bản tiếng Việt/song ngữ để kiểm tra. Không công bố phần trăm chính xác.

SRT tiếng Việt SHA-256:
`4caa358db175e4f24755eaaad1e21fa922666eb6faf0638cd63fdb8a21d00711`.
Đây là validation dịch source bằng core LLMTranslator; chưa là workflow dịch
bằng nút GUI/EXE hoặc synthesis/lồng tiếng. Các mục “chưa dịch” phía trên mô tả
lượt ASR trước yêu cầu dịch bổ sung này.

## File thuộc thay đổi này

- `videocaptioner/core/asr/local/sentence_timing.py`, `review.py`, `pipeline.py`;
  thêm `sentence_fallback.py`.
- `videocaptioner/cli/commands/transcribe.py`, `videocaptioner/ui/thread/transcript_thread.py`.
- `tests/test_asr/test_qwen_sentence_timing.py`, `test_local_s5.py`;
  thêm `test_qwen_sentence_fallback.py`.
- `VideoCaptioner.spec`, `README.md`, `status.md`, tài liệu này,
  `docs/plans/asr-completion-2026-09.md`, `docs/dev/asr-completion-next-session-prompt.md`.

Các báo cáo lecture/native từ trước được giữ nguyên. OmniVoice Studio vẫn là
hạng mục sau ASR, bên cạnh VieNeu Local; OCR dừng. Evidence và EXE không đưa vào Git.
