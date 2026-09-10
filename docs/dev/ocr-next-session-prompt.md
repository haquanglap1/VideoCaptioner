# Prompt phiên tiếp theo — sau pilot OCR local

Tiếp tục **VideoCaptioner-ASR-S3**, nhánh **codex/asr-s3-native**, không làm ở
checkout master. User đã yêu cầu tiếp tục OCR sau sửa Soniox/Qwen; không tự mở
lại toàn bộ nghiệm thu ASR để trì hoãn OCR. Phiên trước đã chạy pilot local,
chưa có so sánh với vision API, chưa triển khai toàn GUI.

## Bắt đầu

Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`,
`docs/dev/ocr-pilot-2026-09.md` và
`docs/plans/video-subtitle-ocr-integration-plan.md`. Chỉ đọc
`docs/dev/asr-recovery-2026-09.md` khi cần phạm vi ASR/build đã có.

Chạy `git status --short --branch`, lấy HEAD thật, đối chiếu tracking/origin.
Snapshot OCR được user yêu cầu submit/push: **`0348d7e`** chứa script pilot,
recipe/lock/hash, worker CPU và packager OCR; commit tài liệu theo sau.
Không coi commit code là HEAD cuối hoặc checkout về `df3aeee`/`f03420c`.
Giữ thay đổi có sẵn. Quyền commit/push chỉ chốt snapshot phiên trước, không
tự áp dụng cho code mới; không reset, merge master, commit/push/tag/release
nếu chưa được yêu cầu.

## Evidence và kết quả phải giữ

Scratch OCR duy nhất: **`build/ocr-pilot-20260910/`**.

- `inputs/manifest.json` và `inputs/crop-01.png` đến `crop-13.png`: đã có
  13 crop màu gốc 1920×80, ROI [0,960,1920,80], không header/đáp án.
  Dùng lại, kiểm SHA khi đọc, không trích lại để tạo cùng input.
- `local-final/raw.jsonl`, `metrics.json`, `comparison.json`,
  `effective-config.json`, `dictionary.json`, `process.json`: lượt chấm
  chất lượng thành công. `report.vi.md` giải thích từng crop bằng tiếng Việt.
- `session-metrics.json`, `gates.json`, `preservation.json` và
  `portability.json`: phạm vi số đo, gate và bảo toàn dữ liệu.
- `vision/plan.json`, `vision/prompt.md`: nhánh AI đã chuẩn bị, **chưa gọi API**.
- `runtime/`: venv OCR đã cài; `portable/models/ocr/`: payload Python độc lập
  đã materialize; `portable/models/portable-models.json`: inventory/hash.
- `synthetic-inputs/`, `synthetic-portable/`: 6 fixture tổng hợp và output thật.
- Giữ `local-fresh/`, `local-startup-diagnostic/`, `local-measured/` cùng
  source/profile cũ trong `upstream/`: đây là các lượt lỗi harness, không phải
  kết quả OCR chấm đúng. Không xóa hoặc dùng chúng thay `local-final`.

Local: **13/13 có chữ, 10/13 exact, 12/13 đủ chữ** theo tham chiếu agent.
Câu 4 thiếu chữ “tháng” dù ảnh rõ và sai dấu ba chấm; câu 10 sai dấu ba chấm;
câu 6 khác ASCII/fullwidth dấu hỏi. Raster không xác định được encoding gốc,
không coi mọi khác biệt codepoint là sai nghĩa. Tham chiếu chưa được người bản
ngữ xác nhận. Không sửa raw hoặc chép đáp án vào output engine.

Lượt thành công: 13 fresh/0 cache, 13 detector/13 recognizer/0 classifier,
load 0,435 s, vòng xử lý 2,440 s, process 3,703 s, peak working set 490.553.344
byte. Process mới nhưng OS cache đã ấm do debug; chưa benchmark cold-disk.
Tổng phiên gồm cả 13 crop lỗi ghi metric và 6 fixture: **32 detector/32 recognizer**.
6/6 fixture exact, **158 tests pass**, Ruff/Pyright/translations pass.
Không chạy lại chỉ để lấy số pass mới nếu không có thay đổi cần kiểm.

Nguồn cũ:
`build/asr-session-evidence/VC-UserClip-20260908-114035/`.
Sample `inputs/sample-zh.mp4`, reference `reports/reference-provenance.json`,
mapping `reports/source-caption-visibility-refined.json` được giữ nguyên.
Video 30 fps, time base 1/16000; representative cũ trên lưới 25 Hz được ghép
frame PTS gần nhất, delta tối đa 13,3125 ms. Đây là delta trích ảnh, **không phải
độ đúng biên cue**. Start/end vẫn prototype, chưa nghiệm thu OCR timing.

## Công việc tiếp theo

1. Tiếp tục cả hai hướng **OCR local và AI đọc ảnh**, chưa chọn engine mặc định
   hoặc kết luận bên nào tốt/rẻ hơn. Local pilot đã có số đo; không cài/tải lại
   hoặc sweep nhiều model. Nếu cần sửa lỗi chữ, thử có giới hạn và giữ riêng
   kết quả mới; không thay input của phép so sánh 13 crop ban đầu.
2. Nhánh AI thiếu endpoint, model nhận ảnh, nguồn key đúng phạm vi và ngân sách.
   Kiểm tra user đã bổ sung lựa chọn trong hội thoại mới chưa; nếu chưa, hỏi
   đúng thông tin còn thiếu trước API. Không suy model dịch nhận ảnh hoặc dùng
   STT key. Dùng cùng 13 crop/prompt; giữ raw/usage/latency/call count, không đưa
   tham chiếu/contact sheet/transcript vào request. Không coi lượt agent đã xem
   ảnh là phép thử vision API độc lập. Thiếu usage/cost để null.
3. Khi AI chưa có cấu hình, tiếp tục phần local độc lập của **OCR-2** theo plan,
   không chặn mọi tiến độ và không gọi cloud ngầm. Ưu tiên domain/fixture trước
   GUI: ROI transform, decode theo PTS thật, bộ đệm tối đa 8 ROI frame, tối đa
   3 ảnh đại diện/track, backpressure, cancel/timeout/drain stderr/join reader.
   Không đưa prototype giữ toàn video dưới dạng list ảnh vào app.
4. Gom thay đổi chữ phải phát hiện đổi một ký tự, hai dòng, câu lặp sau khoảng
   trống, fade, empty ROI và video không audio; thử VFR/nonzero PTS/offset/rotation/
   SAR bằng fixture tổng hợp. Chữ/timing còn bất định phải giữ review, không
   xuất rỗng/thiếu như thành công. Chỉ chọn chuỗi engine đã đọc thật, không ghép
   chữ tùy ý, đổi giản/phồn thể, sửa tên hay đoán ký tự thiếu.
5. OCR timing là thời gian chữ hiện trên màn hình, không phải timestamp lời nói.
   Không gán speaker/xưng hô. Contract `VisualSourceIdentity`/`OcrDocument`,
   adapters/review/CLI là OCR-3; GUI/model manager/frozen là OCR-4. Giữ metadata
   typed, CommandStack và quy tắc save của editor khi đến bước tích hợp.
6. Báo rõ thay đổi/validation mới, số crop/call/cache/fresh, decode/load/inference/
   process wall time và RAM theo từng phạm vi; không cộng stage chồng nhau thành
   total giả. Agent đối chiếu ảnh, giải thích bằng tiếng Việt; không giao user
   nhiệm vụ chấm từng chữ Trung. Không gọi OCR hoàn tất khi chưa đủ gate plan.

## Runtime, build và dữ liệu

- Host Python 3.12.13: `../VideoCaptioner/.venv/Scripts/python.exe`; FFmpeg/ffprobe
  đã có trong `../VideoCaptioner/AppData/bin/ffmpeg/`. Không Python 3.13, cài
  global hoặc sync/nâng dependency app.
- Recipe `scripts/ocr_pilot_data/profile.json`: RapidOCR 3.9.2 / ONNX CPU 1.29.0,
  PP-OCRv5 mobile detector + Chinese server recognizer, dictionary 18.383 entry
  và SHA rõ. Có 23 dependency pin/hash trong `requirements.lock`. Không dùng
  `RapidOCR()` với model mặc định ngầm; classifier bundled được nạp do upstream
  nhưng 0 inference. Không import NumPy/cv2/ONNX/Paddle/Torch vào Qt.
- Profile cuối thêm kiểm SHA dictionary sau lượt đo đầu, không đổi preprocessing.
  Dùng profile/hash đi cùng từng receipt; không coi hash profile đầu là hash payload.
- Packager hỗ trợ `--ocr-runtime`, payload OCR 4.477 file / 398.907.184 byte.
  Python/stdlib/deps đã kiểm nằm trong payload, không có venv home ngoài gói.
  **Chỉ kiểm thư mục mới cùng ổ, chưa EXE/GUI/khác ổ.** App chưa có locator OCR.
- EXE test phải kèm runtime/model đã cài trong `models/` cạnh EXE, tự tìm được
  khi chuyển ổ. Dùng một `VideoCaptioner.spec` và `VC_TEST_MODELS_DIR`.
  Giữ/tái sử dụng bộ ASR/TTS đã verify; không stage lại 48 GB hoặc tải model
  chỉ vì build mới. Bộ `portable/` của pilot chỉ chứa OCR, không tự coi là
  bộ đủ mọi model ASR/TTS cho EXE test.
- `package_test_models.py` hiện không tự ghép vào collection đã verify không có
  owner staging; khi cần thêm OCR vào bộ test đầy đủ, làm thay đổi có kiểm hash/
  inventory và giữ bộ cũ, không bỏ guard hoặc ghi đè artifact tùy tiện.
- LLM dịch hiện có: `https://api.videocaptioner.cn/v1`, `gpt-5.6-terra`,
  timeout 300 s. Không đổi gateway/model. Key ở `../../Api.txt` chỉ đọc khi
  cần và đúng endpoint/phạm vi user cho; không mặc nhiên được dùng cho vision.
  Không ghi key vào settings/chat/argv/env/log/Git; LLMCredentials trong RAM,
  subprocess dạng list và `child_environment()`.
- Giữ clip 30 s, ASR/bản dịch/6 WAV, Soniox 21 cue/review gốc, bài giảng và
  151 WAV/121 nhóm lời đã sửa. Không nhận dạng/dịch/TTS/render lại các job đó.
  Giữ các guard Soniox/Qwen đã sửa; các giới hạn ASR còn mở không biến thành pass.
- Không đưa media/raw riêng/key/settings/WAV/log vào Git hoặc gói model.
  Không xóa runtime/download/artifact để dọn ổ. Không bật Computer Use cho
  file/code; nếu cần GUI thì chỉ đúng process test, đóng sạch sau nghiệm thu.
- DeepLX/Google/Bing/Bijian/Bilibili/Jianying/ElevenLabs vẫn ngoài nghiệm thu.
  Không dùng fallback ngoài phạm vi hoặc lấy video mới.

Cập nhật status/biên bản theo bằng chứng mới; phân biệt source/isolated runtime/
packaged Python/frozen/GUI, pass/fail/chưa chạy. Bàn giao bước tiếp cụ thể.
