# OCR: chẩn đoán mất chữ và so sánh v6 — 2026-09-11

Tiếp tục trên `codex/asr-s3-native`, baseline **bdd8186**. User yêu cầu tiếp tục
sau đề xuất kiểm nguyên nhân mất chữ, so v5/v6 small/medium và kiểm thêm mẫu
độc lập trước khi tích hợp. Phiên này hoàn thành phép đo chất lượng có giới hạn;
chưa đổi profile mặc định, code ứng dụng, resource, dependency hoặc artifact.
Không gọi API/vision, đọc key, chạy ASR/TTS hoặc commit/push trong lượt đo.
Sau nghiệm thu, user yêu cầu submit snapshot tài liệu và chuẩn bị
[prompt tích hợp phiên sau](ocr-next-session-prompt.md); lấy HEAD/tracking
thực tế từ Git, không quay về baseline này.

## Kết luận để chọn bước tiếp

- **PP-OCRv6 medium** là ứng viên ưu tiên chất lượng: giữ đủ chữ/số ở **23/23**
  crop đại diện của một video, **19/23** khớp nguyên văn tham chiếu agent.
- **Detector v5 mobile + recognizer v6 small** là ứng viên ưu tiên tốc độ:
  **23/23** đủ chữ/số, **18/23** khớp nguyên văn. Đây là kết hợp có cơ sở từ
  phép đối chiếu chéo, chưa được cài vào app.
- Không chọn trọn bộ **v6 small** làm mặc định từ kết quả ban đầu: ở phần
  sau video, detector bỏ dấu ba chấm đầu câu dù recognizer trả score rất cao.
- Các sai khác còn lại của medium/hybrid nằm ở dấu câu. Một số là khác
  codepoint ASCII/fullwidth, một số là thêm/bớt dấu chấm. Không tự chuẩn hóa
  raw, ghép chữ hoặc coi tất cả các trường hợp này tương đương.

Tham chiếu video được agent đọc ảnh, chưa native-confirmed. Bộ ảnh đều từ
một video chữ trắng/nền đen, không đại diện font/nền/độ phân giải khác. Không
hiệu chuẩn score thành xác suất đúng hoặc mở auto-accept từ kết quả này.

## Nguyên nhân mất chữ ở câu 4

Một lượt v5 mới ghi lại crop detector, tensor normalized và top-5 CTC. Raw,
score **0,90359** và hộp detector khớp lượt cũ. Chữ nghĩa là "tháng" vẫn rõ
trong ảnh đã normalize đưa vào recognizer; không bị ROI cắt mất hoặc tầng
review loại bỏ sau nhận dạng. Top-1 CTC của lượt đó không có chữ này.

Nhận dạng riêng hình chữ nhật bao cùng hộp cũng thiếu chữ. Crop sát dòng chữ
đã thử trước đó đọc được chữ, được chạy thêm đúng một lần để ghi trace. Không
sửa input/prompt/tham chiếu hoặc lấy biến thể thay bảng so sánh crop gốc.

Giữ nguyên tensor và đổi riêng recognizer cho ma trận 3×3; ba ô đường chéo
dùng kết quả có sẵn, chỉ chạy **6** ô còn lại:

| Recognizer / tensor từ detector | v5 mobile | v6 small | v6 medium |
| --- | --- | --- | --- |
| v5 server | Thiếu chữ | Thiếu chữ | Đủ chữ |
| v6 small | Đủ chữ | Đủ chữ | Đủ chữ |
| v6 medium | Đủ chữ | Đủ chữ | Đủ chữ |

Đây là bằng chứng về độ nhạy của recognizer v5 với hình học/nội suy của dòng
chữ và khả năng đọc tốt hơn của v6 trên ca này. Chưa phải phân tích toàn bộ
nguyên nhân huấn luyện/weights hoặc phép đối chiếu Paddle native với ONNX.
Không tìm thấy lỗi ứng dụng xóa chữ để sửa; không đổi painter/ROI/decoder CTC.

## Bộ đo và thứ tự quyết định

1. Dùng nguyên **13 PNG gốc 1920×80**, giữ SHA; v5 lấy baseline cũ ngoài lượt
   chẩn đoán câu 4. Chạy mới v6 small và medium, mỗi cấu hình 13 detector/
   13 recognizer, không warmup/retry. Cả hai **11/13 exact, 13/13 đủ chữ/số**.
2. Lấy **8 cue đầu có start ≥60 s** từ document scan hoàn chỉnh cũ; candidate
   đầu mỗi cue, không chọn theo text. Decode đúng PTS bằng FFmpeg đã bundle,
   từng RGB SHA khớp candidate cũ. Agent viết tham chiếu trước lượt model mới;
   worker không nhận tham chiếu. Cả ba cấu hình **8/8 đủ chữ/số**; exact v5
   **7/8**, small **5/8**, medium **6/8**.
3. Small bỏ dấu ba chấm đầu cue thứ 7 của tập sau: bbox chỉ bao chữ phía sau,
   raw score **0,99941**. V5 và medium bao vùng dấu chấm và giữ được. Kết hợp
   v5 detector/v6 small recognizer được chọn để thử từ bằng chứng này và ma
   trận trên; chạy đúng 13+8 crop, giữ chữ và dấu ba chấm đầu cue đó.
4. Hai cue cuối còn lại được giữ riêng tới sau khi chọn cấu hình kết hợp.
   Medium **2/2 exact**, hybrid **1/2 exact**, cả hai **2/2 đủ chữ/số**. Tám cue
   ở bước 2 đã tham gia chọn hybrid, nên không gọi chúng là holdout độc lập
   cho hybrid. Hai cue cuối cũng chưa đủ làm benchmark sản phẩm.
5. Bộ **6 fixture tổng hợp cũ** (giản/phồn, số, đổi chữ, hai dòng, empty, blur)
   được chạy mới với medium và hybrid: mỗi cấu hình **6/6 exact**, 0 lỗi trên
   63 ký tự. Không sinh lại fixture hoặc dùng kết quả OCR làm đáp án.

| Cấu hình | 13 crop đầu: exact / đủ chữ-số | 8 crop sau: exact / đủ chữ-số | 2 crop cuối: exact / đủ chữ-số |
| --- | --- | --- | --- |
| v5 mobile det + v5 server rec | 10/13 / 12/13, baseline cũ | 7/8 / 8/8 | Không chạy mới |
| v6 small det + rec | 11/13 / 13/13 | 5/8 / 8/8 | Không chạy |
| v6 medium det + rec | 11/13 / 13/13 | 6/8 / 8/8 | 2/2 / 2/2 |
| v5 mobile det + v6 small rec | 11/13 / 13/13 | 6/8 / 8/8 | 1/2 / 2/2 |

Không so phần trăm trên hai mẫu số 21/23 như cùng tập. Chỉ số chữ/số bỏ
punctuation/whitespace để đo riêng; không có nghĩa raw đã đầy đủ mọi ký tự.

## Runtime, model và hiệu năng

Dùng nguyên Python **3.12.13**, RapidOCR **3.9.2**, ONNX Runtime CPU **1.29.0**
trong runtime OCR đã có. Không đổi host `.venv`, cài package, dùng GPU hoặc nạp
OCR nặng vào Qt. V6 small vốn nằm trong wheel, được kiểm SHA và dùng lại.
Chỉ tải hai weights medium vào scratch mới, tổng **138.749.438 byte**, SHA
khớp catalog `v3.9.2` đã có trước khi tải. Không ghi vào runtime/app cũ.

| Model | SHA-256 |
| --- | --- |
| v6 small detector | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| v6 small recognizer | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` |
| v6 medium detector | `92078b7355007ccfffcd4c8cd441a3afd4538904d06881b29a155e1e679907c2` |
| v6 medium recognizer | `eef444829dbbe18d7fea59a3f6eb75647518d2b3a9568d27c92e42940204894b` |

Dictionary lấy từ metadata weights v6: **18.708 entry** trước blank/space,
SHA JSON compact `679f4f4cbbb4f762e84fae998e02c08a556afbd115968104ca3b4aeee5cb2b19`.
Giữ preprocessing của phép đo trước, recognizer height48/dynamic width,
batch1, CPU threads4/1; chọn rõ version/model/language và đường weights.
Không dùng constructor mặc định hoặc đổi dictionary của v5.

| Cấu hình, cùng 13 crop gốc | Vòng xử lý | Trung vị/crop | Peak Windows working set |
| --- | --- | --- | --- |
| v6 small | 1,975 s | 0,146 s | 415.481.856 byte |
| v6 medium | 6,672 s | 0,504 s | 669.364.224 byte |
| v5 det + v6 small rec | 1,880 s | 0,139 s | 407.093.248 byte |

Các process chạy tuần tự. Thời gian gồm đọc crop/ghi raw và trace câu 4,
không gồm import/load; file cache đã ấm, không phải cold benchmark hoặc
latency của toàn luồng GUI/video. Không đem baseline v5 cũ làm benchmark
tốc độ cùng phiên. Peak là của worker, không gồm tổng RAM host/FFmpeg/Qt.

Nguồn model: [catalog RapidOCR](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml),
[công bố PP-OCRv6 của PaddlePaddle](https://huggingface.co/blog/PaddlePaddle/pp-ocrv6).
Số liệu trong bảng trên đo tại máy; không dùng benchmark upstream thay nghiệm thu.

## Ledger, bảo toàn và giới hạn bàn giao

Evidence mới: `build/ocr-pilot-20260910/ocr-quality-21/`, ngoài Git. Có plan
ban đầu và các quyết định mở rộng có lý do, weights/receipt, input/ref mới,
raw/tensor/top5, score, process receipts, `summary.json`, `attempt-ledger.json`
và `report.vi.md`. Giữ các kết quả xấu cùng kết quả tốt; không chạy lại để
chọn response hoặc sửa tham chiếu sau khi xem output.

- Tổng phiên **89 detector /96 recognizer /0 classifier** bắt đầu và hoàn tất;
  gồm chẩn đoán, 6 lượt chỉ-recognizer đối chiếu chéo, mọi cấu hình và fixture.
  Mỗi begin có end trong ledger, mọi worker exit0, không lỗi inference.
- **0 network attempt trong inference**, 0 retry tự động, **0 vision /0 text
  LLM API**. Download medium là bước chuẩn bị riêng; cap vision14 giữ nguyên.
- **91 đường dẫn bảo toàn** giữ SHA/trạng thái tồn tại, gồm crop/raw/ledger cũ,
  settings và artifact được theo dõi. Video đầu vào giữ SHA sau hai lượt
  decode phần sau; mỗi crop mới khớp RGB SHA/PTS của document scan đã có.
- Một lệnh in phân tích score gặp `UnicodeEncodeError` do stdout cp1252
  **sau khi đã ghi đủ ba score file**. Đọc lại bằng UTF-8; không chạy OCR hoặc
  score lại. Lỗi truy vấn PowerShell/path lúc tìm file không làm đổi app.
- Gate mới chỉ là **isolated CPU inference + crop extraction + scoring/
  receipt/preservation**. Chưa có source app pipeline, packaged Python,
  frozen CLI, native GUI hoặc live API chạy v6/hybrid. Không build lại LogsLayout,
  chạy full suite/lint/typecheck/translations hoặc hash lại payload49GB vì
  không đổi code/resource/dependency ứng dụng.

**Bước triển khai tiếp theo:** profile ứng viên medium và tùy chọn tốc độ
hybrid phải mô tả đúng version/model/dictionary từng stage; worker app hiện
ghim metadata v5, nên không chỉ thay tên weights. Cần nối profile có validation,
giữ review chưa hiệu chuẩn, kiểm pipeline/lifecycle, rồi đóng gói và nghiệm thu
EXE riêng nếu tích hợp. Chưa gọi chất lượng chung, dấu câu hoặc OCR toàn plan
hoàn tất từ các phép đo này. Không tự chọn thêm model/GPU/vision để tiếp tục sweep.
