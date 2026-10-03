# Thử hai job GPU và thư mục video lồng tiếng

Yêu cầu 2026-10-03, baseline `e469d40`: thử hai job GPU cùng tiến hành, chọn thư mục
lưu video lồng tiếng tập trung; để trống giữ đầu ra cạnh nguồn.

1. [x] Thêm GPU jobs 1/2 trong Batch. Faster-Whisper và OmniVoice hỗ trợ chế độ2;
   runtime GPU khác giữ độc quyền. Mỗi job OmniVoice có worker/config/cancel riêng.
   Giữ khóa OS giữa các app, chia quyền trong đúng Batch, nhả sau cleanup.
2. [x] Thư mục lưu chung cho Batch và tab Lồng tiếng; snapshot lúc bắt đầu, không
   thay dữ liệu cũ. Chống trùng tên/ghi đè, receipt gắn nguồn, reuse và final synthesis
   cùng thư mục đã chọn. Mở thư mục đầu ra đi tới kết quả thực tế.
3. [x] Test offline resource lease, isolation, cancel/retry, 429; thư mục trống/có chọn,
   nguồn trùng tên, lỗi ghi, title/reuse và captions. Đo GPU1/GPU2 trên cùng corpus,
   VRAM/process/elapsed/decode; chọn mặc định dựa trên số đo, giữ OmniVoice batch1.
4. [x] Ruff/Pyright/CLI/sync/full offline, build onedir với payload đã có, source-match,
   native GUI/CLI và payload inventory. Deploy E khi idle, backup delta, hash dữ liệu bảo vệ.

Không cài/tải model/dependency hoặc thay settings user khi đo. Không commit/push mới
trong phase này. CUDA process overlap không được trình bày thành kernel overlap hay
tăng tốc nếu chưa đo; nghe/production online là gate riêng.

## Source và phép đo

- Core `BatchGPUSession` giữ một OS lease cho đúng Batch, cấp context riêng cho mỗi
  worker đã được scheduler nhận. OmniVoice theo context: worker/pipe/options/cancel
  riêng, cùng model pin. Ngoài Batch vẫn giữ quyền độc chiếm cũ của managed runtimes.
- Chế độ2 chỉ chia sẻ giữa Faster-Whisper và OmniVoice; Qwen/aligner/VieNeu/Local AI
  vẫn chạy riêng. Giữ mặc địnhGPU1 cho bản portable, cho phép chọnGPU2 để thử trên máy
  đủ VRAM. Không đổi cấu hình cá nhân, batch size OmniVoice, voice, tempo hoặc timing.
- Thư mục chung lưu trong `Dubbing.OutputDirectory`, mặc địnhtrống. Claim tên file
  bằng exclusive create, thêm số khi trùng, giữ cả sidecar cũ; chỉ xóa placeholder
  rỗng của chính job khi hủy/lỗi. Receipt theo nguồn nằm trong `.videocaptioner`,
  kiểm checksum output/captions trong cùng root trước reuse. Snapshot áp dụng cho
  Batch, tab Lồng tiếng và handoff sang ghép video. Không di chuyển output cũ.
- Focused131 pass. Full đầu2489 pass/1 fail do test chọn provider đã có sẵn không
  phát signal đổi provider; fixture nay bắt đầu từ OpenAI, giữ assertions. Full cuối
  **2490 pass / 5 skip / 58 deselected**, exit0/240,30s. Ruff/Pyright0/0/sync pass.
  Giữ các lỗi harness ban đầu (fake thiếu field, thiếu qapp, Qt teardown) trong audit;
  runner giữ một QApplication sống và settings riêng, không bỏ teardown/assertions.
- Loopback ASR/LLM/TTS + FFmpeg thật:3 nguồn cùng tên ở3 thư mục khác nhau,11,875s;
  peak ASR2/LLM3 tổng/TTS2;3 output khác tên trong thư mục chung, decode0/stderr0.
  Reuse16ms, không lỗi hoặc sửa input.
- GPU thật, ba clip tổng hợp15s: Faster-Whisper CUDA **large-v3**, OmniVoice batch1,
  LLM loopback. GPU1 **153,531s**, GPU2 **94,875s** (giảm khoảng38% trên phép đo này).
  Peak process model1/2; VRAM **toàn GPU** peak8069/12726MiB, baseline3325/3408MiB.
  GPU1 chạy trước, không phải benchmark hoán đổi thứ tự; không suy rộng thành tốc độ
  playlist dài hay kernel overlap. Cả6 MP4 decode0/stderr0,0 owned survivors,
  input nguyên hash; reuse16/31ms. Chưa nghiệm thu nghe/chất lượng bản dịch thật.
- Hủy thực với hai worker/giọng nữ1 và nam1: job1 CANCELLED, job2 COMPLETED; cleanup
  job1 **0,547s**, process job2 vẫn sống. Retry job1 COMPLETED, ba runtime riêng,
  giọng theo đúng job,0 survivors và0 GPU session slots còn giữ.
- Evidence: `.tools/gpu-output-20261003/`.

## EXE và bản chạy thật

- Build exit0/231,047s,6 WARNING/0 ERROR,31.749.133bytes,
  SHA256 `88062ce08305feb2d32e791ed74196ff637904be14b08a7b650ac62313494ce9`.
- 18 module khớp source;99.315 file/8 component model-runtime khớp size inventory,
  không cài/tải mới. Native CLI loopback40/40 cue,peak20,13,016s/exit0.
  Native GUI30,641s/exit0,0 owned survivors. GPU2 và thư mục chung được kiểm ở source;
  chưa có full Batch qua GUI EXE với provider online thật hoặc nghiệm thu nghe.
- Deploy E khi idle:602 app files khớpSHA,delta4 có backup;6.826 file settings,
  cookies, giọng, media/cache/manifest giữ nguyên hash. Không chép models, giữ
  tên EXE/shortcut. Live CLI help0; GUI/CLI loopback kế thừa same-SHA artifact.
- Không commit/push. `closeout.json` giữ danh sách file sửa và toàn bộ receipt.
