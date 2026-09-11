# OCR vision crop 5 và phục hồi nhật ký yêu cầu — 2026-09-11

Tiếp tục ASR-S3 `codex/asr-s3-native`, HEAD **a528d85**, giữ toàn bộ thay đổi
ReviewVI/media/UI trước đó. User yêu cầu test AI đọc ảnh bằng gateway/key đã
dùng cho Terra và báo mất chức năng nhật ký. Khi được hỏi model cho lượt mới,
user chọn rõ **gpt-5.6-terra, thử lại crop 5 còn thiếu**: tối đa một request
mới, 1.000 completion token, không retry tự động. Không gọi GPT-6 Astra hoặc
đổi endpoint/backend theo tên model của agent.

## Vision thật: một lượt đã được duyệt

Endpoint `https://api.videocaptioner.cn/v1`, model `gpt-5.6-terra`, timeout
300 s. Key đọc từ file riêng user chỉ định vào RAM, không settings/argv/env/
log/Git. Dùng lại crop 5 gốc, đúng hash và prompt đã pin, cùng hai receipt cũ.
Không gửi ảnh đã có kết quả thành công, transcript, tham chiếu hoặc ảnh lân cận.

Preflight lần đầu dừng **trước đọc key/API** vì prompt scratch CRLF khác hash
LF đã pin, đúng lỗi lịch sử được ghi trong bàn giao. Chuyển sang file nguồn
`scripts/ocr_pilot_data/vision-prompt.md` khớp hash; không sửa prompt/crop/plan
hoặc receipt cũ. Lỗi preflight được giữ trong evidence, không tính là API attempt.

| Lượt mới | Kết quả |
| --- | --- |
| Request/response mới | **1/1**, HTTP 200 |
| Model ID trả về | `gpt-5.6-terra`; không suy backend từ alias |
| Thời gian đo ở harness | **15,607 s**, có ghi metadata journal |
| Prompt/input token | **8.890** |
| Completion/output token | **43** |
| Total token | **8.933** |
| Cached input provider báo | **7.488**, đã nằm trong input |
| Reasoning token | Không cung cấp, không ghi 0 |
| Chữ crop 5 | Đủ chữ, exact với tham chiếu agent đã lưu |

Đầu vào đã chọn chỉ là crop phụ đề. Provider không tách riêng token ảnh và
token text trong tổng input; không ước lượng hai phần hoặc giá tiền từ alias.

Tổng pilot sau lượt này là **14 attempts /13 response /1 timeout cũ**,
một retry tường minh, **0 retry tự động**, app vision cache 0. Usage xác nhận
của 13 response: **46.980 input +651 output =47.631 token**, trong đó provider
báo **34.368 cached input**. Usage timeout cũ, tổng đủ 14 attempts và cost tiền
vẫn `null`. Không cộng cached/reasoning thêm vào total.

Đủ 13 crop giống nhau: local **10/13 exact, 12/13 đủ chữ-số**; vision **9/13
exact, 13/13 đủ chữ-số**. Khác codepoint dấu câu không tự là sai nghĩa.
Tham chiếu chưa native-confirmed, không chốt engine thắng/thua hoặc tự duyệt.
Lỗi chữ ở câu 4 của local chưa được sửa; không OCR lại video hoặc chạy model local.

Evidence: `vision-terra-03/` giữ raw/usage/metrics mới;
`vision-combined-04/` giữ so sánh và report Việt mới. **23 file được theo dõi
giữ hash**, gồm 13 crop, prompt/plan/manifest và raw/receipt hai lượt trước.
Cap 14 đã dùng hết; không có lượt vision tiếp theo được duyệt.

## Nguyên nhân và sửa nhật ký

Menu **Nhật ký yêu cầu** vẫn được đăng ký trong main window. Logger cũ dùng
HTTPX hook đồng bộ và `ContextVar`, nhưng luồng dịch/tách/tối ưu mới dùng
`OwnedLLMRequest`/`AsyncOpenAI` riêng, không nối logger. Vì vậy những request
đó không có dòng nhật ký. Log detail còn gọi `.get()` trên usage `null`, và
bảng cũ hiển thị thiếu usage thành 0 token.

- `OwnedRequestLog` giữ snapshot request/task/stage riêng cho mỗi request và
  ghi đúng một kết quả cuối, tránh dựa vào context của HTTP task con. Nối vào
  `OwnedLLMRequest`: success, HTTP error, timeout, cancel và lỗi khác có
  status/duration/outcome; không ghi exception body chứa dữ liệu riêng tư.
  Giữ retry/timeout/cancel/socket ownership hiện có, không đổi translator policy.
- Nhật ký dịch text thông thường giữ request/response như tính năng cũ;
  lọc key và dữ liệu media. OCR draft và vision dùng `log_content=False`,
  chỉ ghi model/tham số/đếm text-ảnh/status/usage, không prompt text, ảnh
  base64, OCR raw hoặc response text. Raw pilot riêng vẫn chỉ nằm trong scratch.
- OCR draft có task/stage `ocr-review-translate`; pilot có `ocr-vision`.
  Logger đồng bộ cũ vẫn giữ đường đi trước đó; không tuyên bố các lỗi của
  mọi provider/ASR/TTS đều được tính vào nhật ký LLM.
- Giao diện thêm **Trạng thái**, chi tiết/tooltip có input, output, total,
  cached và reasoning. Thiếu usage hiện **—**, phân biệt với 0 được báo thật.
  Total chỉ suy từ input+output khi đủ cả hai; cached/reasoning không cộng lại.
- Watch thư mục cha nếu chưa có journal để thấy request đầu tiên; refresh
  khám phá lại ngày/file mới; không giữ hàng cũ khi ngày đang chọn không còn file.
  Không xóa hoặc di chuyển log cũ của user.
- Root fixture cô lập `request_logger.LOG_PATH`, để test dùng SDK/HTTP mock
  không ghi nhật ký tổng hợp vào AppData thật.

## Gate source và giới hạn

- Scoped đầu **91 pass**; scoped LLM/translate/OCR/UI sau bổ sung **343 pass /
  14 deselected**, 32,07 s, exit 0. Full offline có FFmpeg/Qt offscreen:
  **1.774 pass /5 skip /51 deselected**, 158,31 s, exit 0. Skip là 4 TTS cần
  key/service và 1 QtMultimedia backend. 11 test mới, gồm thực SDK qua transport
  giả, concurrency/context, timeout/cancel/error, không lộ key/ảnh và log đầu tiên.
- Ruff app/tests/pilot pass; Pyright app **0 error/0 warning**; translations
  in sync. Không thay dependency hoặc model/runtime.
- Native source log viewer mở chính journal của request thật: row có model,
  **8933 token**, trạng thái thành công, detail có input/output/cached và
  reasoning chưa cung cấp. Không gọi API thêm khi xem log. Harness đầu đã
  lưu ảnh/receipt rồi exit 1 vì stdout cp1252 không in được tiếng Việt;
  sửa stdout ASCII và nền wrapper theo host, lượt sau exit 0. Không sửa painter.
- Chưa nghiệm thu dịch Việt thật của ReviewVI, AI vision trong GUI, GPU OCR,
  hiệu chuẩn, cache disk/resume inference hoặc native full-suite teardown cũ.

Evidence sửa/kiểm log: `build/ocr-pilot-20260910/ocr4-request-logs-18/`.
Chưa commit/push; các artifact cũ và gói C giữ nguyên. Bản build mới và các
gate frozen được ghi riêng bên dưới.

## Gói EXE mới

`dist/VideoCaptioner-OCR4-RequestLogs-20260911/`, nguyên gói onedir với models
và media. Dùng lại payload đã verify, một spec và workpath mới trong scratch;
không stage/tải model từ cài đặt gốc. Giữ các bản Media/ReviewVI và gói C.

1. **Build:** PyInstaller exit **0**, **309,985 s**, **6 warning /0 error**
   (js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit); warning dependency
   Python giữ trong log, không đổi package.
2. **Artifact:** EXE **31.401.858 byte**, local **2026-09-11 11:59:16**, SHA-256
   `045f2e3fdb7c011e450e76cd2a2d87af9da0217da96e3564696c97d5dcdce598`.
   **127.610 file model /48.739.395.432 byte** ở đích mới khớp toàn bộ SHA
   manifest. Media/worker/profile khớp nguồn; **7 module** khớp code trong PYZ,
   host không chứa dependency OCR nặng. Verification **117,016 s**.
3. **GUI startup/close:** PATH Windows/System32, settings mới tắt update, không
   key. Cửa sổ **3,109 s**, sống 30 s, tổng **31,515 s**, đóng đúng PID, exit
   **0**, 0 child/traceback, settings giữ hash. Chưa click log viewer từ GUI frozen.
4. **Frozen CLI logging:** dịch một SRT tổng hợp qua HTTP mock chỉ ở loopback:
   EXE exit **0**, một HTTP request và đúng một journal entry success, output
   đúng fixture, server/thread đóng, settings giữ hash. Usage 12/6/18 là
   **số giả lập**, không cộng vào usage gateway hoặc kết quả chất lượng.
   Harness đầu exit 1 vì đoán phải có hai request; app/ghi log đã thành công.
   Kiểm lại receipt với contract một entry cho mỗi request quan sát được pass,
   giữ lỗi cũ và không chạy request lần nữa.

Chưa chạy gateway thật từ EXE hoặc thao tác GUI log viewer trong EXE. Evidence
API thật và native source viewer ghi riêng; không dùng mock/startup thay gate đó.
Không chép journal API riêng, settings/key hay dữ liệu cá nhân vào gói mới;
AppData mới chỉ có settings smoke và log/cache tổng hợp do test artifact tạo.
Không chạy OCR scan, model ASR/TTS hoặc dịch Việt thật của ReviewVI trong phiên.

## File thay đổi trong lượt này

- `videocaptioner/core/llm/request_logger.py`, `owned_request.py`, `log_summary.py`.
- `videocaptioner/core/ocr/assistance.py`, `videocaptioner/ui/thread/ocr_thread.py`,
  `videocaptioner/ui/view/llm_logs_interface.py`, `scripts/ocr_vision_pilot.py`.
- `tests/conftest.py`, `tests/test_llm/test_owned_logging.py`,
  `tests/test_llm/test_daily_logs.py`, `tests/test_ocr/test_assistance.py`,
  `tests/test_ui/test_ocr_assistance.py`.
- `README.md`, biên bản này, `docs/dev/ocr-gui-2026-09.md`, `status.md` và
  `docs/dev/ocr-next-session-prompt.md`.

Giữ nguyên phần thay đổi sẵn có của spec, dialog OCR, test OCR cũ và các tài
liệu/artifact trước đó. `git diff --check` pass; chưa commit/push. Tổng mới
**1 vision request thật /0 retry tự động /0 CPU OCR /0 text LLM gateway**;
unit tests và một request loopback của frozen có phạm vi riêng.
