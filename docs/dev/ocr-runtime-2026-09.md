# OCR-2: CPU streaming thật và tiếp tục vision — 2026-09-10

Tiếp tục theo yêu cầu user trên ASR-S3, nhánh `codex/asr-s3-native`, HEAD **1457808**.
Giữ 23 file chưa commit của lượt trước; không sửa master, commit/push, cài/tải lại
runtime/model, đổi dependency app hoặc nhận dạng/dịch/TTS lại các job đã có.

**Kết quả:** pipeline source đã nối với CPU worker thật và quét hết sample 60 giây,
1.800 frame → 13 track. Chất lượng vẫn cần review. Vision đã có thêm 8 response,
tổng 12/13 ảnh có kết quả; crop 5 timeout cũ chưa retry trong ngân sách 13 request.
OCR-3 document/identity/CLI/review/editor và OCR-4 GUI/frozen vẫn chưa triển khai.

## Supervisor và transport

- `core/ocr/runtime.py`: `CpuOcrRuntime` nhận root, bridge, job directory và SHA
  profile tường minh. Process riêng giữ model suốt job; không nạp OCR dependency
  vào host. Kiểm health protocol/profile/bridge SHA/provider CPU; thiếu runtime
  dừng trước inference, không tải ngầm hoặc chọn model khác.
- `scripts/ocr_stream_worker.py`: dùng Python OCR đã cài, verify package/model/
  dictionary, chặn network/download, pin cùng profile PP-OCRv5. Không sửa bridge,
  profile hoặc inventory trong runtime/payload pilot cũ. Bridge mới nằm ở source,
  chưa phải locator/bundle cho pip/frozen.
- Mỗi request ghi một `frame.rgb` trong thư mục job sở hữu, header nhỏ có ID,
  kích thước và SHA. Worker kiểm size/hash, chuyển RGB → BGR tường minh rồi gọi
  engine. Response giữ nguyên lines/score/box; không sửa chữ hoặc ghép candidate.
- Output queue 16 message, response tối đa 1 MiB, stderr drain theo block 4 KiB
  và chỉ đếm byte. Timeout/cancel/protocol failure đóng đúng cây process, join
  cả reader và cleanup job. Giới hạn request dừng khi tracking tạo quá nhiều
  nhóm; không restart hoặc reset ngân sách ngầm.
- Worker phát bộ đếm khi vào wrapper ONNX trước call, nên hủy vẫn giữ dấu vết
  attempt. Bộ đếm này **không bảo đảm ONNX đã hoàn tất** khi process bị hủy.
- `scripts/ocr_stream_pilot.py` nối snapshot → probe → decode → tracking → runtime
  → raw/review, lấy mẫu RSS host/worker tree/FFmpeg. Đây là harness source để đo,
  chưa phải lệnh `videocaptioner ocr`, không xuất accepted SRT.

## Lỗi thật đã sửa

1. Python `-I` trên Windows có stdout pipe cp1252. Hai lượt đầu đã chạy model
   nhưng lỗi `UnicodeEncodeError` khi trả chữ Trung. Transport nay ghi UTF-8
   trực tiếp vào stdout binary, có regression cp1252; không dùng env để sửa lách.
2. `FIND_EDGES` khuếch đại nhiễu codec mức sáng 0–1 trên nền đen thành mask giả.
   Lượt sample đầu tạo 16 nhóm rỗng trước cue thật và chạm cap 39 request.
   Nay bỏ tín hiệu có luma range <4 **trước** lọc cạnh; fixture nhiễu xác minh
   không sinh cue giả. Chữ sát noise floor/fade vẫn chưa có bảo đảm timing;
   không coi ngưỡng này là hiệu chuẩn cho mọi video/nền động.
3. `RoiDecoder.close()` lần hai từng kéo dài clock decode dù process đã đóng.
   Đã làm close idempotent và kiểm metric không đổi. Receipt `cpu-stream-final-03`
   giữ giá trị decode cũ 0,766 s có lỗi đo này; receipt sample cuối đã đúng phạm vi.

Không giấu các lượt lỗi: `cpu-stream-01/`, `cpu-stream-diagnostic-02/`,
`cpu-sample-05/` giữ nguyên trong `build/ocr-pilot-20260910/`.

## Nghiệm thu local thật

**Fixture streaming** `cpu-stream-final-03/`: cùng video lossless VFR/nonzero
origin/no-audio của lượt trước, 3 track đúng biên và **3/3 text hai dòng exact**.
6 candidate → 2 fresh/4 cache hit, **2 detector/4 recognizer/0 classifier** (hai
dòng mỗi ảnh); load 0,682 s, inference 0,237 s, worker process 2,422 s, vòng harness
2,497 s. Không lấy decode clock của receipt này làm số đo sau sửa idempotency.

**Hủy inference thật** `cpu-cancel-04/`: sau message vào detector wrapper, cancel
→ process đã dừng/readers joined/job sạch trong **0,377 s**. Một detector attempt,
0 recognizer; không có response hoàn chỉnh và không xác định call detector đã xong.

**Sample 60 s** `cpu-sample-final-06/`:

| Chỉ số | Giá trị |
| --- | --- |
| Frame / track / candidate crop | **1.800 / 13 / 39** |
| Fresh / cache hit | **38 / 1** |
| Detector / recognizer / classifier | **38 / 38 / 0** |
| Network attempts / vision calls của local run | **0 / 0** |
| Text / exact codepoint / đủ chữ-số | **13/13 / 10/13 / 12/13** |
| Review | **13/13**, profile chưa hiệu chuẩn |
| Verify / import / load worker | **0,061 / 0,576 / 0,542 s** |
| Inference thật / host chờ recognition | **9,812 / 10,751 s** |
| Tracking | **17,464 s** |
| FFmpeg process và vòng pipeline (overlap) | **28,968 s** |
| Worker process wall | **30,797 s** |
| Harness wall, gồm snapshot/probe/load/close, trừ host import/startup | **30,889 s** |
| Queue peak / bound payload decoder | **4 / 8 ROI frame** |
| Host sampled RSS / peak Windows working set | **35.258.368 / 36.552.704 byte** |
| Worker tree sampled RSS / worker peak Windows working set | **505.303.040 / 510.349.312 byte** |
| FFmpeg sampled RSS | **98.553.856 byte** |
| Reader join / job cleanup | **pass / pass** |

Thời gian decode có backpressure/chờ OCR; **không phải decode thuần**. Không cộng
các stage chồng nhau thành total hoặc cộng peak của ba process thành peak đồng thời.
Model/file cache đã ấm; chưa cold-disk. Đây là một sample, không benchmark video dài.

Cả 13 track dùng PTS/time base **1/16000** của nguồn, không lưới 25 Hz. Bảng chấm
giữ ms phân số và delta với prototype chỉ để đối chiếu; prototype không phải
ground truth độc lập cho độ chính xác biên. Fixture timing đã pass; chưa gọi
timing của video riêng được nghiệm thu frame-accurate bằng tham chiếu độc lập.

Ba ảnh thật/track vẫn cho cùng lỗi bỏ chữ “tháng” tại câu 4. Đồng thuận có thể
cùng sai; không tự chấp nhận chỉ vì nhiều ảnh có cùng text. Không sửa raw.

**Thử có giới hạn tại câu 4** `local-bounded-crop04-07/`: hai biến thể từ crop gốc,
lấy hộp detector đã có + margin, và bản đó phóng 2×. Crop sát chữ đọc lại được
chữ “tháng” nhưng chỉ giữ hai dấu chấm; bản 2× lại bỏ chữ này. **2 fresh/2 detector/
2 recognizer**, không thử model khác hoặc sweep. Ảnh nguồn 13-crop vẫn nguyên SHA;
kết quả biến thể không thay bảng so sánh gốc và chưa bật preprocessing tự động.
Agent đã xem hai ảnh và đối chiếu chữ; tham chiếu vẫn chưa native-confirmed.

**Tổng attempts của lượt tiếp tục này**, không chỉ lượt thành công:
`cpu-attempt-ledger.json` ghi 7 run, **84 request worker / 81 response hoàn chỉnh**,
**84 detector wrapper / 59 recognizer wrapper / 0 classifier**. Gồm hai lượt lỗi
UTF-8, hủy, sample chạm cap và hai biến thể. Một detector bị hủy chưa rõ completion;
không gọi toàn bộ số wrapper đó là inference hoàn tất. Gate cũ 32 detector/32
recognizer của OCR-1 giữ phạm vi riêng, không ghi đè.

## Vision continuation

User yêu cầu làm tiếp: cùng gateway/model/key, giữ ngân sách tổng **13 requests**.
`--previous-run` đọc receipt, tính cả timeout, không gửi lại crop từng thử và chặn
receipt trùng/mismatch. `vision-terra-02/` đã gửi **crop 6–13: 8 request/8 response**,
retry 0. Tổng hai lượt: **13 attempts, 12 response, crop 5 timeout chưa retry**.

Trên **12 crop chung**, local **9/12 exact và 11/12 đủ chữ-số**, vision **8/12 exact
và 12/12 đủ chữ-số**. Vision khác encoding dấu ba chấm/các dấu hỏi/chấm than ở crop
4, 6, 7, 11; local thiếu một chữ ở crop 4. Không coi strict codepoint là sai nghĩa
hoặc suy engine thắng/thua từ một sample. Không thay 12-crop bằng 13-crop denominator.

Usage của **12 response**: **38.090 prompt + 608 completion = 38.698 token**;
gateway báo **26.880 cached prompt tokens** trên 7 response. Đây là cache provider,
khác **0 cache hit của app**. Các response cùng trả model ID `gpt-5.6-terra` nhưng
usage shape khác nhau (974 và khoảng 4.746 prompt token); giữ nguyên metadata,
không suy backend model hoặc tính giá từ tên alias.

Median latency 12 response **22,351 s**, max **241,266 s**; timeout cũ 300,009 s.
Usage request timeout/tổng đủ 13 attempts/cost tiền vẫn **null**. Hai receipt và
raw giữ riêng; `vision-combined-03/comparison.json` chỉ là phép đối chiếu sau khi
có raw, không là request mới.

Đã chuẩn bị flag retry tường minh với cap tổng 14, chỉ cho crop đã lỗi mà chưa
có kết quả thành công; đã hỏi user quyền thêm đúng một request cho crop 5.
**Chưa gửi request thứ 14 khi chưa có câu trả lời.** Không dùng model/key khác.

## Validation và bước tiếp

- Scoped OCR **63 pass** trước test retry cuối. Full offline Qt offscreen
  **1.680 pass / 5 skip / 51 deselected**, 172,56 s, exit 0. Bốn skip TTS cần
  key/service, một QtMultimedia offscreen; không chứng minh online/GUI native.
- Sau đó thêm test retry và type annotation PIL/đưa runtime vào isolation check;
  chạy lại OCR/CLI và quality gate cuối, số cuối ở `status.md`.
  Kết quả cuối **213 passed (64 OCR +149 CLI)**, 20,12 s; Ruff app/tests/ba script
  pass, Pyright app 0/0, translations in sync.
- Gate native full suite crash teardown từ lượt trước còn mở, không biến thành
  pass chỉ vì offscreen pass. Không build EXE/GUI mới trong lượt này.
- Chưa có locator/runtime install/model manager OCR, document/identity/review CLI,
  adapter/editor metadata, cache disk, GUI/frozen. Bridge source mới chưa được
  cài/bundle vào runtime portable cũ, nên không lấy source pass làm frozen pass.
- Bước tiếp: giữ chữ/timing review, thiết kế OCR-3 typed document/source identity
  và resume/export có kiểm provenance; không tự gán speaker/xưng hô hoặc xuất
  SRT thiếu như success. Gate chất lượng cần giải quyết lỗi chung của ba ảnh.

Thay đổi của lượt này: thêm `core/ocr/runtime.py`, `scripts/ocr_stream_worker.py`,
`scripts/ocr_stream_pilot.py`, `tests/test_ocr/test_runtime.py` và biên bản này;
sửa decoder/tracking, script vision và các test tương ứng/isolation, status/plan/
prompt. Giữ các file OCR-2 chưa commit của lượt trước; không có media/raw/key/model
trong tập file để Git theo dõi.

Sau nghiệm thu, user yêu cầu submit/push snapshot và prompt phiên sau. Code/domain/
supervisor/harness/test đã chốt ở **`ed1c3a6`**; tài liệu đi theo. Không chạy lại
model/API/build/test chỉ để chốt Git. Prompt mới thay các snapshot chồng nhau,
giữ yêu cầu crop 5 cần budget bổ sung chưa được duyệt; quyền push chỉ cho snapshot này.
