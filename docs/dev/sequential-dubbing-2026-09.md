# Đọc tuần tự và rút gọn riêng lời vượt khung — 2026-09-09

## 2026-09-29 — đọc đủ lời ở 1×, giới hạn trễ 1000 ms

Ưu tiên mới của user thay cấu hình gợi ý trong các mốc lịch sử bên dưới:
Natural + sequential, provider speed 1.0, natural_max_speed 1.0,
max_start_delay_ms 1000, rewrite_enabled False. Giữ gap 80 ms, không phải nghỉ
1 giây mỗi câu. Thực hiện trên subtitle có sẵn, độc lập với gate OCR/ASR.

- Đường scheduling hiện có đã đáp ứng thứ tự/không overlap ở 1×; không viết
  scheduler mới. Thời lượng WAV được đo và kiểm lại cả fresh/cache/resume.
- Tái hiện mất prefix lặp có chủ ý trong group (`Go now` + `now please.`).
  Sequential nay nối nguyên text; giữ grouping, cue IDs, source/display/timing.
  Các policy khác giữ heuristic và mặc định cũ. Cache key theo lời đầy đủ nên
  không dùng nhầm WAV đã mất từ. Review cũ có `original_tts_text` khác bị chặn
  mismatch thay vì âm thầm coi nội dung cũ là đủ; giữ checkpoint để đối chiếu.
- Tái hiện video 3 s/audio gốc 1 s bị mux thành video 0,9 s, mất tone đuôi.
  Keep/reduce nay dùng `amix duration=longest`; `-shortest` vẫn giới hạn theo
  video. Không audio stream tiếp tục mute fallback.
- Ca video 3 s/audio gốc 5 s từng được coi là khung 5 s, cho xuất lời tới 4 s.
  Sequential nay đọc duration của video stream `v:0`, hỗ trợ tag Matroska và
  từ chối duration không xác định trước TTS; không đoán từ subtitle.
- Vượt trễ/cuối video giữ review với số đo cụ thể. Khi cache tắt, WAV hoàn tất
  được giữ tại `review-audio/vc_dub_*` dưới cache root; resume vẫn synthesize
  lại theo lựa chọn không cache. Cache bật dùng lại đúng WAV, đo lại timing.
  Provider lỗi không xuất output thiếu lời; resume chỉ tạo group thiếu khi có cache.
- GUI/CLI đã có đủ controls/flags; regression xác nhận readback đủ 1×/1000 ms/
  no rewrite/80 ms. Không sửa settings thật hoặc mặc định toàn app, không thêm preset.

Audit `.tools/tts-sequential-20260929/` giữ reproduction, scope, Git/hash baseline,
logs/XML fail và pass. Baseline đã sửa assertion so object trong fixture:
**9 failed/10 passed**; một ca bổ sung về audio gốc dài hơn video **fail trước sửa**.
Lượt đầu có một lỗi test so object thay vì fields; giữ log, không tính là lỗi app.
Validation cuối: **201 passed/0 skipped**, gồm **30 ca mới**, 1 warning dependency;
Ruff scoped pass, Pyright scoped 0 error/0 warning. Không cộng các lượt chạy lặp.
FFmpeg thật kiểm tone đuôi tới 2,98 s của video 3 s, keep/reduce/mute, nguồn có
audio ngắn/không audio, và toàn engine export MP4/Matroska tới cuối video ở 1×.

Đây là machine verification với fake TTS/tín hiệu tổng hợp, không chứng minh
provider thật đã đọc từng từ hoặc giọng nghe tự nhiên. Chưa nghe thật, native
GUI/EXE/whole-video, GPU/API hoặc build mới. Không install/download, ASR/OCR
inference, đổi Pages, commit/push. TTS không đóng P1/P2, D3, D1, numerical
frontend hoặc real-model cache parity đang mở. Baseline HEAD/origin/master
`03ac8907c4f0987a4d6ef216536066f0184df376`; hai stash được giữ.

Hướng dẫn chọn cấu hình: [Natural Dubbing](natural-dubbing.md#đọc-lần-lượt-không-chồng-lời).
Phần dưới là lịch sử, không phải chỉ dẫn tự nâng trễ/tốc độ hay rút lời cho job này.

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
