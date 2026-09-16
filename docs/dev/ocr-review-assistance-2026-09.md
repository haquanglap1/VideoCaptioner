# OCR: bản Việt tham khảo trong review — 2026-09-11

Tiếp tục trên `codex/asr-s3-native`, HEAD **a528d85**. User giao tiếp tục plan
sau khi hỏi về vùng OCR, CPU/GPU và model đọc ảnh. Giữ các thay đổi UI/media
bundle trước đó; không commit/push, đổi model/runtime hoặc gọi API thật.

## Hành vi mới

Trong cửa sổ OCR, chọn một câu và một bản đọc, rồi bấm **Dịch bản đọc đang chọn
sang Việt**. Ô bên cạnh raw/hiện tại hiển thị bản Việt tham khảo và các điểm
chưa rõ do LLM nêu. Nhãn luôn ghi **AI chưa nhìn ảnh**: đây là dịch từ chữ OCR,
không phải một lượt nhận dạng ảnh hay bằng chứng chấp nhận câu.

- Mở dialog, chọn câu/bản đọc và mở review không gọi mạng. Chỉ nút dịch gửi
  đúng nguyên chuỗi của một candidate tới dịch vụ/model LLM đang chọn trong
  Cài đặt. Không gửi ảnh/video, câu lân cận, source ID, tên/path file hay transcript
  toàn video. Không dùng STT key hoặc tự chọn endpoint/model khác.
- Một action tối đa một request, không retry tự động, tối đa 1.000 completion
  token. Timeout lấy cấu hình LLM hiện có (1–600 s). Request sở hữu socket và
  giữ cơ chế hủy của `OwnedLLMRequest`; hủy local không bảo đảm provider ngừng
  xử lý/tính phí. Token chỉ hiện khi provider trả số liệu, thiếu không ghi 0.
- Chỉ nhận JSON đủ hai trường `translation_vi` và `uncertainties_vi`; từ chối
  response bị cắt, field thừa/trùng, kiểu sai hoặc dữ liệu quá dài. Lỗi được
  báo bằng thông điệp đã lọc, không ghi raw response/credential vào log.
- Bản tham khảo nằm riêng trong RAM, tối đa 64 candidate trong một dialog;
  chọn lại cùng candidate/cấu hình dùng kết quả đã có. Đổi model/endpoint/
  timeout yêu cầu action mới. Đổi candidate/document không hiện nhầm bản dịch;
  đóng dialog xóa cache và bỏ kết quả muộn.
- **Lưu review** vẫn chỉ lưu `ocr-document-v1`, chưa lưu bản Việt tham khảo.
  Dịch không thay raw/candidate/ID/timing, không thực hiện command duyệt và
  không mở khóa export/handoff. Dịch chính thức của phụ đề đã duyệt vẫn ở
  bảng phụ đề như trước.

Phần đối chiếu tại máy phân biệt ba tình huống: các bản đọc giống nhau;
giống chữ/số nhưng khác dấu câu/khoảng trắng/xuống dòng; hoặc khác chữ/số.
Không suy bản nào đúng. Nhiều ảnh đồng thuận vẫn có thể cùng bỏ sót chữ.

## Giới hạn chất lượng

Câu 4 trong pilot có chữ "tháng" trên ảnh nhưng local đã bỏ sót ở cả ba lần
đọc. Crop sát chữ cũ có kết quả đầy đủ chữ nhưng khác dấu câu; không thay raw
hoặc tự bật preprocessing từ một ca. Tính năng bản Việt **chưa sửa lỗi đó**:
dịch text thiếu chữ không thay thế việc đọc lại ảnh có bằng chứng.

OCR hiện vẫn là RapidOCR/PP-OCRv5/ONNX CPU với vùng chọn cố định. Chưa thêm
GPU, AI vision trong GUI, importer kết quả vision cũ, hiệu chuẩn, downloader,
cache disk/quota hoặc resume inference. Cap vision cũ giữ nguyên; "tiếp tục
plan" không cấp thêm lượt crop 5 hoặc đổi dịch vụ để né cap.

## Nghiệm thu

Evidence mới ở `build/ocr-pilot-20260910/ocr4-review-assistance-17/`.
Test dùng fixture tổng hợp và response giả; không gọi model OCR hoặc LLM thật.
Gate source, native render và EXE được ghi riêng khi hoàn tất trong phần dưới.

Native source render đã thấy crop tổng hợp, raw/hiện tại và bản Việt cạnh nhau,
nút dịch và thông báo phạm vi rõ; export/handoff vẫn khóa. Render dùng Segoe UI
9, cửa sổ 1120×904; process exit 0, worker đã kết thúc. Đây là Qt native với
response giả, không phải nghiệm thu chất lượng dịch hay thao tác GUI frozen.
Offscreen render trước đó không vẽ được glyph và có size hint khác native;
không dùng nó để kết luận lỗi painter/crop của app, không sửa painter.

Hai test đầu fail do fixture dùng sai tên field source identity và phép thử
đóng một dialog chưa show không phát sự kiện đóng. Đã sửa test show dialog
trong Qt offscreen và barrier giữ request tới sau khi đóng;
giữ log lần đầu. Lint ban đầu có hai lỗi thứ tự import, đã sửa đúng hai block.

- Scoped OCR/GUI/CLI: **274 pass /21 skip**, 19,88 s, exit 0. Lượt này chưa
  đưa FFmpeg vào PATH nên 21 test media skip; không dùng skip làm bằng chứng media.
- Full offline với FFmpeg đã cài và Qt offscreen: **1.763 pass /5 skip /
  51 deselected**, 262,07 s, exit 0. Bốn skip TTS cần key/service và một
  QtMultimedia cần backend native. Gồm 24 test mới cho request giới hạn, parse,
  bảo toàn raw/guard, cache/candidate/model/source và đóng khi request chưa trả.
- Ruff app/tests pass; Pyright app **0 error/0 warning**; translations in sync.
  Không nâng dependency theo thông báo phiên bản mới của Pyright.
- **0 request OCR /0 vision /0 LLM thật** trong các gate này; fixture/mock chỉ
  chứng minh luồng và guard. Native full-suite teardown cũ chưa được xác định/sửa.

Các file thay đổi trong lượt này: `core/ocr/assistance.py`,
`ui/components/ocr_dialog.py`, `ui/thread/ocr_thread.py` (dưới `videocaptioner/`),
`tests/test_ocr/test_assistance.py`, `tests/test_ui/test_ocr_assistance.py`,
`README.md`, biên bản này, `docs/dev/ocr-gui-2026-09.md`,
`docs/plans/video-subtitle-ocr-integration-plan.md`, `status.md` và prompt bàn giao.
Giữ nguyên phần diff có sẵn của spec và các test UI cũ.

## Artifact mới và giới hạn nghiệm thu

`dist/VideoCaptioner-OCR4-ReviewVI-20260911/` là gói onedir đầy đủ mới; giữ
nguyên các artifact cũ, kể cả gói media tại C. Dùng một spec và workpath mới
trong scratch; tái sử dụng `models/` và cặp media từ gói Media-20260911,
không stage lại từ cài đặt gốc hoặc tải model/dependency.

1. **Build:** PyInstaller exit **0**, wall **316,219 s**, **6 warning /0 error**
   của PyInstaller (js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit).
   Có thêm 9 dòng warning Python từ dependency trong log, không sửa/nâng package.
2. **Artifact:** EXE **31.395.029 byte**, local **2026-09-11 10:23:36**, SHA-256
   `ca1860a65cca66c9c9a331644300eb2b454ab29a9bb3588f734079b343518289`.
   **127.610 file model /48.739.395.432 byte** trong bản mới khớp toàn bộ SHA
   manifest; cặp FFmpeg/FFprobe và resource OCR khớp bộ nguồn. Ba module mới/
   thay đổi khớp code trong PYZ; host không chứa dependency OCR nặng. Kiểm
   payload mới **123,203 s**, không hash lại bộ C đã nghiệm thu.
3. **Native GUI frozen startup:** PATH chỉ Windows/System32, settings mới chỉ
   tắt update, không credential. Cửa sổ hiện sau **3,078 s**, sống 30 s,
   tổng **31,156 s**, đóng đúng PID bằng WM_CLOSE, **exit 0 /0 child**, không
   traceback stderr; settings test giữ hash.
4. **Chưa chạy mới:** dịch LLM thật/chất lượng bản Việt, thao tác review/dịch
   trong GUI frozen, OCR scan, isolated runtime, packaged Python, frozen CLI,
   chuyển bản ReviewVI sang C hoặc máy sạch. Các gate cũ vẫn là lịch sử;
   startup/PYZ parity không thay thế workflow GUI hay API thật. Câu 4 còn lỗi.

Settings dev được theo dõi, manifest/crop 4 pilot và các artifact/settings
được theo dõi trong builder giữ hash. Bản ReviewVI tạo settings smoke riêng;
không chép settings/key của user. `git diff --check` pass; chưa commit/push.
**Tổng phiên 0 request CPU OCR /0 vision /0 text LLM thật.**
