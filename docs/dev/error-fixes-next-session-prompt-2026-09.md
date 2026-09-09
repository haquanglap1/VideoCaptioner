# Prompt phiên tiếp theo — sau sửa Qt shutdown và Bing

**Đã chuyển sang [prompt nghiệm thu online/media](online-media-next-session-prompt-2026-09.md)
theo yêu cầu user ngày 2026-09-10.** Google/DeepLX đã sửa, có 71 regression mới
trong gate 309 pass/15 deselected và EXE `VideoCaptioner-GoogleDeepLXFix-20260909`.
User yêu cầu chốt Git snapshot này; lấy HEAD/tracking bằng Git. Đọc phần mới
nhất của `status.md` cùng [báo cáo Google/DeepLX](google-deeplx-errors-2026-09.md).
Mục ứng viên bên dưới là lịch sử, không lặp sửa/test/build đã hoàn tất. Phạm vi
online/media mới theo prompt mới, vẫn giữ bài giảng/model/OCR đã chốt.

Tiếp tục project VideoCaptioner tại worktree **VideoCaptioner-ASR-S3**, nhánh
**`codex/asr-s3-native`**. Không làm ở checkout `VideoCaptioner` đang là master.

## Git và môi trường

- Nền trước lượt sửa lỗi: `8278d1549a7db9c08da5be1c1b3664103a271b25`.
- Qt shutdown: `d1ab4ca` — `fix(ui): retain version checks through window shutdown`.
- Bing: `a5ba2be4a83d461abac4edf56a435b75fa603c1b` —
  `fix(bing): reject incomplete translations and bound auth recovery`.
- Sau hai commit code có commit tài liệu chứa prompt này. **Lấy HEAD cuối bằng
  Git**, đối chiếu SHA trong tin nhắn bàn giao và `origin/codex/asr-s3-native`;
  không coi source commit phía trên là HEAD cuối nếu còn commit tài liệu.
- User đã yêu cầu commit/push snapshot hiện tại; quyền đó không tự áp dụng cho
  thay đổi mới ở phiên sau. Không reset, force-push, merge master, tag/release.
- Python **3.12.13** có sẵn ở `../VideoCaptioner/.venv/Scripts/python.exe`;
  chú ý dấu phân cách trước `.venv`. Worktree không có `.venv` riêng. Không
  sync/cài dependency. FFmpeg có ở `../VideoCaptioner/AppData/bin/ffmpeg/`.

## Đọc trước

1. `AGENTS.md`, `README.md`, phần mới nhất của `status.md`.
2. [Báo cáo sửa Qt/Bing và nghiệm thu EXE](gui-shutdown-bing-errors-2026-09.md).
3. [Nghiệm thu review/resume và synthesis R6](dubbing-review-resume-2026-09.md).
4. [Plan theo session](../plans/asr-completion-sessions-2026-09.md) khi cần.

Chạy `git status --short --branch`, kiểm tra HEAD và giữ mọi thay đổi có sẵn.
Các dòng lịch sử “chưa có review/resume”, “đang chờ GUI”, “chưa commit” không
thay thế trạng thái mới nhất.

## Đã hoàn thành, dùng lại bằng chứng

- Core/GUI review sửa lời đọc theo group, lưu/mở/nhập checkpoint, chọn cache;
  resume giữ lời đã duyệt và chỉ tạo WAV cần thiết. Layout cuộn và xuống hàng đã sửa.
- OmniVoice downloader giữ partial, HTTP Range/resume/416 và xử lý disk/network;
  Ready/reuse model thật đã kiểm tra, không tải lại model có sẵn.
- Entry EXE chuẩn UTF-8; synthesis phân biệt input/output layout, giữ thứ tự
  phụ đề song ngữ qua pipeline/reexport/ghép lại.
- Qt version checker luôn complete, tự thoát QThread, supervisor giữ/join worker
  khi đóng app; bỏ wait hai giây và bỏ dialog/startup đến muộn.
- Bing validate nguyên batch, không nuốt lỗi/cache bản dịch thiếu, auth refresh
  đồng bộ và retry một lần. Cache `validated-v2` bỏ qua namespace cũ nhưng giữ
  dữ liệu cũ; câu dài hơn 5000 ký tự báo cần chia thay vì cắt text.
- Gate cuối **409 pass / 24 deselected**, gồm 30 regression mới; Ruff/Pyright/
  sync pass. Không cộng lại các suite lịch sử hoặc chạy full/build chỉ để lặp gate.

## Artifact mới nhất

`dist/VideoCaptioner-ErrorFix-20260909/`, dùng **nguyên thư mục onedir**.

- Build exit 0 / 216,078 s, 6 WARNING / 0 ERROR.
- EXE 31.262.504 byte, local 2026-09-09 21:56:25, SHA-256:
  `6d0e54ef6c59522f34f6625e3b1f5124425f9919e94a46b490ff0fdfa16070fa`.
- GUI startup sống 25,688 s rồi exit 0; đóng khi request cập nhật còn chờ cũng
  exit 0, không child ở cả hai ca. Request được cô lập bằng proxy loopback.
- CLI help/help dubbing/đối số Unicode sai trả 0/0/2, UTF-8 đúng. Bốn module PYZ
  khớp source. Test AppData/work-dir đã chuyển nguyên vào evidence.
- Evidence: `build/error-fixes-20260909/`. CLI receipt đã hoàn tất dù helper
  in console từng lỗi cp1252; **không chạy lại helper exclusive-create**.
- Chưa chạy workflow media hoặc inference mới trên ErrorFix. Pipeline GUI dùng
  dữ liệu sẵn đã nghiệm thu ở R6; kế thừa đúng giới hạn đó.
- R6 và toàn evidence cũ giữ nguyên; SHA-256 EXE R6 vẫn
  `aa1756106900ed3e8070b9fb6cd38927c9269e1b732a091ee4ddd60570d6fb2c`.

## Việc tiếp theo: ưu tiên lỗi cụ thể

**Ứng viên sửa trước là Google/DeepLX báo thành công với bản dịch thiếu.** Rà
source trong lượt bàn giao cho thấy cả hai `_translate_chunk()` còn catch lỗi
và trả chunk; `BaseTranslator._safe_translate_chunk()` có thể cache kết quả đó.
Google còn cắt input ở 5000 ký tự, DeepLX chưa validate kiểu/nội dung `data`.
Đây là finding từ code, **chưa có regression hoặc sửa trong snapshot này**.

1. Đọc đúng `core/translate/{google_translator,deeplx_translator,base}.py` dưới
   `videocaptioner/`, tìm các call site và test liên quan bằng `rg`.
2. Tái hiện bằng test offline/cache riêng: HTTP lỗi, response thiếu/sai/rỗng,
   lỗi ở giữa batch, hủy đến muộn, cache lỗi cũ và input bị cắt. Kiểm tra thêm
   key DeepLX theo endpoint/config, tránh cache dùng nhầm khi đổi dịch vụ.
3. Chỉ sửa nguyên nhân có test rõ; giữ API/flag/config, không tự đổi provider,
   không log endpoint chứa credential hoặc response nhạy cảm. Không đụng cache thật.
4. Chạy test gần sửa và gate cơ bản. Chỉ build tên mới nếu code thay đổi; giữ
   artifact trước và báo riêng source/build/startup/workflow.

Các mục khác còn mở, không tự biến thành vòng benchmark:

- **Bing upstream:** GET auth hiện có trả 404/0 byte ngày 2026-09-09. App đã báo
  lỗi rõ nhưng dịch vụ chưa phục hồi; không đoán URL mới hoặc đổi User-Agent để
  gọi là fix. Không cần lặp request chỉ để xác nhận lại cùng trạng thái.
- **Qt/SIP ngắt quãng:** chưa có reproducer tất định cho mọi crash lịch sử.
  Nếu có lỗi mới, dùng log/dump và đúng thao tác đó; không chạy GUI stress lặp vô hạn.
- **Qwen generation/quality/RTF:** guard/retry/cache đã có, nguyên nhân model
  sinh lặp và mức chất lượng/tốc độ toàn corpus chưa giải quyết. Chỉ mở lại khi
  có yêu cầu/case cụ thể; không sweep model hoặc chấm lại benchmark sâu.
- **Nghiệm thu mở rộng:** nhiều người nói/xưng hô, phồn thể strict, provider ngoài
  scope, cài trên máy sạch và fresh full inference là các hạng mục riêng.

## Giữ nguyên phạm vi

Bản bài giảng user đã chấp nhận “tạm ổn”: không tự ASR/dịch/TTS/render lại.
Giữ 151 WAV, 121 nhóm đổi lời; replay 1,00×, trễ tối đa 2284 ms. Giữ video,
runtime/model, settings, cache và artifact lỗi. Không tìm key cũ, tải model
đã có, chạy helper cũ hoặc mở OCR. Không tự commit/push thay đổi phiên sau.

Nếu user cung cấp lỗi cụ thể mới thì ưu tiên lỗi đó. Nếu finding Google/DeepLX
đã được xử lý trong Git mới hơn, kế thừa kết quả và hỏi một câu ngắn để chọn
hạng mục khác; không làm lại snapshot đã hoàn tất.
