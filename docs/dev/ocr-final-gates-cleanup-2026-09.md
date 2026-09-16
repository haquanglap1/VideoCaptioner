# OCR v6: hoàn tất gate còn mở và kiểm kê dung lượng — 2026-09-11

User yêu cầu tiếp tục ba gate còn mở và dọn file do agent tạo. Giữ nhánh
`codex/asr-s3-native`, HEAD `f274af2` và các thay đổi tích hợp v6 chưa commit.
Phiên này chỉ sửa test, cập nhật tài liệu và kiểm bản EXE đã có; không build,
chép thêm bộ models, tải model, đổi dependency, gọi API hoặc commit/push.

## Sửa nguyên nhân full offline fail

`_wait_for_vieneu` chỉ kiểm `QThread.isRunning()`. Thread Start có thể đã
kết thúc ở mức native trong khi signal result/finished còn đợi Qt xử lý.
Lần `processEvents()` cuối của helper chạy callback Start và khởi động thread
Voices; helper lại trả về ngay, khiến test đọc danh sách giọng còn rỗng.

Regression mới dùng QThread/service fake hiện có, chủ động giữ result trong
hàng đợi và chặn Voices cho tới vòng xử lý event tiếp theo. Test tái hiện
fail với helper cũ, không dùng dịch vụ TTS thật. Helper mới chờ tập thread
được slot finished xử lý hết, rồi gọi `wait()` trước khi trả về. Không đổi
logic VieNeu hoặc làm chậm ứng dụng để che race của test.

- Trước sửa: regression mới **fail** đúng tại giọng chưa nhận.
- Sau sửa: `test_vieneu/test_ui_thread.py` **8 pass**, 4,81 s.
- Full offline FFmpeg + Qt offscreen: **1.794 pass, 0 fail, 5 skip,
  51 deselected**, 168,85 s. Skip gồm 4 TTS cần key/service và 1 backend
  QtMultimedia; không coi skip là pass online.
- Ruff toàn app/tests pass. Không chạy lại Pyright/translations/build vì
  code ứng dụng, resource và dependency không đổi trong lượt này.

## Hai gate native GUI còn thiếu

Dùng nguyên gói `dist/VideoCaptioner-OCR6-Medium-20260911/`, SHA EXE
`211ef75bbc7999f36ab13f357a892f4f88fe9385651deedb31c15aee32bae165`.
Fixture 1,9 s cũ kết thúc trước thao tác hủy ở phiên trước. Lượt này stream-copy
lặp chính fixture tổng hợp đó thành video 30 phút, **63.566.828 byte**, để
giữ decode/tracking hoạt động đủ lâu. Không chạy thêm ma trận chất lượng,
media riêng của user hoặc dịch/TTS; ảnh lặp dùng cache OCR trong cùng job.

- **Cancel:** quan sát tiến độ đang chạy, bấm Hủy, GUI báo đã hủy và còn review
  chưa hoàn chỉnh. Checkpoint lưu được với `complete=false`, **11.096 frame /
  2.560 cue**, **2 request/2 response, 2 det/4 rec/0 cls**, 5.118 cache hit;
  job 30,532 s. Export bị chặn. Sau hủy, app vẫn sống, **0 child**, jobs rỗng.
- **Close while busy:** bắt đầu job thứ hai, ảnh GUI ghi nhận đang xử lý và
  các control bị khóa; đóng hộp thoại OCR khi job còn hoạt động, sau đó đóng
  cửa sổ chính. Watcher thấy Python v6 và FFmpeg trong gói được đóng. Không
  persist checkpoint của job đóng cửa sổ nên không suy số inference từ job
  đầu; tổng inference của cả hai job không được ghi thành một con số đo đủ.
- App sống **410,235 s** gồm thao tác, **exit 0**, **0 child còn lại**, jobs
  rỗng, không traceback. **78 đường dẫn** được theo dõi giữ hash. PATH chỉ
  Windows/System32; settings cũ của bản test giữ nguyên, autoupdate tắt,
  watcher 50 ms không thấy kết nối. Đây không phải trace toàn bộ network/DLL.

Ba gate còn mở của phần tích hợp v6 đã được khép lại. Hiệu chuẩn/auto-accept,
vision GUI, inference resume, disk cache/quota và nghiệm thu chất lượng rộng
vẫn ngoài phạm vi này; không gọi toàn bộ roadmap OCR đã hoàn tất.

## Dung lượng và lệnh dọn bị chặn

Kiểm kê thấy 6 gói portable cũ ở `dist/` và 2 bản thử chuyển ổ trong Temp
mỗi gói giữ lại một bộ model/runtime gần 49 GB. Các inventory cũ đều là
tập con khớp hash/size của bộ OCR6 mới nhất đã verify. Tổng theo inventory
của **8 bản sao: khoảng 389,12 GB**. Đây là phần chép lặp do quá trình build/
nghiệm thu và giữ artifact cũ; không phải model v6 tải mới hàng trăm GB.

Danh sách dự kiến chỉ xóa thư mục `models` trong các gói sau:

- `dist/VideoCaptioner-ASRRecovery-20260910/`
- `dist/VideoCaptioner-OCR4-20260910/`
- `dist/VideoCaptioner-OCR4-LogsLayout-20260911/`
- `dist/VideoCaptioner-OCR4-Media-20260911/`
- `dist/VideoCaptioner-OCR4-RequestLogs-20260911/`
- `dist/VideoCaptioner-OCR4-ReviewVI-20260911/`
- `%LOCALAPPDATA%/Temp/vcm910/VideoCaptioner-ASRRecovery-20260910/`
- `%LOCALAPPDATA%/Temp/vco911/VideoCaptioner-OCR4-Media-20260911/`

Giữ nguyên gói OCR6 đầy đủ, AppData/work-dir, video, phụ đề và journal. Có
plan cụ thể, kiểm owner/manifest/path boundaries, không có runtime process
hoặc settings đang hoạt động trỏ vào 8 model root tại preflight.

**Chưa xóa:** lệnh PowerShell bị bộ duyệt tự động chặn trước khi thực thi,
chỉ báo `blocked by policy`. User sau đó xác nhận cụ thể xóa 8 bản sao model;
lệnh thứ hai vẫn bị chặn. Không đổi shell/tool hoặc chia lệnh để né chặn.
Cả 8 thư mục vẫn tồn tại; **không báo đã giải phóng 389 GB**.

Metadata backup vừa tạo trong lượt kiểm kê được gom thành hai inventory gzip
có hash kiểm lại, từ 195,46 MB xuống 12,69 MB. Chỉ thu gọn metadata mới tạo;
không coi đây là dọn các bản model cũ. Evidence và danh sách đầy đủ ở
`build/ocr-pilot-20260910/ocr-final-gates-cleanup-23/`, ngoài Git.

## File thay đổi trong lượt tiếp tục

`tests/test_vieneu/test_ui_thread.py`, `status.md`,
`docs/dev/ocr-v6-integration-2026-09.md`,
`docs/plans/video-subtitle-ocr-integration-plan.md` và tài liệu này.
Giữ nguyên các thay đổi tích hợp v6 chưa commit của phiên trước.
