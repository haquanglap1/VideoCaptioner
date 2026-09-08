# Prompt phiên tiếp theo — OCR local và AI đọc ảnh cho phụ đề Việt

Tiếp tục ở checkout **VideoCaptioner-ASR-S3** user chỉ định, nhánh **codex/asr-s3-native**.
Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`,
[kế hoạch OCR](../plans/video-subtitle-ocr-integration-plan.md) và phần mới nhất của
`docs/dev/asr-implementation-2026-09.md`. Chạy `git status --short --branch` trước sửa.
Không phục hồi các gate đã pass từ prompt ASR cũ.

## 1. Mục tiêu và trạng thái thật

- Mục tiêu của user: **video tiếng Trung → phụ đề tiếng Việt**. User không biết tiếng
  Trung; agent tự kiểm tra kỹ thuật và đối chiếu chữ nguồn, không hỏi xác nhận từng nút.
- User thấy cách agent đọc ảnh cho kết quả tốt và muốn cân nhắc công sức/token so với
  engine OCR. Giữ **hai hướng OCR local và AI đọc ảnh** trong thiết kế; chưa chọn engine
  mặc định và chưa có phép đo chứng minh AI hay OCR local chính xác/rẻ hơn bao nhiêu.
- **Kế hoạch ASR đã viết, sản phẩm ASR chưa nghiệm thu xong.** S1–S5/S5.2 và Lifetime
  đã có code, một số workflow đã pass; clip thực tế 60 s vẫn fail alignment và có chữ
  nhận dạng sai. Scribe, phồn thể, nhiều speaker/xưng hô và giới hạn SIP còn mở. **Chưa S6.**
- OCR mới hoàn thành **OCR-0: thống kê và kế hoạch**. Chưa có engine OCR local, model
  vision API, CLI OCR hoặc GUI OCR được triển khai. Bản Việt 13 câu vừa làm là bản agent
  biên tập từ chữ có sẵn trong video, không phải ASR tự động thành công.
- User đã chấp nhận mẫu Việt public cũ 4,204 s / 1 cue. Nhận xét đọc ảnh tốt trên clip
  mới không được nâng thành nghiệm thu toàn bộ bản dịch/timing/speaker hoặc cả video.

## 2. Git, runtime và artifact

- Baseline trước lần chốt tài liệu này: **fb2bfad63ee42fcb0c5530b7e37e3d34d92930e8**.
  Manifest gồm **status.md**, **docs/dev/asr-implementation-2026-09.md**,
  **docs/dev/asr-vietnamese-next-session-prompt.md**,
  **docs/plans/video-subtitle-ocr-integration-plan.md** và **prompt này**.
  Lấy HEAD thật từ Git hoặc HEAD user bàn giao, không checkout về baseline cũ.
- Code Lifetime **e6c0074250df41b5da4b7eaa71b2e9f21e4adcab**, S5.2 **073510d** là
  ancestor. Các lượt cleanup/clip/OCR-0 không đổi code/tests/spec/dependency/model/policy.
- Artifact chính: `dist/VideoCaptioner-ASR-S52-Lifetime-20260907/`, EXE cùng basename,
  **31.161.900 byte**, SHA-256
  **b2dfe8692266fd08dc2471f54838385b975c6ebfe0839d8aa1d5436b38a75f78**.
  Final cũ `dist/VideoCaptioner-ASR-S52-Review-20260907-Final/` giữ SHA-256
  **457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649**.
- Runtime giữ tại `build/S5-Qwen-Runtime-20260907-R2/` và
  `build/S51-Community1-Runtime-20260907/`; không move/copy venv hoặc tải lại model đó.
- Python **3.12.13** có sẵn trong `.venv` của checkout VideoCaptioner bên cạnh;
  ASR-S3 không có venv riêng. Xác minh import đúng checkout và cô lập config trước import
  app. Không dùng Python trên PATH chưa kiểm tra, cài global hoặc nâng dependency Qt.
- Lần này user đã yêu cầu **commit/push tài liệu**. Quyền đó chốt manifest trên, không
  tự cho phép commit/push/tag/release thay đổi phiên sau. Lưu prompt không khởi chạy task,
  automation, pilot, tải model hoặc job có phí.

## 3. Evidence đã gom, không tạo lại rác

Root chung: **`build/asr-session-evidence/` trong checkout ASR-S3**. Bảy thư mục VC-*
cũ đã move vào đó; `relocation-20260908.json` giữ mapping và 2.710 hash/size/mtime.
Path cũ trong helper/report là lịch sử. Không chạy lại helper create-only vào output đã có.
Chín bản sao app và cache/build cũ đã vào Thùng rác; artifact gốc vẫn giữ. Đừng empty
toàn bộ Thùng rác hoặc suy dữ liệu đã được xóa vĩnh viễn.

Job gần nhất **`VC-UserClip-20260908-114035/`** dưới root trên:

- `README.md`: kết quả và giới hạn của lượt clip.
- `reports/source-preflight.json`: resolve đúng file gốc user đã chọn, hash/mtime;
  không hỏi lại path hoặc quét thư mục media. Video dài **111,333 s**, đã thử **60 s đầu**.
- `inputs/sample-zh.mp4`, `inputs/sample-zh.wav`: mẫu riêng, **960.000 PCM sample**.
- `outputs/sample-zh.review.json`, `reports/asr-diagnosis.json`: raw ASR lỗi.
- `inputs/source-caption-refined.png`: ảnh tổng hợp **13 dòng**, có header thời gian.
- `reports/source-caption-visibility-refined.json`: 13 khoảng hiển thị + representative_ms.
- `inputs/reference-zh.srt`, `reports/reference-provenance.json`: agent đọc chữ và biên tập;
  là tham chiếu có ảnh đối chiếu, không mặc nhiên là ground truth đã được người bản ngữ chấm.
- `outputs/reference-vi-edited.srt`, `outputs/reference-vi-preview.mp4`: bản Việt xem thử.
  `reference-vi-google.json` và `reference-vi-google-target.srt` là bản Google riêng.
- `reports/ocr-method-statistics-20260908.json`: thống kê từ evidence, không inference mới.
- `reports/final-verification.json`, `reports/job-cleanup.json`: nguồn/review/bundle giữ
  hash, lease giải phóng; EXE + `_internal` bản chạy tạm đã được dọn vào Thùng rác.

**Chưa có thư mục chứa 13 crop độc lập ở độ phân giải gốc.** Chỉ có contact sheet và
video mẫu. Khi chuẩn bị pilot, lấy đúng 13 representative_ms, crop vùng chữ gốc từ
sample đã có và lưu một bộ input dùng chung. Không OCR cả contact sheet kèm header
rồi coi đó là phép so sánh crop công bằng; không cần quét lại toàn video để chọn câu.

## 4. Những gì đã đo và chưa đo

| Mục | Bằng chứng |
| --- | --- |
| ASR clip thực tế | Một job Lifetime/Qwen 0.6B, **exit 5 / 46,375 s**, 94 token; raw lexical khớp text nhận dạng, nhưng có chữ sai so với hình |
| Timing lỗi | **6 token: 32, 35, 49, 73, 76, 94**; hai zero-duration, hai interval đảo, ba overlap có một token thuộc hai loại |
| Review | Identity khớp, 0 override, pending true; **chưa chạy tới Community-1**, không ASR JSON/SRT thành công |
| Quét chữ prototype | ROI **1920×80 tại y=960**, grayscale **960×40**, 25 mẫu/s; khoảng 1.500 mẫu danh nghĩa, gom 13 cue / 94 ký tự |
| Giới hạn phép đo | 40 ms là lưới mẫu, chưa phải sai số timing; chưa lưu PTS/count frame thực. Lệnh quét cuối ~2,664 s **chưa gồm engine đọc chữ** |
| OCR recognition | **0 lượt engine local**; agent đọc ảnh. Chưa có token agent theo bước, peak RSS hoặc phép so sánh với model vision API |
| Bản Việt đối chiếu | Google 13 câu exit 0 / 15,047 s nhưng sai thuật ngữ; agent biên tập riêng. Target-only export 0,312 s, app ASS synthesis 8,141 s; ffprobe/frame pass |

Prototype đang giữ raw frames và bản Pillow của toàn clip trong RAM; payload suy tính
~54,9 MiB mỗi bản trên mẫu này, chưa phải RSS. Bản tích hợp phải streaming có buffer giới
hạn. Gom 1.500 mẫu còn 13 ảnh không chứng minh giảm 99,13% token hoặc nhanh hơn OCR bao nhiêu.

## 5. Phạm vi tiếp theo: pilot so sánh trước khi làm toàn bộ GUI

Khi user giao thực hiện pilot/OCR-1 ở phiên mới, triển khai theo thứ tự:

1. Đọc/kiểm tra evidence, chuẩn bị **13 crop cùng nội dung và kích thước** trong một
   thư mục pilot duy nhất dưới root evidence. Giữ mapping cue/PTS/hash; không copy EXE
   chỉ để thử recognizer crop và không tạo thư mục VC-* cạnh checkout.
2. **Nhánh local:** ứng viên RapidOCR + ONNX Runtime CPU, model giản/phồn thể được
   chọn tường minh. Chốt package/model/dictionary/lock/hash và runtime riêng khi được
   giao triển khai/cài runtime; không đổi venv Qt, ASR pins hoặc dùng model mặc định
   ngầm của RapidOCR. Tải/nạp là gate riêng, không tự gọi inference là đã pass chỉ vì import được.
3. **Nhánh AI đọc ảnh:** user chưa chọn model nhận ảnh, endpoint hoặc ngân sách API.
   Chuẩn bị cùng input/prompt/metric độc lập trước. Chỉ gọi job có phí sau khi user chọn
   model/endpoint/phạm vi và nhập credential kín; không tìm key trong chat/env/AppData/log.
   Không lấy STT key làm vision key. Nếu dùng model vision local phải xác định rõ model,
   license/runtime, không tự tải bộ model lớn. Nhánh chưa có dịch vụ ghi **chưa đo**;
   vẫn làm phần chuẩn bị/local đã được giao, không lặp các gate cũ để lấp chỗ trống.
4. So sánh **đọc chữ trước**, chưa trộn dịch/biên tập vào điểm OCR: cùng crop, giữ
   script/tên/số, trả raw text và chỗ không chắc. Không gửi text đáp án hoặc bản dịch
   tham chiếu cho recognizer/model vision. Bản agent đã đọc trong phiên cũ là reference
   review, không phải lượt AI API mù độc lập hoặc số usage có thể dùng làm benchmark.
5. Ghi số dòng đúng/sai/bỏ sót, khác biệt ký tự và câu cần review; tách load/inference/
   total time, số detector/crop calls, RSS host/worker, disk, cache và token provider
   thực trả. Nếu thiếu usage để null, không đoán giá hoặc lấy usage chung tài khoản
   làm usage job. Cache và số ảnh/độ phân giải/prompt phải được ghi để so sánh có nghĩa.
6. Báo kết quả tiếng Việt, chỉ minh họa câu nguồn khi cần kỹ thuật. Agent đối chiếu ảnh;
   không giao user không biết tiếng Trung chấm từng ký tự. Chưa có số đo thì chưa chọn
   mặc định. Giữ quyền chọn OCR local và AI đọc ảnh; không mặc định loại AI chỉ vì tốn token.
7. Chốt lại bước OCR-2→OCR-4 theo kết quả: streaming PTS/ROI, contract/CLI/review rồi GUI/
   binary. Pilot này giới hạn 13 câu, **không phải corpus/benchmark sản phẩm S6** hoặc
   quyền làm toàn bộ GUI, xóa chữ gốc hay xử lý phần video còn lại.

Không cài/tải hoặc gọi API trong một phiên chỉ được giao đọc/cập nhật kế hoạch. Không
coi việc user khen agent đọc ảnh là đã chọn model API, cấp key hoặc chấp nhận chi phí.

## 6. Contract và gate giữ nguyên

- Timing OCR là thời gian chữ xuất hiện trên hình, không âm thanh. Không chạy ForcedAligner
  để hợp thức hóa OCR hoặc sửa/clamp/drop token raw của job ASR đã fail. Không retry cùng
  ASR, phồn thể token 7 hay Whisper chỉ vì nợ 429 cũ.
- Nguồn OCR cần visual/file identity riêng; audio identity không chứng minh cùng chữ trong
  video. OCR metadata optional phải giữ qua ASRData/JSON/translation/editor; không giả
  `ASRMetadata(timing="native"/"aligned")`, không tự suy speaker hoặc xưng hô.
- ROI/PTS phải đúng rotation/SAR/VFR/selection offset; dòng ngắn/bị che/biên mơ hồ giữ
  review, không xuất rỗng/partial như success. Tất cả edit qua CommandStack, normal save
  JSON+SRT; không thêm PySide6/MPV, không nạp OCR/GPU libraries trong Qt process.
- Full offline/static/build/GUI/playback/cancel của Lifetime giữ evidence kế thừa đúng
  snapshot. Không rerun vì chỉ sửa tài liệu hoặc pilot crop. Khi thực sự sửa metadata/
  runtime/lifetime phải chạy regression và các gate theo AGENTS; build tên/output mới
  bằng spec duy nhất, báo đủ bốn gate artifact. Source pass không thay EXE acceptance.
- Giữ media, AppData, runtime, artifact và logs gốc; chỉ metadata không nhạy cảm vào Git.
  Dọn đúng temp/copy do job tạo sau khi kiểm tra, không blanket-delete hoặc empty Recycle Bin.
  Bàn giao rõ file đã sửa, số đo mới/kế thừa/chưa đo và điều kiện còn thiếu. **Chưa S6;
  không tự commit/push thay đổi mới.**
