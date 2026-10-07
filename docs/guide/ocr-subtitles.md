# OCR phụ đề trong hình — cách hoạt động và cách dùng

Hướng dẫn ngắn cho cửa sổ **Nhận dạng → OCR phụ đề trong hình**. Contract dữ liệu, cache, resume và
kết quả nghiệm thu nằm trong các tài liệu `docs/dev/ocr-*.md`.

## Khi nào dùng

Video có **phụ đề cứng** (chữ đã ghi sẵn trong hình, thường tiếng Trung) và bạn muốn lấy đúng chữ gốc
thay vì nhận dạng giọng nói. OCR đọc chữ trong **một vùng cố định** của khung hình. Mặc định chữ được đọc
bằng **AI qua API LLM** trong Cài đặt (model phải đọc được ảnh); bỏ chọn ô đó để đọc bằng PP-OCR chạy
**CPU tại máy** (cần runtime OCR đã cài, không tự tải model).

## Cách hoạt động

1. App chụp bản sao video vào thư mục job riêng và hash để mọi kết quả gắn đúng nguồn.
2. FFmpeg giải mã từng frame trong đoạn đã chọn và cắt đúng vùng ROI bạn đã kéo.
3. Bộ theo dõi phát hiện lúc chữ trong vùng đổi; mỗi khoảng chữ giữ nguyên thành một **câu** (cue) với
   thời điểm đầu/cuối tính bằng millisecond. Đường AI theo dõi nét chữ sáng/mảnh nên nền chuyển động
   không tách câu; cảnh không có chữ nhưng lọt vào tờ ảnh sẽ được AI trả rỗng và bị loại.
4. Mỗi câu được đọc trên một vài ảnh đại diện (**bản đọc**). Với AI qua API, app lấy crop nét nhất của
   mỗi câu, ghép tối đa 16 crop thành một tờ ảnh đánh số và gửi một lượt; AI trả về đúng một chữ cho
   mỗi dòng, dòng trống bị loại. Với CPU, các bản đọc giống nhau thành chữ của câu; khác nhau thì giữ
   cả để bạn xem trong **Chi tiết bản đọc**. OCR không tự sửa hoặc đoán chữ thiếu.
5. Kết quả là bảng câu + thời gian; có thể xuất SRT/JSON ngay hoặc chuyển sang bảng phụ đề để dịch và
   lồng tiếng như phụ đề từ ASR.

## Dùng trong GUI (4 bước)

1. **Chọn video…** (hoặc **Mở dữ liệu OCR…** để tiếp tục một lần quét đã lưu).
2. Nhập thời điểm đang hiện phụ đề vào **Ảnh mẫu tại** rồi bấm **Tải ảnh chọn ROI**, hoặc bấm **Lấy ảnh
   giữa video**. Trên ảnh, **kéo chuột quanh dòng phụ đề**: bao trọn chữ và một chút lề, tránh chữ giao
   diện/logo. **Quét toàn bộ video** bật sẵn và tự điền độ dài video; bỏ chọn nếu chỉ cần một đoạn.
3. **Đọc phụ đề bằng AI (API)** khi ô **Đọc chữ bằng AI qua API LLM trong Cài đặt** đang bật (mặc định),
   hoặc **Đọc phụ đề bằng CPU** khi bỏ chọn. Thanh trạng thái hiện tiến độ và tên model; có thể **Hủy
   tác vụ** rồi **Lưu dữ liệu OCR…** và sau này **Tiếp tục quét** từ chỗ dừng (cần giữ đúng model đã
   dùng). Tốc độ CPU phụ thuộc độ phân giải và số frame; đường AI chủ yếu chờ API, mỗi lượt gửi tới 16
   câu.
4. **Xuất phụ đề…** (SRT chỉ giữ chữ/giờ, JSON giữ cả bản đọc) hoặc **Mở bảng phụ đề / dịch…** để dịch
   sang tiếng Việt, chỉnh sửa và lồng tiếng.

## Mẹo và tùy chọn nâng cao

- **Số crop mỗi lượt gửi AI** (Tùy chọn nâng cao, mặc định 16): ít hơn thì nhiều lượt hơn, nhiều hơn thì
  model dễ bỏ sót dòng. Đường AI chỉ gửi crop, số dòng và ngôn ngữ; không gửi tên file hay audio.
- ROI nên cao khoảng 1,2–1,5 lần chữ. Nếu vùng dính chữ nền/giao diện (đường CPU), mở **Tùy chọn nâng cao** → bật
  **Chỉ lấy dòng đi qua vạch chọn** với vị trí `50` (một dòng) hoặc `25,75` (hai dòng); vạch vàng trên ảnh
  cho thấy vị trí.
- Nền chuyển động làm câu bị tách nhỏ: bật **Ổn định nhóm phụ đề một dòng (CPU)** (chậm hơn, chỉ với một
  vạch).
- **Kiểm tra model đã cài** chỉ đối chiếu file/profile; bộ `models/ocr-v6-medium` trong bản portable được
  ưu tiên, bộ v5 cũ vẫn chọn được qua **Chọn runtime…**.
- **ROI số** cho phép nhập lại chính xác vùng đã dùng (x, y, rộng, cao theo tỷ lệ 0–1).
- **Cache chữ OCR** (mặc định 64 MiB) giúp quét lại cùng video/vùng nhanh hơn; xóa cache không ảnh
  hưởng dữ liệu đã lưu.
- Chữ sai hoặc thiếu dấu: sửa trong bảng phụ đề hoặc Video Editor. Nút **Dịch bản đọc đang chọn sang
  Việt** chỉ gửi chữ (không gửi ảnh) tới LLM đang cấu hình để tham khảo, không tự sửa phụ đề.

## CLI

```powershell
uv run --frozen videocaptioner ocr --help
uv run --frozen videocaptioner ocr video.mp4 --vision-llm --start-ms 0 --end-ms 60000 --roi 0.05,0.86,0.90,0.10 -o captions.srt
uv run --frozen videocaptioner ocr-export saved.ocr.json --source video.mp4 -o captions.srt
```

Lệnh `ocr` nhận ROI/đoạn thời gian/vạch chọn tương ứng với các control trong cửa sổ; xem `--help` để
biết tên tham số hiện hành.
