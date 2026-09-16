# OCR-4: đối chiếu cửa sổ capture — 2026-09-10

Tiếp tục trên ASR-S3, `codex/asr-s3-native`, HEAD `a528d85`; HEAD/tracking và
remote branch qua `ls-remote` khớp. Giữ các sửa đổi progress/combo và tài liệu
đang có. Phiên này chỉ bổ sung evidence/tài liệu, không sửa code app, build,
commit/push hoặc chạy lại OCR/model/API.

## Phép kiểm mới

Để tách ảnh sai cửa sổ khỏi crop bị vẽ đen, harness native source phát lại đúng
`diagnostic-crop.png` tổng hợp đã lưu trong `ocr4-exe-flow-10/`. PNG 640×160,
SHA-256 `2251d57b1a3d49c86571c02cb92b0b3586f8492b4020a56d9c8d62ae35f8f218`.
Không decode video, verify nguồn/PTS lại hoặc gọi recognizer. Harness dùng
`OcrDialog`, `OcrWorker` và canvas hiện tại; thêm nhãn màu magenta có mã `7319`
bên ngoài canvas để đối chiếu cửa sổ. Không đổi painter.

Computer Use chọn đúng một cửa sổ theo title `VC OCR CAPTURE 12 - MAGENTA 7319`
và app Python trả về từ `list_windows`/`get_window`:

1. Capture đầu tiên trả ảnh ngoài cửa sổ OCR, không có nhãn nhận diện. Không
   thao tác theo tọa độ của ảnh đó hoặc lưu ảnh ngoài task vào scratch.
2. Refresh danh sách, chọn lại đúng cửa sổ rồi `activate_window` một lần thành
   công. Capture kế tiếp có đúng title/nhãn magenta và crop hai dòng nhìn rõ.
   Không kéo splitter, sửa kích thước canvas hoặc thay painter giữa hai capture.
3. Đóng đúng nút trong ảnh đã đối chiếu. Native source chạy Qt platform `windows`,
   tồn tại **62,250 s** kể cả thao tác tool; đây không phải latency OCR.

Đã tái hiện **capture trả sai cửa sổ trước activation** và recovery thành công
trong lượt này. Không dùng metadata cửa sổ đơn độc làm bằng chứng ảnh đúng đích.
Kết quả không chứng minh mọi lần crop đen trên EXE cũ đều có cùng nguyên nhân;
activation cũng có thể kích hoạt repaint, và không có ảnh crop đen đúng đích
trong phép thử này để phân biệt thêm. Chưa có căn cứ sửa painter.

## Gate và giới hạn

- Native source saved-PNG replay: crop hiển thị rõ sau recovery, QImage không
  null, progress 100%, sáu issue vẫn mở, export khóa. Không có quyết định duyệt
  mới; đây không phải lượt scan, source verification hoặc EXE workflow.
- Process launcher/venv và Python thực đã kết thúc; launcher ghi **exit 0**,
  supervisor còn **0 worker**. Kiểm cả hai PID sau đóng: không còn process.
- Settings master/artifact và PNG tổng hợp giữ SHA; settings ASR-S3 vẫn không
  tồn tại. Không mở video riêng, recrop hoặc chạy lại kiểm 13 crop pilot.
- **0 CPU model request, 0 vision request**; không đọc key hoặc tăng cap vision.
  Stderr chỉ có warning pydub thiếu FFmpeg trên PATH của harness. Harness này
  không gọi media tools; warning không được tính là gate FFmpeg pass/fail.
- Không chạy lại pytest/Ruff/Pyright/translations/build vì không đổi code app.
  Gate offline **1.739 pass/5 skip/51 deselected** là kết quả phiên trước.
- EXE chưa được build lại với hai fix UI. Native EXE crop đen, native teardown
  `0xC0000005`, gói khác ổ/tự đủ FFprobe và review hỗ trợ Việt vẫn còn mở.

Evidence mới: `build/ocr-pilot-20260910/ocr4-capture-diagnostic-12/`, gồm harness,
receipt/event canvas, process/preservation và stdout/stderr. Quan sát hai ảnh
capture nằm trong tool output; không persist payload screenshot của lượt này.
