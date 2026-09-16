# Sửa shutdown GUI và xử lý lỗi Bing — 2026-09-09

Tiếp tục snapshot `8278d15` trên `codex/asr-s3-native`. User yêu cầu ưu tiên
xử lý lỗi. Phạm vi lần này là hai lỗi tái hiện được trong ứng dụng; giữ các
nghiệm thu R6, media, runtime/model và cache đã có.

## Lỗi và thay đổi

### Luồng kiểm tra cập nhật khi đóng cửa sổ

`VersionChecker.checkCompleted` trước đây không phát khi HTTP lỗi hoặc dữ liệu
rỗng; cửa sổ cũng không nối completion với `QThread.quit()`. Luồng đã kiểm tra
xong vẫn giữ event loop. Khi đóng cửa sổ trong lúc request đang chạy,
`quit()` không hủy request và `wait(2000)` chặn Qt main thread đủ hai giây rồi
tiếp tục shutdown dù worker có thể chưa xong.

Nay completion luôn phát trong `finally`, nối trực tiếp tới `quit()` và thu hồi
QObject ở thread finish. `WorkerSupervisor` sở hữu QThread tới khi request kết
thúc, join tại app shutdown qua event loop hiện có. Đóng cửa sổ yêu cầu ngắt,
không wait hai giây trên main thread. Request vẫn có timeout hiện có; đây không
phải cơ chế hủy socket tức thì. Cờ closing chặn timer startup và dialog cập nhật/
thông báo đến muộn. Không đổi dependency Qt/SIP hoặc cơ chế giữ QApplication.

Regression dùng QThread/QEventLoop thật, request được điều khiển bằng Event:
completion cả success/empty/error, không còn idle thread, close trả nhanh,
worker được giữ và join, timer Qt vẫn chạy khi drain, bỏ callback muộn.
Mọi worker test đều `wait()` trước khi thoát scope.

### Bing nuốt lỗi và cache kết quả thiếu

Trước đây HTTP lỗi, response thiếu/sai hoặc refresh token chỉ được log rồi trả
chunk chưa dịch; base coi đó là success và ghi cache. Response bị lỗi ở cuối
batch còn có thể để lại mutation từ các dòng đầu. Input dài bị cắt ở 5000 ký tự.

Nay Bing kiểm tra đủ batch và text hợp lệ trước khi áp kết quả, ném lỗi khi thiếu
bản dịch và yêu cầu toàn document hoàn tất. HTTP 401/403 chỉ refresh rồi thử lại
chunk một lần; các chunk đồng thời chia sẻ một refresh cho token cũ. Lỗi khác
không tự retry. Hủy không publish/cache kết quả đến muộn. Giới hạn 5000 ký tự
của app giữ nguyên nhưng báo cần chia câu thay vì cắt chữ. Constructor lỗi và
`close()` thu hồi session/executor. Thông báo lỗi không chép body/request nhạy cảm.

Cache Bing dùng namespace `validated-v2`, không đọc kết quả thiếu từ namespace
cũ. Cache cũ vẫn nằm nguyên trên đĩa; các kết quả Bing cũ hợp lệ cũng cần dịch
lại khi người dùng chạy job mới. Cache ASR/LLM/TTS và các provider khác không đổi.

Một GET trực tiếp tới endpoint auth hiện có trả **HTTP 404**, body 0 byte trong
phiên này. Không gửi subtitle hoặc tìm credential. Không đổi URL/User-Agent hay
suy đoán endpoint thay thế. Đây là sửa xử lý lỗi phía app; **Bing online vẫn
chưa hoạt động qua endpoint đó**. App báo chọn provider khác khi auth unavailable.

## Validation source

- Trước sửa: 23 regression đầu chạy được, **22 fail / 1 pass**, tái hiện lỗi.
- Sau sửa: **409 pass / 24 deselected**, gồm UI/thread/CLI/translate và editor
  startup; 30 regression mới nằm trong tổng này, không cộng lặp. Các test online/
  integration/slow/llm được loại trừ. Một warning, không skip.
- Ruff toàn app/tests pass; Pyright app **0 error / 0 warning**; translations sync.
  Dùng Python **3.12.13** và FFmpeg đã cài, không sync/cài dependency.
- Một lượt sau sửa gặp 6 fail do Response fixture chưa đánh dấu body đã đọc;
  đã sửa fixture theo Requests non-streaming. Không nới logic sản phẩm để pass.
  Pyright ban đầu báo enum Qt và chọn môi trường chưa đúng; đã dùng enum có type
  và venv hiện hữu, gate cuối được chạy lại.

Không chạy benchmark Qwen, inference ASR/LLM/TTS, tải model hoặc render bài giảng.
Các lỗi sinh lặp/chất lượng model và crash SIP ngắt quãng không được tuyên bố
đã hết chỉ từ regression shutdown này. Lượt sửa/validation chưa commit; sau đó
user yêu cầu chốt Git và prompt phiên sau, ghi bên dưới. Không merge/release.

## EXE và nghiệm thu shutdown

Artifact: `dist/VideoCaptioner-ErrorFix-20260909/`, dùng nguyên thư mục onedir.
Giữ nguyên bản R6 trước đó. Evidence: `build/error-fixes-20260909/`.

1. PyInstaller **exit 0 / 216,078 s**, **6 WARNING / 0 ERROR**; warning optional/
   platform giống các build trước (js/emscripten, curl_cffi, yt_dlp_ejs, tzdata,
   sip, AppKit), có thêm SyntaxWarning từ dependency. Log và receipt ở
   `pyinstaller.log`, `build.json`.
2. EXE **31.262.504 byte**, timestamp local **2026-09-09 21:56:25**; SHA-256
   `6d0e54ef6c59522f34f6625e3b1f5124425f9919e94a46b490ff0fdfa16070fa`.
   Bốn module main window/version checker/supervisor/Bing trong PYZ khớp source;
   `packaged-source.json` giữ kết quả đối chiếu.
3. Chính EXE chạy Qt Windows với settings mới ở artifact, FFmpeg sẵn trên PATH.
   Proxy loopback cô lập request cập nhật, không gọi API/model bên ngoài:
   - Startup: sống **25,688 s**, đóng cửa sổ đúng PID, **exit 0**, không child còn lại.
   - Đóng khi request cập nhật còn chờ: server xác nhận request đã bắt đầu; gửi
     WM_CLOSE vào đúng cửa sổ/PID. App vẫn sống chờ request sau **0,6 s**; server
     trả lỗi transport tổng hợp, app đóng **exit 0** sau **0,812 s** tính từ yêu
     cầu đóng, không child còn lại. Receipt `close-during-version-request.json`.
   Log chỉ có hai warning proxy chủ đích, không traceback/InfoBar/QThread error.
4. `--help`, `dub --help` và đối số Unicode không hợp lệ trả **0/0/2**, stream
   decode UTF-8 đúng (`cli.json`). Helper đã lưu/validate receipt rồi lỗi cp1252
   khi in receipt Unicode ra console; đọc lại receipt xác nhận các gate EXE đã
   pass, không chạy lại helper hoặc xem lỗi console đó là lỗi app.
5. Chưa chạy workflow media/ASR/LLM/TTS mới trên artifact này. Kết quả pipeline
   R6 được kế thừa đúng phạm vi, không thay bằng smoke startup/shutdown.

Sau khi đóng hết process, AppData/work-dir của ca thử được chuyển nguyên vào
evidence; artifact không mang settings/cache thử. Hash EXE mới giữ nguyên, hash
R6 vẫn `aa1756106900ed3e8070b9fb6cd38927c9269e1b732a091ee4ddd60570d6fb2c`.

## File thay đổi

- `videocaptioner/ui/view/main_window.py`
- `videocaptioner/ui/thread/version_checker_thread.py`
- `videocaptioner/core/translate/bing_translator.py`
- `tests/test_ui/test_version_checker_lifecycle.py`
- `tests/test_translate/test_bing_failures.py`
- `docs/dev/gui-shutdown-bing-errors-2026-09.md`
- `status.md`

## Chốt Git và bàn giao

User đã yêu cầu commit/push snapshot sửa lỗi và chuẩn bị phiên sau. Code Qt
được chốt ở `d1ab4ca`, Bing ở `a5ba2be`; tài liệu/prompt có commit riêng theo sau.
HEAD và tracking Git là nguồn trạng thái cuối, không dùng ghi chú chưa commit
của lượt validation để phủ nhận snapshot mới. Không chạy lại test/build/model
chỉ để chốt tài liệu, không đưa build/dist/evidence vào Git.

[Prompt mới](error-fixes-next-session-prompt-2026-09.md) ghi bằng chứng đã hoàn
tất và ứng viên lỗi tiếp theo: Google/DeepLX còn catch lỗi rồi trả chunk để
base có thể cache kết quả thiếu. Đây là finding từ source, chưa có regression/
sửa trong snapshot này. Prompt cũ được thêm liên kết chuyển sang prompt mới.
