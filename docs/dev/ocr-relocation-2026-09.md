# OCR-4: chuyển gói media/model sang ổ khác — 2026-09-11

## Bổ sung mới nhất: OCR GUI từ gói ổ C

Tiếp tục trên `codex/asr-s3-native`, HEAD/tracking/remote trực tiếp **a528d85**.
Dùng nguyên bản `Temp/vco911/VideoCaptioner-OCR4-Media-20260911/` đã chuyển,
EXE giữ SHA `5bee44fd3277a9fb8c8239f51d28684a3d99e4b01024ed470825ca6727873d80`.
Không build, copy/stage model lại, đổi source/test/spec, cài dependency hoặc
gọi vision. Các mục phía dưới là snapshot trước lượt GUI này.

Computer Use native khả dụng ở lượt mới. Mở đúng EXE test với PATH chỉ có
`Windows/System32`, bỏ override Python/Qt/runtime và lọc credential bằng
`child_environment()`. Input/output/cwd đều trong work-dir gói C; dùng lại
fixture tổng hợp, không video riêng. Mở OCR từ màn Nhận dạng, để trống runtime,
bấm kiểm model, chọn đoạn **0–1.900 ms**, preview tại 100 ms và xác nhận ROI
toàn khung **640×160** đã dùng cho fixture.

| Gate GUI mới | Kết quả |
| --- | --- |
| Kiểm bộ đã cài | UI báo model/profile khớp SHA; tự tìm runtime, không tải model |
| Một scan CPU | **13 frame /3 cue /6 candidates**, **3/3 câu hai dòng exact** với fixture |
| Request và thời gian | **2 request /2 response**, 2 detector/4 recognizer/0 classifier attempts, 4 cache hit; job **2,391 s**, inference **0,210 s** |
| Progress và guard | Scan hoàn tất **100%**; 6 issue vẫn mở, export/handoff khóa; candidate trên một hàng |
| Crop ba cue | Chọn từng cue, lấy crop đúng PTS, cả **3/3** được GUI xác nhận SHA; PNG capture gốc chứa hai dòng chữ |
| Lưu/mở lại | Lưu `gui-scan-16.ocr.json` mới rồi mở lại trong GUI; complete=true nhưng vẫn review; không scan lần hai |
| Document | Tất cả field ngoài metrics khớp document pending trước: raw/candidates/IDs/source/config/timing/issue giữ nguyên |
| Discovery process | Watcher thấy Python OCR, bridge, model root và job-dir thuộc gói C; FFmpeg/FFprobe từ `_internal/resource/bin` của chính gói |
| Đóng | Đúng EXE exit **0**, 0 child sót, thư mục job OCR rỗng, stderr không traceback |

GUI sống **481,906 s**, gồm toàn bộ thao tác/capture; đây không phải latency
OCR. Các stage metrics có overlap, không cộng thành total. Watcher lấy mẫu
20 ms, thấy một worker OCR; không phải trace mọi file/DLL/network access.
Một scan này là tổng **2 CPU request /2 response** mới, **0 vision request**;
giữ ledger các phiên cũ và cap vision/crop 5 nguyên trạng.

### Phân biệt PNG gốc và ảnh hiển thị qua tool

Tool có một lỗi `element 80 is not available in cached app state`; sau refresh,
thao tác theo screenshot của modal hoàn tất. Trường focus accessibility của
file dialog cũng không khớp ô có con trỏ; dùng ô tên file quan sát được trước
khi gõ. Không dùng index/focus sai làm bằng chứng app đã thao tác đúng.

Ảnh crop đầu hiển thị qua tool trông đen; refresh/chọn/activate đúng target
một lần vẫn vậy, còn ảnh câu hai có lúc chỉ hiện ký tự thay đổi. **PNG capture
gốc đã lưu không đen**: hai vùng chữ câu đầu có **4.363 +4.074 pixel sáng**;
RGB của từng vùng khớp byte-for-byte với preview đã thấy rõ trước scan, kể cả
PNG trước/sau activation và sau chọn cue. Câu hai có **4.640 +4.074 pixel sáng**;
vùng sai khác chỉ nằm ở ký tự thay đổi. Câu ba khớp hai vùng chữ câu đầu.
Đây là kiểm pixel trên PNG GUI frozen, không dùng source preview để thay gate.

Không kéo splitter, resize, đổi painter hoặc gọi model để khắc phục hình nhìn
đen. Lượt này có bằng chứng nội dung chữ trong PNG gốc; chưa xác định tầng nào
của đường capture/hiển thị gây khác biệt, không suy mọi lần crop đen lịch sử
cùng nguyên nhân hoặc native teardown đã được sửa.

Harness đối chiếu PNG ban đầu exit 1 vì đòi toàn canvas (gồm phần ngoài chữ/ROI)
giống nhau. Diagnostic xác nhận hai vùng chữ khớp bytes; sửa phép so để kiểm
đúng hai vùng chữ, giữ số đo toàn canvas và lỗi lần đầu trong evidence. Lượt
validation cuối exit **0**, không sửa PNG/raw/đáp án hoặc chạy OCR/GUI lại.

### Bảo toàn và phạm vi còn mở

**24 tệp được theo dõi giữ SHA**, gồm settings master/ASR-S3/các artifact,
EXE/manifest/fixture/review cũ và source dialog/test/spec/README. Giữ cả gói C
mới lẫn `Temp/vcm910/`; chỉ thêm review/output evidence mới. Evidence tại
`build/ocr-pilot-20260910/ocr4-relocated-gui-16/`: monitor, verification harness,
process/preservation/validation receipts, review JSON, PNG GUI và stdout/stderr.
Không đưa dữ liệu này vào Git. Phiên này chỉ sửa biên bản này, `status.md` và
`docs/dev/ocr-next-session-prompt.md`; chưa commit/push.

Không rerun offline suite/Ruff/Pyright/translations/build hoặc hash lại toàn
49 GB chỉ để có số pass mới; không đổi code/resource. Kiểm mới là GUI frozen,
document/capture/process/preservation và `git diff --check`.

Gate scan/runtime-check/crop/save-reopen trên GUI gói C đã có bằng chứng mới.
**Chưa máy sạch**, chưa thử từng ASR/TTS runtime hoặc workflow online/video
riêng trên bản C. Flow export/handoff/undo/redo/cancel/close-while-busy dùng
evidence GUI ổ D trước đó; không gọi chúng là lượt nghiệm thu mới tại C.
Review hỗ trợ Việt, lỗi câu 4 thiếu chữ, hiệu chuẩn, native teardown
`0xC0000005`, cache disk/quota, resume inference, downloader/update OCR và
subtitle stream extraction vẫn mở; cần phạm vi user giao cho phần tiếp theo.

## Snapshot trước: copy và kiểm gói, chưa thao tác OCR GUI

Tiếp tục ASR-S3 `codex/asr-s3-native`, HEAD **a528d85**, khớp tracking và
remote trực tiếp ở đầu phiên. Giữ nguyên source/test/spec cùng các tài liệu
đang sửa; phiên này chỉ bổ sung validation và bàn giao, chưa commit/push.
Không build, stage lại từ các cài đặt gốc, tải dependency/model hoặc gọi API.

## Gói được di chuyển

Dùng nguyên artifact đã có ở `dist/VideoCaptioner-OCR4-Media-20260911/`.
Sao chép EXE, `_internal/` và toàn bộ `models/` sang thư mục test mới ở ổ C:
`Temp/vco911/VideoCaptioner-OCR4-Media-20260911/`. Không sao chép `AppData/`
và `work-dir/` đã sinh khi nghiệm thu; bản test có settings mới chỉ tắt check
update/VieNeu auto-update, không credential. Fixture/review tổng hợp được chép
vào work-dir của bản test và kiểm hash, để các lệnh EXE dùng input/output/cwd
ở ổ C. Evidence tập trung trong scratch OCR cũ trên ổ D.

Giữ artifact nguồn, artifact OCR cũ và bản `Temp/vcm910/` từng bị chặn xóa.
Không xóa, di chuyển hoặc sửa bản test cũ. Bản mới ở ổ C cũng được giữ lại.

- Robocopy **exit 1**, nghĩa là có file được copy thành công; **0 failed /
  0 mismatch**, wall **75,547 s**. Đây không phải exit code PyInstaller.
- **129.628 file /49.321.971.851 byte** trong payload được chép. Manifest model
  giữ nguyên bytes, đủ tám component như gói nguồn. Không có symlink/junction
  trong bản đích; không phụ thuộc liên kết về ổ D.
- **127.610 file model/runtime /48.739.395.432 byte** khớp từng size/SHA-256
  theo manifest đã verify. **2.017 file ứng dụng/phụ trợ** còn lại khớp nguồn;
  tập đường dẫn đích khớp đầy đủ, cộng một file manifest. Kiểm hash/inventory
  **291,844 s**; tổng copy và verification **367,672 s**, không phải thời gian OCR.
- EXE **31.385.758 byte**, mtime local **2026-09-11 00:44:04**, SHA-256
  `5bee44fd3277a9fb8c8239f51d28684a3d99e4b01024ed470825ca6727873d80`.
  Binary không thay đổi; gate build/source parity ở
  [biên bản media bundle](ocr-media-bundle-2026-09.md) vẫn là phép đo trước.

## Gate tại ổ C

Các lệnh EXE và interpreter nhận PATH chỉ có `Windows/System32`; bỏ các
override Python/Qt/runtime liên quan khỏi môi trường con, dùng
`child_environment()` để lọc credential của app. Không truyền root/runtime/
bridge hoặc đường dẫn media tool tường minh cho lệnh frozen review/status.

| Gate | Kết quả mới | Phạm vi bằng chứng |
| --- | --- | --- |
| Media executable | FFmpeg và FFprobe `-version` đều exit 0 | Cặp static trong `_internal/resource/bin` ở ổ C |
| Frozen review pending | Exit **5**, không tạo subtitle; save/load document bằng bản nguồn | Sáu issue vẫn mở; không auto-accept |
| Frozen review đã duyệt | Exit **0**, JSON subtitle khớp kết quả cũ; document giữ nguyên | Review/resume tại máy, không inference lại |
| Media discovery của EXE | Watcher thấy FFprobe thuộc chính gói ổ C trong cả hai lượt review | Không dùng FFprobe từ PATH/cài đặt dev |
| Frozen `local-asr status` | Exit **0**, thấy Qwen 0.6B/1.7B, aligner, Community-1 | Locator/file status; chưa health/inference mới |
| Packaged Python OCR | Python **3.12.13**, stdlib/NumPy/cv2/ONNX Runtime/RapidOCR nằm trong runtime ổ C | Import với `-I -B`; sys.path không có checkout dev |
| Crop với media đã di chuyển | **3/3 crop tổng hợp** đúng PTS/ROI và khớp SHA RGB candidate | Source preview core gọi tường minh cặp media ổ C; không phải thao tác GUI frozen |
| Native GUI startup/close | Cửa sổ sau **1,203 s**, sống đủ **30 s**, tổng **31,093 s**, exit **0** | Đúng EXE ổ C, 0 child sót, không traceback stderr |

Interpreter OCR nhập RapidOCR **3.9.2**, ONNX Runtime **1.29.0**, NumPy **2.5.3**
đã đóng gói; không đổi package. Harness chặn socket network và khởi tạo ONNX
session trước import RapidOCR: **0 network attempt /0 ONNX session attempt**.
Không nạp weights, khởi động worker OCR hoặc gửi request nhận dạng. Không chạy
lại import/health của từng runtime ASR/TTS đã kiểm ở phiên cũ.

Preview dùng fixture tổng hợp đã có, không đụng 13 crop pilot riêng. Đã nhìn
PNG câu đầu: chữ hai dòng rõ. Kiểm ba SHA là bằng chứng crop decoder; không
suy từ PNG này rằng cửa sổ GUI ở ổ C đã hiển thị crop đúng. Phiên này không có
runtime Computer Use native khả dụng để thao tác review trên bản đã di chuyển;
GUI chỉ được harness kiểm cửa sổ startup và đóng đúng process test. Flow/crop
GUI tương tác ở ổ D vẫn giữ bằng chứng phiên trước.

## Bảo toàn và giới hạn

Settings master/ASR-S3/artifact nguồn/bản C cũ, EXE nguồn, manifest nguồn và
bản C cũ, fixture/review/output tổng hợp gốc giữ hash. Settings và input mới
ở ổ C cũng giữ hash sau test. `README.md`, spec, source dialog và test OCR
giữ hash của đầu phiên. Không thay raw, ID, timing, quyết định review hoặc
inventory model; không can thiệp painter/native teardown.

Evidence: `build/ocr-pilot-20260910/ocr4-relocation-15/`, gồm copy log,
`copy-verification.json`, `app-payload-hashes.json`, `relocation-result.json`,
preservation receipt, stdout/stderr, ba PNG crop và hai harness. Raw/log/media/
receipt có đường dẫn local nằm ngoài Git. Tổng phiên **0 CPU model request /
0 vision request**, không đọc key, không tăng cap request crop 5.

Đã kiểm copy toàn payload sang ổ C, hash, local frozen review/media discovery,
packaged OCR imports và GUI startup/close. **Chưa phải máy sạch**: ổ D và các
cài đặt dev vẫn tồn tại; không có phép theo dõi mọi file/DLL access của toàn
app. Chưa chạy OCR scan từ gói ổ C hoặc thao tác GUI runtime-check/crop/review
tại đó; chưa nghiệm thu inference mới của từng ASR/TTS runtime hay API.
Không gọi toàn bộ tính năng OCR portable hoặc chất lượng đã hoàn tất.

Review hữu dụng bằng tiếng Việt, lỗi câu 4 đồng thuận nhưng thiếu chữ, hiệu
chuẩn, native teardown `0xC0000005`, cache disk/quota, resume inference và
downloader OCR còn mở. Các phần mở rộng cần phạm vi user giao tiếp; không dùng
validation này để tự tăng vision budget hoặc auto-accept.

Không rerun full offline/Ruff/Pyright/translation/build chỉ để có số pass mới:
không sửa code/resource. Gate nguồn **1.739 pass/5 skip/51 deselected** trước
đó vẫn là lịch sử. Harness mới syntax/exit 0 và `git diff --check` pass;
không có gate mới fail/skip. File tài liệu sửa trong phiên: biên bản này,
`status.md`, `docs/dev/ocr-next-session-prompt.md`.
