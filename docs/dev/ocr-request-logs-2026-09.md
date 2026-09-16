# OCR vision crop 5 và phục hồi nhật ký yêu cầu — 2026-09-11

## Bổ sung mới nhất: sửa footer và layout chi tiết, EXE LogsLayout

Tiếp tục đúng checkout ASR-S3, nhánh `codex/asr-s3-native`; HEAD, tracking và
remote trực tiếp đều **501c6ff**. Giữ ba tài liệu chưa commit của lượt GUI
trước. Phiên này chỉ sửa hai lỗi trình bày đã quan sát, không thay logger,
OCR/review policy, runtime, model, dependency hoặc spec; chưa commit/push.

Footer cũ ghép `共 <số> 条` trực tiếp khi cập nhật nên bỏ qua translator,
dù nhãn khởi tạo có bản Việt. Nay cả khởi tạo và cập nhật dùng cùng chuỗi
`tr("共 {0} 条").format(count)`, dịch thành **Tổng {0} dòng**. Số đếm vẫn là
toàn bộ kết quả lọc, không chỉ số dòng trên trang đang xem.

Hàng metadata chi tiết cũ dùng `QHBoxLayout`, co các pill khi sidebar mở
rộng. Đổi sang `FlowLayout` có khoảng cách ngang/dọc rõ ràng: giữ chiều rộng
theo nội dung và xuống dòng. Time/stage/model/duration/input/output hiện đủ
trong trường hợp đã báo lỗi; giữ nguyên dữ liệu, JSON và semantics usage.
Không sửa painter/crop hoặc coi mọi vấn đề layout của ứng dụng đã giải quyết.

### Gate source

- LLM/CLI offline: **191 pass, 0 skip, 0 deselected**, **6,60 s**, exit **0**.
  Ruff app/tests pass; Pyright app **0 error/0 warning**. Không nâng Pyright
  theo banner phiên bản mới. Không chạy lại full suite cho thay đổi UI hẹp này;
  full offline **1.774 pass/5 skip/51 deselected** bên dưới là gate trước sửa layout.
- Native source với journal tổng hợp, Segoe UI 9: footer đúng ở 0/51 dòng,
  sang trang 2 vẫn đếm 51; lọc còn 1/0 dòng đúng. Các pill không bị co ngang,
  không ra ngoài dialog hoặc chồng lên Request; kiểm chiều rộng parent
  728/1000/728 và xem PNG. Đây là source render, tách biệt gate GUI frozen.
- JSON Việt development/fallback đã sync, `sync_translations.py --check`
  pass. TS Anh/Trung giản thể/Trung phồn thể có placeholder đúng, XML hợp lệ.
  Máy thiếu `lrelease`; QM giữ nguyên, chưa nghiệm thu bản dịch mới của ba
  locale đó trong binary. Không sửa QM bằng tay hoặc cài thêm toolchain.

### Artifact mới và gate GUI frozen

`dist/VideoCaptioner-OCR4-LogsLayout-20260911/`, nguyên gói onedir. Một spec,
tên/workpath mới; dùng lại models/media đã verify của gói Media, không stage
lại từ cài đặt gốc. Giữ nguyên RequestLogs/ReviewVI/Media và các gói tại C.

| Gate mới | Kết quả |
| --- | --- |
| PyInstaller | Exit **0**, **340,906 s**, **6 warning/0 error** (js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit); warning dependency giữ trong log |
| EXE | **31.401.901 byte**, local **2026-09-11 13:23:45** |
| SHA-256 EXE | `3cafde0d06ad335ee44c3606d95d7f730e7a310246f8746f46ca789dcff95276` |
| Payload tại đích mới | **127.610 file /48.739.395.432 byte** khớp từng size/SHA; đủ inventory cũ, không hash lại toàn bộ gói C |
| Source/resource parity | **7 module** khớp PYZ; JSON Việt ở hai vị trí, media và resource OCR khớp; OCR nặng không vào host. Verification **121,500 s** |
| Native GUI 1050×800 | Mở đúng EXE mới, PATH chỉ Windows/System32; sidebar mở/thu gọn đều hiện đủ sáu pill, kể cả usage null |
| Footer và journal đầu tiên | **Tổng 0 dòng → Tổng 4 dòng** tự động khi tạo journal đầu tiên, chưa bấm refresh; lọc ID → **1**, không khớp → **0**, bỏ lọc → **4** |
| Đóng/bảo toàn | GUI sống **219,125 s** gồm thao tác, exit **0**, **0 child** từng được thấy/còn sót, stderr không traceback; **44 đường dẫn** theo dõi giữ nguyên, journal replay cũng giữ hash |

Gate GUI đọc lại **bốn entry metadata mock** của phiên `gui-19`, không khởi
động server hoặc gửi lại request. Usage 120/30/150, cached80/reasoning10 vẫn
là số giả lập cũ; usage thiếu vẫn hiện **—**. Không cộng bốn dòng được chép
vào request/token mới. AppData gói mới chỉ có settings smoke không credential
và dữ liệu test; journal/settings/artifact cũ giữ nguyên. Trước gate mới,
40 đường dẫn dữ liệu/artifact còn khớp receipt bảo toàn của phiên trước.

Watcher 50 ms không thấy kết nối mạng; không phải trace mọi kết nối/file/DLL.
Computer Use `set_value` gặp lỗi thuộc tính UIA cache **0x80070057**; refresh
thấy ô tìm kiếm còn trống và có focus, dùng `type_text` hoàn tất. Giữ state lỗi
và capture chuyển cảnh; không đổi app hoặc chạy lại build/request vì lỗi tool.

Evidence: `build/ocr-pilot-20260910/ocr4-request-logs-layout-20/`, ngoài Git,
gồm log/receipt source, build/verification, native GUI PNG/accessibility,
journal replay, process/preservation và `validation.json`. Tổng phiên
**0 CPU OCR/0 vision/0 text LLM/0 HTTP mock request**; cap vision14 không đổi.

**Đã kiểm first-file trên GUI frozen bằng journal tổng hợp; day rollover vẫn
chưa kiểm.** Không có gate inference mới ở isolated runtime/packaged Python,
frozen CLI, live API, video/FFmpeg workflow hoặc review Việt thật. GUI RequestLogs
bấm dịch và OCR GUI gói C giữ evidence cũ riêng. Không chốt chất lượng OCR,
câu 4, vision GUI, máy sạch hoặc native full-suite teardown từ sửa layout này.

File sửa trong phiên: `videocaptioner/ui/view/llm_logs_interface.py`;
`resource/translations/VideoCaptioner_vi_VN.json`, `VideoCaptioner_en_US.ts`,
`VideoCaptioner_zh_CN.ts`, `VideoCaptioner_zh_HK.ts`;
`videocaptioner/resources/translations/VideoCaptioner_vi_VN.json`; biên bản
này, `status.md`, `docs/dev/ocr-next-session-prompt.md`. Giữ nội dung bàn giao
GUI trước đó; không sửa test, spec, dependency hoặc artifact cũ.

## Bổ sung: nghiệm thu GUI RequestLogs bằng mock sau snapshot 501c6ff

HEAD và tracking cùng **501c6ff**, working tree sạch đầu phiên. User giao tiếp
nghiệm thu nhật ký và review Việt trên **chính EXE RequestLogs hiện có**, dùng
fixture/mock, giữ dữ liệu/artifact và không chạy lại gate đã qua. Không sửa
source/resource/spec, build lại, chạy OCR scan hoặc gọi gateway. Cap vision
**14 đã dùng hết**, không đọc key hoặc thêm attempt.

Computer Use native điều khiển đúng process test của
`dist/VideoCaptioner-OCR4-RequestLogs-20260911/`. Dùng review 3 cue/6 candidate
và video tổng hợp cũ; mở review và xem một crop bằng FFprobe/FFmpeg trong gói,
không chạy recognizer. Settings smoke của riêng gói được sao lưu, tạm dùng
endpoint `127.0.0.1` và credential giả, rồi khôi phục nguyên bytes khi đóng.
Không thay settings dev hoặc mang key thật vào artifact.

| Gate GUI mới | Kết quả |
| --- | --- |
| Review trước dịch | 3 cue/6 issue, export/handoff khóa; mở review và crop không gửi LLM |
| Bấm dịch | Response giả hiện cạnh raw/crop, có nhãn **AI chưa nhìn ảnh** và chỉ giữ trong phiên |
| Cache và candidate | Bấm lại cùng candidate vẫn **1 request**; chọn cue khác hoặc cue trùng chữ nhưng khác ID ẩn bản dịch cũ |
| Thiếu usage | Response success không có usage được báo thiếu số liệu; journal/detail hiện **—**, không 0 |
| HTTP lỗi | Một HTTP 500, báo lỗi đã lọc, không tự retry; review và guard giữ nguyên |
| Hủy | Bấm thử lại tường minh để tạo request mock đang chờ, rồi **Hủy tác vụ**; GUI trở lại idle, journal ghi `cancelled` |
| Lưu review | Output mới **khớp byte-for-byte** với pending đầu vào; raw/candidate/IDs/timing/issue không đổi, bản Việt không persist |
| Nhật ký | Menu mở được; **4 dòng mới/4 request**, gồm 2 success, 1 HTTP error, 1 cancelled; dòng mock CLI cũ vẫn có |
| Chi tiết và lọc | Mở success có usage và success usage null không lỗi; lọc model và Làm mới giữ đúng 4 dòng |
| Đóng và bảo toàn | EXE **exit 0**, 0 child/job OCR sót, server mock đóng, stderr không traceback; settings khôi phục, log cũ giữ nguyên prefix |

Usage **giả lập** của response đầu: **120 input +30 output =150 total**,
cached input **80**, reasoning **10** đã nằm trong input/output. Ba lượt còn
lại không có usage; không tính tổng 4 lượt thành 150 và không cộng vào ledger
gateway. Mock kiểm mỗi request chỉ chứa prompt chung và đúng nguyên text của
candidate đã chọn, tối đa 1.000 completion token; không ảnh/path/câu lân cận.
Journal chỉ có metadata/usage, không credential giả, raw OCR, bản Việt hoặc
error body marker. Có đúng một action retry tường minh để kiểm hủy, **0 retry
tự động**. Nội dung Việt là sentinel tổng hợp để phân biệt response trên UI,
không phải bản dịch tham chiếu và **không nghiệm thu chất lượng dịch**.

Hai lỗi trình bày được quan sát và **chưa sửa**: footer số dòng còn tiếng
Trung (`共 4 条`); khi cửa sổ 1050×800 mở rộng thanh bên, các nhãn thời gian/
stage/model/input/output trong chi tiết bị cắt. Thu gọn thanh bên thì nhãn
token đầy đủ; JSON response vẫn giữ đủ số ở cả hai trạng thái. Gate chức năng
pass trong phạm vi mock; không gọi UI đã hoàn thiện. Không sửa painter hoặc
quy lỗi capture lịch sử về cùng nguyên nhân.

Evidence ngoài Git: `build/ocr-pilot-20260910/ocr4-request-logs-gui-19/`, gồm
harness, mock request, journal mới, accessibility/JPEG, review output và
`validation.json`. **44 đường dẫn** bảo toàn được theo dõi; các file đang có
giữ SHA, đường dẫn settings chưa có vẫn chưa có. Một journal cũ được giữ
nguyên prefix, chỉ app append 4 entry mới. GUI sống **457,125 s**, gồm thời
gian thao tác; không phải latency dịch. Watcher 50 ms chỉ thấy kết nối EXE
với loopback, không phải trace toàn bộ network hoặc mọi file/DLL.

Harness ban đầu dùng nhầm `raw.text` trong JSON và dừng trước đổi settings/
mở EXE/server; chuyển sang loader document typed rồi chạy GUI đúng một lần.
Computer Use một lần lỗi index modal không có trong cached state; refresh và
tọa độ screenshot modal hoạt động. File dialog trả tên focus accessibility
khác ô tên file có selection trên ảnh; dùng focus quan sát được. Những lỗi
harness/tool này không phải lỗi app và không được xóa khỏi lịch sử evidence.

Gate mới: GUI frozen và kiểm receipt/document/privacy/preservation **pass**.
Không chạy lại source tests/Ruff/Pyright/translations/build/hash 49 GB;
không inference ở isolated runtime/packaged Python, frozen CLI hoặc live API
mới. Chưa kiểm first-file/day rollover bằng GUI frozen, dịch Việt thật, lỗi
câu 4, vision GUI, máy sạch hoặc native full-suite teardown cũ. Chỉ cập nhật
biên bản này, `status.md` và prompt bàn giao; chưa commit/push.

## Snapshot trước: vision thật và sửa logger

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
