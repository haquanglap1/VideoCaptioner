# Prompt phiên tiếp theo — OCR ReviewVI, nhật ký và vision đủ 13 crop

Tiếp tục **VideoCaptioner-ASR-S3**, nhánh **codex/asr-s3-native**, không làm
ở checkout master. Đây là bàn giao snapshot ngày **2026-09-11** mà user yêu
cầu submit/push. Quyền đó chỉ áp dụng snapshot vừa chốt, không tự cấp quyền
commit/push code mới, gọi thêm API, tải model hoặc đổi dependency.

## Bắt đầu

1. Đọc đầy đủ `AGENTS.md`, `README.md`, mục mới nhất của `status.md` và:
   - `docs/dev/ocr-request-logs-2026-09.md`: logger, API/token và EXE mới nhất.
   - `docs/dev/ocr-review-assistance-2026-09.md`: bản Việt tham khảo, cache/guard.
   - `docs/dev/ocr-relocation-2026-09.md`: gate GUI ổ C đã qua.
   - `docs/plans/video-subtitle-ocr-integration-plan.md`: phạm vi tổng thể.
   Đọc thêm tài liệu GUI/document/runtime khi cần contract hoặc lịch sử;
   không dùng snapshot cũ thay trạng thái hiện tại.
2. Chạy `git status --short --branch`, lấy HEAD thật, đối chiếu tracking/origin.
   **a528d85 là mốc trước snapshot này**, không phải HEAD cần checkout về.
   Các câu "chưa commit/push" trong biên bản cũ mô tả thời điểm nghiệm thu.
3. Giữ mọi thay đổi ngoài task và mọi artifact/evidence/settings/media/key/log.
   Không reset, merge master, tag/release hoặc chạy lại gate chỉ để có số pass mới.
   Không mở lại ASR để trì hoãn OCR.

## Hiện có trong ứng dụng

- OCR tích hợp là **RapidOCR3.9.2 /ONNX Runtime CPU1.29.0 /PP-OCRv5 mobile
  detector + Chinese server recognizer**, pin model/dictionary/profile.
  Runtime riêng; host Qt không import/bundle NumPy/cv2/ONNX/RapidOCR/Paddle/Torch.
  **Chưa GPU OCR hoặc AI vision trong GUI**; không đổi mặc định theo tên model.
- GUI **Nhận dạng → OCR phụ đề trong hình** có chọn video/đoạn, preview và kéo
  một ROI cố định hoặc nhập tọa độ. **Chỉ vùng cắt được đưa vào OCR**; không tự
  nhận toàn khung. Có xử lý SAR/rotation/letterbox, crop review đúng PTS/SHA.
  Chữ chạy/karaoke/nhiều vùng động và inpaint chữ gốc chưa thuộc MVP.
- Streaming PTS/time base, queue thực4/bound8 ROI payload/tối đa3 ảnh mỗi track;
  tracking/consensus/cache RAM, backpressure, timeout/cancel/kill tree/readers
  join, contextvars và worker supervisor. Không list ảnh toàn video trong RAM.
- `VisualSourceIdentity` dựa trên toàn snapshot hình/stream/geometry/time base/
  origin/selection, không AudioIdentity. `ocr-document-v1` giữ stable IDs,
  raw/candidates/edited và measured timing/PTS/uncertainty/profile; save/load atomic.
  Resume hiện là **review scan đã đủ**, chưa resume inference của scan bị hủy.
- Review chỉ chọn nguyên chuỗi một candidate engine đã đọc, có lý do; timing
  override riêng. Không ghép chữ, đổi giản/phồn, tự sửa tên hoặc LLM điền thiếu.
  Profile chưa hiệu chuẩn: đồng thuận vẫn có thể cùng sai. Pending/incomplete
  không xuất success; **scan100% không tự duyệt**.
- Handoff typed sang bảng/editor giữ raw/IDs/OCR metadata, không giả ASR native/
  speaker và không tự dịch/TTS/optimize/split. Editor mutation qua CommandStack;
  normal save JSON+SRT, ASS chỉ action riêng; split cần text boundary tường minh.
- **Bản Việt tham khảo:** bấm nút mới gửi đúng text của một candidate tới LLM
  đang cấu hình. **AI chưa nhìn ảnh**; không gửi ảnh/video/câu lân cận/path.
  Một request/action, retry tự động0, tối đa1.000 completion token, timeout1–600s.
  Cache RAM tối đa64 candidate, chưa lưu vào review JSON; không sửa raw hoặc duyệt.
- **Nhật ký đã phục hồi:** `OwnedLLMRequest` từng bỏ qua logger cũ. Nay request
  có record riêng giữ context/request/response/status/time/usage, cả HTTP lỗi/
  timeout/cancel. Text thường giữ nội dung như trước; OCR draft/vision chỉ
  metadata/usage, không key/chữ/ảnh base64. UI có Trạng thái/cached/reasoning;
  thiếu usage hiện **—**, không0. Cached/reasoning nằm trong input/output.
  Tự thấy journal đầu tiên; refresh ngày/file mới; không xóa log cũ của user.

## Vision — cap 14 đã dùng hết

- User chọn **`https://api.videocaptioner.cn/v1`**, **`gpt-5.6-terra`**, timeout300s;
  key trong `Api.txt` theo vị trí user đã chỉ định. Không hỏi lại cấu hình,
  dùng STT key hoặc suy backend từ alias. Chỉ đọc key khi có lượt API được phép;
  key ở RAM, không settings/argv/env/log/Git.
- `vision-terra-01/` và `vision-terra-02/` có13 attempts/12 response/crop5 timeout.
  **User đã duyệt và đã dùng đúng một retry crop5** tại `vision-terra-03/`:
  HTTP200, **15,607s**, chữ đủ/exact với tham chiếu agent đã lưu.
- Lượt mới: **8.890 input +43 output =8.933 token**, cached input **7.488**
  đã nằm trong input, reasoning không cung cấp. Không tự tách token ảnh/text.
- Tổng **14 attempts/13 response/1 timeout cũ**, một retry tường minh,
  **0 retry tự động**, app cache0. Usage13 response: **46.980 input +651 output
  =47.631 token**, cached input **34.368**. Usage timeout/toàn đủ14 attempts/cost
  vẫn **null**; không cộng cached thêm lần nữa.
- `vision-combined-04/`: cùng13 crop, local **10/13 exact,12/13 đủ chữ-số**;
  vision **9/13 exact,13/13 đủ chữ-số**. Khác dấu câu/codepoint không tự là sai
  nghĩa; tham chiếu chưa native-confirmed, không chốt engine thắng/thua.
- **Không gọi thêm vision hoặc lặp recipe retry cap14 với chỉ hai receipt cũ.**
  Submit/push hoặc "tiếp tục" chung không tăng cap. API mới cần phạm vi user
  giao rõ và ledger tính đủ attempts đã có, kể cả timeout.
- Dùng **`scripts/ocr_pilot_data/vision-prompt.md`**, LF/hash khớp plan.
  Scratch `vision/prompt.md` là CRLF khác hash; preflight đã từng dừng trước
  key/API. Không sửa hash/prompt/plan/receipt/input để né guard. Chỉ gửi một crop
  và prompt chung; giữ raw/usage/latency trước khi chấm, không gửi đáp án tham chiếu.

## Artifact mới nhất — dùng lại

**`dist/VideoCaptioner-OCR4-RequestLogs-20260911/`**, nguyên gói onedir.

- EXE **31.401.858 byte**, local **2026-09-11 11:59:16**, SHA-256
  `045f2e3fdb7c011e450e76cd2a2d87af9da0217da96e3564696c97d5dcdce598`.
- Build exit0, **309,985s**, 6 warning PyInstaller/0 error (js/emscripten,
  curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit); giữ warning dependency trong log.
- **127.610 model/runtime file /48.739.395.432 byte** khớp SHA tại đích mới,
  đủ bộ đã có Faster-Whisper, Qwen/aligner, Community-1, OmniVoice, VieNeu và OCR.
  FFmpeg/FFprobe ở `_internal/resource/bin`; 7 module khớp PYZ, OCR nặng không vào host.
- GUI frozen mới **chỉ startup/close**: PATH Windows/System32, settings mới
  không key, hiện3,109s/sống30s/exit0/0child/không traceback.
- CLI chính EXE dịch SRT tổng hợp qua loopback mock: exit0, **một request/một
  journal**, output đúng. Usage12/6/18 **giả lập**, không cộng vào usage gateway.
  Harness đầu đoán hai request nên exit1; kiểm receipt đúng contract pass,
  giữ lỗi và không chạy request lần nữa.
- **Chưa** gateway thật từ EXE, click log viewer hoặc dịch tham khảo qua GUI
  frozen. API thật và native source log viewer là evidence riêng. Journal API
  riêng không được chép vào gói; AppData artifact chỉ có smoke/mock data.

Build sau vẫn một `VideoCaptioner.spec`. Chỉ khi code/resource thực sự đổi:
dùng `VC_TEST_MODELS_DIR` trỏ `models/` đã verify và `VC_TEST_MEDIA_TOOLS_DIR`
trỏ thư mục cặp static đã cài của artifact hiện có. **Không thêm
`VC_TEST_OCR_MODELS_DIR`** vào bộ đã có OCR. Dùng tên/output/workpath mới,
kiểm target trước `--clean`; không bỏ owner/inventory/hash guards. Không stage
lại48GB từ cài đặt gốc, tải model hoặc cài dependency để đóng gói.

## Gate và việc tiếp theo

- Source mới nhất: scoped **343 pass/14 deselected**, full offline FFmpeg+
  Qt offscreen **1.774 pass/5 skip/51 deselected**, **158,31s**, exit0.
  Ruff/Pyright0/0, translations in sync. Skip4 TTS cần key/service,1 QtMultimedia
  cần backend native. Không coi offline/skip là nghiệm thu online.
- Native source đã thấy review Việt với response tổng hợp và log viewer đọc
  journal API thật (8933 token/status/input/output/cached/unknown reasoning).
  Lỗi stdout/font wrapper của harness không phải fix painter của app.
- Gói **Media-20260911 tại C** đã qua scan/runtime-check/crop/save-reopen GUI:
  fixture1,9s/13frame/3cue/6candidates,3/3 câu hai dòng exact,2request/2response,
  job2,391s/inference0,210s; progress100 nhưng6issue còn review/export khóa.
  Python/bridge/model/media từ góiC, exit0/0child/jobs rỗng,24file giữ hash.
  **Chưa máy sạch**, bảnC chưa có ReviewVI/logger mới.
- Flow GUI EXE ở D cũ đã qua CPU/review/undo-redo/export/handoff bảng/editor/
  save-reopen/cancel/close-while-busy trên fixture. Không gọi đó là gate mới
  của GUI RequestLogs. Không rerun OCR/API/build/hash49GB chỉ để tăng số pass.

Ưu tiên tiếp là nghiệm thu **nhật ký và review Việt trong GUI của chính EXE
RequestLogs hiện có** khi user giao tiếp flow này; dùng fixture/mock/dữ liệu cũ,
không tự gọi gateway. Công cụ GUI phải thật sự khả dụng, chỉ đúng process test
và đóng sạch; không dùng Computer Use cho file/code. Source render/CLI mock
không thay click GUI frozen.

Chất lượng còn vướng **câu4**: cả ba ảnh local bỏ chữ "tháng".
`local-bounded-crop04-07/` có crop sát detector box giữ chữ nhưng khác dấu,
bản2× lại thiếu. Không tự bật biến thể, sweep model/GPU hoặc thay raw. Bản Việt
từ text không xác minh ảnh và không sửa được lỗi này; không giao user nhiệm vụ
tự chấm từng chữ Trung để vượt guard.

Các phần tiếp theo cần phạm vi user giao: visionGUI, hiệu chuẩn, lưu bản Việt,
cache disk/quota, resume inference, downloader/update OCR, trích subtitle stream
text/PGS. **Chưa có** các phần này; selector/check runtime không phải installer.
Native full-suite teardown **0xC0000005** cũ chưa được xác định/sửa. Capture đen
có bằng chứng sai target/ảnh hiển thị khác PNG gốc; các lần sau PNG chứa đủ chữ.
Không sửa painter/kéo splitter theo suy đoán hoặc quy mọi lỗi cũ về một nguyên nhân.

## Evidence và dữ liệu phải giữ

Scratch duy nhất **`build/ocr-pilot-20260910/`**, ngoài Git:

- `ocr4-request-logs-18/`: gates, live journal, preservation, tests/build,
  native source PNG/receipt, frozen smoke/mock. `vision-terra-03/` và
  `vision-combined-04/` giữ raw/usage/comparison/report mới;23file cũ giữ hash.
- `ocr4-review-assistance-17/`: gate/EXE ReviewVI; `ocr4-exe-flow-10/` tới
  `ocr4-relocated-gui-16/`: GUI/capture/media/copy/ổC; `ocr3-contract-08/`,
  `ocr4-gui-09/`: contract/fixture/đóng gói đầu. Giữ cả các run lỗi/hủy.
- `inputs/manifest.json` +13 `crop-*.png` gốc1920×80, ROI[0,960,1920,80].
  Không recrop cùng input; giữ `local-final/`, `cpu-sample-final-06/`,
  `local-bounded-crop04-07/`, ledgerCPU, receipt vision01/02 và runtime cũ.
- User cho dùng một trong hai video thật để OCR local; đường dẫn đã kiểm ở
  **`user-test-videos.local.md`**. Không hỏi lại quyền dùng hai đầu vào đó.
  Clip111,333s đã qua sourceOCR:23cue/68request/68response/27,969s; chưa chạy
  bài giảng. Không nhận dạng/dịch/TTS/render lại media/ASR/WAV cũ để lấy số mới.
- Giữ mọi artifact D/C, kể cả `Temp/vcm910/` từng bị chặn xóa và
  `Temp/vco911/VideoCaptioner-OCR4-Media-20260911/`; không né chặn bằng cách khác.
- Host Python **3.12.13**: `../VideoCaptioner/.venv/Scripts/python.exe`;
  FFmpeg/ffprobe từ bộ đã cài hoặc media bundle. Pyright
  `--venvpath ../VideoCaptioner`. Không Python3.13/global install/uv sync/nâng deps.
  Giữ root fixtures cô lập settings/CLI config/OPENAI và **request_logger.LOG_PATH**;
  test QThread qua event loop phải `thread.wait()` trước khi object rời scope.

Chỉ cập nhật status/biên bản khi có thay đổi bền vững. Báo riêng source, isolated
runtime, packaged Python, frozen CLI, native GUI và live API: pass/fail/skip/chưa
chạy. Không gọi OCR toàn sản phẩm hoàn tất từ fixture, mock hoặc build.
