# OCR xuất thẳng, bỏ bước duyệt bắt buộc — 2026-09-13

User yêu cầu tiếp tục OCR với hai video hiện có và **bỏ phần review**.
Ứng dụng xuất bản đọc OCR khi quét xong, không yêu cầu bản chữ gốc, xác nhận
từng candidate hoặc nhập bằng chứng. Yêu cầu này thay điều kiện khóa export
do chưa duyệt trong các biên bản OCR trước đây. Không đổi model hoặc dùng
confidence làm chứng nhận chữ đúng.

## Hành vi

- GUI có bảng kết quả ba cột và hai action **Xuất phụ đề** / **Mở bảng phụ đề
  / dịch** dùng được ngay sau một scan đầy đủ có dữ liệu hợp lệ. Bỏ nút duyệt
  chữ/giờ và ô lý do. **Chi tiết bản đọc** thu gọn mặc định; crop/bản dịch
  tham khảo vẫn xem được khi cần. Chỉnh sửa dùng bảng phụ đề hoặc Video Editor.
- **Lưu/Mở dữ liệu OCR** giữ checkpoint cho tiếp tục quét. File review cũ
  vẫn mở/xuất được mà không chạy OCR lại hoặc sửa các quyết định đã lưu.
- CLI `ocr ... -o captions.srt` hoặc `.json` không cần file review.
  `--checkpoint scan.ocr.json` là tùy chọn, `--review` là alias tương thích.
  Chọn ít nhất một trong output phụ đề hoặc checkpoint để tránh mất kết quả.
- `ocr-export scan.ocr.json --source video.mp4 -o captions.srt` kiểm nguồn
  rồi xuất local; `ocr-review` vẫn là alias, các tùy chọn sửa cũ còn tương
  thích. `ocr-resume ... -o captions.srt` xuất khi quét phần còn lại xong.
- Report giữ `pending_issues` cho chẩn đoán và thêm `export_issues` cho lỗi
  thực sự chặn xuất. Scan đầy đủ xuất thành công trả **exit0**; scan dở hoặc
  dữ liệu không hợp lệ vẫn **exit5**, các mã input/config không đổi.

## Dữ liệu và lỗi xử lý

`OcrCue.export_issues` và `OcrDocument.export_issues` tách lỗi cấu trúc khỏi
thông tin nhận dạng/độ bất định. Bất đồng, ít crop, score thấp, profile chưa
hiệu chuẩn hoặc biên chưa được duyệt không chặn xuất nếu có chữ và timing
hợp lệ. Không tự sửa chữ/dấu, ghép candidate, kéo dài cue hoặc ghi một quyết
định duyệt giả để vượt gate.

Vẫn chặn scan chưa xong, không cue/read, read rỗng, thiếu snapshot profile,
sai model/source/ID/raw reference, timing âm/zero/overlap/vượt selection
hoặc issue không biết cách xử lý. JSON/SRT không được ghi đè input/runtime.
Không xuất một phần rồi gọi là toàn bộ thành công.

Schema `ocr-document-v1` và `editor-project-v1` giữ nguyên. ID, source SHA,
PTS, measured timing, raw/candidates, lựa chọn đã lưu và flags chẩn đoán
không bị đổi khi xuất. Metadata của subtitle/editor chấp nhận observations
chưa duyệt; clone/dịch/split/merge/save/load tiếp tục giữ lineage. Binary cũ
có thể từ chối JSON mới chứa observations chưa duyệt; không hứa tương thích
ngược với điều kiện kiểm của bản cũ.

## Kiểm tra source

- Regression trước sửa: **4 fail / 1 pass**, tái hiện khóa export với chữ/giờ
  hợp lệ, checkpoint cũ và CLI bắt buộc `--review`.
- Sau sửa: **372 test OCR/CLI/GUI pass**. Một assertion của test cache vẫn
  đòi khóa export đã được đổi theo yêu cầu mới; giữ log lượt **81 pass/1 fail**.
- Full offline cuối: **1.853 pass / 5 skip / 51 deselected**, 193,18 s,
  exit0. Có alias `ocr-export`, output-only scan, export/handoff GUI trên
  worker, source mismatch, hủy/tiếp tục, JSON/dịch/editor với observations
  chưa duyệt và giữ tương thích các quyết định cũ.
- Ruff app/tests sạch; Pyright app **0 errors/0 warnings**; translations
  đồng bộ. Test dùng dữ liệu tổng hợp, cô lập settings/cache/logger, chờ
  `QThread.wait()`. Không cài dependency hoặc gọi API.

## EXE và hai đoạn video

- PyInstaller một spec, stage mới, chỉ phần app: **exit0**, 238,359 s,
  **6 warning / 0 error**. Warning về urllib3 emscripten/js, dữ liệu
  curl_cffi/yt_dlp_ejs, hidden import tzdata/sip và AppKit trên Windows.
  Không truyền `--noconfirm`, tải/cài hoặc copy bộ models49GB.
- Đối chiếu bytecode **8 module** sửa giữa source/PYZ khớp; OCR/NumPy/Torch
  không vào process Qt. Export checkpoint tổng hợp cũ → 3 cue JSON exit0,
  cùng toàn bộ observations; checkpoint dở vẫn exit5 và không tạo SRT.
- Hai video do user chỉ định được probe và lấy một frame tại 15 s để chọn
  vùng. SHA toàn hai file được lưu trước và đối chiếu sau lượt thử, không
  đổi media. Nội dung/path riêng chỉ có trong evidence local, ngoài Git.
- Video 1, đoạn **13–15 s**, ROI cũ: **60 frame / 1 cue / 3 request / 3 det
  / 3 rec**. Scan xuất JSON ngay exit0, không chọn candidate/duyệt; xuất lại
  SRT bằng `ocr-export` exit0, giữ raw/IDs/PTS/source/metadata.
- Video 2, đoạn dự kiến **14–16 s**, ROI theo ảnh: **không hoàn tất**.
  Lượt smoke chạm trần riêng **8 request**, giữ checkpoint `complete=false`
  với 5 cue và không tạo subtitle success; exit5. Đã xử lý 12 frame,
  8 det/73 rec/0 cls; `fresh_calls=9` gồm lần gọi thứ 9 bị chặn trước gửi
  worker. Đây không phải trần CLI mặc định 1000. Giữ assertion fail/log/raw
  của harness, không retry hoặc đổi ROI/cấu hình để lấy lượt pass.
- Tổng hai scan mới **11 worker request / 11 det / 76 rec / 0 cls / 0 API**.
  Các process được theo dõi đều kết thúc, jobs trống. Đây là kiểm luồng trên
  đoạn ngắn, chưa chạy hết hai video hoặc chấm độ chính xác nhận dạng.

## Cài đặt và GUI native

Đã thay riêng EXE/`_internal` trong `dist/VideoCaptioner-OCR6-Medium-20260911/`.
Models, AppData và work-dir giữ ở vị trí cũ; app trước nằm trong
`ocr-direct-export-32/rollback-app/`. Artifact hiện tại:

- EXE **31.429.660 byte**, timestamp **2026-09-13 02:00:19+07**.
- SHA-256 `58548169a739abcfe467c7ccc2250f522964ca2f5dbec27081d4402c2877593c`.
- App **590 file / 529.736.078 byte**, chưa tính bộ models được dùng lại.
- App trước có EXE SHA `34a1e970fcb643b3435ef09b09f73df9fc26ee8831c8b70e1101e643284338f1`.

Native smoke chạy chính EXE tại dist, **395,156 s / exit0**, không traceback
hoặc child còn lại; watcher100ms không quan sát remote connection. Mở OCR,
nạp checkpoint tổng hợp cũ và nguồn tương ứng, thấy 3 cue và nút xuất/handoff
dùng được ngay; không có bước duyệt. Xuất `gui-handoff.json` và mở đúng bảng
phụ đề 3 cue; JSON khớp toàn bộ kết quả CLI, giữ raw/IDs/source/metadata.
Chỉ mở bảng dịch, không bấm chạy dịch hoặc gọi API.

Computer Use báo element77 không có trong cache hai lần; chuyển sang thao
tác bàn phím và tọa độ từ ảnh mới để hoàn tất. Không coi hai lỗi công cụ đó
là lỗi app. Đã nhìn giao diện native, chi tiết bản đọc thu gọn, không còn
cột/nút duyệt hoặc ô bằng chứng.

Backup AppData thực trước smoke. Mở GUI làm đổi 5 cache database; giữ bản
sau smoke rồi khôi phục từng file từ backup đã kiểm SHA. **6 file AppData
khớp hash trước smoke**, gồm settings và 5 cache, không process app còn lại.
Không tuyên bố một lượt hash mới toàn payload models49GB.

Nếu cần quay lui sau khi app đóng, script local
`build/ocr-pilot-20260910/ocr-direct-export-32/Update-App.ps1 -Action Rollback`
chỉ trả EXE/`_internal`, kiểm đường dẫn/hash và process trước khi di chuyển.
Nhánh Rollback chưa được chạy; giữ cả backup app và AppData.

Evidence local: `build/ocr-pilot-20260910/ocr-direct-export-32/`.
Không chạy lại audit chất lượng, 16 fixture dấu câu, CTC hoặc width×2.
Nhãn độc lập vẫn chưa có; không suy việc bỏ bước duyệt thành cải thiện chữ.

## Tập file thay đổi

20 file trong snapshot user yêu cầu commit/push sau nghiệm thu; lấy mã
commit thực tế từ Git. `ffcachePuSHPB` có từ trước và được giữ ngoài Git.

```text
README.md
status.md
docs/dev/ocr-direct-export-2026-09.md
docs/dev/ocr-next-session-prompt.md
docs/plans/video-subtitle-ocr-integration-plan.md
videocaptioner/cli/main.py
videocaptioner/cli/commands/ocr.py
videocaptioner/core/ocr/document.py
videocaptioner/core/ocr/adapters.py
videocaptioner/core/ocr/metadata.py
videocaptioner/core/ocr/service.py
videocaptioner/core/ocr/resume.py
videocaptioner/ui/components/ocr_dialog.py
tests/test_ocr/test_direct_export.py
tests/test_ocr/test_document.py
tests/test_ocr/test_metadata.py
tests/test_ocr/test_service.py
tests/test_ocr/test_resume.py
tests/test_ui/test_ocr.py
tests/test_ui/test_ocr_assistance.py
```
