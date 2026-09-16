# Cache bản đọc OCR có hạn mức — 2026-09-11

**Bổ sung 2026-09-12:** [cache đã qua gate EXE và GUI native](ocr-cache-binary-2026-09.md).
Gói OCR6 giữ lại đã được thay riêng EXE/`_internal`, có app quay lui, không
chép models. Cold/warm/status/clear/review/cancel/close pass từ binary.
Các dòng “chưa build” dưới đây là snapshot của lượt source ngày 2026-09-11.

User đã tự dọn các thư mục nặng, giữ `VideoCaptioner-OCR6-Medium-20260911`,
rồi yêu cầu tiếp tục plan. Lượt này triển khai cache disk/quota trong mục 7
trên ASR-S3, giữ các thay đổi v6 chưa commit. Agent không xóa artifact/model,
chép thêm bộ models hoặc thay EXE đang giữ.

## Hành vi

- GUI OCR thêm **Cache chữ OCR (MiB; 0 = tắt)**, **Dung lượng cache** và
  **Xóa cache OCR**. Mở cửa sổ không truy cập cache; status/clear qua worker,
  không sửa review. Hạn mức chọn theo phiên, chưa lưu vào settings.
- CLI `ocr --cache-mib N`: mặc định **64 MiB**, nhận **0–512 MiB**. `0` bỏ
  disk cache, vẫn giữ cache RAM giới hạn trong job. `ocr-cache status` xem
  dung lượng; `ocr-cache clear` xóa riêng các bản đọc tạm.
- Đường dẫn theo `config.py`: `APPDATA_PATH/ocr/cache/raw-v1/reads.sqlite3`,
  tương ứng source/pip/frozen. SQLite thuộc thư viện chuẩn; không thêm dependency.
- Chỉ lưu raw EngineRead JSON (text/score/bbox/revision), key và checksum.
  Không pickle, ảnh/video, credential, bản dịch hoặc quyết định duyệt. Cache
  có chữ nguồn riêng tư ở máy, không được đưa vào Git hoặc gói build.
- Key gồm SHA nguồn, config (ROI/selection/geometry/transform, bridge,
  tracking/consensus, profile/model/dictionary), kích thước và SHA crop.
  Đổi scope thì đọc lại. Profile/worker vẫn được kiểm trước khi dùng cache.
- Cache hit không thành bằng chứng độc lập hoặc auto-accept. Schema/config
  và ID giữ nguyên; `cache_hit`/metrics phản ánh lần quét hiện tại. Review
  đã lưu giữ quyết định riêng và không phụ thuộc cache còn tồn tại hay không.

## Dung lượng và lỗi

Quota tính byte JSON + key/checksum, **chưa gồm metadata SQLite**; tối đa
4.096 entry, mỗi JSON tối đa 1 MiB. LRU thu hồi khi ghi hoặc mở với quota
nhỏ hơn. Các job dùng chung bảng/transaction; writer áp quota của job đó
lên toàn bảng. Nhiều app chọn quota khác nhau thì writer sau áp lại quota
của nó, không cấp quota riêng cho mỗi job.

`auto_vacuum=FULL` trả page trống sau thu hồi/xóa; journal dùng DELETE. GUI/CLI
báo cả payload và kích thước database thực. Journal có thể chiếm thêm dung
lượng tạm trong transaction. Quota không giới hạn snapshot video của job.

Chỉ thao tác database có application ID/schema đúng, từ chối symlink/junction
và hardlink. Không duyệt/xóa cả thư mục hoặc mở model/review để dọn. Cache
chưa có thì status/clear không tạo file. Raw sai checksum/schema/revision
thành cache miss. Lỗi disk/lock quá 100 ms dùng RAM/CPU và thông báo đã lọc
path/text; hủy vẫn truyền lên. Cache không phải bản sao lưu của review.

## Gate

- Test gần đầu **35 pass**, 10,31 s; thêm ba regression trong full suite.
  Các ca gồm reopen/scope/LRU/quota/thu hồi SQLite, corrupt/disk-full/lock/
  concurrent jobs/hủy/clear chỉ cache, giữ ID/review và worker GUI.
- Full offline FFmpeg + Qt offscreen: **1.817 pass /0 fail /5 skip /
  51 deselected**, 180,99 s. Skip 4 TTS cần key/service và 1 QtMultimedia;
  không coi skip là pass online. Ruff pass, Pyright 0/0, translations in sync.
- Video tổng hợp với recognizer giả: lần hai 0 fresh calls, cùng ID/raw/
  nguồn và export vẫn khóa. Scan bị hủy chỉ giữ response đã hoàn tất; chạy
  lại chỉ gọi recognizer cho crop còn thiếu. Tests dùng scratch/cache/settings
  và request logger cô lập, không ghi dữ liệu máy dev.
- Layout source offscreen 1120×900 đã xem bằng Noto Sans SC trong repo.
  Lần render đầu thiếu glyph do font hệ thống trong backend offscreen;
  giữ ảnh lỗi harness và ảnh font tường minh, không sửa app để che lỗi.
  Evidence ngoài Git: `build/ocr-pilot-20260910/ocr-cache-24/`.
- **Worker v6 thật** trên fixture cũ 13 frame/3 cue/6 candidate: cold có
  **2 request/2 response, 2 det/4 rec/0 cls**, job 3,812 s; warm có **0 request /
  0 inference, 6 cache hit**, job 1,828 s. Cùng ID/raw, giữ 6 issue và export
  khóa. Worker vẫn startup/kiểm profile ở lần warm. Cache hai entry:
  **1.024 byte payload /20.480 byte database**. Đây là fixture rất ngắn,
  không phải benchmark chất lượng/tốc độ cho video riêng hoặc corpus rộng.
- Source harness dùng runtime trong gói giữ lại, nhưng app code từ source;
  không gọi là binary cache pass. Harness thêm `-B` cho child Python để
  tránh sinh bytecode trong runtime, không sửa worker/bridge. Jobs rỗng;
  **7 file** giữ hash: EXE, fixture, profile, bridge và ba weights. Không hash
  lại toàn bộ payload49GB. Receipt ở `ocr-cache-24/real-worker/receipt.json`.

**Chưa build EXE có cache.** EXE OCR6 giữ lại vẫn là bản trước cache; gate
source mới không chứng minh tính năng trong binary. Không API, corpus riêng,
tải model, cài dependency, commit/push. Bước binary phải dùng lại models,
tránh thêm một bản sao 49 GB.

Cache dùng lại bản đọc, **chưa phải resume decode/inference tại mốc bị hủy**:
scan sau vẫn snapshot/probe/decode/tracking lại selection. Hiệu chuẩn/
auto-accept, AI đọc ảnh trong GUI và downloader/update OCR vẫn còn mở.

## File thay đổi của lượt này

- App dưới `videocaptioner/`: `core/ocr/cache.py` (mới), `core/ocr/service.py`,
  `core/entities.py`, `cli/main.py`, `cli/commands/ocr.py`, `ui/task_factory.py`,
  `ui/thread/ocr_thread.py`, `ui/components/ocr_dialog.py`.
- Test: `tests/conftest.py`, `tests/test_ocr/test_cache.py` (mới),
  `tests/test_ocr/test_service.py`, `tests/test_ui/test_ocr.py`.
- Tài liệu: file này, `README.md`, `status.md`,
  `docs/plans/video-subtitle-ocr-integration-plan.md`, `docs/dev/ocr-next-session-prompt.md`.

Các file đang sửa khác thuộc lượt v6 trước đó, được giữ nguyên.
