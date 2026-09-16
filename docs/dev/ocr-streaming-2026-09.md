# OCR-2 local và vision qua gateway — 2026-09-10

Worktree ASR-S3, nhánh `codex/asr-s3-native`, HEAD đầu **1457808** sạch, khớp
tracking và `git ls-remote origin`. Không sửa checkout master, commit/push,
đổi dependency, cài/tải model, build EXE hoặc chạy lại ASR/dịch/TTS của user.

**Kết quả:** đã có domain OCR-2 và fixture streaming/lifecycle. Vision qua gateway
đã thử thật, nhưng dừng ở request 5 do timeout; chưa hoàn tất so sánh 13 crop.
Đây chưa phải tính năng OCR có CLI/GUI hay nghiệm thu OCR-2 toàn bộ trên video thật.

## Domain mới

`videocaptioner/core/ocr/` độc lập Qt và runtime nhận dạng:

- `geometry.py`: ROI chuẩn hóa trên ảnh đã áp SAR/rotation, chuyển drag qua
  letterbox, ánh xạ ngược tới pixel nguồn. Chỉ nhận quarter-turn không mirror/shear;
  RGB trước crop giữ đúng ROI lẻ, không bị căn chroma làm tròn.
- `models.py`: geometry/timing/frame/span và raw line/read typed. PTS/time base
  gốc giữ riêng; nội bộ OCR-2 dùng phân số ms chính xác để kiểm fixture. Việc
  chốt integer ms và document/source identity thuộc OCR-3, chưa thay entity/editor.
- `source.py`: snapshot video trong job root do caller cấp, kiểm disk space,
  copy và SHA-256 cùng lượt, phát hiện nguồn đổi, cancel/timeout và cleanup đúng
  thư mục job. Chưa nối locator `APPDATA_PATH/ocr/jobs` vào CLI/GUI.
- `decoder.py`: FFmpeg `-copyts`, không autorotate ngầm, không filter `fps`,
  output passthrough. Hai reader ghép RGB với `showinfo` theo thứ tự và time base;
  metadata thiếu/hỏng/thừa, PTS đảo, frame cụt hoặc process lỗi đều dừng.
  Xem semantics của [FFmpeg](https://ffmpeg.org/ffmpeg.html).
- Queue chứa tối đa **4 ROI frame**; bound bảo thủ **8 payload ROI** gồm queue,
  buffer đọc/ghép và lookahead. Metadata queue tối đa 8; stderr line tối đa 16 KiB,
  không giữ toàn bộ stderr hoặc ảnh toàn video. Process có backpressure, timeout
  khi chờ decode, cancel, đóng cây process sở hữu và join reader. Reader giữ contextvars.
- Selection quét từ origin, giữ frame đang hiển thị khi selection bắt đầu giữa
  hai PTS. Timeline trừ **format start_time**, không tự mất offset stream video.
  Chưa tối ưu seek; video dài có đoạn chọn gần cuối vẫn phải decode phần trước.
  EOF thiếu duration giữ review và khoảng bất định, không dựng giờ theo frame rate.
- `tracking.py`: edge mask có ngưỡng contrast, so theo tile để bắt đổi một chữ,
  một ROI gồm một/hai dòng; blank ngắt cue, câu lặp sau blank tạo cue mới.
  Giữ first/sharpest/latest, tối đa **3 ảnh/track**. Fade/contrast đổi, biên
  selection và thời gian giữ nhóm quá dài có issue/khoảng bất định. Đây là
  heuristic đã đo trên fixture, chưa được hiệu chuẩn cho mọi nền động/font/cỡ chữ.
- `consensus.py`: chọn nguyên một chuỗi engine đã đọc; giữ script, dấu câu,
  xuống dòng và các candidate. Cache RAM theo SHA nguồn/profile/policy/crop,
  giới hạn số entry và byte JSON; đây không phải phép đo RSS heap Python.
  Cache hit không tính là một lần xác minh ảnh độc lập. Chưa có cache disk/eviction bền vững.
- `pipeline.py`: streaming tới recognizer được inject, không export thành công
  nếu ROI không ra nhóm. Empty read/bất đồng/chưa hiệu chuẩn luôn review. Kết quả
  trả ra không giữ payload ảnh của mọi cue. Consumer dừng sớm phải đóng iterator
  (ví dụ `contextlib.closing`); decoder tự đóng khi lỗi/cancel trong pipeline.

Chưa nối recognizer CPU thật vào RPC của pipeline này. Test recognizer ở OCR-2
là fake có kiểm tra cancel, cache và raw; không dùng test đó làm bằng chứng OCR
inference/cancel của runtime thật. Runtime pilot local và payload cũ giữ nguyên.
App host không import NumPy/cv2/ONNX/Paddle/Torch/Qt khi nạp các module OCR mới.

## Fixture, số đo và lỗi đã bắt

Video tổng hợp lossless, không audio; thử VFR, nonzero PTS, selection offset,
SAR 2:1, rotation 0/90/180/270 và ROI lẻ. Có đổi một ký tự giữa hai câu hai dòng,
câu lặp sau blank, fade vàng, ROI rỗng. So biên với PTS nguồn thật, không frame_index/fps.

Lượt đo riêng trong `build/ocr-pilot-20260910/ocr2-streaming-evidence/metrics.json`:

| Phạm vi | Số đo |
| --- | --- |
| Nguồn / selected spans / track | 9 frame / 8 spans / 3 track |
| Time base / origin | 1/10240 / 3 s |
| Biên track ms | 100–400, 400–700, 900–1200, khớp fixture |
| Queue peak / ứng viên mỗi track thực tế | 4 / 2 (6 crop đại diện, chưa OCR) |
| Tạo fixture / probe | 0,083 / 0,062 s |
| Process decode, có overlap tracking | 0,063 s |
| Tracking / toàn vòng decode + tracking | 0,024 / 0,075 s |
| Host sampled RSS / Windows peak working set | 33.427.456 / 33.898.496 byte |
| FFmpeg sampled RSS / observed Windows peak working set | 22.405.120 / 23.306.240 byte |
| Local detector/recognizer / vision calls của fixture | 0 / 0 / 0 |
| OCR load/inference | null, không chạy engine |

Không cộng các stage chồng nhau thành total. Mẫu ngắn này không là benchmark cold-disk,
video dài hoặc hiệu năng OCR thật. RSS được lấy mẫu mỗi 5 ms; không có RAM backend vision.

Fault injection dùng process Python thật: truncated frame, thiếu/thừa/hỏng PTS,
PTS không tăng, metadata quá dài, process treo/exit; kiểm process chết và reader join.
Đã bắt race **reader lỗi trong lúc queue get chờ, EOF đi trước kiểm lỗi** có thể
coi frame thiếu metadata là kết thúc bình thường. Sửa bằng kiểm lại lỗi trước nhánh EOF;
regression hiện pass. Thử early-close iterator, cancel giữa recognition fake,
snapshot cancel/disk shortage và context propagation riêng.

## Vision API: lượt thật bị dừng, không retry

User chọn cùng gateway `https://api.videocaptioner.cn/v1`, model `gpt-5.6-terra`,
sau đó chỉ định nguồn key trực tiếp. Credential giữ trong `LLMCredentials` ở RAM,
không settings/env/argv/log/Git. Dùng client riêng không shared prompt logger,
không dùng STT key. Giới hạn lượt thử: tối đa 13 request, 1.000 completion token/request,
timeout 300 s, retry 0; dừng ở lỗi đầu theo plan cũ.

13 crop giữ nguyên SHA. Guard đầu tiên dừng **trước API** vì prompt trong scratch
là CRLF còn hash plan thuộc file nguồn LF. Hai nội dung giống nhau sau chuẩn hóa
xuống dòng; dùng file nguồn khớp hash, không sửa prompt/crop/plan cũ.

`scripts/ocr_vision_pilot.py` chỉ gửi một crop màu nguyên gốc và prompt chung mỗi
request. Không tham chiếu/contact sheet/transcript/ảnh lân cận/absolute path trong
request. Raw response ghi trước parse/chấm; lỗi không ghi exception body có thể nhạy cảm.

- **5 request bắt đầu, 4 response hoàn chỉnh, crop 5 timeout 300,009 s; 8 crop chưa gửi.**
  Retry/cache app = **0/0**. Timeout không chứng minh provider chưa xử lý/tính phí.
- Bốn response trả đúng model ID `gpt-5.6-terra`; latency **6,224 / 6,605 / 7,606 /
  96,432 s**, median **7,106 s**. Vòng request gồm timeout **416,953 s**.
- Receipt đầu gọi trường này là `process_wall_s`, nhưng clock bắt đầu sau đọc
  config/credential, trước tạo client: **không bao gồm toàn OS process startup/import/exit**.
  Script đã sửa tên thành `request_loop_wall_s`, để process wall chưa đo là null;
  receipt/raw lượt đầu giữ nguyên, không ghi đè để che khác biệt.
- Usage xác nhận của **4 response**: **3.896 input + 297 output = 4.193 token**.
  Request timeout, total cả 5 attempts và cost tiền: **null**; không suy giá từ OpenAI
  cho gateway này. Load/inference backend và RAM vision chưa đo.

Trên **4 crop chung có response**, local và vision đều **3/4 exact codepoint**;
local giữ đủ chữ/số **3/4**, vision **4/4**. Vision đọc được chữ “tháng” ở crop 4
mà local bỏ, nhưng viết sáu dấu chấm ASCII thay hai ký tự ellipsis của tham chiếu.
Raster không xác định được encoding gốc, nên strict codepoint/CER không đồng nhất
với sai nghĩa. Không sửa raw, không ghép chữ từ đáp án vào output engine.

Agent đã xem lại 13 ảnh, diễn giải từng crop bằng tiếng Việt trong
`vision-terra-01/report.vi.md`; bảng chấm `comparison-partial.json` phân biệt response /
timeout / chưa gửi. Tham chiếu vẫn chưa được người bản ngữ xác nhận. Không lấy 4
crop này để kết luận bên nào tốt/rẻ hơn hoặc chọn engine mặc định.

Lượt local cũ giữ **13/13 có chữ, 10/13 exact, 12/13 đủ chữ**; không chạy lại model,
không sửa raw/profile/runtime/packaged Python. Tổng local inference mới của phiên = 0.

## Gate và phần còn mở

- OCR scoped ban đầu **46 pass**. Full offline với **Qt offscreen: 1.663 pass,
  5 skip, 51 deselected**, 140,25 s, exit 0. Skip: 4 test TTS thiếu service/key và
  1 QtMultimedia preview ở offscreen. Đây không phải pass online.
- Full offline native lượt trước tới 100% rồi exit **0xC0000005** lúc kết thúc,
  không có summary pass. Chưa xác định nguyên nhân; pass offscreen không xóa gate lỗi này.
- Sau full suite, sửa phạm vi clock vision, khoảng bất định EOF/holding limit,
  reject timeout không hữu hạn và xử lý POSIX process đã thoát; chạy lại scoped OCR/CLI
  trên source cuối. Xem số cuối trong `status.md` và `ocr2-final-scoped.log`.
  Kết quả cuối **196 passed (47 OCR + 149 CLI)** trong 10,48 s.
- Ruff app/tests/script pass, Pyright app **0 errors / 0 warnings**, translations
  in sync. Dùng Python 3.12.13 đã có, không `uv sync`/nâng tool. Pyright có thông báo
  worktree thiếu `.venv`, đã trỏ `--pythonpath` tới interpreter app.
- Hash source sample, mapping, reference, 13 crop và raw local vẫn khớp receipt cũ
  (`ocr2-preservation.json`). Không sửa media/ASR/Soniox/dịch/TTS/model cũ.
- Chưa: nhận dạng local streaming thật/cancel inference thật; hiệu chuẩn tracking
  trên clip riêng/nền động; cache disk; OCR timing của 13 cue thật; OCR-3 identity,
  document/CLI/review/adapters/editor; OCR-4 GUI/model manager/frozen/khác ổ.

Bước tiếp: giữ receipt timeout của crop 5, chốt một lượt tiếp tục vision tường minh
khi dịch vụ đáp ứng (không retry ngầm); nối recognizer CPU đã pin vào supervisor RPC
để đo decode→tracking→recognition/cancel thật trước OCR-3. Giữ cả hai hướng và chưa
chọn engine mặc định. Không mở lại nghiệm thu ASR để chặn phần OCR này.

## File thay đổi

23 file, không có media/raw/credential/model trong Git:

- `status.md`
- `docs/dev/ocr-streaming-2026-09.md`
- `docs/dev/ocr-next-session-prompt.md`
- `docs/plans/video-subtitle-ocr-integration-plan.md`
- `scripts/ocr_vision_pilot.py`
- `videocaptioner/core/ocr/__init__.py`
- `videocaptioner/core/ocr/models.py`
- `videocaptioner/core/ocr/geometry.py`
- `videocaptioner/core/ocr/source.py`
- `videocaptioner/core/ocr/decoder.py`
- `videocaptioner/core/ocr/tracking.py`
- `videocaptioner/core/ocr/consensus.py`
- `videocaptioner/core/ocr/pipeline.py`
- `tests/test_ocr/__init__.py`
- `tests/test_ocr/conftest.py`
- `tests/test_ocr/test_geometry.py`
- `tests/test_ocr/test_decoder.py`
- `tests/test_ocr/test_tracking.py`
- `tests/test_ocr/test_consensus.py`
- `tests/test_ocr/test_lifecycle.py`
- `tests/test_ocr/test_pipeline.py`
- `tests/test_ocr/test_source.py`
- `tests/test_ocr/test_vision_pilot.py`
