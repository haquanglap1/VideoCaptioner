# Cache OCR trong EXE và GUI native — 2026-09-12

Tiếp tục worktree ASR-S3, nhánh `codex/asr-s3-native`, HEAD **cb92305**,
tracking `origin/codex/asr-s3-native`. Không reset/merge/commit/push.
Snapshot cache/v6 **d6d613c** được giữ; lượt này khép gate binary/native
của [cache OCR](ocr-cache-2026-09.md), không mở rộng corpus hoặc vision.

## Thay đổi source và kiểm tra

Worker OCR nay chạy Python với **`-I -B`**. `-I` bỏ qua biến môi trường Python,
nên đặt `PYTHONDONTWRITEBYTECODE` ở harness không ngăn import ghi `.pyc` vào
runtime đã verify. Regression import một module tổng hợp trong process thật
fail trước sửa vì sinh `.pyc`, pass sau sửa. Bridge/model/profile không đổi.

- 54 test runtime/cache/service/GUI và 149 test CLI đã pass, tổng **203 test
  riêng biệt**. Lượt đầu 47 pass/7 skip do FFmpeg thiếu trên PATH; chạy lại
  service cùng CLI bằng FFmpeg của gói: 157 pass, không còn skip ở phạm vi này.
- Ruff app/tests pass; Pyright app **0 error/0 warning**; translations in sync.
- Không chạy lại full offline 1.817 pass/5 skip của snapshot trước. Các gate
  online/TTS đã skip trước đó vẫn chưa được nghiệm thu; không cấp thêm API.

## Build và thay riêng phần app

Dùng duy nhất `VideoCaptioner.spec`, Python3.12.13 hiện có, tên build cũ nhưng
`--distpath`/`--workpath` mới dưới evidence. Chỉ đặt media tools từ gói hiện có;
không đặt biến copy model, không `--noconfirm` lên gói đang giữ.

- PyInstaller **exit0**, **251,562s**, **6 warning/0 error**: js/emscripten,
  curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit; log giữ cả SyntaxWarning dependency.
- App mới: **590 file /529.730.769 byte**, EXE **31.424.351 byte**,
  local **2026-09-12 02:41:04 (+07:00)**, SHA-256
  `cef53f77b8ae00cc7ecece96e6a9d5cbc4043b45e10aeadcf2ac952f68c87ef2`.
- Chín module cache/runtime/service/CLI/GUI/task/entity trong PYZ khớp source;
  bridge, hai profile và FFmpeg/FFprobe khớp nguồn. OCR nặng không vào Qt bundle.
- Nghiệm thu trong staging với junction dùng lại `models/` hiện có và AppData
  riêng không key/autoupdate. Sau gate, **chỉ EXE và `_internal`** được chuyển
  vào `dist/VideoCaptioner-OCR6-Medium-20260911/`. Models không bị copy/move.
- App cũ **590 file /529.719.828 byte** được chuyển nguyên vào `rollback-app/`
  dưới evidence. EXE cũ vẫn SHA
  `211ef75bbc7999f36ab13f357a892f4f88fe9385651deedb31c15aee32bae165`.
  Inventory toàn bộ app mới và app quay lui khớp hash sau chuyển.

Quay lui khi app và worker đã đóng, từ root worktree:

```powershell
& ./build/ocr-pilot-20260910/ocr-cache-binary-25/Update-App.ps1 -Action Rollback
```

Script kiểm root, process và SHA EXE; giữ app mới về staging rồi trả EXE/
`_internal` cũ lại. Không đụng models/AppData/work-dir. Đã kiểm cú pháp và
nghiệm thu nhánh Install; **chưa thực thi nhánh Rollback**. Cần giữ evidence
và `rollback-app/` nếu muốn dùng lệnh này.

## Gate từ đúng binary

Fixture tổng hợp cũ `ocr4-gui-09/synthetic.mov`, 1,9s, full-frame ROI:

| Gate | Cold | Warm |
| --- | --- | --- |
| CLI worker request/response | 2/2 | 0/0 |
| CLI detector/recognizer/classifier | 2/4/0 | 0/0/0 |
| GUI worker request/response | 2/2 | 0/0 |
| GUI detector/recognizer/classifier | 2/4/0 | 0/0/0 |
| GUI job wall time | 2,375s | 2,000s |
| GUI cache hit | 4 | 6 |

Cả CLI và GUI giữ **13 frame/3 cue/6 candidate**, đúng 3/3 câu hai dòng của
fixture, cùng ID/raw/source/config/review sau khi loại metrics/cache_hit.
**6 issue vẫn mở**, không tự duyệt; CLI **exit5**, không tạo subtitle output;
GUI khóa export/handoff. Warm vẫn startup/kiểm profile và decode lại video.
Không dùng fixture ngắn này làm benchmark corpus hoặc độ chính xác sản phẩm.

CLI status báo 2 entry, **1.024 byte payload/20.480 byte database**; clear
xóa riêng bản đọc, file review giữ hash, status về 0. Native GUI cũng bấm
status → clear → status: 2 → 0 entry; bảng review và khóa export còn nguyên.

Native dùng lại `ocr-final-gates-cleanup-23/lifecycle-loop.mov` đã có:

- Cancel khi đang chạy: checkpoint **complete=false**, 6.008 frame/1.386 cue,
  2 request/2 response, 2 det/4 rec/0 cls, 2.770 cache hit, job17,922s;
  review chưa hoàn chỉnh được giữ, 0 child và jobs rỗng sau hủy.
- Scan tiếp cùng selection rồi đóng OCR khi đang xử lý; sau đó đóng app.
  Không lưu checkpoint lần đóng nên không báo số inference của lần đó.
- GUI staging sống **442,641s**, **exit0**, không traceback, 0 process con,
  jobs rỗng. Watcher50ms thấy Python/FFmpeg của bộ hiện có, Python có `-B`;
  không thấy kết nối, không coi polling là trace toàn bộ network.
- Sau cập nhật, mở **chính EXE trong dist**, mở cửa sổ OCR thấy đủ control
  cache; sống **55,578s**, đóng exit0, không traceback, không process sót.
  Không chạy lại OCR trong AppData của gói đã cài.

## Bảo toàn dữ liệu và sự cố harness

Trước build đã ghi SHA **4.970 đường dẫn**, gồm 4.960 file runtime v6 thực tế,
manifest models, EXE, settings và dữ liệu AppData/work-dir sẵn có. Không hash
lại toàn bộ 49GB; không suy inventory cũ thành một lượt verify mới toàn models.
Sau scan staging, không có file runtime mới, mọi hash giữ nguyên.

Smoke ở vị trí dist làm initializer `diskcache` mở lại năm database cache
rỗng và đổi bytes. Hậu kiểm phát hiện và dừng trước bàn giao. Khởi tạo cache
rỗng bằng **thư viện hiện có trong scratch**, sau hai lần mở thu được đúng
hai SHA baseline (cache thường và cache có tag). Chỉ khôi phục khi toàn file
khớp SHA trước phiên; giữ bản sau smoke/journal trong evidence, checkpoint
journal bằng SQLite rồi trả byte gốc. **Không sửa tay header hoặc đoán dữ liệu**.
Hậu kiểm cuối đủ **4.970 hash khớp**, EXE cũ được kiểm ở vị trí quay lui;
settings, media, log cũ, work-dir và runtime không mất dữ liệu.

Tool UIA vẫn báo chỉ mục modal không tồn tại; dùng screenshot Computer Use.
Một ảnh close-start bắt tooltip; ảnh close-busy kế tiếp ghi được job đang chạy.
Giữ cả evidence của lỗi harness/hậu kiểm, không chạy lại build hoặc OCR để che lỗi.

**Junction tạm còn giữ:** bộ duyệt tự động chặn lệnh gỡ link `stage/.../models`
với lý do **`blocked by policy`**. Không thử xóa bằng tool/shell khác. Link trỏ
vào models gốc, không là một bản sao 49GB; staging không còn EXE/`_internal`.
Đây là link của lượt này, không mở lại nhiệm vụ dọn model cũ user đã tự làm.

Evidence ngoài Git: `build/ocr-pilot-20260910/ocr-cache-binary-25/`, gồm
receipt build/parity/CLI/GUI/install/smoke/preservation, review tổng hợp, ảnh,
log, inventory, cache restoration và script quay lui. Không đọc Api.txt,
gọi API/vision/dịch/TTS, tải model, cài dependency hoặc commit/push.

## File thay đổi, chưa commit

- `videocaptioner/core/ocr/runtime.py`
- `tests/test_ocr/test_runtime.py`
- `README.md`
- `status.md`
- `docs/dev/ocr-cache-2026-09.md`
- `docs/dev/ocr-cache-binary-2026-09.md` (mới)
- `docs/dev/ocr-next-session-prompt.md`
- `docs/plans/video-subtitle-ocr-integration-plan.md`

Decode resume, hiệu chuẩn/auto-accept, vision GUI, downloader/update và corpus
rộng vẫn còn mở. Gate này chỉ khép cache binary/native, không toàn roadmap OCR.
