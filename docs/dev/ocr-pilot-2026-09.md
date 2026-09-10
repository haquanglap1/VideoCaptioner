# OCR-1: pilot local trên 13 crop — 2026-09-10

Làm tại worktree ASR-S3, nhánh `codex/asr-s3-native`. HEAD đầu phiên
`df3aeeeeb09aa587ec41e3f5a1f1d05d6ac3baef`, sạch, trùng tracking và `ls-remote`
origin. Không đổi master, commit/push, gọi ASR/dịch/TTS hoặc mở Computer Use.

**Kết quả:** local đã đọc đủ 13 crop nhưng chưa đủ để xuất tự động không review.
So với tham chiếu agent có sẵn: **10/13 câu khớp nguyên văn**, **12/13 giữ đủ chữ**.
Câu 4 thiếu một chữ và sai dấu ba chấm; câu 10 sai dấu ba chấm; câu 6 khác mã dấu
hỏi ASCII/fullwidth. Raster không chứng minh mã Unicode gốc của dấu hỏi, nên không
đồng nhất mọi sai khác codepoint với sai nghĩa. Agent đã xem cả 13 ảnh nguồn;
tham chiếu vẫn chưa được người bản ngữ xác nhận. Không sửa raw hoặc chép đáp án
tham chiếu vào kết quả engine. Diễn giải từng câu bằng tiếng Việt nằm trong
`build/ocr-pilot-20260910/report.vi.md`, không đưa transcript/media riêng vào Git.

## Input và timing

- Dùng lại sample 60 s trong evidence cũ; không tải/cắt video lại. Một scratch duy
  nhất: `build/ocr-pilot-20260910/`. Evidence ASR/Soniox/TTS cũ giữ nguyên.
- 13 PNG màu **1920×80**, ROI **[0,960,1920,80]**, tổng **126.830 byte**. Không
  header, watermark đáp án hoặc contact sheet làm input. Worker chỉ nhận crop và
  manifest, không nhận SRT/tham chiếu. Nhánh AI dùng cùng hash/input.
- Probe **1.800 frame**, time base **1/16000**, 30 fps, square pixel, start PTS=0,
  không rotation. Prototype dùng 25 mẫu/s: chọn PTS nguồn gần representative_ms
  nhất, tie chọn frame trước; kiểm tra PTS FFmpeg `showinfo` khớp 13 file PNG.
  Độ lệch lớn nhất **13,3125 ms**; mapping lưu cả PTS, time base, ms chính xác dạng
  phân số, delta, ROI và SHA-256. Không dùng `frame_index/fps` để tự dựng timing.
- Biên câu vẫn lấy từ prototype; **chưa đo lại độ đúng start/end**, không gọi
  delta trích frame là độ chính xác timing cue. Đây là thời gian chữ trên hình,
  không phải lời nói. VFR/nonzero PTS/rotation/SAR/tracking thuộc OCR-2.

## Recipe và cách ly

Pin **RapidOCR 3.9.2 + ONNX Runtime CPU 1.29.0**, Python **3.12.13**. Runtime riêng
cài bằng `uv --no-config`, lock toàn bộ **23 dependency với hash**, không sync app.
App Python được kiểm tra không có NumPy/OpenCV/ONNX Runtime; worker không import Qt.

Nguồn chính thức: [RapidOCR](https://github.com/RapidAI/RapidOCR/tree/v3.9.2),
[catalog](https://rapidai.github.io/RapidOCRDocs/main/en/model_list/),
[ONNX Runtime CPU](https://onnxruntime.ai/docs/get-started/with-python.html).
Model upstream detector/recognizer đều được gắn Apache-2.0 trên model card
[detector](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det) và
[recognizer](https://huggingface.co/PaddlePaddle/PP-OCRv5_server_rec).
NOTICE ghi cả giới hạn: link MODEL_LICENSES.md từ README RapidOCR trả 404;
không bịa biên bản conversion. Package giữ license file trong dist-info.

| Thành phần | Pin/hash SHA-256 |
| --- | --- |
| PP-OCRv5 detector Chinese mobile, 4.819.576 byte | `4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae` |
| PP-OCRv5 recognizer Chinese server, 84.577.022 byte | `e09385400eaaaef34ceff54aeb7c4f0f1fe014c27fa8b9905d4709b65746562a` |
| Dictionary trong metadata ONNX, 18.383 entry trước blank/space | `02c0a0121c577dfa211f11de21084e3abd23478a77ea4fbdf71ee7a3e990a717` |
| Classifier v4 bundled, nạp do constructor upstream; **0 inference** | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |

URL revision ModelScope `v3.9.2` và expected hash lấy từ manifest trong wheel
RapidOCR đã kiểm SHA theo PyPI; model tải xuống khớp hash. Dictionary được xuất
UTF-8 JSON compact và kiểm hash; decoder thêm blank đầu và space cuối. Wheel có
model v6 không dùng; không chạy sweep. Hai file v5 tải mới tổng **89.396.598 byte**;
weights ASR/TTS đã có không bị tải lại.

Tiền xử lý ghim trong `scripts/ocr_pilot_data/profile.json`: input BGR từ crop
màu gốc, không threshold/upscale đầu vào; black vertical padding ratio=8; detector
max-side mode, resize theo implementation 3.9.2 và bội số 32; mean/std 0,5,
thresh 0,3, box thresh 0,5, unclip 1,6, dilation; perspective crop rồi recognizer
height 48, dynamic width tối thiểu 320, batch=1, normalize [-1,1], greedy CTC.
CPU intra/inter threads **4/1**, CPU arena tắt, CUDA/DML/CANN/CoreML tắt.
Text-score filter=0 để không giấu dòng điểm thấp. Effective config đã lưu riêng.

Trong inference, chặn entry download của RapidOCR và Python socket connect/DNS;
**0 lần thử network**, provider list chỉ CPU. Đây là gate của process pilot,
không phải thử mất mạng cấp hệ điều hành hay lifecycle của app tương lai.

## Số đo trên máy thực

Máy AMD Ryzen AI 9 HX 370, 12 core/24 logical. Lượt thành công ở `local-final/`:

| Chỉ số | Kết quả |
| --- | --- |
| Crop / detector inference / recognizer inference / classifier inference | **13 / 13 / 13 / 0** |
| Fresh / cache hit / warmup tường minh | **13 / 0 / 0** |
| Lỗi engine / crop rỗng / cue bị bỏ toàn bộ | **0 / 0 / 0** |
| Exact codepoint | **10/13**, edit distance **4/103 = 3,88%** |
| Chữ và số, bỏ punctuation/whitespace để chấm riêng | **1/94 = 1,06%** lỗi; không chuyển giản/phồn thể |
| Tên riêng/thuật ngữ có trong mẫu | Hai tên riêng và thuật ngữ đã đối chiếu giữ đúng; chưa đại diện mọi tên |
| Số | Clip không có chữ số; đo riêng ở fixture tổng hợp |
| Xác minh model/input trước load | **0,056 s** |
| Import / nạp model | **0,408 / 0,435 s** |
| Vòng xử lý 13 crop, gồm I/O và ghi raw | **2,440 s** |
| Detector / recognizer stage tổng | **1,825 / 0,555 s** |
| Mỗi crop: trung vị / chậm nhất | **0,171 / 0,261 s** |
| Worker wall / toàn process kể cả khởi động và thoát | **3,342 / 3,703 s** |
| Working set lúc cuối / peak Windows working set | **242.421.760 / 490.553.344 byte** (~231,2 / 467,8 MiB) |
| Chuẩn bị input / riêng FFmpeg extraction | **9,355 / 2,386 s** |
| Cài runtime và tải hai model v5 | **17,932 s**, tách khỏi inference |
| RAM host/ffprobe/FFmpeg; VRAM | Chưa đo, `null` |
| API vision / dịch / ASR / TTS trong pilot | **0 / 0 / 0 / 0** |
| Usage token / cost provider, token agent đọc ảnh | Không có số liệu tách riêng, `null` |

Không cộng setup/preparation/inference thành một phép đo end-to-end giả. Process
OCR mới nhưng OS file cache đã ấm do debug; chưa phải benchmark cold-disk. Không
suy confidence 0,90 thành 90% xác suất đúng hoặc chốt threshold từ 13 câu.

**Lỗi harness được giữ:** `local-fresh/` và `local-startup-diagnostic/` dừng trước
inference vì serialize WindowsPath ở effective config (lượt đầu chưa giữ stderr,
lượt diagnostic đã giữ). `local-measured/` có 13 detector + 13 recognizer calls
nhưng ghi raw thất bại do duration classifier `None`; không dùng lượt đó chấm chữ.
Sửa serializer và giữ `null` rồi chạy `local-final/`. Tổng công việc thực của phiên
gồm **32 crop attempts có inference**: 13 lượt ghi lỗi, 13 thành công, 6 fixture;
**32 detector / 32 recognizer / 0 classifier**. Các lần startup lỗi không bị ghi
thành thành công và không bị giấu vào số 13 của lượt đo cuối.

## Fixture và payload portable

Sáu ảnh tổng hợp được sinh bằng NotoSansSC trong repo, font có hash: giản thể,
phồn thể, đổi một chữ, hai dòng với hai tên gần nhau và số 12/13, empty, blur nhẹ.
Chạy trên **Python của payload đã materialize**: **6/6 exact**, 0/63 edit distance;
5 crop có chữ, 1 empty đúng kỳ vọng, 6 detector và 6 recognizer calls, 0 lỗi.
Đây chỉ là font/nền được kiểm soát; không chứng minh grouping, fade/video dài.

`package_test_models.py --ocr-runtime` thêm lựa chọn stage runtime vào
`models/ocr/`, gồm `env/python.exe`, stdlib, dependencies, weights, profile,
lock, NOTICE và bridge. Không có pyvenv.cfg phụ thuộc máy dev; source venv giữ
nguyên. Payload **4.477 file / 398.907.184 byte**, copy/verify SHA, **0 download khi
package**. Chạy `-I` xác nhận Python/stdlib/NumPy/cv2/ONNX/RapidOCR đều ở payload.
Đây là thư mục mới **cùng ổ**, chưa thử khác ổ hoặc EXE. Không stage lại 48 GB
ASR/TTS cũ. Spec đã copy trọn `VC_TEST_MODELS_DIR`, không cần thêm spec/import Qt.
Chưa có app locator/model manager cho OCR; các bước đó thuộc OCR-4.

Recipe cuối thêm kiểm tra hash dictionary sau khi lần đo đầu xuất dictionary;
thay đổi này không đổi model/preprocessing/text. Profile đầu được giữ trong
`upstream/profile-first-measurement.json`; payload cuối có profile riêng đã hash
và được kiểm trong lượt fixture. Receipt installation ban đầu là lịch sử lúc cài.

## Nhánh AI và bước tiếp

Đã chuẩn bị `vision/plan.json`, prompt và manifest chung: một crop/request, 13
request dự kiến, không transcript/đáp án/context ảnh lân cận, không retry ngầm,
giữ script/tên/số/dấu câu và đánh dấu phần không đọc được. Chỉ chấm sau khi có raw.
Đã hỏi user lựa chọn endpoint/model nhận ảnh, nguồn credential đúng phạm vi và
ngân sách; **chưa có cấu hình được chốt**, vì vậy **chưa gọi API**, usage/cost null.
Không đọc Api.txt, không dùng key STT hay suy model dịch hiện tại nhận ảnh. Agent
đọc crop để kiểm tra chất lượng không phải nhánh vision API độc lập.

Đề xuất giữ PP-OCRv5 CPU làm **ứng viên**, chưa chốt mặc định/thắng-thua với AI.
Trước khi cho tự động xuất cần xử lý ca thiếu chữ rõ và dấu ba chấm: OCR-2 giữ
tối đa ba ảnh thật/cue, đối chiếu chuỗi đã đọc, giữ review khi bất đồng; không
chép thêm chữ từ đáp án hoặc ghép ký tự tùy ý. Cần đo PTS/tracking/ROI, rồi typed
document/review/CLI và cuối cùng GUI/frozen theo plan. Không triển khai toàn GUI
trong pilot hoặc coi OCR-1 so sánh local/AI đã hoàn tất.

## Gate và cách lặp lại

- **158 tests pass / 2 warnings**, gồm 5 test pilot, 4 portable hiện có và 149 CLI;
  temp/settings được cô lập. Không chạy full suite vì không đổi code app/domain.
- Ruff app/tests và ba script pilot + packager pass; Pyright app **0 errors,
  0 warnings**, translations in sync. Pyright báo đường `.venv` worktree không
  tồn tại nhưng đã dùng `--pythonpath` interpreter app hiện có; không cài/nâng tool.
- Source local OCR và isolated packaged Python có evidence thật như trên.
  **Không build EXE, smoke GUI, OCR frozen, API vision hoặc workflow dịch/TTS mới.**
- Git diff/check và status được kiểm trước bàn giao; không commit/push.

Chạy host bằng Python 3.12 app hiện có, từ đúng worktree, không `uv sync`:

```powershell
# Chỉ tạo runtime khi chưa có; dùng lại installation đã có của pilot.
python -m scripts.build_ocr_pilot_runtime --root <new-runtime> --lock scripts/ocr_pilot_data/requirements.lock
python -m scripts.ocr_pilot prepare --evidence <existing-evidence> --ffmpeg <ffmpeg> --ffprobe <ffprobe> --output <new-input-dir>
python -m scripts.ocr_pilot run --root <installed-runtime> --inputs <input-dir>/manifest.json --output <new-result-dir>
python -m scripts.ocr_pilot score --reference <evidence>/reports/reference-provenance.json --raw <result-dir>/raw.jsonl --output <comparison.json>
python -m scripts.ocr_pilot fixtures --font resource/fonts/NotoSansSC-Regular.ttf --output <new-fixture-dir>
python -m scripts.package_test_models --app-dir <new-stage> --ocr-runtime <installed-runtime>
```

Pilot extractor chỉ chấp nhận geometry/time origin đã kiểm của sample này. Đây
không phải lệnh `videocaptioner ocr` công khai và không xuất SRT đã được chấp nhận.

## File thay đổi của phiên

13 file, không có media/raw/credential trong Git:

- `status.md`
- `docs/dev/ocr-pilot-2026-09.md`
- `docs/plans/video-subtitle-ocr-integration-plan.md`
- `scripts/package_test_models.py`
- `scripts/build_ocr_pilot_runtime.py`
- `scripts/ocr_pilot.py`
- `scripts/ocr_pilot_worker.py`
- `scripts/ocr_pilot_data/NOTICE.md`
- `scripts/ocr_pilot_data/profile.json`
- `scripts/ocr_pilot_data/requirements.in`
- `scripts/ocr_pilot_data/requirements.lock`
- `scripts/ocr_pilot_data/vision-prompt.md`
- `tests/test_utils/test_ocr_pilot.py`

Sau bàn giao, user yêu cầu submit/push snapshot OCR. Code/recipe/test đã chốt ở
`0348d7e`; commit tài liệu theo sau và cập nhật thêm
`docs/dev/ocr-next-session-prompt.md` (tổng 14 file trong snapshot).
Các ghi chú không commit/push phía trên là lịch sử trước yêu cầu này. Không chạy
lại inference/test/build/API để chốt Git; kiểm tra HEAD/tracking khi tiếp tục,
không suy quyền push cho thay đổi của phiên sau.
