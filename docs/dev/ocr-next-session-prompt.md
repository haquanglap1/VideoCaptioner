# Prompt phiên tiếp theo — cache OCR ở source; giữ bộ OCR6 hiện có

Tiếp tục trong worktree **VideoCaptioner-ASR-S3**, nhánh **codex/asr-s3-native**.
Tìm bằng `git worktree list`, không làm ở checkout master. Snapshot code,
tests và biên bản v6/cache đã commit **d6d613c** (`feat(ocr): integrate v6
medium and bounded persistent cache`); prompt/status thuộc commit bàn giao
tiếp theo. **f274af2** là baseline trước snapshot, không phải HEAD cần quay về.
Lấy HEAD/tracking/origin thật từ Git; không reset, merge master hoặc bỏ thay
đổi mới nếu có. User đã yêu cầu submit/push snapshot này; quyền đó không tự
cấp commit/push/tag/release cho thay đổi của phiên tiếp theo.

## Trạng thái mới nhất

User đã tự xóa các thư mục nặng, giữ **VideoCaptioner-OCR6-Medium-20260911**,
sau đó nói **“xoá hết rồi, làm tiếp theo plan”**. Nhiệm vụ dọn không còn mở.
Hai lần tool chặn xóa trước đó vẫn được ghi trong biên bản cũ; agent không
thực hiện việc xóa hoặc báo số byte thu hồi thay user.

Đã triển khai cache disk/quota ở source: raw EngineRead JSON/checksum,
key theo nguồn/config/profile/crop. Mặc định 64 MiB payload + metadata SQLite,
0–512 MiB, tối đa 4.096 entry, LRU/auto-vacuum. `0` tắt disk cache; lỗi disk/
lock dùng RAM/CPU và thông báo. GUI có quota/status/clear qua worker; CLI
`--cache-mib`, `ocr-cache status|clear`. Cache không giữ ảnh/video, credential,
bản dịch/quyết định duyệt; không tự duyệt hoặc sửa schema/ID.

## Đọc trước khi sửa

1. AGENTS.md, README.md, phần mới nhất status.md; kiểm Git status/HEAD/upstream.
2. `docs/dev/ocr-cache-2026-09.md` và `docs/plans/video-subtitle-ocr-integration-plan.md`.
3. Khi liên quan runtime/binary: `docs/dev/ocr-v6-integration-2026-09.md` và
   `docs/dev/ocr-final-gates-cleanup-2026-09.md`. Gate v6 cũ đã khép, nhưng
   không chứng minh cache mới trong binary.

## Gate cache đã chạy

- Full offline FFmpeg + Qt offscreen: **1.817 pass /0 fail /5 skip /
  51 deselected**, 180,99 s. Skip 4 TTS cần key/service, 1 QtMultimedia.
- Ruff app/tests pass; Pyright app 0/0; translations in sync.
- Test video tổng hợp/recognizer giả: giữ IDs/raw/nguồn/review, scope/quota/
  LRU/reclaim/lock/disk-full/corrupt/clear/cancel/concurrent jobs và worker GUI.
- **Worker v6 thật trên fixture tổng hợp cũ:** cold 13 frame/3 cue/6 candidate,
  2 request/2 response, 2 det/4 rec/0 cls; warm 0 request/0 inference, 6 cache
  hit. Cùng ID/raw, giữ 6 issue và export khóa. Hai entry: payload 1.024 byte,
  database 20.480 byte. Job 3,812 s và 1,828 s; không là benchmark corpus.
  Worker vẫn startup/kiểm profile ở lần warm. Jobs rỗng; 7 file theo dõi giữ
  hash (EXE, fixture, profile, bridge, 3 weights). Harness thêm `-B` cho child
  Python để không sinh bytecode trong runtime giữ lại; không sửa bridge.
- Layout source offscreen 1120×900 đã xem với Noto Sans SC trong repo. Ảnh
  đầu thiếu glyph do font hệ thống được giữ riêng. Evidence ngoài Git:
  `build/ocr-pilot-20260910/ocr-cache-24/`, receipt thật ở `real-worker/receipt.json`.
- **Chưa build EXE có cache.** Không coi source pass là binary đã được cập nhật.

## Artifact phải giữ

`dist/VideoCaptioner-OCR6-Medium-20260911/`, nguyên thư mục gồm `models/`,
`_internal/`, AppData và work-dir. EXE 31.413.410 byte, local 2026-09-11
15:45:47, SHA-256:
`211ef75bbc7999f36ab13f357a892f4f88fe9385651deedb31c15aee32bae165`.

Artifact v6 đã qua PyInstaller exit0/6warning/0error, inventory 132.083 file/
49.187.596.170 byte đã verify, CLI/GUI fixture 3/3 câu, cancel và close khi bận,
giữ review/export guards, không process con. **Đây là binary trước cache.**
Không ghi đè cả thư mục bằng PyInstaller --noconfirm hoặc chép thêm bộ 49 GB.

## Bước tiếp và giới hạn

- Gate còn thiếu gần nhất là **cache trong binary và GUI native**. Khi user
  giao tiếp tục phần này, chuẩn bị phương án build/cập nhật riêng phần app
  với khả năng quay lại bản cũ, dùng bộ model/runtime đã verify hiện có.
  Giữ AppData/work-dir/media/log; không dùng `--noconfirm` lên nguyên gói
  giữ lại hoặc nhân bản 49 GB. Dùng một `VideoCaptioner.spec`, nghiệm thu
  cold/warm cache, status/clear, review/export guards và worker lifecycle
  từ đúng artifact; báo source/binary/native gate riêng.
- Cache vẫn snapshot/probe/decode/tracking lại selection; **chưa phải resume
  tại mốc bị hủy**. Resume decode, hiệu chuẩn/auto-accept, vision GUI,
  downloader/update và nghiệm thu corpus rộng còn mở trong plan.
- **0 API mới được cấp; cap vision14 đã hết.** Không đọc Api.txt, gọi vision,
  dịch/TTS hoặc tải model khác. Không cài/nâng dependency, uv sync,
  Python3.13/global install. Host `../VideoCaptioner/.venv/Scripts/python.exe`
  (3.12.13); Pyright `--venvpath ../VideoCaptioner`.
- RapidOCR3.9.2/ONNX Runtime CPU1.29.0 đã có; OCR nặng ngoài Qt. V6 medium/multi
  pin model/dictionary từng stage, vẫn đọc v5 tường minh. Chất lượng cũ 23/23
  đủ chữ-số, 19/23 exact; tham chiếu agent chưa native-confirmed, không là
  auto-accept hoặc chất lượng toàn sản phẩm.
- Giữ `.env`, cookies, Api.txt, AppData, work-dir, media, raw/evidence và log.
  Giữ weights/evidence `ocr-quality-21/`; không thay raw cũ bằng raw v6.
- Test cô lập settings/CLI config/OPENAI/request logger/OCR cache; QThread
  phải `wait()` trước khi object rời scope. Dùng `child_environment()` và
  contextvars helper hiện có. OCR pending CLI **exit5**, không phải exit6.
- Không chạy lại full suite/build/crop sweep đã qua chỉ để có số mới; chạy
  thêm theo thay đổi hoặc gate còn thiếu. Bàn giao kiểm Git status, liệt kê
  đúng file mới/gate/skip và giữ các thay đổi chưa commit. Không gọi toàn bộ
  roadmap OCR hoàn tất.
