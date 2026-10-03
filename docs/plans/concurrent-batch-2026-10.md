# Xử lý nhiều video đồng thời

Ngày 2026-10-03. User yêu cầu lập kế hoạch và triển khai sau khi đã khảo sát Batch.

## Phạm vi và hành vi

- Nhiều video cùng tiến hành, mỗi video giữ thứ tự ASR → subtitle/translate → dubbing → synthesis.
- Mặc định 3 video; giới hạn riêng ASR 2, subtitle 3, dubbing 2, synthesis 1. Chọn 1 video để chạy tuần tự.
- Local GPU ASR và managed TTS dùng chung một suất GPU trong Batch. Cloud/CPU có thể chạy song song;
  OmniVoice giữ nguyên batch size/giọng/timing. Không mở nhiều model GPU trước khi có benchmark.
- Giới hạn `Translate.ThreadNum` là tổng request LLM của Batch, gồm split/optimize/translate/title/rewrite.
  Giữ cooldown chung, quota-stop, không tự gửi lại request timeout/mất kết nối.
- Chụp cấu hình từng video lúc xếp hàng; work path phân biệt nguồn cùng tên, không lẫn cue/audio/output.
- Chờ công đoạn/GPU có trạng thái riêng; hủy một video, hủy toàn bộ, retry và cleanup không chặn Qt.
  Chỉ nhả suất sau native QThread completion; không để late signal chạy công đoạn tiếp theo.

## Các bước

1. [x] Core admission + GUI scheduler theo công đoạn; giới hạn và cấu hình Batch.
2. [x] Shared LLM admission, snapshot cấu hình, định danh/workspace từng video, trạng thái và cancellation.
3. [x] Test overlap thật bằng nhiều worker, GPU exclusivity, request ceiling, 429, timeout,
   cancel/retry, same-name isolation; Ruff/Pyright/CLI/translations/full offline suite.
4. [x] Build onedir mới với model/runtime đã có; đối chiếu source/frozen, native EXE CLI/smoke,
   kiểm payload/model inventory. Deploy E khi idle, backup delta và kiểm hash dữ liệu bảo vệ.

## Nghiệm thu

Đo peak concurrency và thời điểm bắt đầu/kết thúc công đoạn; không suy số worker thành tăng tốc.
Offline/fake provider, real GPU/media, EXE và nghe thật là các gate riêng. Không thay settings/API keys,
cookies, model/runtime, media/cache user; không commit/push. Kết quả từng bước sẽ cập nhật tại đây.

## Kết quả 2026-10-03

- Đã triển khai và deploy vào bản E. Giới hạn GPU áp dụng trong Batch; các tab chạy độc lập
  vẫn có cơ chế quản lý runtime hiện có. API ASR cần forced alignment cũng giữ suất GPU.
- Snapshot cấu hình toàn bộ các công đoạn trước khi chạy; shared admission áp dụng cả LLM phụ trợ.
  Hai nguồn khác thư mục cùng basename có workspace riêng; checkpoint cũ qua kiểm tra nguồn được
  đọc lại rồi xuất sang workspace mới. Hai nguồn cùng thư mục và cùng stem bị báo xung đột đầu ra.
- Cache WAV ghi có khóa, giữ entry đã publish; tên video dịch được reserve trước khi xuất.
  Việc hủy chỉ nhả suất sau native thread cleanup, quota-stop ngăn công đoạn sau.
- Full offline: **2472 pass / 5 skip / 58 deselected**; focused cuối **64 pass** (gồm các guard
  bổ sung cho forced alignment và quota giữa video). Ruff/Pyright/sync pass. Lượt full đầu gặp
  WinError145 khi dọn fixture TemporaryDirectory; chuyển sang tmp_path, giữ assertions và wait.
- Production QThreads với loopback ASR/LLM/TTS và FFmpeg thật: 3 video/12,282s; peak ASR2,
  LLM3 tổng, TTS2. Ba output có video/audio/subtitle, decode exit0/stderr0.
- GPU source: Faster-Whisper CUDA tiny + OmniVoice batch1, LLM loopback, 3 video tổng hợp15s,
  tổng121,485s; không chồng hai công đoạn GPU, cả3 output decode exit0/stderr0. Đây là kiểm
  luồng/tài nguyên, không phải benchmark chất lượng hay nghiệm thu nghe.
- EXE: build0/218,469s,6 WARNING/0 ERROR;31.738.627bytes,
  SHA256 `9135e454d0aa30547c59b666d45fe64dd1e43a89d5f9be87a560db70876dc6f9`.
  16 module khớp source;99.315 file/8 component model-runtime khớp size manifest.
  Native CLI loopback40/40 cue,peak20; GUI30,563s/exit0/0 owned survivors.
- Deploy E khi idle:602 app files đối chiếu SHA,delta4 có backup;4.258 file được bảo vệ
  nguyên hash. Không chép model hoặc đổi settings/key/cookie/shortcut. Live CLI help exit0;
  GUI/CLI loopback kế thừa same-SHA artifact. Chưa chạy Batch qua GUI của EXE với dịch vụ thật,
  chưa nghiệm thu nghe. Không commit/push.
- Evidence, raw failures, inventory và danh sách file: `.tools/concurrent-batch-20261003/`.
