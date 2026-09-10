# Prompt phiên tiếp theo — sau submit OCR-3/4 GUI và EXE

Tiếp tục **VideoCaptioner-ASR-S3**, nhánh **codex/asr-s3-native**, không làm ở
checkout master. User đã yêu cầu submit/push snapshot hiện có và prompt bàn giao;
không suy quyền commit/push code mới hoặc gọi thêm vision API từ yêu cầu đó.

## Bắt đầu

1. Đọc `AGENTS.md`, `README.md`, phần mới nhất `status.md`,
   `docs/dev/ocr-gui-2026-09.md`, `docs/dev/ocr-document-2026-09.md` và
   `docs/plans/video-subtitle-ocr-integration-plan.md`. Đọc
   `ocr-runtime-2026-09.md`, `ocr-streaming-2026-09.md`, `ocr-pilot-2026-09.md`
   khi cần lịch sử đo; trạng thái trong các snapshot cũ không thay thế code hiện tại.
2. Chạy `git status --short --branch`, lấy HEAD thật, đối chiếu tracking/origin.
   Code OCR-3/4 chốt ở **`dbbd062`** (42 file); commit tài liệu theo sau. Không
   coi commit code là HEAD cuối hoặc checkout về `dc94a46`/`ed1c3a6`.
3. Giữ mọi thay đổi có sẵn. Không reset, merge master, commit/push/tag/release nếu
   chưa được yêu cầu. Không chạy lại test/model/API/build chỉ để có số pass mới.
   Không mở lại nghiệm thu ASR để trì hoãn OCR.

## Đã có — không viết lại từ đầu

- OCR-2 streaming PTS/time base, SAR/rotation/ROI, selection offset/lookahead,
  tracking/consensus/cache RAM và CPU runtime riêng. Queue thực **4**, bound
  bảo thủ **8 payload ROI**, tối đa **3 ảnh/track**. Không list ảnh toàn video.
  Backpressure, timeout/cancel, stderr drain, kill tree, join reader và contextvars.
- `VisualSourceIdentity`: SHA toàn snapshot + size/stream/geometry/time base/
  origin/selection. Không dùng AudioIdentity; cùng audio/duration nhưng khác
  chữ phải mismatch. Snapshot có kiểm nguồn thay đổi và cleanup.
- `ocr-document-v1`: stable cue/candidate IDs, raw/edited riêng, integer ms cùng
  rational ms/PTS/uncertainty/clipped provenance, config/profile snapshot,
  atomic save/load validation. Rỗng/thiếu/bất đồng/chưa duyệt/incomplete không
  xuất success. Đồng thuận ba crop vẫn có thể cùng sai; profile chưa hiệu chuẩn.
- Review chỉ chọn nguyên chuỗi một candidate engine đã đọc, có lý do; timing
  override riêng. Không ghép chữ, đổi giản/phồn, sửa tên hoặc LLM điền thiếu.
  Resume hiện là **review/resume scan đầy đủ**, chưa resume inference scan bị hủy.
- Optional OCR metadata giữ qua ASRData/clone/dịch/table/JSON/editor; hai dòng
  nguồn vẫn một cue. Không giả ASR native/aligned, speaker hoặc xưng hô.
  `editor-project-v1` giữ schema; mutation qua CommandStack; split cần text
  boundary tường minh, merge giữ lineage. Normal save JSON + SRT, ASS chỉ action riêng.
- CLI `ocr`/`ocr-review` có bundled bridge/profile và discovery runtime portable;
  override cũ vẫn dùng được. Review cần `--source`, verify tại máy, không nhận
  dạng/upload lại. Exit 5 khi còn review, 0 khi xuất đầy đủ đã duyệt. CLI subtitle
  với OCR không mặc định optimize/split; `--optimize` là opt-in.
- GUI **Nhận dạng → OCR phụ đề trong hình**: chọn video/selection/ROI, kiểm bộ
  đã cài, CPU/progress/cancel, mở/lưu review, crop/preview, undo/redo và export/
  handoff typed sang bảng phụ đề. Mở dialog không IO/model/network. Giữ raw và
  giải thích issue bằng Việt; không bắt user đoán từng chữ Trung để hoàn tất.
- Crop review lấy đúng PTS/ROI/transform, verify toàn nguồn và SHA RGB trước
  hiển thị. Preview tại ms lấy frame đầu tại/sau vị trí, không phải timing
  measurement mới. Worker xử lý IO/model; result muộn không sửa dialog đã đóng.
  Handoff không tự chạy dịch/TTS; bảng GUI không tự optimize/split OCR.
- `resources/ocr` có profile/worker cho source/pip/frozen. Worker giữ AST pilot
  (khác directive pyright), test parity profile bytes. Host không import/bundle
  NumPy/cv2/ONNX/RapidOCR/Paddle/Torch. Runtime/bridge pilot cũ không bị ghi đè.

## Việc tiếp theo ưu tiên

1. **Nghiệm thu toàn flow OCR bằng GUI của chính EXE hiện có**: chọn file/đoạn/ROI,
   CPU, progress/cancel/close, crop review, save/reopen/undo/redo, export, handoff
   bảng dịch/editor; dùng fixture tổng hợp trước. Binary hiện mới đo OCR qua CLI
   và GUI startup/close. Không cần build lại nếu chưa đổi code/resource; chỉ đúng
   process test và đóng sạch.
2. **Kiểm tính di chuyển toàn gói** khi cần gate khác ổ: EXE đi cùng đủ model/runtime,
   tự tìm path, không phụ thuộc checkout dev. Dùng lại bộ đã verify, không stage
   lại 48 GB từ đầu, tải model hoặc cài dependency. Không dùng gói OCR-only làm
   EXE test đầy đủ. Giữ artifact cũ, kể cả bản test ổ C từng bị automatic review
   chặn xóa; không thử cách khác để vượt chặn.
3. **Review hữu dụng/chất lượng**: đọc evidence lỗi chung của ba ảnh câu 4 trước
   khi đề xuất thay đổi. Bản Việt dự thảo/AI đọc ảnh chưa có trong review GUI;
   không tự mở network hoặc auto-accept để làm UI trông hoàn tất. Không chọn
   engine mặc định/thắng-thua từ fixture hoặc exact-codepoint đơn lẻ.
4. Sau các gate ưu tiên, triển khai theo phạm vi user tiếp tục giao: cache disk/
   quota, resume inference, downloader/update OCR có action tường minh, trích
   subtitle stream text/PGS. Những phần này **chưa có**; nút chọn/kiểm runtime
   hiện tại không phải model installer hoàn chỉnh. Karaoke/chữ chạy/vùng động,
   inpaint chữ gốc và suy speaker/TTS từ hình vẫn ngoài MVP hiện tại.
5. Fix nhỏ theo nguyên nhân, test gần trước; đổi metadata/lifecycle/runtime thì
   full offline Qt offscreen theo AGENTS. Native full-suite teardown
   **0xC0000005** cũ còn mở; source dialog hoặc GUI startup pass không chứng minh đã sửa.

## Artifact hiện có — dùng lại

`dist/VideoCaptioner-OCR4-20260910/VideoCaptioner-OCR4-20260910.exe`, onedir.

- Build **exit 0**, khoảng **440,338 s** kể cả copy/verify payload; **6 warning /
  0 error** (js/emscripten, curl_cffi, yt_dlp_ejs, tzdata, sip, AppKit).
- EXE **31.385.562 byte**, local **2026-09-10 19:42:10**, SHA-256
  `865c07a6104168bd6f7758abc04c70c0d45747a701aa779415bcf1d44664e7ff`.
- Models **127.610 file /48.739.395.432 byte**, mọi SHA đích khớp manifest;
  đủ Faster-Whisper, Qwen/aligner, Community-1, OmniVoice, VieNeu và OCR.
  **32 module app thay đổi** trong PYZ khớp source; resources khớp, host không
  có dependency OCR nặng. Artifact build trước commit, cùng code đã chốt.
- Native source dialog: fixture 13 frame VFR/nonzero PTS/no-audio, **3/3 câu
  hai dòng exact**, 3 track /6 candidates /2 fresh /4 cache. 2 detector/4 recognizer/
  0 classifier, job 2,922 s, inference 0,175 s, vòng GUI 3,703 s; đóng exit 0,
  0 worker. Harness chỉ duyệt tự động vì fixture có đáp án biết trước.
- Frozen CLI: cùng fixture **3/3 exact**, raw/IDs/source/config khớp source;
  2 fresh/4 cache, 2 detector/4 recognizer/0 classifier. Exit **5 đúng guard**,
  không SRT giả success; resume đã duyệt **exit 0**, không inference lại.
  Job 3,203 s, inference 0,173 s, OS process 4,531 s; stage overlap không cộng.
- GUI EXE startup: cửa sổ sau **1,719 s**, sống 25 s, tổng 26,203 s, đóng exit 0,
  0 child sót/không traceback stderr. Settings smoke mới tắt update/VieNeu
  auto-update, không credential. FFmpeg dùng bộ đã cài trên máy.
- Chưa nghiệm thu pip-installed, toàn flow GUI EXE, chuyển toàn gói sang ổ khác,
  từng ASR/TTS runtime mới hoặc video riêng/video dài. Không nâng phạm vi từ fixture.

Build sau này vẫn **một `VideoCaptioner.spec`**. Nếu dùng bộ đầy đủ đã có OCR ở
artifact trên, chỉ truyền `VC_TEST_MODELS_DIR` tới `models/` đó; **không truyền
thêm `VC_TEST_OCR_MODELS_DIR`** vì helper từ chối OCR trùng. Khi dùng bộ ASR/TTS
cũ `dist/VideoCaptioner-ASRRecovery-20260910/models/`, có thể ghép bộ OCR
`build/ocr-pilot-20260910/portable/models/` qua biến thứ hai vào đích mới có
owner/inventory hợp lệ. Không bỏ guard hoặc sửa inventory để né lỗi. Standard
spec dùng staging `build/VideoCaptioner/`; kiểm target build/dist trước `--clean`.

## Evidence, runtime và dữ liệu phải giữ

Scratch duy nhất: **`build/ocr-pilot-20260910/`**. Không đưa raw/media/key/log/model
vào Git hoặc xóa artifact/runtime/download để dọn ổ.

- OCR-3 `ocr3-contract-08/`: gates/full-offline/preservation; 278 scoped pass,
  full lúc đó **1.718 pass/5 skip/51 deselected**.
- OCR-4 `ocr4-gui-09/`: `gates.json`, `full-offline.log`, `source-gui-receipt.json`,
  `source-pending.ocr.json`, `source-reviewed.ocr.json`, `synthetic.mov`, PNG UI,
  `artifact-receipt.json`, `changed-source-match.json`, `frozen-*`, `build.log`,
  GUI stdout/stderr và harness. Gate cuối **1.735 pass/5 skip/51 deselected**,
  159,84 s; scoped trước tinh chỉnh cuối **271 pass**, 23,21 s. Ruff/Pyright **0/0**/
  translations pass; 4 skip TTS cần service/key, 1 QtMultimedia cần backend native.
- OCR-4 thêm **4 CPU request/4 response**, **4 detector/8 recognizer/0 classifier
  attempts**, **0 vision request**. Giữ scope riêng, không ghi đè ledger OCR-2.
- `inputs/manifest.json` +13 `crop-*.png` gốc **1920×80**, ROI [0,960,1920,80],
  vẫn **13/13 khớp SHA**. Dùng lại, kiểm SHA, không trích lại cùng input.
- `local-final/`/`report.vi.md`, `cpu-sample-final-06/`: sample 60 s/1.800 frame/
  13 track/39 candidates, **10/13 exact, 12/13 đủ chữ-số**. Cả ba ảnh câu 4 bỏ
  “tháng”; câu 4/10 khác ellipsis, câu 6 khác mã dấu hỏi. Giữ raw/review.
- `local-bounded-crop04-07/`: crop sát detector box đọc lại “tháng” nhưng sai dấu;
  bản 2× lại mất chữ. Không tự bật biến thể, sweep model hoặc thay input gốc.
- `cpu-attempt-ledger.json`: continuation OCR-2 **84 request/81 response**,
  84 detector wrapper/59 recognizer/0 classifier; một detector hủy chưa rõ
  completion. OCR-1 có 32 detector/32 recognizer ở scope riêng. Giữ các run lỗi/
  debug/hủy và `upstream/`, không dùng chúng thay raw chấm chất lượng thành công.
- `cpu-stream-final-03/` có decode clock double-close cũ 0,766 s, không dùng làm
  clock mới. `cpu-cancel-04/` đóng worker/readers/job sạch 0,377 s. Metrics sample
  warm-cache/RSS/overlap đầy đủ ở `ocr-runtime-2026-09.md`; không cộng stage/peak
  thành total giả hoặc lấy chúng làm benchmark video dài/cold-disk.
- Nguồn cũ `build/asr-session-evidence/VC-UserClip-20260908-114035/` giữ sample,
  provenance/visibility reports. Nguồn 30 fps/time base 1/16000; prototype 25 Hz
  không phải ground truth độc lập cho biên cue. OCR đo chữ hiển thị, không lời nói.
- Host Python 3.12.13 `../VideoCaptioner/.venv/Scripts/python.exe`, FFmpeg/ffprobe
  `../VideoCaptioner/AppData/bin/ffmpeg/`. Pyright dùng `--venvpath ../VideoCaptioner`.
  Không Python 3.13/global install/uv sync/nâng dependency hoặc tải lại model.
- Recipe RapidOCR 3.9.2/ONNX CPU 1.29.0, PP-OCRv5 mobile detector +Chinese server
  recognizer, dictionary 18.383 entry, 23 deps lock/hash. Không RapidOCR() mặc định.
  OCR runtime/payload cũ giữ nguyên, app dùng bridge trong resources hiện tại.
- Giữ clip 30 s, ASR/dịch/6 WAV, Soniox 21 cue/review gốc, bài giảng 151 WAV/121
  nhóm lời đã sửa; không nhận dạng/dịch/TTS/render lại. DeepLX/Google/Bing/Bijian/
  Bilibili/Jianying/ElevenLabs vẫn ngoài nghiệm thu. Không bật Computer Use cho
  file/code; GUI chỉ đúng process test, đóng sạch.

## Vision: endpoint đã chọn, cap cũ đã hết

- User chọn **`https://api.videocaptioner.cn/v1`**, **`gpt-5.6-terra`**, timeout
  300 s; key gateway từ `Api.txt` ở gốc ổ đã chỉ định trong hội thoại. Không hỏi
  lại endpoint/model hoặc dùng STT key. Chỉ đọc key khi có lượt API được phép;
  LLMCredentials ở RAM, không settings/argv/env/log/Git.
- `vision-terra-01/` +`vision-terra-02/`: **13 attempts/12 response/retry 0**,
  crop 5 timeout 300,009 s. Không gửi lại crop thành công hoặc retry trong cap 13.
- `vision-combined-03/`: 12 ảnh chung local **9/12 exact, 11/12 đủ chữ-số**;
  vision **8/12 exact, 12/12 đủ chữ-số**. Khác ellipsis/ASCII/fullwidth không tự
  là sai nghĩa; tham chiếu agent chưa native-confirmed, không suy engine thắng/thua.
- Usage 12 response: **38.090 prompt +608 completion =38.698 token**, provider
  báo 26.880 cached prompt token, khác 0 cache hit của app. Timeout/toàn 13 attempts/
  cost tiền = null. Median 22,351 s/max 241,266 s. Không suy backend từ model alias.
- **Đã hỏi thêm đúng 1 request crop 5, cap tổng 14; chưa có trả lời cho phép.**
  Submit/push hoặc “làm tiếp” chung không tự tăng cap. Chỉ khi được duyệt rõ:
  `--retry-crop crop-05 --max-calls 14`, cùng cả hai `--previous-run`, output mới,
  tối đa 1.000 completion token, retry tự động 0. Không đổi model/key/endpoint để
  che timeout. Prompt scratch CRLF khác source LF; dùng prompt/hash đã kiểm,
  không sửa hash/receipt/input để né guard.
- Request chỉ từng crop +prompt chung, không reference/transcript/contact sheet/
  ảnh lân cận. Giữ raw/usage/latency/attempt rồi mới chấm, giải thích bằng Việt;
  không giao user việc chấm từng chữ Trung.

Cập nhật status/biên bản khi có behavior/validation mới; báo source/isolated runtime/
packaged Python/frozen CLI/GUI riêng và pass/fail/skip/chưa chạy. Không gọi OCR
hoàn tất khi chưa đủ gate; quyền submit/push chỉ cho snapshot vừa chốt.
