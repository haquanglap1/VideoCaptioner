# OCR-3: định danh hình, document, CLI và metadata — 2026-09-10

Tiếp tục sau mốc này: [GUI/crop review và runtime bundled](ocr-gui-2026-09.md)
đã được thêm. CLI hiện tự tìm bridge/profile/runtime portable khi không truyền
override. Các đoạn “chưa GUI/bundled” bên dưới ghi phạm vi của lượt OCR-3 trước đó.

Tiếp tục tại worktree ASR-S3, nhánh `codex/asr-s3-native`, HEAD đầu **dc94a46**,
sạch và khớp tracking/origin. Đây là thay đổi source chưa commit/push; không
sửa checkout master, chạy lại model/video riêng, gọi vision hoặc build EXE.

## Contract và review

- `VisualSourceIdentity` dùng SHA-256 toàn snapshot, size, video stream, geometry,
  SAR/rotation, time base, timeline origin và selection. Không có audio identity,
  tên/path nguồn hoặc nhãn người nói. Verify dùng snapshot có kiểm thay đổi nguồn,
  cleanup/cancel; video khác chữ bị chặn kể cả cùng audio và duration.
- `OcrConfig` giữ ROI/selection/ngôn ngữ, policy, SHA profile/bridge và snapshot
  package versions, model/dictionary hashes, params/preprocessing. Snapshot không
  chứa đường dẫn cài đặt hoặc URL tải; hash profile đối chiếu đúng bytes recipe.
- `ocr-document-v1` giữ ID document/cue/candidate tất định, first/last/candidate PTS,
  exact rational ms và integer ms canonical. Làm tròn rational → ms, không tự kéo
  dài cue có độ dài làm tròn về 0; trường hợp đó vẫn review. Biên clipped/uncertain,
  bbox, score, raw read/model revision và cache-hit được giữ riêng.
- Lưu JSON atomically bằng temp cùng thư mục, flush/fsync/replace; lỗi replace
  giữ file trước. Load giới hạn 32 MiB, từ chối duplicate/unknown/missing fields,
  sai type, NaN, ID/reference/PTS/profile mismatch và trạng thái review giả thiếu
  quyết định tương ứng. Fraction lưu `[numerator, denominator]`, không dùng float
  để dựng lại thời gian nguồn.
- Raw text là nguyên chuỗi của candidate ban đầu. Review chỉ chọn nguyên chuỗi
  một candidate khác, giữ `edited_text` và ghi lý do. Không ghép ký tự, chuyển
  giản/phồn, sửa tên hay gọi LLM điền chữ. Review timing cần hai biên integer ms
  và lý do riêng; measured timing/PTS/issues gốc không bị sửa.
- Profile hiện vẫn **chưa hiệu chuẩn**. Đồng thuận nhiều crop không tự thành
  accepted. Incomplete scan, không cue, thiếu/empty read, revision mismatch,
  bất đồng/chưa duyệt hoặc timing chưa giải quyết không được xuất success.
  File review được giữ khi scan lỗi sau khi đã xác định nguồn; phần đã có không
  được gọi là kết quả đầy đủ. Resume ở bước này là **review/resume một scan đầy đủ**,
  chưa có resume inference từ checkpoint của scan bị hủy.

## CLI source

Ví dụ dùng runtime và streaming bridge **đã có**, không cài/tải model:

```powershell
python -m videocaptioner ocr video.mp4 --start-ms 0 --end-ms 60000 `
  --roi 0,0.8,1,0.2 --language zh `
  --ocr-runtime path/to/installed-ocr `
  --ocr-bridge scripts/ocr_stream_worker.py `
  --profile-sha256 <SHA-256-cua-profile.json> `
  --review pending.ocr.json -o captions.json --report metrics.json

python -m videocaptioner ocr-review pending.ocr.json --source video.mp4 `
  --select-candidate <cue-id>:<candidate-id> --note "Ly do va bang chung da kiem" `
  --save-review reviewed.ocr.json -o captions.json

python -m videocaptioner subtitle captions.json --target-language vi `
  --layout target-only -o captions.vi.json
```

ROI trong ví dụ chỉ minh họa. CLI dùng `--start-ms`/`--end-ms` tường minh,
`--max-requests` (mặc định 1000), `--timeout` (30 s/request), `--ffmpeg` và
`--ffprobe`. Chưa có locator/model manager OCR: bridge/root/hash bắt buộc,
không suy rằng bridge đã được cài trong payload portable cũ.

`ocr-review` bắt buộc `--source`, hash/probe lại nguồn tại máy và không gọi
recognizer/vision. `--select-candidate` và `--set-timing CUE:START_MS:END_MS` lặp
được; thay đổi cần `--note` cùng `--save-review` ở file riêng. Đường dẫn review,
output và report không được trùng/alias input hoặc ghi vào runtime đang dùng.
Các chuỗi chưa chắc chắn không được tự duyệt bằng ví dụ trên: đây là contract
cho quyết định có bằng chứng, không phải yêu cầu user chấm từng chữ Trung.
Giao diện crop/seek và hỗ trợ đọc ảnh có budget vẫn là phần tiếp theo.

Exit code: input thiếu **3**, config/argument/output path lỗi **2**, runtime
thiếu **4**, processing/review chưa giải quyết **5**, chỉ kết quả đầy đủ đã duyệt
mới **0**. Không đổi exit code/flag ASR cũ. Output JSON giữ metadata; SRT chỉ
giữ text/time. Review JSON không được đưa thẳng qua lệnh `subtitle` để né gate.

Service giữ streaming OCR-2 (queue 4, bound 8 payload, 3 ảnh/track), lưu raw
metadata theo cue thay vì giữ RGB cả video. Report tách pipeline/decode có
backpressure, tracking, recognition wait, inference/worker process và job wall
(gồm worker startup/close, trừ host import và ghi report/checkpoint cuối).
Các stage overlap không cộng thành total. Detector/recognizer/classifier là
**wrapper attempts**, không suy đã hoàn tất khi bị hủy. Với recognizer inject
không có worker measurement, các field worker là `null`, không giả là 0.

## Handoff, dịch và editor

- `ASRDataSeg.ocr_metadata` và `ASRData.visual_source` thêm sau tham số cũ;
  `EditorCue`/`EditorProject` có field tương ứng, vẫn `editor-project-v1`.
  Metadata OCR có lineage observations/config/raw/edited riêng, không giả
  `ASRMetadata(timing="native"/"aligned")` hoặc gán speaker/diarization.
- Clone/selection/translator giữ document source và cue IDs. Hai dòng nguồn
  vẫn nằm trong một `text`; không đi qua SRT để đoán hai ngôn ngữ.
  `has_metadata` nhận OCR; JSON/table export/editor handoff giữ visual source.
- CLI `subtitle` với OCR mặc định giữ text/cue/timing: không tự optimize/split.
  `--optimize` là opt-in mới cho chỉnh text LLM; raw OCR vẫn được giữ. Core
  automatic splitter từ chối OCR trước nhánh native ASR. GUI hiện có cần tắt
  split/optimize khi xử lý dữ liệu OCR đã duyệt; chưa có flow OCR GUI riêng.
- Editor text/timing edit, split và undo/redo đi qua `CommandStack`. Split OCR
  cần ranh giới text tường minh; nếu bản dịch/lời đọc khác nguồn thì cần ranh
  giới riêng. Chưa thêm dialog chọn ranh giới trong GUI; nút split cũ báo cần
  chọn ranh giới thay vì ước lượng. Merge giữ tập observations và ID mới tất định,
  chặn trộn khác source/profile hoặc OCR với legacy.
- Timing sửa/split/merge được đánh dấu edited, không ghi đè measured timing.
  Cue ngắn giữ giờ đã đo, không clamp; OCR không được phép overlap theo ngoại lệ
  nhiều speaker của ASR native. Editor worker kiểm nguồn hình khi Open/Load,
  việc hash/probe không chạy trên Qt main thread.
- Normal project save vẫn JSON + SRT, chỉ Save as ASS xuất ASS. Binary cũ có thể
  bỏ metadata mới khi save; không bảo đảm round-trip qua binary trước OCR-3.

## Kiểm tra và giới hạn

- Scoped **278 passed**: 101 OCR (64 cũ +37 mới), 149 CLI cũ, 8 editor model/
  commands/store, 20 subtitle editing; 20,70 s. Fixture mới dùng readings tổng hợp,
  riêng source test decode FFmpeg thật với no-audio/VFR/nonzero PTS/selection và
  hai video có PCM silence giống nhau nhưng khác chữ. Không chạy OCR model thật.
- Ruff app/tests pass; Pyright app **0 errors/0 warnings** với `--venvpath`
  trỏ môi trường dùng chung; translations in sync. Lần gọi Pyright ban đầu chưa
  chỉ đúng venv sinh lỗi import, không dùng làm kết luận code. Một lệnh test gõ
  sai tên file đã dừng collection, sau đó chạy đúng file ở scoped gate trên.
- Full offline Qt offscreen **1.718 passed / 5 skipped / 51 deselected**, 154,29 s,
  exit 0. Bốn skip TTS cần key/service, một QtMultimedia cần backend native.
  Đây là regression offline, không chứng minh model/online/GUI native mới đã pass.
- Cả **13 crop gốc khớp SHA** trong manifest; không recrop. Kết quả và log full
  ở scratch mới; 0 request OCR model thật và 0 request vision mới trong phiên.
- Không chạy native GUI, pip-installed, isolated OCR model, packaged Python hoặc
  frozen mới. Lỗi native teardown **0xC0000005** cũ còn mở; offscreen pass không
  chứng minh đã sửa. Bridge/runtime/model inventory cũ giữ nguyên.
- Pilot local **10/13 exact, 12/13 đủ chữ-số** và vision **13 attempts/12 response**
  giữ nguyên; không đổi chất lượng chữ/timing từ việc thêm contract. Crop 5 chưa
  được duyệt request thứ 14. Chưa có auto acceptance/calibration, cache disk,
  crop review GUI, model manager hay nghiệm thu OCR binary/video dài.

Evidence mới chỉ ở `build/ocr-pilot-20260910/ocr3-contract-08/`; các receipt/raw/
runtime/media cũ không sửa. OCR-3 source contract không đồng nghĩa OCR sản phẩm
đã hoàn tất. Các bước tiếp cần tập trung chất lượng/review hữu dụng rồi OCR-4;
không suy quyền commit/push/API từ phiên này.

## Tập file thay đổi

29 file, bao gồm file mới và file sửa; không có model/media/raw/key trong tập này:

```text
README.md
status.md
docs/dev/ocr-document-2026-09.md
docs/plans/video-subtitle-ocr-integration-plan.md
videocaptioner/cli/main.py
videocaptioner/cli/commands/ocr.py
videocaptioner/cli/commands/subtitle.py
videocaptioner/core/asr/asr_data.py
videocaptioner/core/ocr/adapters.py
videocaptioner/core/ocr/codec.py
videocaptioner/core/ocr/document.py
videocaptioner/core/ocr/geometry.py
videocaptioner/core/ocr/identity.py
videocaptioner/core/ocr/metadata.py
videocaptioner/core/ocr/pipeline.py
videocaptioner/core/ocr/profile.py
videocaptioner/core/ocr/runtime.py
videocaptioner/core/ocr/service.py
videocaptioner/core/editor/adapters.py
videocaptioner/core/editor/commands.py
videocaptioner/core/editor/models.py
videocaptioner/core/editor/project_store.py
videocaptioner/core/split/split.py
videocaptioner/core/subtitle/editing.py
videocaptioner/ui/thread/editor_media_thread.py
videocaptioner/ui/view/subtitle_interface.py
tests/test_ocr/test_document.py
tests/test_ocr/test_metadata.py
tests/test_ocr/test_service.py
```
