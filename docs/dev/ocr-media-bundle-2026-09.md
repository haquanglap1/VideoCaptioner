# OCR-4: crop trong EXE và bộ công cụ media — 2026-09-11

Tiếp tục ASR-S3 `codex/asr-s3-native`, HEAD/tracking `a528d85`, giữ tất cả thay
đổi có sẵn. Phiên này sửa `VideoCaptioner.spec` và hướng dẫn build; không đổi
painter, OCR engine/profile, runtime model hoặc các quyết định review. Hai fix
progress/combo từ phiên trước được giữ trong source để đưa vào binary mới.

## Crop trong EXE cũ

Dùng đúng `VideoCaptioner-OCR4-20260910`, SHA
`865c07a6104168bd6f7758abc04c70c0d45747a701aa779415bcf1d44664e7ff`.
Chọn fixture tổng hợp và mở `pending.ocr.json` cũ qua GUI; background xác minh
nguồn tại máy. Lấy crop cho lần lượt ba cue: **cả ba hiện rõ ngay sau load**,
UI báo SHA khớp, không kéo splitter/resize hoặc activation bổ sung sau yêu cầu
crop. Sáu issue vẫn mở; không duyệt, xuất hay chạy nhận dạng mới.

Đóng GUI chính **exit 0**, sống **417,516 s** gồm thao tác tool; không dùng làm
latency OCR. Không child sót/traceback stderr. Settings master/ASR-S3/artifact
và fixture giữ nguyên SHA. Watcher thấy FFmpeg từ models của artifact nhưng
FFprobe từ cài đặt dev. Không có FFprobe trong toàn artifact khi kiểm file.

Capture đúng đích đã được đối chiếu bằng UI. Không tái hiện crop đen ở lượt này;
không gọi nguyên nhân hiện tượng cũ hoặc lỗi native teardown đã được sửa.
Computer Use có lỗi cache accessibility (`element 206 is not available in
cached app state`); hoàn tất chọn file bằng ô tên file có con trỏ quan sát được
và bàn phím. Không dùng ảnh/focus metadata sai để làm bằng chứng tính năng pass.

Evidence: `build/ocr-pilot-20260910/ocr4-exe-capture-13/`, gồm ba PNG đúng đích,
visual receipt, process/preservation, child paths và stdout/stderr. **0 CPU
model request, 0 vision request**.

## Sửa đóng gói media

Spec nhận biến tùy chọn `VC_TEST_MEDIA_TOOLS_DIR`, yêu cầu có cả `ffmpeg.exe`
và `ffprobe.exe` trước bước Analysis. Dùng cặp **static đã cài** và đưa đúng hai
file vào `_internal/resource/bin`; `config.py` đã hỗ trợ tìm thư mục này.
Không thêm locator khác, copy toàn AppData, tải model/dependency hoặc ghi lại
model inventory. README mô tả điều kiện và hành vi khi không truyền biến.

Bản mới dùng lại bộ models có OCR của artifact cũ qua `VC_TEST_MODELS_DIR`;
không truyền thêm `VC_TEST_OCR_MODELS_DIR`. Build có tên/output riêng và
`--workpath` trong scratch mới để giữ nguyên staging/artifact cũ.

Đối chứng EXE cũ: PATH chỉ có `Windows/System32`, không tìm được ffprobe từ
PATH; mở tiếp **review đã duyệt** thất bại exit 5, không tạo output. Đây là lỗi
thiếu tool của gói cũ, không phải review guard. Không inference lại.

## Gate bản mới

Artifact: `dist/VideoCaptioner-OCR4-Media-20260911/`, onedir; phân phối nguyên
thư mục. Build **exit 0**, **508,094 s** gồm copy model, **6 warning PyInstaller/
0 error**, thêm **9 dòng warning Python** từ pydub/modelscope/pkg_resources.
Warning pydub lúc build không chứng minh công cụ thiếu trong bản đích; gate
thực thi media được đo riêng bên dưới. Không nâng dependency để xử lý warning.

EXE **31.385.758 byte**, local **2026-09-11 00:44:04**, SHA-256
`5bee44fd3277a9fb8c8239f51d28684a3d99e4b01024ed470825ca6727873d80`.
Cặp media khớp SHA nguồn: FFmpeg **145.871.872 byte**, FFprobe **145.660.416 byte**.
Manifest models đích khớp bytes nguồn; artifact cũ/settings được bảo toàn.

- **127.610 file model /48.739.395.432 byte**: kiểm từng size/SHA pass, đủ tám
  component như gói nguồn (Faster-Whisper, Qwen, Community-1, OmniVoice, VieNeu,
  các weights tương ứng và OCR). Đây là file verification, không chạy lại các engine.
- PYZ của `ocr_dialog`, `ocr_region_canvas`, `config` khớp source hiện tại; worker/
  profile OCR bundled khớp SHA. Host archive không có NumPy/cv2/ONNX/RapidOCR/
  Paddle/Torch. Hai fix UI cũ đã nằm trong EXE mới.
- Với PATH chỉ có `Windows/System32`, hai executable media chạy `-version`
  **exit 0**. Frozen CLI `ocr-review` bản pending **exit 5 đúng guard**, không
  tạo subtitle output; bản reviewed **exit 0**. Save/load document giữ nguyên,
  JSON subtitle khớp output đã duyệt cũ. Không inference lại.
- Native GUI của đúng EXE dùng cùng PATH tối thiểu và working directory scratch:
  mở pending review, lấy crop câu đầu **SHA khớp/chữ hiện rõ**, không kéo splitter.
  Progress **100% sau mở review/lấy crop**, candidate hiển thị trên một hàng;
  sáu issue vẫn mở, export/handoff khóa. Đây không phải lượt CPU scan mới; gate
  scan 94% → 100% của source vẫn là bằng chứng phiên trước.
- Process GUI sống **162,500 s**, được quan sát qua startup/review/crop rồi đóng
  **exit 0**, không child sót/traceback stderr. Watcher ghi FFprobe và FFmpeg đều
  từ `_internal/resource/bin` của artifact mới, không từ model tools hay checkout
  dev. Settings mới chỉ chứa cấu hình smoke tắt update, không credential.
- Settings master/ASR-S3/hai artifact, fixture và pending review được theo dõi
  giữ hash; artifact cũ/model manifest nguồn được bảo toàn. Không chạm media
  riêng hoặc recrop/chạy lại phép kiểm 13 crop pilot.

Evidence tại `build/ocr-pilot-20260910/ocr4-media-bundle-14/`: build/verification/
GUI process receipts, source/target media hashes, hai ảnh GUI, review outputs,
đối chứng old-clean-path, stdout/stderr, version logs và harness. Tổng phiên
**0 CPU model request /0 vision request**, không đọc key hoặc tăng cap vision.

Đã chứng minh gói tự dùng cặp media tools cho local review/crop trên máy hiện
tại với PATH tối thiểu. **Chưa chuyển toàn onedir sang ổ khác hoặc thử máy sạch**;
chưa chạy lại CPU scan, các ASR/TTS runtime, dịch/TTS/API hoặc workflow video riêng
trên binary mới. Crop đen không tái hiện ở các lượt này; nguyên nhân mọi lần lỗi
cũ và native full-suite teardown `0xC0000005` vẫn chưa được chốt/sửa. Review hỗ
trợ Việt/vision, hiệu chuẩn, cache disk, resume inference và downloader OCR còn mở.

Không chạy lại bộ offline chỉ để đổi số pass: source app giữ nguyên các fix đã
qua **1.739 pass/5 skip/51 deselected**, Ruff/Pyright/translations phiên trước.
Gate mới tập trung syntax spec, hash/code/resources trong binary và media/local
review từ artifact. Chưa có quyền vision mới hoặc commit/push; raw/media/key/
log/model không đưa vào Git.

File sửa trong phiên: `VideoCaptioner.spec`, `README.md`, biên bản này,
`status.md`, `docs/dev/ocr-next-session-prompt.md`. Các source/test/tài liệu có
sẵn từ đầu được giữ nguyên; scratch/build/dist ngoài Git. `git diff --check`
và compile syntax spec pass; không gọi gate offline cũ là lượt chạy mới.
