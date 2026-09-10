# Prompt phiên tiếp theo — sau submit OCR-2 CPU streaming

Tiếp tục **VideoCaptioner-ASR-S3**, nhánh **codex/asr-s3-native**, không làm ở
checkout master. User yêu cầu submit/push snapshot này và prompt bàn giao;
không suy quyền commit/push code mới hoặc gọi thêm vision API từ yêu cầu đó.

## Bắt đầu

1. Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`,
   `docs/dev/ocr-runtime-2026-09.md` và
   `docs/plans/video-subtitle-ocr-integration-plan.md`. Đọc
   `ocr-streaming-2026-09.md` / `ocr-pilot-2026-09.md` khi cần lịch sử đo.
2. Chạy `git status --short --branch`, lấy HEAD thật, đối chiếu tracking/origin.
   Code/domain/CPU/vision/test đã chốt ở **`ed1c3a6`**; commit tài liệu theo sau.
   Không coi commit code là HEAD cuối hoặc checkout về `1457808`/`0348d7e`.
3. Giữ mọi thay đổi có sẵn. Không reset, merge master, commit/push/tag/release nếu
   chưa được yêu cầu. Không chạy lại test/model/API/build chỉ để có số pass mới.
   Không mở lại nghiệm thu ASR để trì hoãn OCR.

## OCR-2 đã có, không viết lại từ đầu

- `core/ocr/`: geometry, typed frame/span/read, snapshot SHA, decoder, tracking,
  consensus/cache RAM, pipeline và **CpuOcrRuntime thật**. Chưa có
  VisualSourceIdentity/OcrDocument/public CLI/review/adapters/editor OCR.
- Decode theo PTS/time base nguồn, SAR/rotation/ROI tường minh, không frame_index/fps.
  Selection offset và frame đang hiển thị có lookahead; clipped/uncertain boundary
  giữ review, EOF không biết duration không tự dựng giờ.
- Queue thực **4**, bound bảo thủ **8 payload ROI** gồm buffer/lookahead, tối đa
  **3 ảnh/track**. Không giữ ảnh toàn video thành list. Backpressure, timeout/cancel,
  drain stderr, đóng cây process, join reader và contextvars đã có.
- `scripts/ocr_stream_worker.py` dùng Python OCR đã cài; verify package/model/
  dictionary/profile SHA, giữ model trong process riêng, chặn network/download.
  Request RGB có SHA, chuyển BGR, output UTF-8 binary. Không import NumPy/cv2/ONNX/
  Paddle/Torch/Qt vào host. Bridge mới ở source, **chưa cài/bundle vào payload cũ**.
- `scripts/ocr_stream_pilot.py` là harness evidence, không phải public CLI.
  Chưa có cache disk, locator/model manager, GUI/frozen OCR.
- Đã sửa race reader lỗi bị EOF bỏ qua, stdout cp1252 của Python `-I`, codec noise
  luma 0–1 bị edge filter khuếch đại thành cue giả, và close kéo dài clock lần hai.

## Evidence phải giữ

Scratch duy nhất: **`build/ocr-pilot-20260910/`**. Không đưa raw/media/key/log/model
vào Git hoặc xóa runtime/artifact/download để dọn ổ.

- `inputs/manifest.json` + 13 `crop-*.png`: crop gốc 1920×80, ROI [0,960,1920,80],
  có SHA. Dùng lại, kiểm SHA, không trích lại cùng input.
- `local-final/` + `report.vi.md`: pilot gốc 13/13 có chữ, **10/13 exact,
  12/13 đủ chữ-số**. Câu 4 thiếu “tháng”; câu 4/10 khác dấu ba chấm, câu 6 khác
  mã dấu hỏi. Tham chiếu agent chưa native-confirmed, không sửa raw theo đáp án.
- `cpu-stream-final-03/`: fixture VFR/nonzero PTS/no-audio, 3/3 text hai dòng exact,
  6 candidate → 2 fresh/4 cache, 2 detector/4 recognizer/0 classifier. Receipt
  decode 0,766 s có lỗi double-close trước sửa, không dùng làm clock mới.
- `cpu-cancel-04/`: hủy sau detector wrapper bắt đầu, process/readers/job sạch
  trong **0,377 s**. Một detector attempt chưa biết completion.
- `cpu-sample-final-06/`: sample 60 s → **1.800 frame /13 track /39 candidate**,
  **38 fresh/1 cache**, 38 detector/38 recognizer/0 classifier, network 0.
  **10/13 exact, 12/13 đủ chữ-số**, cả ba ảnh câu 4 cùng bỏ “tháng”. Giữ review.
- Lượt sample cuối: load 0,542 s, inference 9,812 s, tracking 17,464 s,
  decode/pipeline 28,968 s có overlap/backpressure, worker process 30,797 s,
  harness 30,889 s trừ host startup/import. Host/worker peak working set
  36.552.704/510.349.312 byte; FFmpeg sampled RSS 98.553.856 byte.
  Không cộng stage/peak riêng thành total giả; chưa cold-disk/video dài.
- `local-bounded-crop04-07/`: crop sát detector box đọc lại “tháng” nhưng sai dấu;
  bản 2× lại mất chữ. Không tự bật biến thể, sweep model hoặc thay 13 input gốc.
- `cpu-attempt-ledger.json`: cả debug/lỗi/hủy/biến thể của continuation:
  **84 request worker /81 response**, 84 detector wrapper/59 recognizer wrapper/
  0 classifier. Một detector bị hủy chưa rõ completion. OCR-1 có 32 detector/32
  recognizer ở phạm vi lịch sử riêng, không ghi đè hoặc gọi toàn bộ wrapper đã hoàn tất.
- Giữ các lượt lỗi `local-fresh/`, `local-startup-diagnostic/`, `local-measured/`,
  `cpu-stream-01/`, `cpu-stream-diagnostic-02/`, `cpu-sample-05/` và profile cũ
  trong `upstream/`; không dùng thay raw chấm chất lượng thành công.
- `cpu-final-gates.json`, `cpu-final-scoped.log`, `cpu-full-offline.log` và các
  preservation/metrics trước đó ghi phạm vi gate; artifact ngoài Git.

Nguồn cũ `build/asr-session-evidence/VC-UserClip-20260908-114035/` giữ sample,
`reports/reference-provenance.json`, `reports/source-caption-visibility-refined.json`.
Video 30 fps, time base 1/16000. Delta prototype 25 Hz với PTS nguồn **không phải
ground truth độc lập cho biên cue**. Fixture timing pass; chưa chứng nhận mọi biên
cue video riêng frame-accurate. OCR đo chữ hiển thị, không đo lời nói.

## Vision: đã có cấu hình, cap cũ đã hết

- User đã chọn **`https://api.videocaptioner.cn/v1`**, **`gpt-5.6-terra`**, timeout
  300 s và cho lấy key gateway từ file `Api.txt` ở gốc ổ đĩa đã chỉ định trong
  hội thoại. Không hỏi lại endpoint/model hoặc dùng STT key. Chỉ đọc key khi cần
  API; LLMCredentials ở RAM, không settings/argv/env/log/Git.
- `vision-terra-01/`: 5 attempts, 4 response, crop 5 timeout 300,009 s.
  `vision-terra-02/`: crop 6–13, 8 attempts/8 response. Tổng **13 attempts,
  12 response, retry 0**; không gửi lại crop thành công hoặc crop 5.
- `vision-combined-03/`: 12 ảnh chung local **9/12 exact, 11/12 đủ chữ-số**;
  vision **8/12 exact, 12/12 đủ chữ-số**. Khác mã ellipsis/ASCII/fullwidth không
  tự là sai nghĩa; không kết luận engine thắng/thua hoặc chọn mặc định.
- Usage xác nhận 12 response: **38.090 prompt +608 completion =38.698 token**;
  provider báo 26.880 cached prompt token, khác **0 cache hit của app**.
  Timeout/toàn đủ 13 attempts/cost tiền = null. Median response 22,351 s,
  max 241,266 s. Cùng model ID nhưng usage shape khác nhau, không suy backend.
- `vision/plan.json` là kế hoạch trước API, giữ lịch sử. Prompt scratch CRLF khác
  hash nguồn LF; lượt thật dùng `scripts/ocr_pilot_data/vision-prompt.md` khớp SHA.
  Không sửa input/hash/receipt để né guard. `process_wall_s` ở receipt đầu thực
  chất vòng request; script mới dùng `request_loop_wall_s`, không sửa raw cũ.
- **Đã hỏi quyền thêm đúng 1 request crop 5, cap tổng 14; chưa có trả lời cho phép
  lúc chốt snapshot.** “Submit and push” không mở lại budget API. Kiểm tra chỉ đạo
  mới trước request thứ 14. Nếu được phép: `--retry-crop crop-05`, `--max-calls 14`,
  cùng cả hai `--previous-run`, output mới, tối đa 1.000 completion token, không
  retry tự động. Không đổi model/key/endpoint để che timeout.
- Request chỉ có từng crop + prompt chung, không tham chiếu/transcript/contact
  sheet/ảnh lân cận. Giữ raw/usage/latency/attempt rồi mới chấm. Agent giải thích
  bằng tiếng Việt; không giao user việc chấm từng chữ Trung.

## Việc tiếp theo: OCR-3 và các gate chất lượng còn mở

1. Ưu tiên domain/fixture **VisualSourceIdentity + OcrDocument/review/resume** theo
   plan; không chặn mọi tiến độ vì crop 5 đang chờ budget. Nguồn hình có SHA toàn
   snapshot, stream/geometry/SAR/rotation/time base/selection; không dùng AudioIdentity.
   Cùng audio/duration nhưng khác chữ phải mismatch.
2. Document `ocr-document-v1`: stable cue/candidate IDs, raw/edited riêng, integer ms
   cùng PTS/uncertainty/clipped provenance, config/profile snapshot, atomic save/load
   validation. Rỗng/thiếu/bất đồng/timing bất định không được xuất success. Chỉ chọn
   chuỗi engine đã đọc, không ghép chữ, đổi giản/phồn, sửa tên hoặc LLM điền thiếu.
   Đồng thuận ba crop vẫn có thể cùng sai.
3. Nối CLI/review/translator/editor bằng typed metadata; audit clone/split/merge/
   translation/JSON/save. Giữ ASR API cũ, không giả OCR là ASR native/aligned hoặc
   tự gán speaker/xưng hô. Editor mutation qua CommandStack, schema editor-project-v1,
   normal save JSON +SRT, ASS chỉ Save as ASS.
4. Chưa mở toàn GUI/model manager/frozen trước contract OCR-3. Giữ fixture đổi một
   chữ, hai dòng, blank/repeat/fade, VFR/nonzero PTS/offset/rotation/SAR/no-audio.
5. Gate đã có: **213 scoped pass (64 OCR +149 CLI)**, full Qt offscreen **1680 pass/
   5 skip/51 deselected**, 4 skip TTS cần key/service, 1 QtMultimedia offscreen.
   Ruff/Pyright 0/0/translations pass. Native full tới 100% rồi crash teardown
   **0xC0000005** ở lượt trước, chưa rõ nguyên nhân; không gọi native/GUI/frozen pass.

## Runtime, build và dữ liệu

- Host Python 3.12.13 `../VideoCaptioner/.venv/Scripts/python.exe`, FFmpeg/ffprobe
  `../VideoCaptioner/AppData/bin/ffmpeg/`. Không Python 3.13, global install,
  uv sync/nâng dependency app, tải/cài lại model đã có.
- Recipe `scripts/ocr_pilot_data/profile.json`: RapidOCR 3.9.2/ONNX CPU 1.29.0,
  PP-OCRv5 mobile detector +Chinese server recognizer, dictionary 18.383 entry,
  23 dependency lock/hash. Không RapidOCR() mặc định ngầm. Classifier bundled
  nạp do upstream, inference 0. Dùng profile/hash đi cùng từng receipt.
- Runtime `runtime/` và payload `portable/models/ocr/` trong scratch giữ nguyên;
  payload OCR 4.477 file/398.907.184 byte, không venv home ngoài gói. Chỉ đã kiểm
  packaged Python ở thư mục mới cùng ổ; bridge streaming mới chưa ở payload,
  chưa EXE/GUI/khác ổ. Đến OCR-4 phải bundle/verify riêng.
- EXE test phải kèm models/runtime đã cài cạnh EXE, tự tìm khi chuyển ổ. Một
  `VideoCaptioner.spec` + `VC_TEST_MODELS_DIR`; tái sử dụng bộ ASR/TTS 48 GB đã verify,
  không stage/tải lại vì code mới. Portable OCR riêng không phải bộ đủ ASR/TTS.
  Giữ guard owner/inventory của packager khi ghép OCR vào bộ đầy đủ.
- Giữ clip 30 s, ASR/dịch/6 WAV, Soniox 21 cue/review gốc, bài giảng và 151 WAV/
  121 nhóm lời đã sửa; không nhận dạng/dịch/TTS/render lại. DeepLX/Google/Bing/
  Bijian/Bilibili/Jianying/ElevenLabs vẫn ngoài nghiệm thu.
- Không xóa artifact/runtime/download, ghi đè dữ liệu user hoặc bật Computer Use
  cho file/code. Nếu cần GUI, chỉ đúng process test và đóng sạch.

Cập nhật status/biên bản khi có behavior/validation mới, báo source/isolated runtime/
packaged Python/frozen/GUI riêng và pass/fail/skip/chưa chạy. Không gọi OCR hoàn tất
khi chưa đủ gate, không suy quyền commit/push sang phiên sau.
