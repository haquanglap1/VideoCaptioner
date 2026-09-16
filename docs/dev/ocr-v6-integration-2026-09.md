# Tích hợp OCR v6 medium — 2026-09-11

**Bổ sung sau nghiệm thu:** [ba gate còn mở đã được khép lại](ocr-final-gates-cleanup-2026-09.md):
sửa race trong helper test VieNeu, full offline 1.794 pass/5 skip, cancel và
đóng hộp thoại OCR khi bận đã kiểm trên chính EXE. Các ghi chú gate chưa qua
bên dưới là snapshot trước lượt bổ sung. Dọn 389 GB bản sao model đã được
user xác nhận nhưng lệnh vẫn bị bộ duyệt tự động chặn; chưa xóa.

Tiếp tục trên `codex/asr-s3-native`, baseline **f274af2**, HEAD/tracking/origin
khớp tại đầu phiên. Tích hợp ứng viên medium theo [kết quả chất lượng đã đo](ocr-quality-v6-2026-09.md).
Không chạy lại ma trận 23 crop, tải model, cài/nâng dependency, gọi API hoặc
commit/push. Cap vision14 đã hết và giữ nguyên.

## Contract và lựa chọn runtime

- Thêm `profile-v6-medium.json`, schema `ocr-profile-v2`: detector/recognizer
  **PP-OCRv6 / medium / multi / ONNX Runtime**, classifier cũ **PP-OCRv4 /
  mobile / ch**, không chạy inference classifier. Mỗi model ghi version,
  loại model, language, engine và dictionary (null ở det/cls).
- Dictionary rec lấy từ metadata ONNX, **18.708 entry**, SHA
  `679f4f4cbbb4f762e84fae998e02c08a556afbd115968104ca3b4aeee5cb2b19`.
  Hai weights medium dùng đúng SHA trong biên bản chất lượng; CPU4/1,
  height48, batch1, preprocessing và raw giữ cách đo trước.
- Worker dùng metadata của recipe, kiểm package/model/dictionary, chặn
  network/download và GPU. Handshake kiểm stage/dictionary trước inference.
  RapidOCR3.9.2 chưa có `LangRec.MULTI`, nên dùng literal `multi` như phép đo.
- `ocr-pilot-profile-v1` giữ byte recipe và cách đọc cũ. Stage metadata v2
  lưu trong `parameters` của snapshot hiện có: không thêm trường JSON làm
  đổi config digest/document ID/cue ID của bản review v5.
  Scan mới bằng v6 có profile/document ID riêng; không gán kết quả mới vào
  document v5 hoặc đòi hai scan khác engine có cùng ID.
- App ưu tiên thư mục `ocr-v6-medium` khi có, dưới `models/` của portable
  hoặc `runtime/` của source/pip. Có thư mục ứng viên bị thiếu/hỏng thì báo
  lỗi, không âm thầm chạy v5; chọn runtime v5 tường minh vẫn được.
  GUI kiểm model hiển thị profile và nhắc chưa hiệu chuẩn.
- CLI không truyền `--profile-sha256` cũng kiểm recipe của runtime đã chọn;
  không lấy SHA v5 cố định khi discovery đã chọn medium.
- Giữ source identity, raw/candidate/edited, review/export guards và lifecycle.
  Không suy auto-accept từ **23/23 đủ chữ-số**; exact cũ là **19/23**,
  tham chiếu agent chưa native-confirmed, chưa benchmark nhiều video/font/nền.

## Đóng gói không thay bộ cũ

Dùng `python -m scripts.package_ocr_candidate --source-models <models-da-verify>
--weights <weights-medium-da-co> --app-dir <dich-moi>` bằng Python3.12 đã có.
Script chỉ lấy environment OCR theo inventory cũ, classifier cũ và hai weights
medium đúng SHA; tạo owner/inventory mới, không lấy lại ASR/TTS từ cài đặt gốc.
Đích không được tồn tại hoặc chứa/lồng vào nguồn; bản copy phải khớp inventory.

Một `VideoCaptioner.spec`, `VC_TEST_MODELS_DIR` trỏ bộ đầy đủ đã verify;
`VC_TEST_OCR_CANDIDATE_DIR` trỏ collection ứng viên mới; media dùng
`VC_TEST_MEDIA_TOOLS_DIR`. Append chỉ vào output mới có owner, giữ toàn bộ
entry/file v5 và ASR/TTS, thêm component `ocr-v6-medium`. Không dùng
`VC_TEST_OCR_MODELS_DIR` cho collection đã có v5; không sửa manifest/weights
của bất kỳ gói cũ nào. Payload ứng viên gồm **4.473 file /448.200.738 byte**.

Evidence ngoài Git: `build/ocr-pilot-20260910/ocr-v6-integration-22/`.
Bộ candidate dùng kiểm source giữ riêng với candidate-pristine để inference
không đưa bytecode cache phát sinh vào inventory đóng gói.

## Nghiệm thu

- Test gần profile/runtime/document/packaging: **62 pass**. Scoped OCR và GUI:
  **164 pass**, 29,50s. Ruff toàn app/tests và script thay đổi pass;
  Pyright app **0 error/0 warning**, translations in sync.
- Source pipeline thật trên `ocr4-gui-09/synthetic.mov` đã có: **13 frame,
  3 cue, 6 candidate, 2 request/2 response, 2 detector/4 recognizer/0 cls**;
  **3/3 câu hai dòng exact**, job3,218s/inference0,298s. Giữ **6 issue**,
  pending export bị chặn; save/load giữ raw/IDs, source identity bằng v5,
  v5 roundtrip không đổi dữ liệu. Jobs rỗng, host không import OCR nặng.
- Harness ban đầu gọi nhầm `to_asr_data` sau khi kết quả đã lưu; giữ lỗi và
  kiểm tiếp file đã lưu bằng `resume`, **không rerun OCR**.
- Full offline FFmpeg + Qt offscreen: **1.791 pass/1 fail/5 skip/51 deselected**,
  182,04s. Fail `test_gui_start_alone_fills_voice_list` ở VieNeu trả danh sách
  trống; chạy riêng `test_vieneu/test_ui_thread.py`: **7/7 pass**, 6,28s.
  Chưa xác định nguyên nhân phụ thuộc thứ tự/timing; không gọi full gate pass.
  Skip vẫn là4TTS cần key/service và1QtMultimedia backend native.
- Rà call site phát hiện CLI còn mặc định SHA v5; đã sửa và thêm regression
  cho lựa chọn SHA tự tìm. CLI/service cuối **155 pass**, 12,65s;
  Ruff pass, Pyright0/0. Không rerun full suite sau thay đổi CLI hẹp này.
- Lượt build đầu dừng có chủ đích trước artifact để sửa đường CLI trên;
  exit15,153,375s, chưa có output EXE/model collection. Giữ log/workpath;
  build cuối dùng workpath mới, cùng tên đích chưa từng được tạo.
- **Artifact:** `dist/VideoCaptioner-OCR6-Medium-20260911/`, nguyên gói onedir.
  PyInstaller **exit0**, thời gian theo log **517,169s**, **6 warning/0 error**
  (js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit); giữ các
  SyntaxWarning của dependency trong log. EXE **31.413.410 byte**, local
  **2026-09-11 15:45:47**, SHA-256
  `211ef75bbc7999f36ab13f357a892f4f88fe9385651deedb31c15aee32bae165`.
  **132.083 file/49.187.596.170 byte** theo inventory ở đích mới khớp SHA;
  toàn bộ entry cũ giữ nguyên, thêm component medium. 7 module khớp PYZ,
  hai profile/bridge/media khớp source; OCR nặng không vào host Qt.
- **Packaged Python:** medium đọc một ảnh fixture hai dòng đã có, **1det/2rec**,
  chữ exact; v5 qua startup/handshake mới, **0 inference**, không đo lại chất
  lượng v5. Cả hai worker/readers/jobs được đóng/dọn theo lifecycle hiện có
  (worker bị taskkill chủ động, exit1; không gọi đó là worker graceful exit0).
- **Frozen CLI:** không truyền runtime/profile override, tự chọn v6 trong gói;
  fixture **3/3 câu exact**,2request/2response, job2,891s/inference0,275s.
  Review có6issue, không tạo subtitle output, **exit5 đúng RUNTIME_ERROR OCR**.
  Một lệnh harness đặt `--config` trước subcommand bị parser từ chối, chưa
  inference. Lệnh sửa đã lưu đủ kết quả nhưng harness đoán exit6; kiểm file đã
  lưu và contract exit5, không chạy OCR lại.
- **Native GUI chính EXE:** tự tìm medium; kiểm SHA, chọn video/selection/ROI,
  scan fixture **3/3 câu exact**,13frame/3cue/6candidate,2request/2response,
  job2,234s/inference0,244s. Progress100 nhưng6issue và export/handoff vẫn khóa.
  Xem crop khớp SHA; save → reopen → save giữ nguyên toàn bộ document,
  raw/IDs/profile/source identity. Không bấm dịch hoặc tự duyệt.
- GUI sống **630,954s** gồm thao tác, đóng **exit0**, **0 child còn lại**,
  jobs rỗng/không traceback; Python/bridge/model/FFmpeg/FFprobe từ chính gói.
  PATH kế thừa chỉ Windows/System32; settings mới không key, autoupdate tắt.
  Watcher50ms không thấy kết nối, không phải trace toàn bộ network/file/DLL.
- Một lần thử hủy GUI đã scan xong trước thao tác hủy có hiệu lực: giữ riêng
  kết quả và counters, **chưa xác nhận cancel GUI v6**, không thử lại để lấy pass.
  **Chưa close-while-busy v6**. Test supervisor/timeout/cancel vẫn là gate
  source; không dùng chúng thay gate GUI chưa bắt được.

Script hậu kiểm build ban đầu đọc manifest25MB cho từng entry nên chậm;
đã dừng riêng vòng kiểm sau khi lấy **exit0 của PyInstaller bằng Windows
GetExitCodeProcess**, rồi đọc manifest một lần để tiếp tục. Không rebuild.
Computer Use có lỗi index UIA của modal dù tree còn index; dùng screenshot
để thao tác. File dialog Windows từ chối đường dẫn dùng slash xuôi; sửa
thành backslash và lưu đúng đích mới. Không sửa app để che lỗi harness/tool.

Tổng các gate thật của phiên: **9request/9response,9det/18rec/0cls**, gồm
source, một crop packaged Python, CLI, GUI scan và lần kiểm hủy đã hoàn tất.
Không cộng lượt startup v5 hoặc save/reopen vào inference. **209 đường dẫn**
bảo toàn đầu/cuối phiên; monitor GUI theo dõi **212 đường dẫn**, đều giữ hash.
Giữ toàn bộ raw/receipt/log của các bước lỗi;0API/0download/0dependency change.

Không nghiệm thu live API, vision GUI, hiệu chuẩn, machine sạch, inference
resume, disk cache/quota hoặc chất lượng sản phẩm trên corpus mới trong phiên này.

## File thay đổi, chưa commit/push

- `videocaptioner/core/ocr/profile.py`, `installation.py`, `runtime.py`, `service.py`.
- `videocaptioner/resources/ocr/ocr_stream_worker.py`, `profile-v6-medium.json` (mới).
- `videocaptioner/cli/commands/ocr.py`, `videocaptioner/ui/components/ocr_dialog.py`.
- `scripts/ocr_stream_worker.py`, `scripts/package_test_models.py`,
  `scripts/package_ocr_candidate.py` (mới), `VideoCaptioner.spec`.
- `tests/test_ocr/test_profile.py` (mới), `test_runtime.py`, `test_service.py`, `test_packaging.py`.
- `README.md`, `status.md`, `docs/plans/video-subtitle-ocr-integration-plan.md`,
  `docs/dev/ocr-v6-integration-2026-09.md` (mới).
