# Plan ưu tiên OCR và speech-to-text trước lồng tiếng

Ngày lập: 2026-09-16. Trạng thái: **PLAN ONLY — chưa triển khai các phase dưới đây**.

> Ghi chú bàn giao sau triển khai: nhãn `PLAN ONLY` và các câu giới hạn phiên lập
> plan bên dưới là trạng thái lịch sử. Commit `5ba151a` đã triển khai một phần;
> P1/P2 chưa đạt quality gate, P3 còn gate native, P4 chưa chạy. Tiếp tục theo
> [kết quả thực tế](../dev/ocr-asr-quality-first-results-2026-09.md) và
> [prompt phiên tiếp theo](ocr-asr-quality-next-session-2026-09.md).

User đã xác nhận cần lập kế hoạch chi tiết trước, sau đó chỉnh thứ tự:
**OCR/ASR tốt trước → phụ đề nguồn đủ và đúng → dịch → lồng tiếng**.
Không tiếp tục thử giọng hoặc tích hợp giọng B trong các phase nhận dạng.
Các ghi chú “OCR dừng” trong plan bài giảng cũ thuộc task khác; không áp vào yêu cầu mới này.

## 1. Phạm vi đã chốt

- Video đánh giá chính: `BV1GFbk6LEVm`, P1 dài 266,566625 s, 1920×886.
- Bản dịch sáu câu trong đoạn 107–126 s đã được user chấp nhận; giữ nguyên.
- Lồng tiếng sau này dùng **một giọng B**. Không quay lại tự đổi giọng theo vai
  hoặc clone nhân vật, vì user đã loại hướng đó.
- Giọng B được chấp nhận qua nghe mẫu; nền đã giảm vocals **chưa được chấp nhận riêng**.
- Ngữ cảnh nhân vật/xưng hô phục vụ dịch; không dùng nó để gán chữ cần nhận dạng
  vào ASR rồi công bố ASR đã nhận đúng độc lập.
- Mục tiêu là phụ đề dùng được và không bỏ lời âm thầm. Không hứa 100% chính xác,
  không công bố CER/WER nếu chưa có reference phù hợp.

Lượt lập plan chỉ đọc source/evidence và tạo tài liệu này. Không inference,
download, cài dependency, sửa app, build, commit hoặc push trong lượt này.

## 2. Baseline và bằng chứng đang có

HEAD và local tracking `origin/master`: `62abacae421d2011948f467d3386d81de9f8879b`.
Working tree sạch trước khi tạo plan. Hai stash phải giữ nguyên:

- `6a1e12d531cfb0e7408ab5737d02c544902001e2`
- `e61dd7e2cea5eeffd2d64a30b84af1477d504558`

| Hạng mục | Đã biết | Còn thiếu |
|---|---|---|
| OCR 20–70 s | Complete 94 cue, 18 lỗi `empty_engine_read`; 58 cue dưới 100 ms | Fragmentation, chữ nền lọt, mất khoảng có caption; chưa có output được nghiệm thu |
| OCR chọn dòng | Policy v3 đã sửa dấu câu cao che chữ | V3 không sửa bộ tracking |
| OCR frame 30 s | Raw đọc được dòng cao 32 px; tracker yêu cầu 36 px từ ROI cao 90 px nên báo absent | Sửa tracking và kiểm hồi quy thực tế |
| OCR ROI hẹp | Giữ thêm vùng chữ nhưng tách vụn hơn, chạm cap 18 request/exit5 | Không dùng làm cấu hình chữa lỗi đã đạt |
| ASR whole video | large-v3 CUDA có 33 cue; raw có hallucination và thiếu lời | Độ đầy đủ/chữ/timing chưa đạt |
| ASR 107–126 s | Cùng 19 s: audio gốc 5 cue, vocals Kim_Vocal_2 có 6 cue | Một số chữ vẫn khác caption; cue count không phải text accuracy |
| ASR 2,8 s | App đã chuyển option vocals tới binary thật, exit0 | Text vẫn sai/lặp; quality fail |
| ASR Qwen | Code Qwen + sentence timing/fallback đã có trong repo | Chưa xác minh runtime/model sẵn sàng cho video này trên checkout hiện tại |

Sửa đã có: `7e2cb10` chọn dòng OCR; `d342d5b` giữ speaker khi dựng cue dubbing;
`62abaca` không làm rơi vocal extraction khi executable dùng đường dẫn đầy đủ.
Không làm lại các sửa này dưới một tên khác.

Evidence gốc, chỉ đọc:

| Thư mục | Đầu vào phải dùng lại |
|---|---|
| `.tools/bv1gf-20260916-145613/` | `source.json`, source media, runtime OCR/OmniVoice/VieNeu, large-v3, tools, checkpoint/raw |
| `.tools/ocr-compare-20260916-155842/` | VAD on/off, frame/gateway reference, line-selection replay |
| `.tools/bv1gf-prosody-20260916-171148/` | `ocr-audit.json`, `gap-probe/result.json`, `ocr-roi/results.json`, ASR 27–34/57–63 s |
| `.tools/bv1gf-clone-20260916-174613/` | Hai ASR 19 s, MDX vocals đã có, 38 OCR observations, native raw và failed short-ASR evidence |

Source SHA-256 đã ghi: `3e56b8d3349bb2013723617ce856cd44a72f1f5140d81ef1c126a65747d13d90`.
Không tải lại video nếu file đúng hash. Ảnh do assistant/gateway đọc là AI reference,
không phải human ground truth. Frame đen/không caption không chứng minh audio im lặng.

## 3. Thứ tự triển khai và điều kiện chuyển phase

| Phase | Kết quả phải giao | Điều kiện chuyển tiếp |
|---|---|---|
| P0 — Bộ đối chiếu | Manifest nguồn/runtime, danh sách lỗi theo mốc, bộ ca cố định | Biết mỗi ca đang sai text, coverage, timing hay export; nguồn không đổi |
| P1 — OCR | Sửa mất vùng chữ và fragmentation có bằng chứng | Không còn lỗi đã biết trên bộ ca nhỏ; raw/guard/resume được giữ |
| P2 — ASR | Chọn đường nhận dạng dùng được dựa trên cùng audio | Lấy lại lời thiếu, không lặp/ảo trên ca đã kiểm; timing câu hợp lệ |
| P3 — Phụ đề và GUI | Hai nguồn OCR/ASR có provenance, xuất/mở/sửa/lưu dùng được | Không rơi cue giữa các tầng; chưa xong phải báo chưa xong |
| P4 — Kiểm đoạn mới rồi toàn video | Báo cáo chất lượng ngoài các đoạn dùng sửa lỗi; toàn nguồn có output hoặc trạng thái thiếu rõ | OCR/ASR đủ tốt để chuyển sang dịch/TTS; GUI/EXE ghi gate riêng |
| P5 — Sau nhận dạng | Tích hợp giọng B, kiểm timing/mix nền rồi lồng tiếng | Chỉ bắt đầu sau P1–P4; không phát sinh TTS trong các phase trên |

P1 và P2 là hai nhánh độc lập, có thể tiến hành xen kẽ khi một nhánh chờ
inference. Không chạy nhiều GPU model đồng thời. Không để khó khăn của OCR
ngăn việc điều tra ASR độc lập, nhưng **chưa chuyển sang TTS khi một nhánh còn lỗi chính**.

## 4. P0 — Cố định dữ liệu và cách đánh giá

### Việc làm

1. Đọc lại guidance/status, Git status/index/diff/refs/stashes; chụp baseline
   mới và tạo đúng một audit root dưới `.tools/ocr-asr-quality-<timestamp>/`.
2. Kiểm SHA nguồn và evidence; giữ settings, cookie, checkpoint, raw, media,
   artifact cũ. Cô lập AppData/cache/temp/log bằng cơ chế `run.py` đã dùng.
3. Inventory runtime thực: executable/Python/model/profile/revision/hash và
   vị trí weights. PP-OCRv6 medium, large-v3/Kim_Vocal_2 đã có trong audit cũ.
   Manifest alignment không chứng minh đã có Qwen recognizer hoặc weights.
4. Nếu test source sửa mới bằng snapshot, chép đúng allowlist và đối chiếu
   bytes trước khi chạy. Không kiểm nhầm `app` snapshot của lần trước.
5. Tạo `cases.json`, `coverage-ledger.json`, `run-ledger.jsonl` trong audit.

Mỗi dòng đối chiếu phải có: source hash, mốc audio/frame, loại bằng chứng,
raw/candidate IDs, model/policy, text được quan sát, vùng còn bất định, output
có/không bao phủ, và trạng thái validation. Giữ **lời nói**, **chữ trên hình**
và **bản dịch** thành các trường riêng.

### Bộ ca cố định

- D1: 27–34 s, ASR mất/nhận sai lời; phần OCR 28,8–32,3 s có mất vùng chữ.
- D2: 57–63 s, tên riêng/câu dài/câu đáp ngắn, dấu nền gây nhiễu OCR.
- D3: 107–126 s, sáu lượt thoại đã đối chiếu; giữ raw khác nhau giữa ASR và OCR.
- Negative controls: frame không caption, nền chuyển động, ký hiệu rời; nhãn
  audio silence chỉ dùng khi audio đã được kiểm riêng.
- Hai đoạn holdout dự kiến 74–94 s và 140–162 s: chốt đầu vào/annotation
  trước khi xem kết quả candidate. Nếu không phù hợp loại lỗi cần kiểm,
  ghi lý do đổi **trước** khi chạy candidate, không lựa chọn theo điểm số.

Không bắt user duyệt mọi cue. Agent dùng ảnh/evidence để giải quyết phần rõ;
phần nghe chưa xác định được phải giữ unknown hoặc đưa một số đoạn cụ thể
cho người hiểu tiếng Trung kiểm. Không tạo nhãn “human-reviewed” tự động.

### Đạt / dừng

- Đạt: ledger nối được từng lỗi với frame/audio/raw cụ thể; inventory có/thiếu
  được nêu rõ, không coi có thư mục hoặc health là inference pass.
- Dừng nhánh tương ứng nếu source khác hash, model thiếu/hash sai hoặc cần
  điều khoản/credential chưa được cấp. Không đoán dựng lại evidence mất.
- Không gọi gateway ở P0. Quyền gateway hiện có dành cho crop OCR, không audio.

## 5. P1 — OCR: mất vùng chữ trước, fragmentation sau

### 5.1 Tái hiện và sửa nguyên nhân

- Viết regression tổng hợp tái hiện chữ cao 32 px trong ROI 90 px bị floor
  `.4 * height` loại bỏ. Không đưa transcript/crop riêng của user vào Git fixture.
- Replay geometry/raw đã lưu trước khi thêm inference. Kiểm cache/no-cache
  trả quyết định tương đương, bbox/PTS không thay đổi.
- Đo riêng hai vấn đề: quyết định có chữ/không chữ và quyết định chữ thay đổi.
  Không coi bỏ floor là đã chữa được fragmentation.
- Thử cách xác định dòng dựa trên vùng chữ/anchor và tỉ lệ chữ thực tế;
  kiểm chữ nhỏ, dấu rời, chữ nền cùng hàng, blank, fade, đổi một chữ hoặc dấu
  chỉ một frame. Không đặt minimum cue duration để xóa các cue ngắn cho đẹp số.
- Đối với fragmentation, phải chứng minh các frame liên tiếp vẫn cùng caption
  và không có blank/đổi chữ ở giữa. Không merge chỉ vì text gần giống hoặc
  bridge qua khoảng tracker chưa quan sát.

### 5.2 Compatibility và guard

- Giữ worker/policy cũ để resume checkpoint cũ. Nếu đổi semantics tracking,
  dùng policy mới có version và companion worker mới, không sửa âm thầm
  `character-features-v1` rồi gán lại hash cho checkpoint đã lưu.
- Hướng file mới có thể là `scripts/ocr_tracking_worker_v2.py` và bản resource
  tương ứng; tên cuối được chốt sau regression, không coi đã tồn tại.
- Giữ `ocr-document-v1`, canonical ms/PTS, source identity, raw provenance.
  New policy được phân biệt trong config/cache/document identity.
- Phân loại 18 `empty_engine_read`: 13 cue chọn text không rỗng nhưng có
  candidate khác rỗng, 5 cue chọn text rỗng. Không đơn giản bỏ guard “candidate
  rỗng”; phải xác định nguồn gốc fade, background hoặc thiếu recognition.
- Giữ xuất thẳng khi document hợp lệ, không đưa lại workflow review bắt buộc.
  Incomplete, text/timing/source lỗi vẫn không được gọi là export hoàn chỉnh.

### Phạm vi file

Đọc/sửa tối thiểu theo regression: `scripts/ocr_tracking_worker*.py`,
`videocaptioner/resources/ocr/ocr_tracking_worker*.py`,
`videocaptioner/core/ocr/{tracking,pipeline,runtime,service,document,resume,installation}.py`,
CLI/GUI OCR nếu cần routing policy, tests tương ứng; spec chỉ khi thêm resource.
Đây là phạm vi dự kiến; trước mỗi sửa phải ghi allowlist cụ thể, không stage wildcard.

### Kiểm chứng và ngân sách

1. Regression fail trên baseline rồi pass với candidate; fixtures phải giữ
   blank/repeat, punctuation, one-frame transition, cache và resume cũ.
2. Replay raw/candidate cũ: không inference, không sửa checkpoint.
3. Candidate scan hai cửa sổ OCR D1/D2, tối đa 40 recognition request mỗi
   cửa sổ/lượt. Ghi riêng tracking request, inference, cache hit, wall time.
4. Mỗi candidate có một lượt thực trên mỗi cửa sổ; chỉ thêm lượt khi có sửa
   nguyên nhân mới và regression mới. Không tăng cap để biến fail thành pass.

Đạt khi không mất caption đã biết, không tách thành chuỗi cue vài chục ms
khi hình chữ đứng nguyên, không thêm chữ nền ở ca negative, text/time hợp lệ
và old resume không đổi. Ít cue hơn hoặc export exit0 một mình không đủ.
Nếu phải hy sinh đổi chữ ngắn hoặc xóa raw để đạt, loại candidate và giữ evidence.

## 6. P2 — Speech-to-text: cùng audio, ngữ cảnh đủ, không đoán chữ

### 6.1 Tái sử dụng baseline

- Giữ large-v3 + VAD-on làm đối chứng. VAD-off đã thất bại, không thử lại mặc định.
- Reuse original/vocals WAV và raw đã có. Kim_Vocal_2 có ích trên D3 nhưng
  không bảo đảm mọi câu đúng; không bật toàn bộ pipeline chỉ dựa vào 5→6 cue.
- Clip 2,8 s gây text sai/lặp; không lấy cắt càng ngắn càng tốt làm policy.
  Câu ở biên cần ngữ cảnh liền kề, rồi map timing về source đúng offset.
- Kiểm `--fw-voice-extraction` thật sự đến executable; bản sửa `62abaca` đã có,
  không lặp native runs chỉ để xác minh lại flag nếu source đó không đổi.

### 6.2 So sánh một candidate khác, có giới hạn

- Kiểm Qwen3-ASR 1.7B qua runtime/recipe đã có trong project trước. Không import
  model vào Qt. Thiếu thành phần mới lập inventory và chuẩn bị trong repo
  theo quyền cài/tải đã có; không cài global hoặc thay environment app.
- Trước hết lấy **TXT** trên ba ca D1–D3, không nạp ForcedAligner nếu chưa cần
  timing. Tối đa ba recognition mới cho candidate đầu tiên.
- Mỗi so sánh engine phải dùng **đúng cùng WAV/hash/preprocessing**. Nếu D3
  dùng vocals làm đối chứng thì candidate cũng dùng đúng WAV vocals đó;
  không đổi cả model và nguồn audio rồi gán cải thiện cho riêng model.
- Không đưa caption OCR/đáp án/tên riêng đã sửa làm initial prompt ở phép đo
  ASR độc lập. Không “sửa raw” bằng LLM hoặc biến OCR thành kết quả ASR.
- So missed dialogue, extra/repeated speech, từ quan trọng/tên riêng khi có
  reference đủ rõ, hoàn tất text, hủy/deadline và thời gian thực tế. Chưa có
  reference chắc chắn thì báo unknown, không tự tính CER/WER có nhãn giả.
- Chưa sweep Qwen 0.6B, Whisper v2 và nhiều model khác cùng lúc. Nếu candidate
  không tốt hơn, ghi kết quả và chọn một giả thuyết tiếp theo cụ thể.

### 6.3 Timing câu và fallback

- Sau khi text candidate dùng được mới chạy timing; reuse recognition cache.
- Tận dụng policy câu và `sentence_fallback` đã có; không mở lại benchmark
  strict token timing của bài giảng cũ. Mốc ms/offset, cue ID và provenance
  phải đúng; không clamp giờ hoặc kéo dài cue rỗng để xuất được SRT.
- Fallback nhận nguyên cặp text+timing của engine dự phòng, giữ provider trên
  cue và raw ban đầu. Không lấy text Qwen ghép với giờ Whisper khác lời.
- Có text nhưng timing fail thì giữ TXT/review đúng luồng đã có, không báo
  timed subtitle success. Không tự bật diarization; user đang muốn một giọng TTS.

### Phạm vi và gate

File chính: `core/asr/{faster_whisper,asr_data,audio_identity}.py`,
`core/asr/local/{runtime,pipeline,audio,sentence_timing,sentence_fallback,review}.py`,
`core/asr/alignment/`, CLI transcribe và worker UI liên quan nếu có lỗi thực.
Model/runtime recipe chỉ đổi nếu inventory hoặc API đã chứng minh cần đổi.

Đạt trên ca đã kiểm khi lấy được các lượt thoại bị thiếu, không thêm đoạn
quảng cáo/lặp ảo, text không bị cắt âm thầm, cue dương và nằm đúng vùng nguồn.
Không bắt số cue của hai engine bằng nhau; một câu có thể tách/gộp khác nhau.
Câu đáp ngắn, interjection và tên riêng được báo riêng thay vì biến mất khỏi bảng.
Quality không đạt dù exit0 thì giữ fail; không chạy lại nhiều lần chọn output đẹp nhất.

## 7. P3 — Đưa kết quả đến bảng phụ đề mà không mất chữ/giờ

### Đầu ra

- `onscreen.zh.json/.srt`: OCR của chữ trên hình, giữ visual provenance.
- `speech.zh.json/.srt`: speech-to-text, giữ audio/provider provenance.
- `coverage-report.json/.md`: hai nguồn khác nhau ở đâu, vùng chưa xác nhận,
  export issues và phương án đang được dùng. Không ép hai nguồn phải trùng nguyên văn.

Không tự hợp nhất bằng phép “chỗ nào trống thì điền OCR”. Trường hợp dùng OCR
để sửa bản phụ đề phải ghi đó là chỉnh sửa có nguồn hình ảnh, giữ raw ASR.
Sáu câu Việt user đã duyệt không bị dịch/rewrite lại trong phase này.

### GUI/source acceptance

- Qua luồng app thật: chọn source/ROI/engine → chạy → hủy/tiếp tục khi được hỗ trợ
  → xuất JSON/SRT → mở bảng phụ đề/Video Editor → lưu/mở lại.
- So số cue, nội dung, ms, stable IDs và metadata trước/sau; xuất đúng phần
  selection, không lấy ba câu đầu rồi gọi là toàn bộ đoạn như mẫu cũ.
- Show tiến độ/cancel trên worker, không block Qt hoặc cập nhật widget từ worker.
  Mở settings không tự load model/download; lỗi worker đóng sạch process thuộc job.
- Không thêm bước user phải approve từng cue để được xuất hợp lệ.

Gate: source mismatch bị từ chối, partial không ghi thành complete, các cue
không mất qua chuyển tab/adapter/export, GUI cancel không treo/crash. Fake-provider
test không thay thế native GUI và real local inference.

## 8. P4 — Holdout, toàn video và EXE

1. Chạy cấu hình thắng trên hai đoạn holdout đã khóa ở P0, một lần mỗi đoạn.
   Lỗi mới phải được phân loại; không sửa riêng theo transcript đáp án của holdout.
2. Khi P1/P2/P3 và holdout đạt, cho phép một lượt whole-video để kiểm chính
   giả thuyết “cấu hình đã chọn bao phủ toàn nguồn và xuất qua app không mất vùng”.
   Không bắt đầu whole-video trong lúc lỗi D1/D2/D3 còn mở.
3. Cố định budget request/thời gian dựa trên phép đo đoạn ngắn **trước lượt chạy**;
   ghi vào run ledger. Nếu chạm cap hoặc hủy, giữ checkpoint/progress và báo partial;
   không tự gấp đôi cap hoặc lặp whole video. Chỉ resume phần thiếu theo policy đúng.
4. Soát coverage toàn 266,566625 s: khoảng có lời/caption, output tương ứng,
   biên selection/đầu-cuối, cue lặp và vùng dài bị bỏ. Mỗi khoảng chưa giải thích
   được vẫn mang trạng thái unresolved. Không dùng “file tồn tại” làm nghiệm thu.
5. Chạy checks liên quan rồi full offline một lần cho bản ứng viên đủ phạm vi.
6. Build sau khi source gates đã đạt. Một `VideoCaptioner.spec`, tên artifact mới,
   không ghi đè dist/build cũ; dùng model/runtime đã có, verify inventory trước.
   Chưa xác minh được bộ `portable-models.json` phù hợp thì đây là gate mở,
   không gọi bundle OCR/ASR đầy đủ. Không tải lại weights để đóng gói.
7. EXE gate riêng: build exit/warnings; artifact size/time/SHA; startup đúng EXE;
   chạy một ca OCR và một ca ASR local thật; mở/export qua native GUI; kiểm relocatable
   model/tool/reference paths. Source pass không thay thế EXE pass.

Đóng giai đoạn nhận dạng khi có output toàn nguồn hoặc phạm vi được nêu rõ,
không còn lỗi coverage chính đã biết, raw/provenance còn nguyên, GUI/EXE có
bảng pass/fail/not-run riêng và phần nghe/chữ bất định được công khai. Khi chưa
đạt, tiếp tục sửa đúng nhánh nhận dạng; không đổi sang thử giọng để né lỗi.

## 9. P5 — Giữ lại cho sau khi OCR/ASR đạt

Giọng B được giữ ở
`work-dir/BV1GFbk6LEVm-voiceB-20260916-192625/voice-b-recipe.json`:

- Reference tiếng Việt 5,16 s từ mẫu Ngọc Linh; SHA
  `509ff70aee71483ec547a0d86d354e153cb61f07ca28e76b3da4078384b14c2d`.
- OmniVoice code `08be0b4ccbac3e13e374e86fbfead4b4cac343e2`, model
  `c5fdb5ccb189668d56333f77ba2629f4cd7535f4`; `instruct=female`, `vi`, seed0,
  32 steps, speed1×. Một reference/voice cho toàn bộ job.
- Recipe hiện **không import trực tiếp vào app**. Worker app bỏ `instruct`
  khi có reference; cần thêm option/CLI/GUI/identity/cache/resume đúng contract.
- Không giữ nguyên cache identity khi đổi instruction; không đổi ngữ cảnh xưng hô
  thành prompt giọng. Model/reference/text riêng không đưa vào Git.
- Trước lồng tiếng dài, điều tra riêng output voice-track 17,28/18,91 s trong
  A/B có timeline 19 s; chưa có kết luận nguyên nhân. Kiểm FFmpeg padding,
  normalization/PTS và cue placement bằng WAV synthetic có onset biết trước.
- Nền residual từ MDX đã có bản thử, chưa được nghiệm thu riêng. Không gọi nó là
  stem nhạc/hiệu ứng sạch. Giữ các mode audio hiện có và kiểm giọng gốc còn sót.

Đây là backlog sau nhận dạng, **không phải phần triển khai ngay của plan này**.

## 10. Lệnh và kiểm soát thực thi cho phiên triển khai

Các lệnh dưới đây là hướng dẫn, **chưa chạy trong lượt lập plan**. Chạy ở repo.
Sau P0, `$runner` phải trỏ tới harness cô lập mới, không dùng snapshot source cũ.

```powershell
$repo = (Get-Location).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
$audit = Join-Path $repo ('.tools/ocr-asr-quality-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
# P0 tạo audit, snapshot, empty.toml và runner dựa trên run.py đã kiểm.
$runner = Join-Path $audit 'run.py'

git status --short --branch
git diff --name-only
git diff --cached --name-only
git rev-parse HEAD origin/master
git stash list --format='%H'
```

Tests gần code, sau khi sync allowlist vào snapshot và đối chiếu bytes:

```powershell
& $python $runner ocr-tests -m pytest tests/test_ocr/ tests/test_ui/test_ocr.py `
  -q --basetemp (Join-Path $audit 'pt-ocr')
& $python $runner asr-tests -m pytest tests/test_asr/test_faster_whisper_vocals.py `
  tests/test_asr/test_faster_whisper_timing.py tests/test_asr/test_qwen_sentence_timing.py `
  tests/test_asr/test_qwen_sentence_fallback.py tests/test_asr/test_audio_identity.py `
  tests/test_cli/ tests/test_ui/test_local_asr.py tests/test_ui/test_qwen_text_result.py `
  -q --basetemp (Join-Path $audit 'pt-asr')
& $python $runner ruff -m ruff check videocaptioner/ tests/
& $python -m pyright videocaptioner/
& $python $runner translations scripts/sync_translations.py --check
git diff --check
```

Mẫu lệnh inference có sẵn, chỉ chạy sau khi P0 gán biến bằng manifest đã verify:

```powershell
# $source, $ocrRuntime, $fwExe, $fwModels, $qwenRuntime, $caseWav: từ manifest P0.
& $python $runner ocr-d1 -m videocaptioner.cli ocr $source `
  --config (Join-Path $audit 'empty.toml') --ocr-runtime $ocrRuntime `
  --roi '0.05,0.88,0.90,0.10' --start-ms 28800 --end-ms 32300 `
  --line-anchors 0.5 --tracking characters --max-requests 40 `
  --checkpoint (Join-Path $audit 'ocr-d1.checkpoint.json') `
  --report (Join-Path $audit 'ocr-d1.report.json') -o (Join-Path $audit 'ocr-d1.srt')

& $python $runner asr-case -m videocaptioner.cli transcribe $caseWav `
  --config (Join-Path $audit 'empty.toml') --asr faster-whisper `
  --fw-program $fwExe --fw-model-dir $fwModels --fw-model large-v3 `
  --fw-device cuda --language zh --fw-vad-method silero_v3 --fw-vad-threshold 0.5 `
  --format json -o (Join-Path $audit 'asr-case.json')
# Chỉ thêm --fw-voice-extraction ở variant đã ghi trước; không xử lý vocals hai lần.

& $python $runner qwen-text -m videocaptioner.cli transcribe $caseWav `
  --config (Join-Path $audit 'empty.toml') --asr qwen-local --language zh `
  --qwen-model qwen-1.7b --qwen-runtime $qwenRuntime -o (Join-Path $audit 'qwen-case.txt')
```

P4 mới chạy full offline/build; chưa mặc định bật các lệnh này khi chỉ sửa một ca:

```powershell
& $python $runner full-offline -m pytest tests/ -q `
  -m 'not integration and not slow and not llm' --basetemp (Join-Path $audit 'pt-full')
# Thêm media integration liên quan; fake provider phải ghi rõ là fake.

# Chỉ dùng khi $verifiedModels/$mediaTools đã verify và tên build chưa tồn tại.
$env:VC_BUILD_NAME = 'VideoCaptioner-OcrAsrQuality-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$env:VC_TEST_MODELS_DIR = $verifiedModels
$env:VC_TEST_MEDIA_TOOLS_DIR = $mediaTools
try {
    & $python -m PyInstaller VideoCaptioner.spec --clean
} finally {
    Remove-Item Env:VC_BUILD_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:VC_TEST_MODELS_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:VC_TEST_MEDIA_TOOLS_DIR -ErrorAction SilentlyContinue
}
```

Mọi subprocess trong code dùng argument list và `child_environment()`; temp,
UV/HF/Torch cache và log ở audit. Không chép credential vào env/prompt/report.
CLI/API OCR không được tự gửi audio lên gateway. Mọi request vision bổ sung phải
có mục tiêu/cap riêng, dùng crop tối thiểu; không retry batch timeout cũ.

## 11. Bàn giao từng phase

Mỗi phase ghi: hypothesis, source/config/model hashes, command, input/output,
fresh/cache/request counts, duration, lỗi quan sát, pass/fail/not-run và stop reason.
Đính kèm diff/allowlist source và test thực sự đã chạy; không cộng trùng số tests.

Không reset/clean/revert, apply/pop/drop stash, overwrite artifact cũ hoặc
stage media/model/raw/private transcript. Quyền commit/push thay đổi liên quan
đã có từ yêu cầu triển khai trước; chỉ dùng trong phiên **triển khai**, sau
review/validation và stage allowlist cụ thể. Lượt **lập plan hiện tại không commit/push**.

Thứ tự commit dự kiến: OCR regression/policy compatibility → ASR fix cụ thể
hoặc routing đã có bằng chứng → GUI/export hardening → docs/packaging acceptance.
Không gộp thử giọng B hoặc thay đổi nền vào các commit nhận dạng.
