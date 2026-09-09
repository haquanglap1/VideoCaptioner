# Google/DeepLX: lỗi bị nuốt và cache bản dịch thiếu — 2026-09-09

Tiếp tục HEAD `cd127e1039a79284b2f48f12f1ba9557958673da` trên
`codex/asr-s3-native`, worktree `VideoCaptioner-ASR-S3`. Git sạch lúc bắt đầu,
HEAD khớp ref tracking `origin/codex/asr-s3-native` tại máy. Không fetch,
commit/push, đổi dependency hoặc mở lại inference/benchmark/OCR.

## Nguyên nhân và thay đổi

Google và DeepLX từng catch lỗi từng dòng rồi trả chunk như thành công.
Google còn bỏ qua HTTP 400, cắt input ở 5000 ký tự và lấy prefix trước dấu `<`
dù container HTML chưa hoàn chỉnh. DeepLX gán trực tiếp `response.json()["data"]`
mà không kiểm tra kiểu, nội dung hoặc mã lỗi trong payload. Base ghi cache cho
chunk được trả về; namespace cũ có thể giữ bản dịch thiếu hoặc bị cắt.

Hai provider nay kiểm tra response, gom bản dịch tạm và chỉ áp kết quả sau khi
cả batch hợp lệ. HTTP/transport/response lỗi dừng batch; hủy trong request bỏ
kết quả đang chờ và không gửi tiếp các dòng còn lại. Response luôn được đóng;
`close()` join executor qua base rồi đóng session. Thông báo/log lỗi transport
không kèm URL, query chứa credential hoặc body của dịch vụ.

`require_complete_result=True` dùng guard sẵn của base: một chunk lỗi cũng
không được trả thành document thành công, kể cả tỷ lệ lỗi dưới 50%. Chunk khác
đã dịch đủ vẫn có thể báo tiến độ và giữ cache để dùng lại. Không sửa policy
của LLM/Bing hoặc API/flag/config hiện có.

- Google giữ mức giới hạn 5000 ký tự của app nhưng báo cần chia câu trước khi
  gửi bất kỳ dòng nào trong batch quá dài. Container `t0`/`result-container`
  phải có đúng một kết quả text hoàn chỉnh; markup lạ hoặc nhiều container
  báo malformed, không trả prefix. HTML entities và Unicode vẫn được giải mã.
- DeepLX đòi payload object có `data` dạng string; input có chữ không được
  nhận bản dịch rỗng/whitespace. Nếu có `code` thì phải là 200; endpoint chỉ
  trả `data` hợp lệ vẫn được hỗ trợ.
- Cache Google/DeepLX dùng namespace `validated-v2`. Cache cũ được giữ nguyên
  nhưng không đọc lại, kể cả bản cũ có text vì Google có thể đã cắt input.
  DeepLX thêm SHA-256 của endpoint hiệu lực sau ưu tiên explicit/env/default;
  đổi dịch vụ hoặc credential trong URL sẽ tách cache, không lưu URL vào key.
  Target language và nội dung vẫn tham gia key; timeout không đổi nội dung.

## Validation source

- 65 regression đầu: **63 fail / 2 pass trước sửa**, **65 pass sau sửa**.
- Bổ sung 6 ca HTML bất thường/compatibility/endpoint hiệu lực: tổng **71
  regression mới**. Gate translator + toàn CLI + subtitle output policy:
  **309 pass / 15 deselected / 1 warning**, không skip. Các marker
  integration/slow/llm được loại trừ; không cộng lặp với 409 test của ErrorFix.
- Ruff toàn app/tests, Pyright app và translation sync pass. Python 3.12.13
  từ môi trường project đã có; không dùng `uv sync` hoặc cài package.
- Runner riêng chuyển cache/log/settings/work-dir trước khi import pytest/app;
  từng regression dùng diskcache trong `tmp_path`, Session giả và response
  Requests thật. Runner chặn socket ngoài loopback. Không đọc/xóa cache dịch
  thật để dựng fixture. Root conftest và fixture cách ly config giữ nguyên.

Evidence riêng: `build/google-deeplx-errors-20260909/`, gồm
`regression-before.log`, `regression-after.log`, `source-gate.log` và
`run_offline.py`. Lệnh Pyright cuối dùng `--venvpath ../VideoCaptioner`;
lần thử truyền đồng thời `--pythonpath` và `--venvpath` bị CLI từ chối, không
phải lỗi type của source.

## Build và nghiệm thu artifact

Artifact mới: `dist/VideoCaptioner-GoogleDeepLXFix-20260909/`, phân phối nguyên
thư mục onedir. Spec gốc giữ nguyên; build dùng bản sao source/resource riêng
đã đối chiếu SHA-256 **289 file**, để import lúc build chỉ tạo dữ liệu ở scratch.
Không copy video, cache hoặc model/settings thật vào build source.

1. PyInstaller **exit 0 / 238,812 s**, **6 WARNING / 0 ERROR**. Warning
   js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit giống ErrorFix;
   có SyntaxWarning từ dependency. Receipt `build.json`, log `pyinstaller.log`.
2. EXE **31.263.856 byte**, timestamp local **2026-09-09 22:56:08**, SHA-256:
   `064907630f4f15bf35e134b4a2f2d331a4e008b2bb96402b9299fa81d2c7291e`.
   Google/DeepLX/base/Bing trong PYZ khớp source; `packaged-source.json` ghi
   từng module. Hash ErrorFix cũ giữ
   `6d0e54ef6c59522f34f6625e3b1f5124425f9919e94a46b490ff0fdfa16070fa`.
3. Chính EXE mở GUI Windows một lần: sống **26,047 s**, đóng đúng PID exit 0,
   không child còn lại. Một request cập nhật đi qua proxy loopback trả lỗi
   tổng hợp, không ra Internet. Receipt `startup.json`.
4. Google trên CLI frozen nhận SRT tổng hợp, request bị proxy loopback từ chối:
   **exit 5**, thông báo request failed đã che endpoint, input/output có sẵn
   giữ nguyên, cache dịch **0 entry**. Receipt `cli-google-offline-r2.json`.
   Lần đầu helper đặt `--config` trước subcommand nên parser trả exit 2 trước
   request; giữ receipt cũ, sửa vị trí flag và chỉ chạy lại CLI, không lặp GUI.
5. Chưa chạy dịch Google/DeepLX online, DeepLX qua workflow GUI frozen, media
   hoặc inference mới. DeepLX có regression core và đối chiếu bytecode bundle;
   các gate đó không thay thế nghiệm thu dịch vụ thật.

Sau khi đóng process, chuyển nguyên AppData/work-dir của artifact thử vào
evidence, không để settings/cache giả trong thư mục phân phối. Không xóa hoặc
ghi đè ErrorFix/R6. Receipt `artifact-final.json` giữ size/hash cuối và kết quả
kiểm tra process. Không chạy lại helper có cơ chế tạo file độc quyền.

Ngày 2026-09-10, theo yêu cầu dọn dữ liệu tạm của user, evidence được gom vào
`build/google-deeplx-errors-20260909/evidence.zip` (49.722 byte). Cả 36 file
trong archive được đối chiếu SHA-256 với bản gốc trước khi dọn. Các log/receipt/
helper nhắc trong báo cáo nằm trong ZIP; bản sao build-source, PyInstaller
trung gian và test scratch đã chuyển vào Thùng rác, không còn là dữ liệu cần
giữ để dùng app. Ba EXE GoogleDeepLXFix/ErrorFix/R6 được kiểm tra hash giữ nguyên.

## File thay đổi

- `videocaptioner/core/translate/google_translator.py`
- `videocaptioner/core/translate/deeplx_translator.py`
- `tests/test_translate/test_http_failures.py`
- `docs/dev/google-deeplx-errors-2026-09.md`
- `docs/dev/error-fixes-next-session-prompt-2026-09.md`
- `docs/dev/online-media-next-session-prompt-2026-09.md` (bàn giao ngày 2026-09-10)
- `status.md`

Lượt validation ban đầu chưa commit/push; ngày 2026-09-10 user yêu cầu chốt
snapshot này cùng [prompt nghiệm thu online/media phiên sau](online-media-next-session-prompt-2026-09.md).
Lấy HEAD/tracking bằng Git sau commit; quyền này không áp dụng thay đổi mới
ở phiên sau. Build/dist/evidence không đưa vào Git.

## Giới hạn và bằng chứng kế thừa

Test xác nhận xử lý lỗi/shape/cache, không xác nhận dịch vụ Google/DeepLX
online hoặc chất lượng bản dịch. Không gửi transcript thật hoặc gọi API bên
ngoài. HTTP request đang chạy vẫn dùng timeout hiện có; hủy không ngắt socket
tức thì. Markup Google thay đổi sẽ báo lỗi rõ và cần case mới để cập nhật parser.

Kế thừa đúng 409 pass/24 deselected và nghiệm thu ErrorFix trong
[báo cáo Qt/Bing](gui-shutdown-bing-errors-2026-09.md); pipeline với dữ liệu có
sẵn của R6 trong [báo cáo review/resume](dubbing-review-resume-2026-09.md).
Giữ bài giảng đã chốt, video, 151 WAV/cache, model/runtime, settings và artifact
cũ. Bing upstream 404, Qt/SIP ngắt quãng và quality/RTF Qwen không được tuyên bố
đã sửa bởi lượt này.
