# Rà sai khác v6 medium và tiêu chí giảm review — 2026-09-12

ASR-S3, nhánh `codex/asr-s3-native`, HEAD/tracking **8b6bb8c**. Tiếp tục
[mục ưu tiên](ocr-next-session-prompt.md) sau cache/resume. Chỉ đọc evidence
đã có; không chạy OCR, decode, API/vision, sweep, build hoặc native smoke mới.
Giữ các sửa đổi prompt/status có trước; chưa commit/push công việc mới.

## Kết luận và quyết định

**Chưa sửa code ứng dụng.** Trong bốn ca medium khác tham chiếu, hai ca có
bằng chứng thiếu số chấm nhìn thấy; hai ca còn bất định về biểu diễn Unicode.
Không thấy lỗi cục bộ ở tầng app làm mất/thêm dấu để sửa. Chưa có căn cứ giảm
review tự động hoặc hiệu chuẩn score. Lượt này khoanh vùng lỗi và chuẩn bị
việc phân xử; **chưa đo được cải thiện nhận dạng hoặc giảm thao tác review**.

Giữ kết quả lịch sử **19/23 exact, 23/23 khớp chữ-số** so với tham chiếu agent
chưa được người đọc độc lập xác nhận. Không gọi 19 ca khớp là 19 nhãn chuẩn.
Bốn sai khác raw có tổng khoảng cách chỉnh sửa **16 codepoint/174 codepoint
tham chiếu**, không phải tỷ lệ lỗi sản phẩm. Phép đo bỏ dấu câu không thấy
khác chữ/số; nó không chứng minh video không còn lỗi tên, chữ hoặc nội dung.

## Bốn ca cần phân xử

ID phải đi kèm tên lượt và SHA crop; `crop-01` lặp giữa các tập. Bảng chỉ ghi
phần dấu khác biệt, không đưa transcript riêng tư vào Git. PTS nguyên lấy từ
manifest cũ; cả hai nguồn có time base 1/16000 theo evidence chuẩn bị cũ.

| Lượt / crop | PTS | Dấu trong tham chiếu → raw | Bằng chứng và phân loại |
| --- | ---: | --- | --- |
| `v6-medium/crop-04` | 348267 | U+2026 ×2 → U+002E ×5 | Crop có 6 chấm sáng rời, đều trong bbox. Ảnh dòng/tensor đã lưu vẫn có dấu; greedy collapse top-1 đã lưu khớp raw 5 chấm. Thiếu số chấm ở kết quả nhận dạng, không phải chỉ khác codepoint. |
| `v6-medium/crop-10` | 709333 | U+2026 ×2 → U+002E ×4 | Crop có 6 chấm sáng rời, đều trong bbox. Thiếu số chấm ở raw; không có tensor/top-5 ca này để tách chính xác ảnh hưởng rectification/recognizer. |
| `v6-medium-holdout/crop-01` | 1058667 | U+2026 ×2 → U+002E ×6 | Crop có 6 chấm, bbox bao đủ. Khác cách mã hóa chuỗi dấu; chưa xác nhận codepoint của nguồn. Không kết luận mất/thêm dấu nhìn thấy. |
| `v6-medium-holdout/crop-08` | 1423467 | U+FF01 → U+0021 | Cùng hình dấu chấm than; raster không xác định duy nhất fullwidth/ASCII. Chưa có text nguồn xác thực để quyết định bên nào đúng. |

Chẩn đoán pixel dùng **một** ngưỡng cố định `min(R,G,B)>185`, thành phần liên
thông 8 hướng trong vùng dấu đã xem; không thử nhiều ngưỡng để chọn kết quả.
Ba vùng lần lượt x=1052..1113, 1023..1082, 991..1052, y=28..39 của crop gốc.
Mỗi vùng có 6 thành phần, 24–26 pixel/thành phần, nằm trong bbox detector.
Đây là kiểm hình học trên nền đen, không phải bộ đọc dấu tổng quát hay nhãn
Unicode. Không suy rằng bbox bao đủ sẽ bảo đảm mọi tensor nhận dạng đều đúng.

Score bốn ca lần lượt **0,90436; 0,91706; 0,93162; 0,78858**. Không suy ngưỡng
đúng/sai từ chúng. NFC không làm ca nào khớp; NFKC làm hai ca biểu diễn khớp,
nhưng vẫn không sửa hai ca thiếu chấm. NFKC ở đây chỉ là chẩn đoán: không sửa
raw/reference hoặc tính lại `exact` thành 21/23, không dùng làm consensus.

Dictionary medium đã lưu có cả `.`, `…`, `!`, `！`. Medium còn trả U+2026 ×2
đúng theo tham chiếu ở `v6-medium-holdout/crop-07` và `medium-final/crop-02`.
Vì thế không có căn cứ quy lỗi cho dictionary thiếu ký tự hoặc đổi mọi chuỗi
dấu chấm thành ellipsis. Quy tắc như vậy có thể sửa sai số thập phân/dấu chấm
thực và tạo chuỗi engine chưa từng đọc.

## Đã truy nguyên đến đâu

- Worker trong `resources/ocr/ocr_stream_worker.py` giữ nguyên `result.txts`,
  ghép score/bbox và trả từng dòng. `core/ocr/runtime.py` dựng `ReadLine` từ
  text đó; `EngineRead.text` chỉ nối dòng bằng newline.
- `choose_read()` chọn nguyên một candidate, so exact codepoint/newline.
  `OcrCue` kiểm `raw_text` khớp candidate; quyết định người dùng tách khỏi raw.
  Không có phép chuẩn hóa dấu/ghép ký tự tại các điểm đã rà.
- Raw isolated medium đã có 5/4 chấm trước app. Trace top-1 ca 04 khớp raw,
  giúp loại giả thuyết review hoặc scorer xóa dấu ở ca này. Chưa chứng minh
  lỗi implementation CTC, weights hoặc tương đương với decoder Paddle native.
- Chưa có ca với nhãn xác định chứng minh lỗi app để viết bản vá. Không đổi
  crop/preprocessing/decoder/profile, schema, ID, cache hoặc review guards.

`uncalibrated_profile` vẫn áp dụng mọi cue của policy hiện tại. Bốn sai khác
giữa model và **tham chiếu** không phải số cue có `engine_disagreement` giữa
các frame. Tập đo có một crop/cue, không đủ đo gánh nặng review toàn pipeline;
không diễn giải thành chỉ cần review 4/23 hoặc 2/23 cue.

## Phương án kiểm tiếp, chưa thực thi

**Phân xử bốn ca hiện có.** Gói local có crop gốc, raw, tham chiếu, vị trí và
codepoint khác nhau, PTS/SHA và trường phân xử để trống. Người đọc độc lập
hoặc text nguồn xác thực cần ghi riêng: quan sát hình dấu, nội dung đọc được,
độ chắc chắn và căn cứ codepoint. Đọc chữ từ ảnh không tự xác nhận Unicode.
Nếu không có text nguồn, giữ hai ca biểu diễn là chưa xác định. Không sửa
tham chiếu cũ sau khi xem output, không bắt user duyệt từng câu tiếng Trung
để coi sản phẩm hoàn tất. Chưa liên hệ/gửi dữ liệu cho ai.

**Fixture có nhãn tác giả biết trước.** Sáu fixture tổng hợp cũ đạt 6/6 exact
trên 63 ký tự theo output đã lưu, nhưng không chứa ellipsis, chuỗi dấu chấm
hoặc dấu chấm than. Chúng chưa kiểm hai vấn đề vừa tìm. Đề xuất đúng **16**
fixture dưới đây, chưa tạo ảnh hoặc chạy model:

| ID | Text nguồn cố định | Mục đích |
| --- | --- | --- |
| P01–P04 | `学生....`, `学生.....`, `学生......`, `学生……` | Tách số chấm 4/5/6 với U+2026 ×2; không tự bù thành 6. |
| P05–P06 | `......学生`, `……学生` | Dấu đầu dòng, kiểm nguy cơ detector bỏ dấu. |
| P07–P08 | `学......生`, `学……生` | Dấu giữa chữ; không áp quy tắc sửa đuôi chung. |
| P09–P12 | `学生!`, `学生！`, `学生?`, `学生？` | ASCII/fullwidth; ghi rõ codepoint tác giả trước render. |
| P13–P14 | `学生3.14`, `学生314` | Số thập phân và cặp chỉ khác một dấu; không dùng chữ-số exact để bỏ lỗi. |
| P15 | `学生三人。` + newline + `学生五人。` | Giữ hai dòng, chữ đổi và dấu riêng từng dòng. |
| P16 | Chuỗi rỗng | Kiểm hallucination; không bù dấu/chữ vào ảnh rỗng. |

Khi được giao phép đo tiếp: đóng băng JSON nhãn UTF-8/codepoints, font/SHA,
renderer/tham số và SHA ảnh **trước inference**. Dùng font và cách render của
fixture cũ nếu còn được xác minh, không tải font/model hoặc thêm dependency.
Một cấu hình medium hiện có, một lượt mỗi ảnh, không retry/warmup/biến thể
hình học để chọn kết quả. Dự kiến 16 detector calls; đặt trần 32 recognizer
calls, 0 classifier, 0 network, ghi mọi begin/end và dừng nếu vượt trần.
Lưu bbox, ảnh dòng, tensor/top-5 ngay lượt đó để khỏi chạy lại chỉ lấy trace.
Đây là **đề xuất**, không là quyền chạy mới hoặc corpus độc lập đã có.

Tiêu chí đánh giá trước khi sửa:

1. So raw exact từng codepoint, vị trí/số dấu, chữ/số và newline riêng; ảnh
   rỗng không được sinh chữ. Không chuẩn hóa để biến sai thành pass. Nếu hai
   codepoint render không phân biệt được, ghi hạn chế biểu diễn riêng; không
   tuyên bố model đọc được codepoint gốc chỉ từ raster đó.
2. Nếu lỗi nằm trong code app/bridge, cần một regression tổng hợp tái hiện
   **fail trước/pass sau** tại đúng tầng. Nếu pixel/tensor đã đủ nhưng engine
   sai, giữ lỗi ở lớp nhận dạng; chưa thay hậu xử lý bằng đoán chữ/dấu.
3. Mọi bản vá sau đó phải giữ byte raw, candidate/source/PTS/ID, selection
   review, save/load và khóa export khi pending. Test gần nằm ở
   `test_consensus.py`, `test_document.py`, `test_metadata.py` và test worker
   tương ứng nếu có sửa worker; không mở lại gate cache/resume chỉ lấy số mới.
4. Đo hỗ trợ review bằng thời gian/thao tác trên cùng ca có nhãn xác định,
   cùng độ đúng của quyết định; số cảnh báo giảm không là tiêu chí thành công.
   Hiển thị vị trí khác biệt có thể là bước UI tiếp sau khi có phép đo nhu
   cầu cụ thể; không tự duyệt hoặc gom ca chưa chắc thành accepted.

Hiệu chuẩn auto-accept còn thiếu tập nhãn độc lập đại diện nhiều nguồn và
phép đo false acceptance tách khỏi tập dùng chọn cấu hình. Một video và
fixture nền đen không đáp ứng điều đó. Phiên này không mở corpus mới.

## Kiểm tra và bảo toàn

Evidence mới ngoài Git: `build/ocr-pilot-20260910/ocr-quality-audit-28/`:
`audit.py`, `audit.json`, `preservation.json`, `review-packet.md`,
`adjudication-pending.json`, `trace-check.py`, `trace-check.json`.

- Audit offline exit0: 23 crop video + 6 crop tổng hợp, đối chiếu SHA
  PNG/raw/reference với receipt, mapping/score và RGB SHA nơi manifest có.
  Tổng hợp khớp số cũ; **53 file đã đọc giữ hash**. Trace check exit0, thêm
  dictionary đã lưu khớp SHA; union **54 file** được kiểm, không hash models49GB.
  Hậu kiểm đầu đếm trùng đường dẫn dùng `/` và `\`, dừng ở assertion trước
  khi kiểm hash; sửa phép đếm đường dẫn ở harness, giữ receipt lỗi và kiểm lại.
- 13 crop đầu có source SHA của clip 60s; 10 crop sau có SHA nguồn đầy đủ.
  Giữ hai identity, không gộp chúng vì cùng nội dung gốc hay crop ID. Không
  decode/hash video mới để lấy lại kết quả cũ.
- Chỉ xem PNG đã lưu và tính toán trên JSON/pixel tại máy. Không import app,
  mở GUI hoặc ghi AppData; không đọc Api.txt/.env/cookie. Gói OCR6, models,
  media, evidence cũ, `ffcachePuSHPB` và junction trước đó giữ nguyên.
- Không có bản vá source/test/resource: **không chạy lại** pytest, Ruff,
  Pyright, translations, build hoặc native smoke đã qua. Audit này không
  thay thế regression nếu phiên sau sửa code, không là gate online mới.

File tài liệu sửa: biên bản này (mới), `status.md`,
`docs/plans/video-subtitle-ocr-integration-plan.md` và bổ sung tiến độ vào
`docs/dev/ocr-next-session-prompt.md`; giữ nội dung chưa commit có trước.
