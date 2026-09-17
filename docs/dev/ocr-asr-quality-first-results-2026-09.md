# OCR/ASR quality-first — kết quả triển khai 2026-09-16

## 2026-09-17 — tiếp tục từ `62e852a`: chọn dấu cuối, loại candidate recognition

Audit mới: `.tools/ocr-asr-quality-20260917-112253/`. Kiểm live HEAD/remote/index/
diff/stash trước sửa; 29 source/runtime/input files đúng hash, 224 file bảo vệ.
Snapshot từ đúng HEAD, sync allowlist trước kiểm; settings/cache/log/temp/HF/Torch/UV
nằm trong audit. Không đổi runtime đã có hoặc cài package global.

### Dictionary và recognition

- PP-OCRv6 medium metadata có 18.708 entry, output 18.710 class; thiếu `诶`.
  Dictionary PP-OCRv5 upstream cũng thiếu glyph này, nên không tải model V5.
- Một giả thuyết: Chinese PP-OCRv4 có glyph cần đọc. Dictionary 6.623 entry,
  model output 6.625 class; verify embedded metadata trước inference. Chỉ tải
  recognizer còn thiếu vào audit, reuse Python/ONNX CPU runtime đã có.
  Model SHA `6a2676219be9907c7fc9cf61ebaa843bf2898777def567925b78886fcd90c07a`
  khớp [manifest RapidOCR](https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml).
- Khóa hai crop raw cùng hash với probe trước, cap 2 recognizer batches/120 s,
  không retry inference. Cả hai vẫn sai glyph; crop sau còn kém phần cuối.
  **Loại candidate, không tích hợp V4**. Dictionary coverage là điều kiện cần,
  không phải accuracy pass. Một lỗi harness thiếu `font_path` xảy ra trước inference;
  lần sửa API mới thực hiện đúng 2 batches/0 cache. Không lặp probes contrast/padding.

### Consensus có bằng chứng ảnh, giữ tracking v3

Ảnh PTS 1006400 và 1007467 đều có cụm dấu cuối; detector ở ảnh đầu chỉ tới x=960,
ảnh sau tới x=1012. Hai raw khác dấu, count hòa nhau; v1 chọn raw thiếu dấu do
confidence cao hơn. Synthetic regression tái hiện fail trước sửa, không đưa crop/
transcript của user vào fixture.

Thêm `witnessed-punctuation-v2`, opt-in CLI `--consensus punctuation-v2`.
Chỉ chọn **nguyên một raw read** có suffix dot/ellipsis, cùng body, bbox cùng hàng
mở rộng sang phải, cùng revision và đúng frame hash. Ảnh ở cả hai candidate phải
có đúng số component sáng/gọn khớp vị trí; fade, blank, thiếu/thêm/đổi vị trí dấu,
đổi body hoặc nhiều dòng không được nâng candidate theo heuristic này.
Disagreement và uncalibrated flags vẫn giữ; không ghép text/merge cue/bỏ guard.
Mặc định `exact-v1` và toàn bộ bytes worker v1/v2/v3 không đổi.

Replay đầu dùng ngưỡng sáng thấp bị lẫn nền vào hai dot component và không chọn
candidate. Tách phần sáng của nét khôi phục 6 component trên cả hai ảnh; replay
cuối đổi đúng raw candidate, **0 inference**. Đây là heuristic hẹp của pilot,
chưa hiệu chuẩn cho nền sáng, màu chữ, font, dấu khác hoặc thay đổi nhỏ không có
trong candidate frames; không tuyên bố sửa mọi lỗi punctuation/tracking.

Policy nằm trong config/document/cache identity, không migrate checkpoint cũ.
GUI resume trước sửa tái tạo consensus mặc định rồi từ chối checkpoint v2;
regression fail đúng ca này, sửa giữ policy đã lưu mà vẫn kiểm profile/worker.
Test harness GUI đầu tạo checkpoint rỗng gây thêm một failure không liên quan;
đã sửa fixture trước khi chốt regression thực và giữ log cả hai attempts.

| CLI thật, một lượt/window | Cue | Fresh/cache | Tracking/feature batches | Wall | Complete/export |
|---|---:|---:|---:|---:|---|
| D1 28,8–32,3 s | 2 | 6/0 | 105/231 | 86,516 s | true/exit0 |
| D2 57–63 s | 4 | 11/0 | 180/287 | 123,391 s | true/exit0 |

Cap khóa trước chạy: 40 recognition và 360 s/window. D1 text/biên giữ nguyên;
D2 giữ biên, lấy lại dấu cuối. Thán từ thiếu vẫn **unresolved**, P1 chưa pass.
17 recognition request window riêng với 2 diagnostic recognizer batches;
actual window recognizer attempts 12+14, detector attempts 111+191.
Tracking/feature batches không cộng vào recognition. Không mở lại window cùng config.

Final consensus source SHA:
`7464cfa5950da83df0f1f88666c4fb59a03b5e6688b71174fdf29bea954961d1`.
Worker v3 vẫn `9bef0946f8456c9f7e4a36f49feba0555f61540dfc8f45eea4f6f94375931447`.
`ocr-consensus-v2/plan.json` và checkpoints giữ đúng bytes đã đo. Phiên sau đổi
semantics consensus cần version mới, giữ đường resume của version đã commit.

### ASR D3 độc lập

Giả thuyết mới: so Qwen trên audio gốc và filtered dump **cùng 107–126 s** để
kiểm ảnh hưởng preprocessing tới lời lặp/đuôi lẻ. Khóa input hash/WAV info/config/
budget trong `asr-original/plan-locked.json` trước request; verify runtime Qwen
cùng pin `7278e1e70fe206f11671096ffdd38061171dd6e5`. Reuse raw Qwen filtered và
Whisper VAD-on original/filtered; không chạy lại các baseline hoặc Kim_Vocal_2.

Đúng **1 request mới/0 cache, 33,812 s**, cap stage 180 s/wall 240 s. Request WAV
SHA `4e02d2ccfa4452bf28e1cdeeb6eadb3e62ccacd20174e3dd1d115049b96dd36c`.
Lời lặp đổi nội dung, đuôi đáng ngờ vẫn tồn tại. Chưa có independent listening
reference; giữ `unknown`, không kết luận preprocessing/model thắng, không CER/WER,
alignment hay ghép text với timing engine khác. Không upload audio/OCR prompt.

### Validation, native và gate còn mở

- Final OCR/GUI scope **337 passed, 7 deselected**; ASR/CLI **243 passed**.
  Test mới gần consensus 16 ca được tính trong 337, không cộng trùng.
  Ruff pass, Pyright 0 errors/0 warnings, translation sync pass.
  Worker/model không đổi; 7 real-model regressions của audit trước được reuse
  theo hash, không gọi là 7 inference tests mới trong phiên này.
- Domain/CLI D1 2 cue, D2 4 cue và ASR baseline 33 cue giữ text/ms/IDs/metadata
  qua table/handoff/undo và hai vòng save/reopen. SRT giữ text/time.
- Qua Computer Use, native Editor mở project D2 được tạo từ CLI candidate,
  phát video thật (quan sát frame và clock tiến từ 57,267 s tới 65,947 s),
  lưu JSON+SRT rồi mở lại đủ 4 cue. Artifact sau native save giữ đúng text/ms/
  IDs/metadata. Không coi thao tác này là native OCR source-to-result workflow
  hoặc xác nhận nghe tiếng Trung, EXE hay inference toàn video.
- **Sai lệch protocol:** click pause khi clock khoảng 73,940 s, dừng thực ở
  **74,539 s**; preview đã lấn 539 ms vào H1 74–94 s. H1 không còn hoàn toàn
  unseen; phải ghi contamination hoặc khóa đoạn thay thế trước phép đo holdout
  tương lai. Không có inference trên H1/H2; không tự coi phần còn lại là holdout pass.
- Native OCR cancel trên candidate cuối chưa chạy; giữ nguyên vi phạm 33,740 s
  so budget 30 s của audit trước, không đổi thành pass. Service/CLI cancellation
  cuối dừng sau 8 tracking/0 recognition/0 feature batches, 18,047 s dưới cap 30 s;
  giữ partial và từ chối export với exit5. Receipt riêng `guard-checks/` không đại
  diện thao tác nút native.
- P1 glyph/text và P2 speech reference vẫn mở. Holdout inference, whole-video,
  full offline, build/EXE, TTS **NOT RUN**. Sáu câu Việt, voice B, media/models/
  raw/settings và hai stash được bảo vệ; chưa merge `master`.

Evidence chính: `dictionary-inventory.json`, `recognizer-v4-{plan,coverage,results}.json`,
`consensus-bright-replay.json`, `ocr-consensus-v2/`, `asr-original/`,
`p3-roundtrip-consensus/`, `native/results.json`, `run-ledger.jsonl`, `review.json`,
`preservation-check.json`, `publication.json`. Failed harness attempts còn trong log;
không tính chúng thành inference pass. Nhánh tiếp theo cần recognizer có coverage
và accuracy trên glyph nhỏ hoặc reference audio đủ tin cậy; không lặp V4/raw hay
Qwen D3 original vừa chạy để chọn output đẹp.

## Tiếp tục từ `46d457e`: tracking D2 đã sửa, text gate còn mở

Audit tiếp theo: `.tools/ocr-asr-quality-20260916-213401/`. Source SHA, 28 file
runtime/input/worker đối chiếu và 59 file bảo vệ được chốt trước sửa; hai stash
giữ nguyên. Qwen được verify lại toàn inventory trước recognition. Các mục bên
dưới section này về v2 là kết quả lịch sử, không phải lượt chạy mới.

### OCR v3

`--tracking characters-v3` chọn worker/policy mới; v1/v2 và recognition bridge
giữ nguyên byte. New scans của GUI vẫn giữ mode cũ; GUI/CLI đọc policy đã lưu
để resume. Model/resource/cache identity phân biệt v3, không migrate checkpoint.

- Regression hai box tổng hợp fail trên v2: box chỉ cắt mép anchor, và box nền
  cao ở gần nhưng lệch tâm dòng. V3 yêu cầu anchor đi qua vùng giữa box và các
  box phụ chia sẻ tâm dòng chính; không mở rộng support hoặc ghép text sau OCR.
- Replay 27 frame PTS thật tái hiện 57,033 s/62,833 s có nền nhưng bị báo present,
  và box nền tại 62,567 s gây split ở 62,600 s. V3 loại các ca đó.
- Khi tiled CTC không có glyph confidence đủ, kiểm nét punctuation độc lập:
  component nhỏ, gọn và cùng hàng có thể giữ dấu chấm ngay cả khi CTC blank.
  Regression gradient fail trước sửa; standalone dots/fade/one-frame glyph change
  được giữ. Đây là heuristic pilot chưa hiệu chuẩn cho mọi font/nền hoặc fade;
  không dùng confidence làm bằng chứng transcript đầy đủ và chưa promote mặc định.

| Ca, candidate v3a | Complete / export | Cue | Fresh / cache | Tracking / feature batches | Wall |
|---|---|---:|---:|---:|---:|
| D1 28,8–32,3 s | true / exit0 | 2 | 6 / 0 | 105 / 231 | 70,625 s |
| D2 57–63 s | true / exit0 | 4 | 11 / 0 | 180 / 287 | 98,344 s |

Mỗi candidate đúng một lượt/window, cap 40 recognition và 360 s/window. D2 giữ
câu đáp 61,867–62,767 s liên tục, không tạo hai cue nền giả, không còn empty
candidate. Raw/guard/cue ngắn còn nguyên; exit0 vẫn **không phải text quality pass**.

Recognizer còn bỏ thán từ đầu dòng ở 62,900 s và dấu cuối. Hai diagnostic riêng,
mỗi diagnostic 6 recognizer batches trên hai frame cố định, kiểm grayscale/local
contrast rồi neutral padding/inversion/isolated glyph. Không phương án nào lấy
lại thán từ; không đưa các variant đó vào app. Inventory dictionary 18.708 entry
xác nhận glyph mà assistant đọc trên ảnh không thuộc dictionary hiện tại. Đây
là nguyên nhân có thể kiểm độc lập; không thể sửa bằng threshold hoặc tự thêm
entry vào dictionary khi weights/output classes không đổi. Reference ảnh vẫn là
AI reference, không được gọi human ground truth. Dấu cuối còn bị detector crop
ở frame đầu và lựa chọn candidate; giữ disagreement, chưa sửa bằng ghép raw.

Diagnostic presence ban đầu thêm 6 recognizer batches (3 frame thật/3 synthetic);
các lỗi harness trước inference do API argument không đúng được ghi riêng.
Replay baseline/candidate có 27 tracking request mỗi lượt, 0 recognition;
không cộng feature batches vào recognition request hoặc giấu attempts thất bại.

**Worker/checkpoint bytes của candidate đầu (v3a):** CLI đo worker SHA
`a62c173ddaa0f63b17e7cd1a5667dacbeeb1c2eb85067ca712d13e99dfd33eb0`.
`candidate-workers/measured-v3.py` và `ocr_stream_worker.py` được giữ để dùng
explicit bridge. Final source SHA
`a7c444ed863bc43c751c5b67ef3476c09da4bc983752fc5e9471f073fa30f760`
chỉ đổi binding `xs` không dùng thành `_` sau Pyright warning. Final bytes có
model regression và cache parity; không rewrite hash checkpoint hoặc nhận
vơ worker đó đã chạy lại hai window. Checkpoint complete, không cần resume.

Review thêm assertion đổi standalone ellipsis thành period phát hiện v3a chỉ
báo uncertain và không tách biên. Candidate v3b thêm so sánh mask nét compact
giữa hai frame liên tiếp khi CTC yếu ở cả hai frame; không bridge qua blank.
Regression fail trước sửa rồi pass; kiểu số NumPy cũng được đổi về scalar Python
trước JSON RPC sau một lần protocol regression fail. Final source/worker SHA
`9bef0946f8456c9f7e4a36f49feba0555f61540dfc8f45eea4f6f94375931447`.
`ocr-v3b/` giữ lượt đo riêng trên đúng final bytes, theo cùng cap/window. Giữ
`candidate-workers/v3a-final.py` cho partial native cũ; không sửa hash checkpoint.

| Ca, final v3b | Complete / export | Cue | Fresh / cache | Tracking / feature batches | Wall |
|---|---|---:|---:|---:|---:|
| D1 28,8–32,3 s | true / exit0 | 2 | 6 / 0 | 105 / 231 | 66,625 s |
| D2 57–63 s | true / exit0 | 4 | 11 / 0 | 180 / 287 | 98,391 s |

Hai candidate tổng cộng 34 recognition request trên bốn window hoàn tất;
18 diagnostic recognizer batches và synthetic tests được tính riêng. Final v3b
không đổi text/biên D1/D2 so với v3a; lỗi dictionary/dấu vẫn được giữ mở.

### ASR ngữ cảnh độc lập

Giả thuyết duy nhất: clip D1 27–34 s thiếu ngữ cảnh ở biên. Chuẩn bị audio gốc
24–36 s cùng mono16k/PCM16, Qwen1.7B/cùng pin/cùng language, không OCR prompt.
Vùng 27–34 s có 99,9893% PCM samples bằng bản cũ và 100% vùng trong sau bỏ
20 ms mỗi đầu; khác biệt nhỏ chỉ ở biên resampling. Energy không xác minh phoneme
hay transcript, nên `speech_reference` vẫn unknown.

Đúng **1 recognition mới, 0 cache hit**, 13,657 s request / 32,844 s toàn CLI,
cap 180 s stage, không retry. Có lại phần đầu bị thiếu và thêm lời ở phần context,
nhưng một từ đáng ngờ vẫn còn. Không chọn engine thắng, không chấm CER/WER,
không alignment hoặc ghép text với giờ Whisper. Qwen vẫn là TXT chưa timed.

D3 có audio gốc 104–129 s để kiểm biên, nhưng không nhận dạng lại: filtered dump
đã khóa chỉ phủ 107–126 s; padding bằng original sẽ đổi cả preprocessing.
Giữ đúng dump cũ và không chạy Kim_Vocal_2 lần hai. P2 quality còn mở.

### Validation và điều kiện dừng

- OCR/GUI offline: **313 passed, 7 deselected**; ASR/CLI: **243 passed**.
- Final worker gần code: **23 passed**, gồm **7 integration** CPU/model thật
  trên synthetic, có cả v2 compatibility. Không cộng trùng thành tổng suite mới.
- Cache/no-cache frame 30 s bằng nhau: 4 tracking, 0 recognition mới, final hash.
- Ruff pass; Pyright working tree 0 errors/0 warnings; translations/diff check pass.
- P3 domain/CLI: D1 2 cue, D2 4 cue và Whisper baseline 33 cue qua table/handoff,
  undo và hai vòng editor save/reopen giữ text/ms/IDs/metadata; SRT giữ text/time.
- Native GUI trên candidate v3a: dùng Computer Use chọn source thật, mở checkpoint D2, xuất JSON và
  lưu checkpoint đủ 4 cue; so byte/domain giữ raw, text, ms, IDs, metadata. Mở
  partial thật, resume model CPU và bấm hủy: worker dừng, GUI còn phản hồi và giữ
  trạng thái partial, không cho xuất; 42 tracking/63 feature batches/0 recognition
  mới, job wall 34,250 s. Click hủy ở 33,740 s, vượt budget thao tác
  30 s đã đặt; giữ ghi nhận vi phạm này, không nới cap hoặc gọi budget pass.
  GUI editor playback/save/reopen và full source-to-result workflow vẫn chưa đủ.
- P3 service cancellation trên bytes v3a trước sửa punctuation: 8 tracking/0 recognition, lưu partial
  thật; CLI từ chối export partial và source khác hash với exit5, không tạo SRT.
  Đây là kiểm service/CLI thật, tách riêng với thao tác nút hủy native.
- Holdout annotation/inference, whole-video, full offline, build/EXE và TTS vẫn
  **NOT RUN** vì P1/P2 chưa đạt. Không thay sáu câu Việt/voice B. Tiếp tục từ
  dictionary coverage và reference audio, không lặp lại candidate cùng input.

Đã bắt đầu triển khai P0–P4 từ
[plan ưu tiên OCR/ASR](../plans/ocr-asr-quality-first-2026-09.md) của phiên trước.
Tiếp tục bằng [prompt bàn giao](../plans/ocr-asr-quality-next-session-2026-09.md).
**Nhận dạng chưa đạt nghiệm thu; chưa chuyển sang dịch/TTS.** Không dùng số cue,
exit code hoặc output tồn tại để thay cho đánh giá chất lượng.

## Trạng thái từng phase

| Phase | Đã làm | Gate còn mở |
|---|---|---|
| P0 | Xác minh Git/source hash; snapshot source; manifests, cases, budgets và ledgers cô lập; khóa H1 74–94 s/H2 140–162 s trước output candidate | Reference audio của người nghe và annotation đầy đủ holdout vẫn unknown; không gán nhãn human-reviewed |
| P1 | Regression 32 px/ROI 90 px; replay 162 raw; worker v2 riêng; kiểm model CPU thật và hai cửa sổ D1/D2 | D2 còn chữ nền, một empty read, tách câu đáp ngắn và thiếu dấu/chữ; chưa đạt quality gate |
| P2 | Cài runtime Qwen 1.7B riêng theo pin có sẵn; đúng 3 recognition TXT/0 cache hit trên WAV đã khóa; reuse Whisper | Qwen còn khác chữ, lặp và phần cuối đáng ngờ; không chọn làm engine thắng, không alignment hoặc sweep thêm model |
| P3 | CLI export, table/export/handoff, undo và hai vòng save/reopen trên OCR D1 và 33 cue Whisper baseline; D2 bị chặn đúng | Native GUI mới kiểm startup/mở OCR; chưa hoàn tất native file/export/cancel/playback workflow |
| P4 | Giữ điều kiện chuyển phase | Holdout inference, whole-video, full offline và build/EXE NOT RUN vì quality gate P1/P2 chưa đạt |

Audit local: `.tools/ocr-asr-quality-20260916-201453/`. Raw/crop/audio/model,
command receipts và transcript nằm trong audit bị Git ignore. Không chép chúng vào
fixture hoặc tài liệu version control. Các mốc bên dưới là timeline nguồn.

## Thay đổi OCR có thể kiểm riêng

Thêm `scripts/ocr_tracking_worker_v2.py` và bản resource byte-identical, policy
`character-features-v2`. CLI chọn tường minh bằng `--tracking characters-v2`;
`characters` và checkbox quét mới của GUI tiếp tục dùng v1. GUI đọc/tiếp tục
checkpoint v2 theo worker đã lưu; CLI resume chọn đúng v1/v2.

- Chiều cao dòng lấy từ hình học dòng ngang cắt anchor, không từ floor `0.4 × ROI height`.
  Dòng 32 px vì thế không còn bị loại chỉ vì ROI cao 90 px. Box ký hiệu cao riêng
  không được làm chuẩn khi có dòng chữ rộng. Box nền lớn chạm mép dọc và box nghiêng
  ngoài phạm vi dòng ngang bị loại trong policy thử nghiệm.
- Chỉ đưa vùng dòng đã detect vào feature input. Khi bbox thay đổi, so hai ảnh
  **liên tiếp** trên cùng support là hợp của hai geometry. Không ghép sau OCR,
  không bridge qua frame chưa quan sát hoặc blank và không xóa cue theo duration.
- Bù dịch một encoder position chỉ khi có cùng số/thứ tự glyph run, confidence phù
  hợp, vị trí gần và feature hình ảnh tương ứng. Trùng text đơn thuần không đủ.
- Chọn candidate sắc nét theo chất lượng riêng của frame, không theo frame trước,
  để điểm bắt đầu resume không đổi cách xếp hạng candidate.
- Không đổi worker recognition gốc hoặc worker tracking v1. Không đổi schema,
  raw, PTS, review/export guards hoặc nội dung checkpoint cũ. Config/bridge hash
  phân biệt cache/document identity của v2. Spec giữ resource mới cho build sau.

Một thử nghiệm mở rộng support làm nền lọt lại đã bị loại. Thử nghiệm đòi
confidence để bắt đầu cue cũng bị loại vì làm mất dòng chỉ có dấu chấm; process
thuộc lượt thử đó đã được dừng, không lấy partial làm bằng chứng quality pass.
Các source worker ứng viên và report thất bại đều được giữ trong audit.

## Bằng chứng thực tế

| Ca | Kết quả CLI candidate | Recognition mới / cache hit | Tracking / feature batches | Wall time |
|---|---|---:|---:|---:|
| D1 OCR 28,8–32,3 s | Complete, 2 cue, không export issue; caption 29,4–32,3 s liên tục | 6 / 0 | 105 / 231 | 99,125 s |
| D2 OCR 57–63 s | Complete scan, 7 cue, 1 `empty_engine_read`; export exit 5 | 16 / 0 | 180 / 288 | 145,875 s |

Cap đặt trước: 40 recognition request và 360 s mỗi cửa sổ/candidate. Không tăng cap.
Feature batches không phải recognition request; detector/recognizer attempts theo
stage nằm riêng trong report. Không cộng thời gian stage có overlap thành wall time.
V2 tốn thêm CPU để so hai frame cùng geometry; đây không phải benchmark tốc độ chung.

Replay 162 candidate không inference mới: geometry v1 loại 2 candidate có text,
v2 giữ cả hai. Phân loại 18 empty issues cũ giữ nguyên: 13 cue có text được chọn
nhưng candidate khác rỗng, 5 cue có text được chọn rỗng. Chưa có căn cứ bỏ guard
candidate rỗng. D2 mới vẫn có background false positive và raw thiếu chữ/dấu dù
scan hoàn tất. Các đoạn này chưa được chữa bằng sửa text hoặc giả review.

Lượt CLI đo dùng bản worker trước cleanup một binding `cv2` không dùng. Audit giữ
nguyên exact worker/hash ở `candidate-workers/final-measured.py`; thay đổi cuối chỉ
bỏ binding đó, có đối chiếu nội dung và model regression trên bytes cuối. Không
ghi đè checkpoint để đổi hash; khi replay checkpoint thử nghiệm phải chọn đúng
bridge đã lưu. Không suy rằng hash khác là checkpoint tự tương thích.

Qwen dùng model pin `7278e1e70fe206f11671096ffdd38061171dd6e5`, runtime lock/recipe
trong repo; Qt environment không bị cài thêm dependency. Lần tạo runtime đầu thiếu
Python trong PATH đã dừng; harness sau dùng CPython 3.12 nền của environment đang
có, giữ runtime lỗi riêng và không cài Python global.

| Ca ASR | Input | Recognition request time | Toàn CLI |
|---|---|---:|---:|
| D1 27–34 s | WAV mono 16 kHz đã dùng cho Whisper | 13,578 s | 43,546 s |
| D2 57–63 s | WAV mono 16 kHz đã dùng cho Whisper | 16,469 s | 29,828 s |
| D3 107–126 s | `*_dump.wav` sau Kim_Vocal_2 mà log XXL xác nhận đã đưa vào ASR | 15,703 s | 34,422 s |

D3 được chốt lại từ file MDX trung gian sang filtered dump **trước** khi chạy
candidate, để khớp preprocessing của Whisper. Hash input/PCM/request WAV đều được
lưu. Không upload audio, không prompt bằng OCR/đáp án, không tách vocals lần hai.
Raw và TXT Qwen được giữ; không ghép text Qwen với timestamp Whisper. Các khác biệt
với caption hình là đối chiếu khác modality, không tự biến thành ground truth lời nói
hoặc CER/WER. Không đo mới peak VRAM và không suy timing từ file TXT.

## Validation và bước tiếp theo

- Regression ban đầu: 4 fail/3 pass trên worker v1. Regression bbox bỏ punctuation
  và nền chữ sát cạnh cũng fail trước sửa; model CPU thật kiểm blank/repeat, fade,
  thay một glyph/dấu một frame, dòng chỉ có dấu chấm và bbox jitter.
- OCR/GUI và ASR/CLI gates, lint/type/translation results cuối được ghi trong
  `status.md` và receipts trong audit. Offline/fake-provider không thay thế local
  inference, native GUI hoặc EXE.
- Bytes worker cuối đã kiểm frame 30 s với detect mới và geometry raw cached:
  quyết định tương đương, `present=true`; 4 tracking request, 0 recognition mới.
- P3: OCR D1 2 cue và Whisper baseline 33 cue giữ text/ms/IDs qua hai vòng editor
  save/reopen; OCR còn giữ visual source/raw metadata. SRT chỉ giữ text/time;
  provenance vẫn ở JSON. Baseline ASR roundtrip pass không sửa chất lượng baseline.
- Chưa promote v2 thành mặc định. Chưa whole-video/build: tiếp tục phân biệt chữ
  nền với dòng phụ đề bằng evidence ở 57,033 s/62,833 s; phải giữ standalone
  punctuation và fade, không chỉ tăng threshold. Điều tra raw detector/recognizer
  bỏ interjection/punctuation ở mép dòng độc lập với fragmentation.
- ASR: trước candidate tiếp theo, kiểm reference lời nói và biên clip D1/D3 bằng
  audio có ngữ cảnh. Giữ phần chưa nghe xác định là unknown; không tăng model sweep,
  không nhận lại cùng input rồi chọn output thuận lợi.
- Hoàn tất annotation holdout và P3 native cancel/save/reopen trước khi mở P4.
  Recipe giọng B, sáu câu Việt đã chấp nhận và toàn bộ TTS artifacts vẫn giữ nguyên.
