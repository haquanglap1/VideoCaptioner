# Prompt phiên tiếp theo — nghiệm thu dịch vụ online và workflow media mới

Tiếp tục VideoCaptioner tại worktree **`VideoCaptioner-ASR-S3`**, cạnh checkout
`VideoCaptioner`, nhánh **`codex/asr-s3-native`**. Không làm ở checkout
`VideoCaptioner` đang là master.

## Yêu cầu hiện tại của user

Ngày 2026-09-10, user yêu cầu commit/push snapshot Google/DeepLX và chuẩn bị
phiên sau để **nghiệm thu dịch vụ online và workflow media mới**. Đây là phạm
vi được mở lại: có thể gọi dịch vụ và chạy ASR/dịch/TTS/render cần thiết trên
mẫu kiểm thử mới, ngắn, với cache/output riêng. Không cần xin lại quyền chung
để thực hiện các bước đó. Chỉ hỏi khi thiếu input, endpoint hoặc credential.

Giữ nguyên bài giảng user đã chốt “tạm ổn”, video, 151 WAV, 121 nhóm sửa lời,
runtime/model/settings/cache và mọi artifact cũ. Không dùng bài giảng để chạy
lại inference/render. Không benchmark sâu, sweep model, OCR, tải model hoặc
cài/sync dependency. Không tự commit/push thay đổi của phiên mới; quyền chốt
Git ngày 2026-09-10 chỉ áp dụng snapshot bàn giao hiện tại.

## Git, môi trường và tài liệu

1. Chạy `git status --short --branch`, lấy HEAD bằng Git, đối chiếu SHA trong
   tin nhắn bàn giao và `origin/codex/asr-s3-native`. Giữ thay đổi có sẵn.
   Parent trước snapshot Google/DeepLX là
   `cd127e1039a79284b2f48f12f1ba9557958673da`; **đó không phải HEAD sau commit**.
   Không reset/force-push/merge master/tag/release.
2. Đọc `AGENTS.md`, `README.md`, phần mới nhất của `status.md` và
   [báo cáo Google/DeepLX](google-deeplx-errors-2026-09.md).
3. Khi chạy pipeline, đọc [nghiệm thu R6](dubbing-review-resume-2026-09.md),
   [ASR thực dụng](asr-practical-sentences-2026-09.md) và
   [OmniVoice Local](omnivoice-local.md) đúng phần cần thiết.
4. Python 3.12.13 đã có: `../VideoCaptioner/.venv/Scripts/python.exe`.
   Worktree không có `.venv` riêng. FFmpeg/ffprobe đã có ở
   `../VideoCaptioner/AppData/bin/ffmpeg/`. Không gọi `uv sync` hay cài package.

## Kết quả đã hoàn tất — kế thừa, không lặp lại

- Google/DeepLX validate cả batch trước mutation/cache, báo lỗi document khi
  chỉ một chunk thiếu, bỏ kết quả đến sau hủy, đóng response/session.
- Google báo cần chia câu vượt 5000 ký tự, không cắt input hoặc lấy prefix
  từ HTML không hoàn chỉnh. DeepLX kiểm tra `data`/mã lỗi và tách cache theo
  hash endpoint hiệu lực. Namespace `validated-v2` giữ nhưng bỏ qua cache cũ.
- Gate source **309 pass / 15 deselected**, gồm **71 regression mới**;
  Ruff/Pyright/translation sync pass. Kế thừa riêng 409 pass/24 deselected
  và nghiệm thu Qt/Bing ErrorFix; không cộng lặp các bộ test.
- EXE hiện tại: **`dist/VideoCaptioner-GoogleDeepLXFix-20260909/`**, nguyên onedir.
  Build exit 0 / 238,812 s, 6 WARNING/0 ERROR. EXE 31.263.856 byte, local
  2026-09-09 22:56:08, SHA-256:
  `064907630f4f15bf35e134b4a2f2d331a4e008b2bb96402b9299fa81d2c7291e`.
- Google/DeepLX/base/Bing trong PYZ khớp source. GUI sống 26,047 s, đóng exit 0,
  không child. Google CLI với proxy loopback trả lỗi đúng exit 5, không ghi
  đè input/output và cache 0 entry. **Đây chưa phải dịch Google online thành công.**
- Evidence `build/google-deeplx-errors-20260909/`. Test AppData/work-dir đã
  chuyển nguyên khỏi artifact vào evidence. Không chạy lại helper tạo file
  độc quyền. `--config FILE` của CLI thuộc subcommand, ví dụ đặt sau `subtitle`.
- ErrorFix/R6 và pipeline R6 với dữ liệu có sẵn giữ nguyên. Chưa nghiệm thu
  Google/DeepLX online hoặc media/inference mới trên GoogleDeepLXFix.

## Bước 1 — nghiệm thu Google và DeepLX online có giới hạn

- Dùng batch tổng hợp 3–5 cue, không chứa transcript riêng tư, có Unicode,
  dấu câu và xuống dòng. Cache/log/output nằm trong evidence mới của phiên;
  cô lập cả cache/log phát sinh lúc import và settings GUI/CLI như runner cũ.
  Không xóa cache thật để ép cache miss; bỏ proxy giả của lượt offline khỏi
  đúng process thử, không đổi cấu hình proxy toàn máy.
- Gọi đúng provider hiện có bằng core/GUI, giữ timeout của app. Với DeepLX,
  dùng endpoint đang được user chọn qua cơ chế cấu hình chuẩn. Nếu thiếu
  endpoint/key hợp lệ, yêu cầu nhập kín rồi tiếp tục phần độc lập. Không quét
  lịch sử/log tìm key, tự chọn dịch vụ thay thế hoặc ghi key vào `os.environ`.
  CLI hiện chỉ liệt kê `llm/bing/google`; không invent `--translator deeplx`.
- Lần đầu phải có request online thật và cache miss. Kiểm tra đủ cue, text
  nonempty đúng kiểu, giữ ID/timing/nguyên văn; xem nhanh tính hợp lý bản dịch.
  Ghi riêng trạng thái HTTP, latency, request count và số cue đã dịch, không
  lưu URL chứa credential/body riêng tư vào tài liệu Git.
- Chạy lại cùng input/config để xác nhận cache hit và không có request mới.
  Không biến cache replay thành bằng chứng online hoặc chất lượng dịch.
- Nếu dịch vụ lỗi/429/timeout/HTML thay đổi, ghi rõ gate chưa pass, không retry
  vô hạn. Giữ response tổng hợp/sanitized tối thiểu để tạo regression offline;
  chỉ sửa nguyên nhân có bằng chứng, không bỏ validation để ép pass. Không
  cố gây lỗi/rate-limit trên dịch vụ thật; ca lỗi/hủy đã có test offline.
- Bing upstream từng 404, vẫn là giới hạn riêng; không đoán URL mới hoặc
  lặp probe Bing chỉ để xác nhận cùng trạng thái.

## Bước 2 — workflow media mới trên GUI/EXE

- Chọn clip kiểm thử mới khoảng 15–30 giây có lời nói, dùng fixture/public
  sample phù hợp đã có hoặc media user cung cấp. Nếu chưa có input thích hợp,
  hỏi user đường dẫn; không tự dùng lại bài giảng đã chốt. Ghi hash nguồn và
  dùng thư mục evidence/cache/output mới, không ghi đè media cũ.
- Ưu tiên chạy luồng thật ngay trên EXE hiện tại: nhận dạng → phụ đề có timing
  → provider dịch online vừa pass → OmniVoice Local đã cài → ghép/export.
  Dùng model/runtime đã ready; không Prepare/download khi mở app. Không tải
  thêm model để mở rộng scope. Nếu cần source để chẩn đoán, phân biệt rõ
  source/frozen và reuse phần đã xong; không lặp inference chỉ để tích lũy gate.
- Phạm vi này cho phép inference mới trên mẫu mới. Mỗi stage ghi rõ fresh
  request/generation hay cache hit, số cue/group/WAV, thời gian và lỗi thực tế.
  Giữ policy nhịp đọc đều và review/resume đã chốt. Nếu có nhóm vượt khung,
  dùng luồng review hiện có, không âm thầm cắt lời hoặc nới guard.
- Xác nhận GUI hiển thị tiến độ/kết quả/lỗi đúng, không treo; transcript và
  timestamp được giữ qua dịch, thứ tự song ngữ đúng, track/output đầy đủ.
  Kiểm tra FFprobe stream/duration, FFmpeg decode; mở xem/nghe mẫu kết quả.
  Ghi riêng kiểm tra kỹ thuật và đánh giá nghe/xem còn cần user xác nhận.
- Đóng đúng process đã tạo, join worker, kiểm tra child/GPU lease được thu hồi.
  Giữ artifact lỗi và kết quả stage hoàn tất để tiếp tục, không chạy lại toàn
  pipeline khi chỉ một bước chưa xong.

## Bàn giao phiên nghiệm thu

Lập báo cáo tách từng gate: Google online, DeepLX online, cache replay,
source/GUI/frozen, ASR/dịch/TTS/synthesis của mẫu mới, kiểm tra media và cleanup.
Gate thiếu key/service/input phải ghi chưa nghiệm thu, không tính pass hoặc
thay bằng mock. Không tuyên bố nghiệm thu mọi provider/chất lượng model/cài
máy sạch từ một clip. Ưu tiên sửa lỗi cụ thể nếu gặp; chạy test gần sửa và gate
cơ bản, chỉ build tên mới nếu source thay đổi. Giữ artifact cũ, báo hash/gate
build riêng, cập nhật `status.md`, không tự commit/push.
