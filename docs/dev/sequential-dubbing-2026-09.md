# Đọc tuần tự và rút gọn riêng lời vượt khung — 2026-09-09

## Chỉ đạo mới: giữ nhịp đọc đều

User phản hồi preview tăng tốc từng nhóm nghe lúc nhanh lúc chậm, không tự nhiên.
Đã thay scheduler thành **một hệ số tốc độ chung cho toàn job**, ưu tiên 1,00×;
gợi ý tăng nhẹ tối đa 1,05×, ưu tiên LLM rút lời dài. Đây thay thế hướng tăng
riêng từng nhóm trong bản thử bên dưới; không gọi bản thử đó là user đã chấp nhận.

Lượt mới trong `build/steady-dubbing-20260909/`:

- User nhập key kín cho scope hai group dài. **3 request LLM** bằng gateway/
  `gpt-5.6-terra`, timeout 300 s; g-0002 có hai phản hồi không parse được JSON,
  g-0003 có một bản rút gọn hợp lệ. Chỉ g-0003 cần một synthesis mới, WAV **6,6 s**.
- Với trần 1,00× và giới hạn trễ 2 s, job dừng review: độ trễ lớn nhất 2,12 s.
  Giữ report lỗi; không gọi các request/TTS đã hoàn tất lại. Key không được lưu.
- Resume bằng rewrite/audio cache, giữ 1,00× và giới hạn trễ **2,5 s** theo ưu
  tiên nhịp tự nhiên của user: preview tạo được, **0 overlap**, trễ lớn nhất
  **2120 ms**, **0 speed adjustments**, 1 group dùng lời rút gọn. Những group
  còn lại giữ text/audio gốc; source subtitle/hash không đổi.
- `lecture-steady-preview.mp4` SHA-256
  `1bec5dee8ae53106136a94c60c16781d2322632c700a2af2d94c1ae2e57b1f4c`.
  Có SRT theo lời đọc mới. Resume không có request LLM/TTS mới.
- Parser rewrite nay chấp nhận một JSON object được bọc trong code-fence, vẫn
  kiểm schema/group ID/nội dung bảo vệ. Không có raw của hai response g-0002,
  nên không khẳng định chúng chỉ lỗi code-fence hoặc đã được khôi phục.
- Cache context dùng subtitle gốc bất biến của câu trước/sau; không đưa output
  rewrite ngẫu nhiên của group trước vào cache key. Prompt version v3.

### Gate bàn giao bản giữ nhịp

- Suite liên quan cuối: **205 pass / 12,58 s**; 24 case tập trung pass. Ruff
  app/tests pass, pyright 0/0, translations in sync. Không chạy lại các gate này
  sau lần ngắt vì chỉ hoàn tất ghi nhận kết quả và tài liệu.
- PyInstaller bản `VideoCaptioner-Natural-Steady-20260909`: **exit 0 / 123,694 s**,
  **6 WARNING / 0 ERROR** (js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit).
- EXE **31.223.652 byte**, timestamp local **2026-09-09 14:40:07**; SHA-256
  `b4e2c87341f6b4047a4b63f3e42c981b1bec53b9c8b6d3535aa3a416471ba961`.
  Giữ nguyên onedir trong `dist/VideoCaptioner-Natural-Steady-20260909/`.
- GUI từ artifact sống **25 s**, cửa sổ chính tồn tại, đóng đúng PID **exit 0**,
  không force; log không traceback/ERROR.
- Frozen CLI **exit 0 / 17,281 s**: dùng lời đọc đã chuẩn bị với mốc gốc của
  từng group và cache WAV, **5 cache hits / 0 TTS generation mới**. Xác nhận
  tốc độ 1,00×, không overlap, trễ tối đa 2120 ms trong trần 2500 ms; không child
  còn sống. Prompt rewrite đóng gói có hash giống source. Không gọi LLM mới.
- Source rewrite thật đã đo phía trên; chưa rewrite online từ EXE, chưa bấm
  toàn workflow GUI hoặc lồng tiếng cả 180 cue. Chất lượng nghe bản mới chờ user.

Các phần phía dưới ghi bản thử tăng tốc cục bộ trước phản hồi này.

User yêu cầu tránh chồng lời, có thể dùng LLM rút gọn riêng câu dài hoặc chờ câu
trước đọc xong và tự tăng tốc khi cần. Đã thêm policy `sequential` trong Natural,
bên cạnh `review` và `allow-overlap`; giữ nguyên lựa chọn Legacy và các dữ liệu cũ.

## Hành vi

- TTS/cache → đo WAV → chỉ rewrite group có `fit_ratio > fit_ratio_limit` → đo
  lại candidate → xếp lịch đọc. Bỏ pre-rewrite dựa vào độ dài dự đoán trước TTS.
- LLM chỉ sửa `tts_text`; source/subtitle display giữ nguyên. Prompt yêu cầu
  rút từ đệm/lặp, dùng lời nói gọn tự nhiên, giữ nghĩa, tên, số, đơn vị và phủ định.
  Budget dùng word-like units hoặc ký tự CJK. Cache rewrite đổi prompt version,
  phụ thuộc ngôn ngữ và dữ liệu/config tất định.
- Rewrite request dùng `OwnedLLMRequest`, credential và deadline riêng của job,
  có hủy trong lúc chờ mạng. Deadline lấy cấu hình LLM hiện có; gateway/terra dùng
  300 s như lượt dịch trước khi cấu hình job tương ứng. Không đặt key vào env.
- Scheduler tính ngược sức chứa tương lai tại trần tốc độ, sau đó chọn tốc độ
  thấp nhất cần thiết; ưu tiên giữ 1×. Câu sau chờ câu trước và khoảng nghỉ mặc
  định 80 ms (ít nhất 20 ms). Tốc độ bổ sung không nhân vượt trần với tốc độ
  provider đã yêu cầu.
- Đo lại WAV sau FFmpeg atempo và dùng duration thật để xếp lượt. Giữ giới hạn
  trễ bắt đầu, mặc định 2000 ms, và thời lượng video. Không thể xếp đủ thì yêu cầu
  review/rút gọn thêm; không mix một kết quả thiếu lời.
- Report giữ `start_time`/`subtitle_end_time` gốc và thêm `playback_start_time`,
  `playback_end_time`, `start_delay`, `applied_speed`. GUI hiển thị giờ đọc, độ
  trễ, tốc độ thêm; summary có số group dời và độ trễ lớn nhất.

GUI: **Tự nhiên → Đọc lần lượt, không chồng lời**, gợi ý Natural tối đa **1,20×**,
trễ tối đa **2000 ms**. Bật **LLM rút gọn riêng lời đọc vượt khung** nếu cần và đã
cấu hình LLM. CLI: `--unresolved sequential --natural-max-speed 1.2
--max-start-delay-ms 2000`. Default của mode/cap cũ không tự bị đổi.

## Preview từ audio đã có

Evidence: `build/sequential-dubbing-20260909/`. Dùng clip 30 s và 5 cache WAV của
lượt OmniVoice trước; original SRT/hash giữ nguyên. Không ASR, dịch, rewrite LLM
hoặc TTS generation mới; worker/model load và reference configuration vẫn là
luồng OmniVoice thật. Adapter synthesis được chặn trong helper để không chạy lại.

- Source CLI **exit 0 / 48,219 s**, 5 cache hits, 0 TTS attempts.
- **Không overlap** sau đo WAV; 3 group dời, độ trễ lớn nhất **1939 ms**.
- Chỉ group 2/3 tăng tốc khoảng **1,199× / 1,195×**, còn lại 1×.
- Lời đọc kết thúc **29,059 s** trong clip khoảng 30 s, không group cần review.
- Có `lecture-sequential-preview.mp4` và `preview.spoken.vi.srt` theo mốc đọc
  mới; file phụ đề gốc không đổi. Mẫu này dùng `--no-timing-rewrite`, nên chưa
  là nghiệm thu LLM rewrite online mới.
- Sau lượt source, sửa trường `fit_ratio` trong report để tính lại theo WAV
  đã tăng tốc. Không ảnh hưởng audio/lịch đọc; frozen validation dùng code cuối.

## Gate

- Dubbing/CLI/thread/UI: **202 pass**. UI thêm case mới: 2 pass sau giữ QApplication
  sống theo session (lượt đầu fixture thả app làm QConfig bị hủy). Tổng 203 test
  khác nhau, không cộng các rerun. Sequential + rewrite cuối: 20 pass.
- Có test thực FFmpeg cho measured-only rewrite và các policy cũ; test lịch nhìn
  trước, tốc độ/drift, remeasure, giữ subtitle gốc, deadline không thể fit,
  provider speed không nhân vượt trần và dữ liệu duration không hợp lệ.
- Ruff app/tests pass, pyright 0/0, translations in sync. Không full corpus,
  không benchmark model, không xin lại API key vì preview không cần gọi LLM.
- Build cuối dùng spec duy nhất, tên `VideoCaptioner-Natural-Sequential-20260909`.
  Build/smoke/frozen receipts nằm cùng evidence; xem các gate ghi bên dưới khi bàn giao.

## File thuộc lượt này

- Thêm `core/dubbing/scheduling.py`; sửa `core/dubbing/{models,config,planner,
  orchestrator,rewrite_service,engine,presets}.py` dưới `videocaptioner/`.
- Sửa `core/prompts/dubbing/rescue.md`, `cli/{main,config}.py`,
  `cli/commands/dub.py`, `ui/common/config.py`, `ui/task_factory.py`,
  `ui/view/dubbing_interface.py`, `ui/components/DubbingReportDialog.py`.
- Thêm `tests/test_dubbing/test_sequential.py`; sửa integration test dubbing
  và `tests/test_omnivoice/test_ui.py`.
- `VideoCaptioner.spec`, `README.md`, `docs/dev/natural-dubbing.md`, tài liệu này,
  `status.md`, plan và bàn giao. Giữ mọi thay đổi ASR/OmniVoice/translation trước đó.

Chưa chấm chất lượng nghe hoặc chạy toàn bộ 180 cue. Rewrite online với prompt
mới và thao tác GUI lồng tiếng đầy đủ chưa được đo; không coi test offline là
pass cho các phần đó. Không commit/push.
