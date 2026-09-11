# OCR-4: nghiệm thu flow GUI trên EXE hiện có — 2026-09-10

Tiếp tục tại `VideoCaptioner-ASR-S3`, nhánh `codex/asr-s3-native`, HEAD
`a528d85` sạch và khớp tracking origin đã lưu (ahead/behind 0/0; không fetch).
Không đổi code/resource/model/dependency, build lại hoặc commit/push. Dùng đúng
EXE `VideoCaptioner-OCR4-20260910`, SHA-256
`865c07a6104168bd6f7758abc04c70c0d45747a701aa779415bcf1d44664e7ff`.

**Flow chức năng GUI đã đi qua; nghiệm thu hiển thị còn mở.** Kết quả này bổ sung
cho [gate source/frozen CLI trước đó](ocr-gui-2026-09.md), không thay bằng chứng
chất lượng video riêng, benchmark hoặc lỗi native full-suite teardown cũ.

## Flow đo bằng chính GUI EXE

Computer Use thao tác đúng process test; file/code/đối chiếu dùng shell/Python.
Khởi động từ scratch làm working directory, dùng settings smoke đã có, không
credential, tắt update/VieNeu auto-update. Runtime OCR để trống nhằm kiểm tự tìm
`models/ocr/` trong gói. Kiểm model/profile SHA thành công trước khi nạp engine.

Fixture ngắn cũ được dùng nguyên file: 13 frame VFR, origin 3 s, time base
1/10240, không audio, ba lần hiện chữ hai dòng. Chọn đoạn 0–1900 ms, preview tại
100 ms và ROI số 0/0/1/1. Gate kéo ROI bằng chuột đo riêng trên fixture hủy.

| Gate | Kết quả mới |
| --- | --- |
| CPU từ GUI EXE | **3/3 câu exact**, timing 100–600, 700–1200, 1300–1800 ms |
| Model/cache | 13 frame, 3 track, 6 candidates, **2 fresh /4 cache**; 2 request/2 response, 2 detector/4 recognizer/0 classifier attempts |
| Thời gian scan ngắn | Job **1,859 s**, inference **0,181 s**; không cộng stage overlap, không benchmark |
| Review guard | Sáu issue còn mở sau scan; export/handoff bị khóa. Không tự nhận đồng thuận là accepted |
| Crop/review | Verify nguồn/PTS/SHA; đã quan sát crop đúng cho cả ba cue. Chọn nguyên candidate cùng ghi chú đối chiếu đáp án fixture; không sửa/ghép chữ |
| Undo/redo | Câu 1 quay lại chưa duyệt rồi khôi phục đã duyệt; số issue 4 → 6 → 4, export vẫn khóa khi còn cue chưa duyệt |
| Lưu/mở review | Giữ riêng pending và reviewed; mở lại reviewed từ GUI verify nguồn tại máy, không inference lại |
| Export/handoff | JSON phụ đề đã duyệt → bảng phụ đề/dịch với đủ ba cue; không tự chạy dịch/TTS/split/optimize |
| Bảng phụ đề | Xuất SRT đúng ba cue; hai dòng nguồn vẫn nằm trong cùng cue |
| Video Editor | Handoff từ bảng, giữ visual source/raw/candidate IDs; normal save tạo JSON + SRT, không ASS; GUI mở lại project thành công |
| Đối chiếu file | Cues/config/source của scan mới khớp frozen CLI cũ; review/export/handoff/editor giữ metadata, không tạo ASR metadata hoặc speaker |

Không dùng lựa chọn duyệt fixture có đáp án biết trước làm policy auto-accept
cho dữ liệu thật. Không có bản Việt dự thảo hoặc AI đọc ảnh trong review GUI.

## Hủy, đóng và bảo toàn

- Fixture hủy tạo bằng stream-copy lặp fixture tổng hợp cũ, không media riêng:
  200 lần /13.420.693 byte. Quét đoạn 380 s, kéo ROI bằng chuột; bấm **Hủy tác vụ**
  khi đang chạy. Bản lưu giữ **complete=false**, 2.554 frame /589 track /
  1.178 candidates, 2 fresh /1.176 cache; 2 request/2 response, 2 detector/
  4 recognizer/0 classifier. Job 8,062 s, inference 0,192 s. Export/handoff
  vẫn khóa, process con đã hết. Đây là gate hủy, không phép đo chất lượng/tốc độ
  video dài hoặc một lượt scan đầy đủ.
- Lần thử đóng đầu tiên trên fixture đó đã đến sau khi scan xong (GUI có 600 cue).
  Giữ lần thử trong accounting; không tính là pass cho đóng khi bận và không có
  receipt metrics của scan này.
- Gate đóng tiếp theo dùng bản stream-copy 2.000 lần /134.200.473 byte. Trước khi
  đóng, GUI đang báo progress và process watcher thấy OCR Python + FFmpeg sống.
  Lượt click/return/capture mất **303 ms**; watcher thấy hết child sau **1.550 ms**
  từ mốc bắt đầu lệnh click, lấy mẫu khoảng 50 ms. Đây gồm chi phí tool/OS,
  không phải phép đo riêng thời gian `closeEvent`. Main window còn phản hồi;
  kết quả muộn không mở lại dialog. Metrics inference của lượt đóng này không
  được persist, không suy số request từ fixture lặp.
- Đóng main window của đúng process test: **exit 0**, không traceback stderr,
  không child sót; tổng thời gian process sống 1.225,469 s gồm thao tác người/agent.
  Không dùng thời gian này làm latency OCR. Settings của artifact, ASR-S3 và
  checkout master cùng fixture gốc giữ nguyên SHA. **13/13 crop gốc** khớp manifest.

Accounting: hai scan có receipt tổng **4 request/4 response, 4 detector/
8 recognizer/0 classifier**; thêm **hai scan không có metrics persist** như trên.
Tổng CPU cả phiên để **null**, không gọi là bốn request hoặc ghi lượt thiếu bằng 0.
**0 vision request**, không đọc key, không tăng cap vision 13 hay retry crop 5.

## Điểm còn mở sau phép đo

1. Crop đôi lúc thành vùng đen trong ảnh Computer Use dù UI báo hash khớp.
   Kéo splitter hoặc thao tác làm vẽ lại thì chữ hiện đúng; có ảnh trước/sau.
   Đối chiếu source helper với cùng FFmpeg của gói cho PNG crop bằng PNG preview
   tại cùng frame, chứa pixel 0–255. Chưa tách được lỗi repaint của app khỏi lỗi
   capture/activation của Computer Use; không sửa painter theo phỏng đoán hoặc
   gọi visual gate đã sạch. Câu 2/3 đã thấy crop đúng trực tiếp sau load.
2. Scan hoàn tất nhưng thanh progress còn **94%**; status đã báo ba cue cần
   review, nút hủy tắt. `_start.finished` đổi range về 0–100 nhưng chưa đặt giá trị
   hoàn tất. Không nhầm “scan hoàn tất” với “các cue đã duyệt”.
3. Combo candidate một dòng hiển thị raw có newline nên bị cắt. Text đầy đủ vẫn
   có trong vùng raw/hiện tại; cần cải thiện nhãn chọn ảnh mà giữ nguyên raw.

Tự tìm **runtime OCR** và chạy từ working directory khác đã pass. Chưa di chuyển
toàn bộ onedir sang ổ khác. FFmpeg của scan được quan sát trong
`models/tools/Faster-Whisper-XXL/`; FFprobe được cấp qua PATH từ bộ cài dev,
không có ở thư mục tool đó. Chưa chứng minh gói tự đủ media tools trên máy sạch.
Không chép/stage lại 48 GB, tải model, thay inventory hoặc đụng artifact ổ C cũ.

Đã đọc lại evidence câu 4: ba crop đồng thuận vẫn bỏ chữ “tháng”; crop sát hộp
detector lấy lại chữ nhưng sai dấu, bản 2× lại mất chữ. Giữ giới hạn chất lượng,
raw và profile chưa hiệu chuẩn; không chốt engine hoặc tự bật biến thể từ fixture.

## Evidence và phạm vi validation

Scratch mới: `build/ocr-pilot-20260910/ocr4-exe-flow-10/`:

- `acceptance-receipt.json`, `verify_results.py`: đối chiếu outputs, source/IDs/
  raw/timing/metadata, SHA 13 crop và lifecycle receipts; **pass** sau sửa tên
  thuộc tính sai trong harness (`speaker_id` → `speaker`). Không đổi code app.
- `pending.ocr.json`, `reviewed.ocr.json`, `captions.ocr.json`, `handoff.json`,
  `handoff.srt`, `fixture.vceditor.json`, `fixture.srt`, `cancelled.ocr.json`.
- Ảnh các bước `01`–`15`, `diagnostic-crop.png`, `process.json`,
  `preservation-before.json`, `children.json`, `close-process-events.json`,
  `close-ui-times.json`, stdout/stderr và hai monitor scripts.

Một lệnh diagnostic ban đầu trỏ nhầm FFprobe không tồn tại trong gói và đã dừng;
đối chiếu PNG sau đó dùng FFprobe thật trên máy. Harness kiểm file có warning
pydub không tìm FFmpeg trên PATH riêng; harness không gọi media/model và các
assert đối chiếu file đều pass. GUI dùng PATH riêng đã chuẩn bị như mô tả trên.

Không chạy lại Ruff/Pyright/pytest/translations/build vì chỉ thay tài liệu và
thêm evidence scratch; giữ nguyên gate offline trước **1.735 pass/5 skip/
51 deselected** như lịch sử, không trình bày là lượt mới. Pip-installed,
packaged Python riêng, ASR/TTS/translation online, video riêng/chất lượng native,
native full-suite teardown `0xC0000005` và di chuyển toàn gói vẫn chưa nghiệm thu.
