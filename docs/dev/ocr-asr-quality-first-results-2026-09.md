# OCR/ASR quality-first — kết quả triển khai 2026-09-16

## 2026-09-18 — D3: frontend không bỏ frame; numerical verifier chưa pass toàn bộ

Audit `.tools/asr-frontend-20260918-005832/`, bắt đầu `f84d5cb` sạch/khớp remote.
Verify **7.969 prior hashes**, bảo vệ **8.020 file**, baseline **764 tracked file**.
App implementation vẫn `724906e`; không chạy app/tạo snapshot, sửa production,
default, parser, OCR hoặc installed runtime. Đọc đúng source/runtime đã ghim.

Hypothesis độc lập kiểm layer **feature extraction → mask/audio placeholders →
decoder constraints**, vì các audit PCM/raw token trước chưa lưu feature tensors.
Khóa input/worker/runtime/budget trước khi chạy: ba synthetic controls và hai WAV
D3 19 s cũ, một lần/case, cap60 s/process. Dùng processor CPU thật và SDK
`Qwen3ASRModel.transcribe`; object thay thế model chặn tại lời gọi `generate`, trước
mọi model forward. Không constructor model/weights, không output nhận dạng giả,
không context/caption hoặc đổi audio. Đây là **preprocessing**, không ASR inference.

Cả original/filtered giữ **304.000 samples, 1.900 active feature frames, 247 audio
tokens**; input IDs/text mask là int64, feature mask là int32, features chuyển BF16.
Không frame bị mask, không NaN/Inf; prompt **265 IDs** khớp record beam5 đã lưu.
Record lịch sử có repetition penalties =1, no-repeat n-gram =0 và không suppression,
bad-word, sequence-bias hoặc forced-word constraints; `num_beams=5` nằm trong
effective overrides, không nhầm với giá trị 1 của base config.

Giới hạn: chưa lưu feature tensors ở lượt recognition lịch sử nên **historical
tensor equality unknown**. CPU reconstruction không chứng minh GPU parity, encoder
attention, BF16 speech accuracy hoặc nội dung lời nói. Warning `mistral-regex` của
Transformers được giữ trong log; không tự sửa tokenizer vì prompt IDs hiện khớp
record. Handoff cũ nhắc `asr-beam-20260917-183523/effective-config.txt` nhưng file đó
không có; dùng config/overrides sẵn trong `worker-raw/generation-01.json`, không dựng lại.

### Verification và failure được giữ

- Synthetic đầu fail vì harness đòi mọi mask int64. NPZ chứng minh feature mask
  int32 và các kiểm equality trước/sau cast đã pass. Amendment sửa assertion thành
  integral dtype, kiểm lại **dữ liệu đã lưu**, rồi chạy hai control còn lại. Không
  lặp silence hoặc thay plan/raw cũ. Tổng vẫn **3 synthetic + 2 retained traces**.
- Verification đầu **36/39 checks pass**. NumPy DFT với ideal FP64 Hann trên các
  frame khóa trước khác frontend FP32 quá `1e-5` ở ba ca; max `2,39482e-5`.
- Khóa một phép kiểm số học bổ sung dùng exact FP32 Hann/product của implementation,
  NumPy FFT độc lập, retained mel matrix/global clipping floor và **cùng ngưỡng**.
  **23/24 frames pass**; synthetic tone còn `1,12271e-5`. D3 original max
  `1,52090e-6`, filtered `9,85374e-6`. Đây chỉ là partial numerical parity;
  **overall numerical verifier NOT PASS**. Không tune threshold, chạy lại processor
  hoặc gọi các failure là pass. Hai verifier đều giữ đủ outputs/logs.
- BF16 rounding được so độc lập bằng integer round-to-nearest-even từ FP32 bits;
  masks/IDs/tensor hashes giữ. Tổng 3.072 mel-bin comparisons mỗi verifier không
  được cộng thành app tests hoặc model inference.

Process synthetic đầu **8,875 s/exit1** do assertion; hai control còn lại
**7,687 s/exit0**; hai D3 **8,219 s/exit0**, đều cap60 s. **0 ASR/OCR/VAD mới,
0 weights loads/model forwards/real generation batches, 0 app tests**. Five dummy
`generate` interceptions không phải model requests. Qwen tổng **14**, SenseVoice
tổng **1**, Whisper mới **0**; không install/download/upload hoặc recognition retry.

Kết quả không cung cấp candidate acoustic/decoder có căn cứ để nhận dạng tiếp.
**D3 content FAIL/P2 unresolved giữ**, không promote hoặc gọi speech accuracy pass.
D1 onset, D2 coverage/native saved-data giữ evidence cũ. Speech ground truth unknown,
không CER/WER. Không playback/annotation/holdout exposure mới; giữ contamination
H1 và lịch sử Whisper H1/H2. Alignment/native mới/holdout/whole-video/full offline/
EXE/translation/TTS NOT RUN. Không file cache/temp mới cần dọn hoặc delete attempt;
giữ model/raw, sáu câu Việt/recipe B và hai stash, không retry cleanup cũ.

Đọc `plan-locked.json`, `plan-amendment.json`, `runtime-manifest.json`,
`*-trace.json`, `*-tensors.npz`, receipts/logs, `verification.json`,
`numerical-verification-plan.json`, `numerical-verification.json`,
`D3-assessment.json`, coverage/phase/cleanup/preservation và `publication.json`.
Không lặp frontend traces hoặc nới numerical tolerance để tạo candidate.

## 2026-09-17 — D3: suy giảm cục bộ có thật, chưa chứng minh separator làm mất lời

Audit `.tools/asr-d3-transfer-20260917-232009/`, bắt đầu ở `724906e` sạch/khớp
remote. Verify **7.068 prior hashes**, bảo vệ **7.969 file**, gồm evidence native
mới nhất và media cache cần giữ; baseline **764 tracked file**. Không chạy app,
không tạo snapshot mới hoặc sửa production/default/parser/OCR. Các con số snapshot
770 file của phiên native là lịch sử riêng, không thay số baseline Git ở đây.

### Phép đo temporal transfer

Hypothesis mới kiểm **lệch thời gian hoặc suy giảm cục bộ** do Kim_Vocal_2 trên
cặp original/filtered đã lưu. Khác phép đo band energy trước: phép này so waveform
theo thời gian, không lặp PCM decode, stereo cancellation hoặc nhận dạng.
Hai input giữ nguyên 304.000 samples mono s16/16 kHz, 107–126 s:

- Original SHA `4e02d2ccfa4452bf28e1cdeeb6eadb3e62ccacd20174e3dd1d115049b96dd36c`.
- Filtered SHA `06c78390aea4e3b17c80c54c45dbf14918a3f6cb621ec07eb6515a98d6f49ea9`.

Khóa worker/input/runtime/threshold trước khi đọc kết quả. Tương quan tuyến tính
chuẩn hóa, bỏ DC, tìm lag ±1.600 samples; FFT được đối chiếu bằng direct dot.
[Định nghĩa correlate của SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.correlate.html)
là tài liệu phương pháp; harness dùng NumPy đã có, không cài SciPy hoặc package mới.
Positive lag nghĩa là filtered trễ hơn original. Giữ toàn clip và đủ sáu interval
Whisper lịch sử, không coi interval đó là lexical alignment đã nghiệm thu.

Đỉnh tương quan đều ở **0 sample**. Vùng tranh chấp 113,970–115,530 s có
correlation **0,864618**; trung bình filtered/original giảm **1,525 dB**. Không
phát hiện gross delay theo phép đo đã khóa, nhưng chưa loại trừ thay đổi phổ
hoặc mất chi tiết lời nói.

Đo đủ **1.899 block 20 ms, hop 10 ms**. Flag khi original RMS ≥−45 dBFS và
filtered/original ≤−20 dB, giữ nhóm block liên tiếp phủ ≥100 ms. Đây là ngưỡng
triage kỹ thuật, không phải ngưỡng accuracy hoặc speech đã hiệu chuẩn. Có 18
nhóm flag trong toàn clip; một nhóm giao vùng tranh chấp: **114,040–114,170 s**,
12 block phủ **130 ms**. Trung bình cả câu đã che mức suy giảm cục bộ này.
Không từ đó gán tín hiệu bị loại thành phụ âm, lời nói hoặc nền.

### VAD cặp theo flag đã khóa

Sau khi lưu kết quả DSP, khóa hypothesis thứ hai: so hoạt động dự đoán trên hai
WAV liên tục để kiểm flag vừa tìm, **không cắt input quanh câu đang tranh chấp**.
Reuse Silero v3 ONNX SHA
`f87d83bb8929f0608b1b907d3f520b865758a93e34f27e78b21d69d1a9fe54ec`
và OCR CPU environment; verify 1.244 runtime hashes, không tải/cài mới.

**2 streams / 198 forwards mỗi stream / 1 model load**, CPU 1 thread,
threshold 0,5, frame 1.536 samples/96 ms. Mỗi stream có h/c zero riêng rồi giữ
state liên tục; frame cuối 1.408 samples thật + 128 zero pad, không bỏ sample.
Đây là VAD D3 mới; không lặp hai stream D1 lịch sử.

Tiêu chí đã khóa: ít nhất hai frame liên tiếp giao flag có original ≥0,5 và
filtered <0,5. Hai frame thực tế:

| Source interval | Original probability | Filtered probability |
|---|---:|---:|
| 114,008–114,104 s | 0,245913 | 0,960973 |
| 114,104–114,200 s | 0,264426 | 0,793105 |

**Tiêu chí mất hoạt động original-only không đạt.** Xác suất filtered cao hơn
trong cả hai frame; không nâng thành bằng chứng từ còn đủ, hoặc tín hiệu bị
loại chắc chắn là nền. VAD có thể sai và chịu ảnh hưởng recurrent state; không
dùng nó làm phoneme/word alignment. **Chưa đủ căn cứ cho EQ, retiming, mixback,
separator mới hoặc thêm lượt ASR. D3 content FAIL/P2 unresolved giữ nguyên.**

### Validation và giới hạn

**11 synthetic checks pass** trước đo: known shifts, gain, erasure, silence và
noise controls. **7 DSP + 6 VAD preflight checks**, **28 final checks pass**.
Replay energy bằng integer PCM độc lập khớp cả 1.899 block; replay **396 tensor
hashes**, kiểm state chain, zero initial state, final state và native probabilities.
Không gọi model lại khi verify; đây là kiểm harness, **0 app tests mới**.

DSP process **0,391 s**, VAD process **0,578 s**, mỗi cap 60 s, exit0, không
timeout/retry/cache/failed attempt. **0 ASR/OCR recognition mới**; VAD mới 2
streams/396 forwards được đếm riêng. Qwen tổng **14**, SenseVoice tổng **1**,
Whisper mới **0**. Không tạo audio đã sửa, ảnh hoặc annotation mới; không upload.
Speech ground truth vẫn unknown, không CER/WER hoặc accuracy winner.

D1 onset vẫn unresolved; D2 saved-data native pass và coverage ngoài 63 s giữ
evidence cũ. Không playback/holdout exposure mới; giữ H1 539 ms và historical
Whisper output/exposure H1/H2. Alignment, native mới, candidate holdout, whole-video,
full offline, EXE, translation/TTS **NOT RUN**. Sáu câu Việt/recipe B và hai stash giữ.
Không có cache/temp/profile file mới cần dọn, 0 delete attempt; không retry cleanup cũ.

Đọc `analysis-plan-locked.json`, `transfer-results.json`, `paired-blocks.jsonl`,
`vad-plan-locked.json`, `vad-pair-results.json`, hai `*-vad-frames.jsonl`,
`D3-assessment.json`, `verification.json`, process receipts, runtime manifests,
coverage/phase/cleanup/preservation và `publication.json`. Không lặp hai VAD
streams, tune threshold hoặc chọn subwindow mới từ kết quả này. Bước mới cần
evidence độc lập khác cho lỗi acoustic/lexical; diagnostic này chưa đưa ra một
candidate nhận dạng có căn cứ để triển khai hay promote.

## 2026-09-17 — Native saved-data D2 pass; sửa controls của checkpoint OCR

Audit `.tools/native-roundtrip-20260917-223430/`, bắt đầu từ `0bbda7d` sạch.
Copy **770 file đúng bytes** từ checkout, gồm `_version.py` sẵn có, không sinh
lại. Verify **7.029 prior hashes**, bảo vệ **7.068 file** và kiểm riêng **16 file
media cache cũ**. Settings/log/cache/output thuộc audit; source/model/raw cũ chỉ đọc.

### Luồng GUI source đã thực hiện

Dùng `computer-use:computer-use` thao tác cửa sổ app thật. MainWindow và các
callback mở/lưu/handoff/edit/undo giữ code app; harness chỉ quan sát trạng thái,
chặn `OcrThread.start` nếu vô tình nhận dạng. Không preload checkpoint thay cho
thao tác mở native. Chọn D2 trước khi chạy: checkpoint complete, **4 cue**, giữ
tracking v3/consensus punctuation-v2 và raw PaddleOCR-VL đã có.

1. Chọn source, mở checkpoint bằng file dialog và để app xác minh source.
2. Lưu checkpoint mới, chuyển JSON sang bảng phụ đề rồi Video Editor.
3. Thay riêng display text cue đầu bằng marker ASCII, Apply → Undo → Redo → Undo.
4. Lưu project JSON + SRT, mở lại, lưu lần hai rồi mở lại lần hai.

Bảng phụ đề và editor giữ đủ 4 cue, text, canonical ms, IDs, OCR metadata/raw.
Chỉnh sửa chỉ đổi display text đã chọn; hai lần Undo khôi phục exact cues.
**Project JSON và SRT giữ exact bytes giữa hai vòng lưu.** Không ghép text
với timing khác nguồn, không dịch hoặc ghi marker vào output cuối.

### Lỗi UI được sửa và kiểm lại

Khi mở D2, dữ liệu đúng nhưng controls vẫn hiện **0–60000 ms** và ROI toàn ảnh.
`accept_document` trước đó chỉ khôi phục line anchors/tracking checkbox. Bản sửa
đồng bộ Đầu/Cuối, Xem tại và ROI số/canvas từ `document.config`, rồi mới refresh
candidate controls. Document/policy/worker/default/parser không đổi.

Hai synthetic regressions cho complete/partial đều fail trước sửa. Bản sửa
trung gian refresh quá sớm gặp stale candidate ID khi đổi document; test có sẵn
bắt được lỗi đó. Final **64 passed, 1 warning** cho UI OCR/assistance/document/
resume, gồm hai regression mới; Ruff, Pyright **0 errors/0 warnings**, translation
sync pass. Pyright lần đầu cảnh báo đường dẫn venv của snapshot; lần cuối chỉ rõ
venv gốc, không cài hoặc nâng dependency.

Native sau sửa mở lại chính checkpoint vừa lưu ở bước 2: controls đúng
**57000–63000 ms**, Xem tại **57000 ms**, ROI **0.05/0.88/0.90/0.10**, đủ 4 cue.
Scan vẫn disabled khi chưa có preview được xác minh; mở dữ liệu không nạp model.
Lưu checkpoint sau sửa giữ exact bytes với file trước sửa. Full editor workflow
ở trên đo trước UI fix; sau fix kiểm riêng native reopen/resave và controls.

**24 final native artifact checks pass.** Hai GUI gate exit0, lần lượt
**790,984 s** và **252,750 s**, không timeout; tổng **1043,734 s**. Lần harness
đầu exit1 sau 2,250 s trước event loop do truyền sai tham số `QApplication.exec_`;
giữ code/log/receipt và sửa observer riêng, không coi là app crash. Giữ cả verifier
ban đầu: một lệnh sai relative path chưa chạy, một assertion đếm nhầm snapshots
redo-enabled thành số lần Undo; final kiểm hai state transitions và exact data,
không replay GUI để chọn kết quả. UIA focus/coordinates ở modal không đáng tin
trên màn hình này; dùng screenshot và bàn phím, không sửa app để né tool.

### Phạm vi và bàn giao

**0 OCR/ASR/VAD/translation/TTS inference mới**, không playback hoặc holdout
navigation. Waveform/thumbnails reuse 16 file cũ đúng hash; editor player giữ
stopped, vị trí 0, viewport trước H1. Giữ contamination/exposure lịch sử H1/H2.
Không đánh đồng saved-data GUI pass với recognition accuracy, fresh full native
OCR, real GPU cancellation, toàn video, full offline suite, EXE hoặc TTS.
**D1/P2 unresolved, D3 content FAIL**; OCR text D2 còn lỗi đã biết, chưa accuracy mới.

Đã dọn **394 cache/temp files / 1.842.398 bytes**, không lỗi; giữ snapshot,
observations/screenshots, raw/output và 16 cached-media files dùng làm evidence.
Không thử lại cleanup audit cũ. Đọc `native-plan-locked.json`, harness amendment,
`native-v2-receipt.json`, `fixed-native-plan.json`, `native-fixed-receipt.json`,
`native-verification-final.json`, `observations*/`, `outputs/`, `screenshots/`,
regression/scoped logs, quality checks, cleanup/preservation và `publication.json`.

## 2026-09-17 — Whisper trên prefix D1 không cung cấp lexical evidence

Audit `.tools/asr-d1-prefix-20260917-220411/`, từ `6bd2743` sạch/khớp remote.
Verify **6.995 hash cũ**, bảo vệ **7.029 file**, baseline **764 tracked file**.
App implementation `6db7921` giữ nguyên; không chạy app hoặc tạo snapshot mới.

### Diagnostic khóa trước inference

Acoustic evidence cũ đặt hoạt động dự đoán qua cut 27 s. Hypothesis mới kiểm
xem riêng audio trước cut có tạo được lexical evidence cho lời mở đầu hay không.
Lấy đúng **48.000 samples mono s16/16 kHz**, khoảng nửa mở **[24,27) s**, từ
192.000 samples context đã lưu; không resample/filter/separation/padding.
WAV SHA `7a2eadfeeac6d0d689b9bef4d33cc9b071c2cda408b7600744c7032519fa99ae`.
Đây là diagnostic prefix cố ý bị cắt, không phải policy cắt ngắn mới hoặc phép
so sánh accuracy giữa engine. Lượt Qwen context cũ không được chạy lại.

Reuse native Faster-Whisper-XXL và **large-v3** đã có; weights SHA
`69f74147e3334731bc3a76048724833325d2ec74642fb52620eda87352e3d4f1`.
Inventory/hash **5.130 file** của tools/model; không cài/tải mới. Cấu hình được
kiểm qua `--help` của executable thực: CUDA FP16, Chinese, Silero v3 CPU,
threshold 0,5, temperature 0, **temperature fallback None**, 5 beams, token cap 64,
word timestamps false, không prompt/hotword/context text. Cap **1 native task /
120 s / 0 retry**. AI visual reference cũ được đọc lại trước candidate; có prior
exposure, không phải independent listening. Không đưa chữ đó vào command.

### Kết quả và cách hiểu

Process **27,219 s**, exit0; model load theo log **1,96 s**, native operation
**25,694 s**, VAD **0,134 s**. Native VAD giữ local **1,788–3,000 s** trong prefix,
tương ứng source **25,788–27,000 s**. Đây là một VAD invocation trên input mới,
không replay stream 24–36 s cũ; số VAD forward nội bộ không được executable lộ ra.
Log có một processing segment; không coi đó là chứng minh mọi internal decoder call.

Raw sinh một câu kêu gọi like/subscribe thay vì lời mở đầu cần kiểm. Giữ native
JSON/TXT/log/token IDs đầy đủ trong audit. **Diagnostic FAIL: không có lexical
evidence đáng tin; true onset INCONCLUSIVE.** Output có biểu hiện hallucination,
chưa có independent listening để chấm speech truth. Native avg_logprob
**−0,217831**, no_speech_prob **0,095581** không được dùng làm điểm accuracy.
Native segment 25,790–26,990 s chỉ là metadata của output không dùng được;
không gắn mốc này cho chữ Qwen. VAD evidence cũ vẫn giữ, vì một bản đọc trên
prefix bị cắt không chứng minh lời mở đầu vắng mặt hoặc cut vô hại.

**6 preflight + 17 checks cuối pass**, kiểm input/plan/worker/runtime,
process/cap, CUDA FP16, native representation và metadata; **0 app tests**.
Harness đầu fail hai giả định: TXT native chứa timing prefix, và timestamp
tokens không bị `skip_special_tokens` loại bỏ. Giữ `verify.py`,
`verification.json`, `token-verification.json` ban đầu; `verify_v2.py` chỉ bỏ
metadata khi đối chiếu. Hai lượt token decode replay, **0 inference replay**;
lượt cuối 33 native tokens gồm 2 timestamp markers và **31 text tokens** khớp
body JSON/TXT. Full generation EOS/logits/beam ancestry chưa được capture;
không gọi native segment tokens là toàn bộ decoder trace.

**Whisper mới 1 native task**, không gọi tổng Whisper lịch sử là 1. **VAD mới
1 prefix stream**, forward count unknown. Qwen tổng **14**, SenseVoice tổng **1**;
OCR/Qwen/SenseVoice/D2/D3 không recognition mới. **P2 unresolved, D3 content FAIL**
giữ nguyên. Chưa chạy word/forced alignment, native GUI/editor, candidate holdout,
whole-video, full offline, EXE hoặc TTS. H1 playback 539 ms và historical Whisper
output/exposure H1/H2 giữ nhãn cũ; không exposure mới.

Đã dọn **15 CUDA cache files mới / 47.635.186 bytes**, inventory/hash/path và
receipt lưu trong audit; không lỗi, không đụng cleanup audit cũ. Model/raw,
sáu câu Việt/recipe B và hai stash được giữ. Đọc `candidate-plan-locked.json`,
`runtime-manifest.json`, `process-receipt.json`, `candidate-results.json`,
`candidate-assessment.json`, `verification-final.json`, `token-verification-final.json`,
`coverage-ledger.json`, preservation, cleanup và `publication.json`.

Không lặp prefix này, kéo dài/cắt thêm để chọn output, hoặc dùng fail làm lý do
chạy lại context/SenseVoice/beam5/chunk7s. D1 vẫn cần evidence lexical đáng tin
trước khi kết luận từ bị cắt; D3 cần hypothesis acoustic có căn cứ riêng.
Không đổi production/default/parser hoặc mở gate sau để né quality còn thiếu.

## 2026-09-17 — D1 có acoustic evidence trước cut; D3 chưa có candidate mới

Audit `.tools/asr-acoustic-20260917-213905/`, từ `372db11` sạch/khớp remote.
Verify **6.888 hash** lịch sử; bảo vệ **6.995 file**, baseline **764 tracked
file**. Không chạy app nên không tạo app snapshot mới; kiểm hash production
trước/sau. App implementation vẫn `6db7921`; không sửa code/default/parser/OCR.

### Phép đo khóa trước khi chạy

Hypothesis: cut 27 s có thể đi qua speech event. Đo hoạt động trên nguyên D1
context **24–36 s / 192.000 samples**, SHA
`246677d5528737b2f7d5ea93f5f414ed8f349a9ec48d3b6010bdd5a9394e5c99`.
Không nhận dạng chữ hoặc dùng caption làm prompt. Reuse **Silero v3 ONNX**,
SHA `f87d83bb8929f0608b1b907d3f520b865758a93e34f27e78b21d69d1a9fe54ec`,
và environment OCR CPU sẵn có; không tải/cài lại. Manifest giữ 1.244 hashes
của model/wrapper/Python/NumPy/ONNX Runtime, không thay installed runtime.

Dùng interface từ wrapper đã lưu, đối chiếu
[Silero v3.1 upstream](https://raw.githubusercontent.com/snakers4/silero-vad/v3.1/utils_vad.py).
CPU 1 thread, frame **1.536 samples / 96 ms**, threshold **0,5**, state liên tục
từ đầu WAV. Cap **1 stream / 125 forward calls / 1 load / 60 s**, retry/cache 0.
Giữ native output hai class, probability và hash tensor từng frame; không sweep
threshold/window. VAD inference không phải ASR recognition hoặc forced alignment.

### Kết quả D1 và D3

VAD complete, process **0,515 s**, load **0,031 s**, inference **0,031 s**,
0 failure/cache/retry. Dải raw score vượt ngưỡng đầu tiên là **26,688–27,552 s**;
cut 27 s nằm giữa dải. Ba frame hoàn toàn trước cut phủ **288 ms**, score
**0,8205 / 0,8489 / 0,8359**; dải dự đoán bắt đầu trước cut **312 ms**.
Kết hợp raw Qwen context lịch sử có lời mở đầu trong khi clip hẹp thiếu nó,
đây là **bằng chứng hỗ trợ boundary hypothesis**, chưa chứng minh onset của
từ bị thiếu hoặc causality riêng cho từ đó. Không coi context dài là thắng
accuracy trên cùng input; **P2 vẫn unresolved**.

Replay đủ 125 probability frames qua `get_speech_timestamps` đã lưu, kiểm
exact float32 tensor SHA, **0 inference mới**. Span đầu của postprocessor
mặc định là **26,658–28,926 s**: hysteresis nối hai raw runs và padding 30 ms
dịch biên. Giữ cả hai biểu diễn; không gán chúng làm timestamp từ/câu chuẩn.

D3 chỉ phân tích phổ trên đủ **sáu interval native Whisper lịch sử**, cùng
original/filtered WAV đã khóa; các interval không phải lexical alignment đã
nghiệm thu. FFT Hann 25 ms, hop 10 ms; không resample/separation hoặc đổi audio.
Vùng tranh chấp **113,970–115,530 s** có RMS **−25,352 / −26,877 dBFS**
(original/filtered), tỉ lệ năng lượng **3–8 kHz: 2,349% / 2,590%**, thấp nhất
sáu vùng ở cả hai input. Đó là mixed-signal statistics, không SNR hoặc phép
đo độ rõ phụ âm. **Chưa chứng minh separator làm mất chữ**; không suy ra EQ,
separation hay model/window candidate mới từ số đo này. **D3 content FAIL giữ nguyên**.

### Validation, preservation và bước tiếp

**7 preflight + 15 verification checks pass**; plan/worker/input/runtime giữ
hash, 125 frame phủ đúng WAV, nguồn/timing map đúng và process trong cap.
125 tensor replays là kiểm audit, **0 app tests mới**; không cộng 17/509 cũ.
**0 Qwen/SenseVoice/Whisper/OCR recognition mới**; Qwen tổng **14**, SenseVoice
tổng **1**. Ghi riêng một VAD stream / 125 forward calls thực tế.

D2 giữ evidence câu cuối ngoài 63 s. Reuse AI visual reference có prior
exposure; speech ground truth unknown, không CER/WER. Không playback/frame
hoặc exposure holdout mới; giữ H1 playback 539 ms và historical Whisper
output/exposure H1/H2. Alignment/native mới/candidate holdout/whole-video/
full offline/EXE/TTS **NOT RUN**. Sáu câu Việt/recipe B và hai stash giữ nguyên.

Không có file cache/temp mới cần xóa; chỉ có thư mục runtime rỗng. Không thử
lại cleanup audit cũ bị policy chặn, không có approval rejection mới phiên này.
Đọc `analysis-plan-locked.json`, `runtime-manifest.json`, `vad-frames.jsonl`,
`vad-results.json`, `upstream-postprocess-replay.json`, `signal-results.json`,
`D3-acoustic-assessment.json`, `boundary-assessment.json`, `verification.json`,
`coverage-ledger.json`, `quality-report.md`, preservation và `publication.json`.

D1 đã có bằng chứng cut qua hoạt động giống lời nói, vẫn thiếu lexical onset.
Không biến VAD thành alignment hoặc chạy lại context đã hết cap. D3 cần thêm
evidence acoustic phân biệt che lấp/cách phát âm với khác biệt caption trước
khi khóa candidate mới; không sweep, ghép output hoặc sửa text theo caption.

## 2026-09-17 — SenseVoice CTC độc lập không giải quyết D3

Audit `.tools/asr-sensevoice-20260917-192331/`, từ `99f4b6d` sạch/khớp remote.
Verify **6.878 hash** lịch sử, bảo vệ **6.888 file**, snapshot **770 file** copy
đúng checkout. App implementation vẫn `6db7921`; không sửa production code,
default/parser, OCR hoặc runtime đã cài.

### Hypothesis, runtime và giới hạn

Qwen greedy/beam và Whisper cho các cách đọc khác nhau ở cụm bị che; một
decoder **SenseVoice CTC** độc lập có thể tránh ảnh hưởng lặp từ decoder
autoregressive. Đây là hypothesis thử nghiệm, không phải kết luận nguyên nhân.
Dùng [API chính thức của sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/sense-voice/python-api.html),
model từ repository được tài liệu đó chỉ dẫn. Không sweep model/config.

Inventory không thấy SenseVoice/sherpa trong runtime Qwen hoặc các artifact
đọc được; một số thư mục temp khác bị access denied, không suy thành vắng mặt
toàn máy. Theo quyền chuẩn bị local, tải **FP32 ONNX** riêng audit, revision
`2365baeacb507f821a0c8120fcee3d484dba7a07`, weights SHA
`977016bd9c79f9eb343430b5cc305e07ab64d5212dff41b0dcfa1694bee9a8cb`.
Verify SHA upstream cho model/wheels và Git blob cho tokens. Cài đúng hai
wheel `sherpa-onnx==1.13.8`, `sherpa-onnx-core==1.13.8` vào dependency target
riêng, reuse Python Qwen; không sửa environment app hoặc installed runtime.
Một lookup package version 1.12.14 trả HTTP 404 trước chuẩn bị; version thật
1.13.8 lấy từ PyPI metadata. Không tính lookup đó thành inference failure.

Khóa trước inference: **1 request/1 batch**, cap process **180 s**, retry/cache
0; CPU **4 threads**, Chinese, greedy CTC, ITN bật. Giữ nguyên canonical WAV
filtered D3 **19 s/304.000 samples**, SHA
`06c78390aea4e3b17c80c54c45dbf14918a3f6cb621ec07eb6515a98d6f49ea9`.
Không VAD chia nhỏ, audio transform, separation, hotword, prompt hoặc context.
Đây là diagnostic engine riêng audit, chưa phải tích hợp CLI/GUI provider mới.

### Kết quả và validation

| Gate | Kết quả mới |
|---|---|
| Request / recognizer batch | 1 / 1 |
| Complete / failed / cache / retry | 1 / 0 / 0 / 0 |
| Process / load / recognition | 2,093 s / 0,984 s / 0,219 s |
| Provider / GPU jobs | CPU / 0 |
| Qwen cumulative / SenseVoice cumulative | 14 / 1 |
| Text gate | FAIL; P2 unresolved |

Câu mở đầu bị thay bằng các chữ không phù hợp, câu nhận lời thiếu từ và cụm
lặp thành các mảnh khác caption. Token đuôi Qwen cũ không xuất hiện, nhưng
không đủ để pass toàn nội dung. Giữ nguyên output, không ghép với những câu
đúng của engine khác hoặc chọn theo caption. Sáu crop đã trực tiếp đọc lại
trước candidate; **AI visual reference**, đã có prior exposure, không phải
blind/human speech ground truth. Không speech CER/WER.

**6 preflight checks** kiểm input, API, một dispatch không hotword và chặn
request lặp. **13 output/provenance checks** pass: plan/worker/runtime/input
hash không đổi, **45 tokens** đều có trong vocabulary và ghép đúng native
text/TXT, metadata nhất quán, process trong cap. Mapping symbol sang token ID
là readback, không phải pre-CTC argmax path. Raw native JSON giữ language,
emotion, event và timestamps; không lưu full logits. EOS không áp dụng CTC.
Native timestamp chỉ được kiểm consistency, **chưa nghiệm thu timing phụ đề**;
không chạy forced alignment. Process kết thúc bình thường, không GPU lease.

**0 app tests mới** vì code app không đổi; không cộng 17/509 lịch sử.
Report script từng gặp `KeyError` do key path Windows khi tổng hợp hash; sửa
đọc hash từ path thật và chạy lại tổng hợp, **0 inference thêm**. Worker/plan/raw
của lượt đo giữ nguyên. Không dùng lỗi report để cấp lại request.

### Coverage và bàn giao

D1 chỉ đọc các row 24–36 s từ baseline cũ: không có cue giao đoạn. Bản native
27–34 s có cue bắt đầu local 60 ms nhưng không chứa lời xưng hô đầu câu,
nên không định vị được onset lời đó. **D1 onset vẫn unresolved**. D2 giữ
evidence câu cuối ở 63,33–64,95 s ngoài clip cũ. **0 D1/D2 request mới**.
Không in thêm row holdout; giữ H1 playback 539 ms và exposure H1/H2 đã ghi.

Evidence: `runtime-preparation-plan.json`, `downloads.json`,
`runtime-manifest.json`, `preflight.json`, `candidate-plan-locked.json`,
`effective-config.txt`, `results/native-result.json`, `candidate-results.json`,
`candidate-assessment.json`, `verification.json`, `asr-visual-comparison.json`,
`boundary-assessment.json`, `coverage-ledger.json`, `quality-report.md`, cleanup
receipt và `publication.json`. Model/raw/private transcript chỉ ở audit ignore.

Candidate đã hết cap; không retry/tune, promote hoặc tải thêm model để sweep.
Bước tiếp cần hypothesis acoustic có căn cứ và budget mới từ cụm tranh chấp,
hoặc evidence onset D1 độc lập. Giữ ambiguity caption/lời nói; không sửa parser
hay text bằng đáp án. OCR giữ mức ưu tiên phụ đã chấp nhận.

Alignment/native GUI/editor mới/candidate holdout/whole-video mới/full offline/
EXE/TTS **NOT RUN**. Giữ model/runtime/raw/snapshot, sáu câu Việt/recipe B và
hai stash; không thử lại cleanup audit cũ từng bị policy chặn.
Cleanup cache/temp/wheel archive dư của audit mới cũng bị automatic approval
review chặn (`blocked by policy`) trước khi tạo process: **0 byte đã xóa**,
**71.343.668 bytes còn nguyên**; giữ receipt, không retry hoặc đổi cách xóa.

## 2026-09-17 — D3 beam search không giải quyết content gate

Audit `.tools/asr-beam-20260917-183523/`, bắt đầu từ `5e3ddfb` sạch và khớp
remote. Verify 6.868 hash cũ, bảo vệ 6.878 file; snapshot 770 file copy bytes
từ checkout và so trước các gate. Không đổi production code/default/OCR,
không cài package hoặc tải model. App implementation vẫn `6db7921`.

### Hypothesis và lượt đo duy nhất

Raw Qwen filtered 19 s lặp cả cụm; chia 7 giây vẫn nhận khác lời. Whisper
large-v3 VAD-on filtered có một cách đọc khác với probability **0,172607** ở
từ tranh chấp. Giả thuyết mới: greedy decoding chốt sớm vào nhánh lặp; beam
search có thể chọn sequence khác mà không đổi acoustic input hoặc thêm text.
Đây là hypothesis thử nghiệm, không khẳng định nguyên nhân đã được chứng minh.

Đã kiểm installed Qwen `generate` chuyển kwargs tới `thinker.generate`; đối
chiếu [Transformers generation](https://huggingface.co/docs/transformers/v4.57.0/main_classes/text_generation).
Bridge riêng audit thay `num_beams=5`, giữ `do_sample=False` và một sequence
được model chọn. Bật `output_scores` chỉ để lưu score/beam ancestry. Không
chọn beam bằng caption. Không thay installed runtime hoặc source bridge.

Khóa trước inference: **1 request/1 generation batch, 5 beams**, retry/cache 0,
stage 120 s, outer process 180 s. Reuse canonical D3 filtered WAV **304.000
samples/19 s**, SHA `06c78390aea4e3b17c80c54c45dbf14918a3f6cb621ec07eb6515a98d6f49ea9`;
model pin đã verify `7278e1e70fe206f11671096ffdd38061171dd6e5`. CUDA/BF16/SDPA,
Chinese, window 19 s và token cap 864; không prompt/context/reference, alignment
hoặc tách vocals lại. So với whole-window filtered baseline, không coi các
partition chunk7s khác nhau là cùng input request.

| Gate | Kết quả mới |
|---|---|
| Request / generation batch / beams | 1 / 1 / 5 |
| Complete / failed / cache / retry | 1 EOS / 0 / 0 / 0 |
| Outer process / inference / model load | 31,500 s / 15,110 s / 11,953 s |
| Generated tokens / cap | 46 / 864 |
| Peak allocated VRAM | 4.698.543.616 byte; không phải toàn bộ GPU memory |
| Qwen cumulative | 14 = 13 lịch sử + 1 mới |

### Kết quả và kiểm chứng

Cụm lặp đã đổi thành một cách diễn đạt khác, nhưng vẫn khác AI visual reference;
token đuôi cũ vẫn còn. Những phần thiếu đầu câu so với caption vẫn được ghi rõ
trong bảng audit. **D3 content gate FAIL/P2 unresolved**; không promote beam5,
không sửa parser, không retry/sweep. Giữ toàn bộ output và đủ sáu raw cũ + hai
output chunk7s + output mới; cả hai baseline Whisper original/filtered được
đọc lại riêng. Không sửa chữ theo caption hoặc gọi khác caption là speech CER/WER.

**1 tokenizer replay** khớp raw trước parser, response và TXT; EOS/token-count/
prompt/budget/plan/worker hashes đều pass. Beam ancestry có nhánh **0/2/4**,
xác nhận đường beam hoạt động. Lưu token IDs, raw decode, effective overrides,
sequence score và ancestry của sequence được model chọn; không lưu mọi logits
hoặc các nhánh bị loại. **0 inference kiểm chứng**. Parser không đổi chữ ở
request này; không suy ngược raw lịch sử chỉ có post-parser text.

**17 targeted tests passed, 1 warning** trên final checkout snapshot. Ba mock
checks kiểm forwarding beam kwargs, raw retention và EOS guard đều pass; không
tính chúng là GPU/model tests. Preflight đầu thiếu NumPy trong app Python,
dừng trước inference; chạy mock bằng Python Qwen riêng đã cài. Giữ receipt lỗi,
không cài dependency vào Qt process. Worker đã đóng/release lease; exit1 là
normal owned-process termination sau response thành công, không phải ASR failure.

### D1/D2: đánh giá coverage riêng bằng evidence đã lưu

Hypothesis riêng: thiếu đầu/cuối khi so caption với audio window hẹp có thể là
giới hạn phạm vi input. Không chạy lại hai context đã đo hoặc lấy output dài
hơn làm bằng chứng accuracy tốt hơn trên cùng audio.

- **D1:** context 24–36 s có phần mở đầu mà request 27–34 s thiếu. Chưa có onset
  timestamp đủ tin cậy để kết luận phần đó bị mốc 27 s cắt hay decoder bỏ.
  Coverage evidence partial; nội dung/syllable còn unresolved.
- **D2:** historical native baseline đặt câu cuối ở **63,33–64,95 s**, hoàn
  toàn ngoài request 57–63 s. Context 54–67 s có câu này; hỗ trợ hypothesis thiếu
  phạm vi. Native timing chưa là speech ground truth. Frame caption 62,9333125 s
  chỉ cách clip end 66,6875 ms, không đủ suy rằng cả lời caption nằm trong clip.
  Spelling tên và thán từ khác caption tiếp tục là bất định lời nói.

**0 D1/D2 request mới**, không căn thời gian hoặc gán giờ Whisper cho chữ Qwen.
Không sửa editor schema/timing/IDs/CommandStack/provenance/save behavior.

### Hiệu chỉnh lịch sử holdout và bàn giao

Khi tra D2, phát hiện whole-source Whisper baseline đã lưu một cue giao H1
và bốn cue giao H2. Excerpt đầu file cũng lộ H1 text và đầu metadata timing H2;
không mở thêm transcript holdout để chấm chất lượng. Vì vậy ghi chú cũ “H2 chưa
inference” chỉ có thể dùng cho **quality-pilot candidate mới**, không phải mọi
ASR lịch sử. Không gọi H1/H2 wholly unseen. Giữ cả 539 ms native playback H1
đã biết; chưa chạy candidate holdout hoặc annotation/acceptance mới.

Evidence: `candidate-plan-locked.json`, `runtime-verified.json`, `preflight.json`,
`attempts.jsonl`, `worker-raw/`, `results/`, `candidate-results.json`,
`token-verification.json`, `boundary-assessment.json`, `holdout-exposure.json`,
`asr-visual-comparison.json`, `coverage-ledger.json`, `quality-report.md`,
`publication.json`. Raw/transcript/absolute paths chỉ nằm trong audit bị ignore.

Alignment/native GUI/editor mới/holdout candidate/whole-video mới/full offline/
EXE/TTS **NOT RUN**. Không đổi sáu câu Việt/recipe B. Không thử lại cleanup cũ
bị policy chặn, giữ artifact phiên này. Candidate đã hết cap: bước tiếp cần
hypothesis acoustic mới hoặc đường ASR độc lập có căn cứ và budget riêng,
không tiếp tục sweep beam/chunk hoặc dùng caption chữa parser.

## 2026-09-17 — ASR D3: một candidate cửa sổ 7 giây đã đo bằng CUDA

Audit `.tools/asr-d3-20260917-180217/`, bắt đầu từ `f3ec6ed`; HEAD/remote,
tree/index và hai stash được kiểm live. Verify **6.858 hash** từ baseline trước,
bảo vệ **6.868 file**, copy **770 file** từ checkout và so bytes trước từng gate.
Giữ OCR hiện tại theo ưu tiên speech-to-text. Không cài/tải thêm model/package,
không sửa app/default/parser hoặc runtime đã cài. Harness chỉ thêm quan sát
token/decode sau `generate`, trước parser, trong bridge riêng của audit;
bỏ đoạn quan sát ra khớp source bridge. Đây là CLI source gate với harness quan
sát, không phải native GUI/EXE hay tích hợp một policy mới vào production.

### Hypothesis và điều kiện đã khóa

Kiểm ảnh hưởng của ngữ cảnh decoder 19 giây tới cụm lặp bằng tùy chọn có sẵn
`--local-chunk-ms 7000`. Reuse D3 original request WAV và đúng Kim_Vocal_2
`*_dump.wav`; không dùng `*_mdx.wav`, tách vocals lại hoặc kéo dài window.
Model pin `7278e1e70fe206f11671096ffdd38061171dd6e5`, CUDA/BF16/SDPA, Chinese,
greedy và EOS budget giữ nguyên. Không prompt/reference/previous text context.

Giới hạn 7 giây được chọn trước khi xem partition/kết quả mới. Splitter hiện có
chọn biên bằng energy, nên original/filtered có partition khác nhau. So mỗi
output với baseline cùng preprocessing; không coi chúng là cặp cùng chunk audio.
Mốc dưới đây là **window nhận dạng**, không phải subtitle/alignment timestamps.

| Input D3 | Các phần tương đối trong 19 s (ms) | Requests / batches | CLI wall |
|---|---|---:|---:|
| Original | 0–6500; 6500–13250; 13250–19000 | 3 / 3 | 28,485 s |
| Filtered | 0–6450; 6450–9650; 9650–15850; 15850–19000 | 4 / 4 | 28,937 s |

Ghép từng partition khớp toàn bộ **304.000 PCM sample/input**, không bỏ/lặp sample.
Khóa **7 request**, batch 1, một attempt/part, **0 retry/cache**, stage 60 s,
hard process cap 240 s; chạy hai job tuần tự. Cả 7 complete/EOS, 0 failed.
Outer process **58,422 s**; inference cộng **32,329 s**, load cộng **18,828 s**,
peak allocated VRAM **4.698.543.616 byte**. Không cộng thời gian con vào process
wall. Hai worker đã đóng/release lease; exit1 do `LocalRuntime.close()` terminate
owned process sau response thành công, không tính thành failed inference.
**Qwen tổng 13 request = 6 lịch sử + 7 mới**, không phải 13 batch mới.

### Kết quả và giới hạn

- Original: token đuôi cũ không còn, nhưng nhận sai cụm lặp vẫn xuất hiện ngay
  trong raw decoder. Chia ngắn chưa giải quyết được lỗi nội dung này.
- Filtered: có thêm phần mở đầu câu chấp nhận; cụm lặp gần caption hơn baseline,
  nhưng còn thiếu một từ nối và thêm thán từ. Token đuôi cũ không còn; punctuation
  mới cắt một câu ở biên chunk. Giữ nguyên toàn bộ output, không sửa dấu/ghép lời.
- Cả hai vẫn thiếu thán từ đầu window so với caption. Caption chỉ là
  **AI visual reference**; các khác biệt chưa tự xác minh được lời thực nói.
  Assistant đọc lại sáu crop D3 đã lưu; không xem thêm holdout hoặc tạo lại frame.
- **D3 text/content gate chưa đạt, P2 unresolved.** Có tín hiệu cải thiện hẹp
  ở filtered và đuôi; không công bố winner/accuracy, promote chunk7s hoặc alignment.
  D1/D2 tiếp tục reuse bốn output cũ; không đổi spelling theo caption hoặc chạy
  lại context chỉ để lấy thêm output. Bảng audit giữ đủ sáu output cũ + hai
  output ghép mới và toàn bộ bảy chunk mới.

**7 tokenizer decode replays** khớp raw decode trước parser và response;
7 EOS/token-count/budget checks đều đạt. Input IDs decode ra cùng prompt cố định
chỉ có audio và Chinese. TXT khớp nối nguyên raw chunk. **0 inference kiểm chứng**.
Trong bảy request này parser không thay chữ; không quy lỗi cụm lặp mới cho parser.
Synthetic replay xác nhận upstream có heuristic rút gọn lặp dài, nhưng output
lịch sử chỉ có post-parser text: replay idempotent không chứng minh raw cũ.
Không sửa parser theo một nguyên nhân D3 chưa được chứng minh.

**17 targeted tests passed, 1 warning**: chunk PCM/retry/cache/EOS, text-only
recovery và CLI TXT guards. Không cộng 509 tests lịch sử. Một lệnh harness đầu
sai đường dẫn script, exit2 trước import/inference; giữ receipt và sửa đường dẫn,
không phải retry model. Ruff/Pyright/full offline không chạy lại vì không sửa
production code. Git diff check và preservation kiểm riêng khi publication.

Evidence: `candidate-plan-locked.json`, `runtime-verified.json`, `inputs/`,
`attempts.jsonl`, `worker-raw/`, `results/`, `candidate-results.json`,
`verification.json`, `token-verification.json`, `asr-visual-comparison.json`,
`quality-report.md`, `publication.json`. Giữ raw/model/checkpoint/snapshot.
Cleanup cache/temp riêng phiên **chưa thực hiện**: automatic approval review
chặn lệnh xóa với `blocked by policy`, kể cả một absolute target đã kiểm tra;
giữ khoảng 264 MB và ghi `cleanup-receipt.json`. Speech ground truth
unknown, không CER/WER, alignment/native mới/holdout/whole-video/full offline/
EXE/TTS **NOT RUN**; H1 đã lộ 539 ms, H2 chưa inference. Recipe B và sáu câu Việt
giữ nguyên. Candidate đã dùng hết budget; không sweep chunk size hoặc lặp lại
7 request. Bước tiếp cần hypothesis mới từ lỗi decoder/acoustic còn lại.

## 2026-09-17 — điều chỉnh tiêu chí theo user: ưu tiên speech-to-text

Sau kết quả candidate, user chấp nhận OCR khoảng **80–90%** và ưu tiên
**speech-to-text tốt**. Đây là tiêu chí sản phẩm mới, không phải một số accuracy
đã được đo. Giữ kết quả OCR hiện có; lỗi glyph/dấu nhỏ ở D2 không còn là điều
kiện chặn tiến độ ASR. Kết quả D2 fail theo exact-text gate cũ vẫn được giữ.

Công việc tiếp theo tập trung ASR D3 (cụm lặp, nội dung khác caption, token đuôi),
rồi coverage đầu/cuối D1/D2. Tiếp tục dùng AI visual reference với nhãn nguồn rõ;
không yêu cầu human transcript mới triển khai, không trộn caption vào prompt ASR.
Chưa có inference, sửa code hoặc phép đo accuracy mới trong lần đổi ưu tiên này.
Các budget đã tiêu thụ, raw/model/media, sáu câu Việt và recipe B giữ nguyên.

## 2026-09-17 — từ `0403e02`: app candidate VL opt-in; D2 chưa đạt text gate

Audit `.tools/ocr-asr-quality-20260917-171207/`. HEAD/remote khớp trước làm,
working tree/index sạch; verify **6.791 hash cũ**, bảo vệ **6.858 file**. Copy 763
tracked file ban đầu; snapshot gate cuối 770 file gồm file mới và `_version.py`
đã có, so bytes checkout trước từng gate. Không cài/tải model hoặc package mới.

### Boundary recognizer đã triển khai

Candidate `paddleocr-vl-1.5-anchor-v1` qua `--recognizer-runtime` hoặc ô runtime
PaddleOCR-VL trong cửa sổ OCR. CPU PP-OCRv6 giữ geometry/tracking; crop RGB union
của dòng được chọn có margin cố định được đưa vào GPU worker riêng. Prompt chỉ
là `OCR:`, không chứa chữ CTC/reference. Recipe pin model/custom code/tokenizer/
packages; BF16/SDPA/greedy96/no KV cache giữ như diagnostic. Chi tiết tại
[contract candidate](ocr-vl-candidate-2026-09.md).

Checkpoint lưu recognizer identity riêng, token IDs/raw decode/EOS/crop hash và
geometry CTC. Read/cache IDs tách khỏi CPU; field mới được omit trên dữ liệu cũ.
GPU score để 0 vì chưa hiệu chuẩn; không dùng box input crop thay detector box
khi cached tracking. Giữ nguyên worker v1/v2/v3 và punctuation-v2; không sửa raw,
dictionary, old resume hoặc export guard. Missing runtime/identity, timeout/hủy,
protocol/crop mismatch và output thiếu EOS đều dừng, không fallback/retry ngầm.

Một GPU lease/job; cap 40 tổng CPU geometry + VL requests và 360 s/job. Transport
giữ các bộ đếm riêng cho request, batch CTC/VL, tracking/features/cache. Test hủy
dùng process thật với worker synthetic; **chưa đo hủy khi model GPU đang generate**.

### Một lượt D1/D2 theo plan khóa

| Window | Cue | CPU requests / rec batches | VL requests / batches | Tracking / features | Process wall | Scan/export | Text |
|---|---:|---:|---:|---:|---:|---|---|
| D1 28,8–32,3 s | 2 | 6 / 12 | 6 / 6 | 105 / 231 | 127,906 s | complete/exit0 | PASS trên frame đã đọc |
| D2 57–63 s | 4 | 11 / 14 | 11 / 11 | 180 / 287 | 171,329 s | complete/exit0 | FAIL |

0 failed inference/cache/retry; 17/17 VL response EOS. Peak allocated VRAM D1
**1.984.445.952 byte** theo runtime receipt; D2 **1.983.719.424 byte**.
Không cộng thời gian tracking/GPU chồng nhau thành tổng. Tổng lịch sử VL hiện
**21 attempts: 20 complete, 1 failed**; bốn diagnostic attempts cũ, gồm first-forward
failure, vẫn giữ nguyên. Không có request mới trên đúng crop diagnostic đã hết quyền.

D1 giữ body/dấu trên ảnh. D2 giữ bốn cue và biên như baseline, nhưng raw được chọn
ở cue cuối sai thán từ; dấu ba chấm cũng khác giữa các raw read. Hai candidate cuối
có score chưa hiệu chuẩn bằng nhau: policy chọn nguyên raw cũ giữ candidate sớm.
Candidate muộn đọc đúng glyph theo AI reference vẫn được lưu, **không chọn riêng
theo đáp án**, không ghép raw hoặc sửa consensus để công bố pass. **P1 unresolved;
candidate D2 text gate FAIL**, không promote default.

Offline readback: 17 token decode replays khớp. Crop diagnostic đầu tại PTS
1006400 nằm nguyên pixels trong crop app có padding; tensor processor khác.
Candidate app sau tại PTS 1007467 khác diagnostic PTS 1006933, nên không có phép
so identical-input cho cặp này. Một harness đầu giả định nhầm PTS đã fail; amendment
chuyển sang match PTS và ghi unmatched rõ ràng. **0 verification inference**;
chưa đủ bằng chứng nhân quả rằng padding tự nó gây lỗi.

Evidence: `candidate-plan-locked.json`, `candidate-code-amendment.json`,
`candidate-D{1,2}/` (inputs/raw/checkpoint/events/runtime receipts),
`candidate-quality-assessment.json`, `candidate-verification*.json`.

### ASR và validation

Assistant đọc 12 frame/crop cũ, ghi source hash/frame hash/PTS khi có, mốc seek
xấp xỉ khi evidence cũ không có PTS chính xác và prior exposure. Đặt
`reference_kind=AI visual reference`, không human-reviewed. Bảng đối chiếu chứa
**cả sáu raw Qwen đã chạy**, mỗi output giữ đúng window/preprocessing/hash.
D1 còn khác từ, D2 khác spelling tên/thán từ; D3 khác cụm lặp và token đuôi.
Giữ **P2 unresolved**, speech ground truth unknown; 0 ASR mới, không upload,
CER/WER, alignment hoặc sửa sáu câu Việt/recipe B. Không chờ human transcript.

**509 passed, 7 deselected, 1 warning**, gồm 23 synthetic contracts mới; không cộng
các lượt test lặp hoặc số lịch sử. Bảy real-model tests deselected được ghi đúng,
không gọi là inference mới. Ruff, Pyright **0 errors/0 warnings**, translation sync
pass. Bốn checkpoint lịch sử v1/v3 giữ exact JSON/config/raw/IDs/metrics.
D1 2 cue và D2 4 cue qua table/handoff/undo/hai vòng editor save-reopen giữ
text/ms/IDs/generation provenance; SRT giữ text/time. Đây là domain/source gate,
không phải native GUI mới hoặc text acceptance D2.

Review cuối bổ sung guard CLI bảo vệ model/dependencies/Python payload nằm ngoài
thư mục manifest khỏi output ghi đè; ba test mới được tính trong 509 ở trên.
Worker/recipe/recognition giữ nguyên, không chạy lại D1/D2. Bản CLI lúc đo được
giữ riêng trong `measured-code/`; `post-review-amendment.json` phân biệt bytes
đã đo với guard output cuối, không gọi toàn bộ CLI sau review là cùng bytes.

Giữ các harness failures trong receipts: module mới chưa có ở red collection;
Git quoting tên Unicode làm snapshot gate lỗi trước test; basetemp parent thiếu;
một lệnh sai test path collect0/exit4; typing/snapshot venv lookup ban đầu và lỗi
stdout encoding của runner; giả định PTS ở kiểm crop nêu trên. Các lần sửa harness
không thêm model inference. EOL-only edit đã undo của `consensus.py` được phục hồi
exact bytes trước inference bằng amendment; plan gốc không bị viết lại.

Native mới, real GPU cancel, holdout, whole-video, full offline, EXE và TTS
**NOT RUN**. H1 contamination 539 ms không đổi. Giữ model/raw/receipts/snapshot;
dọn riêng cache/temp của audit hiện tại. `publication.json`, review/allowlist và
preservation receipts là nguồn trạng thái Git cuối.

## 2026-09-17 — từ `56bbbdf`: crop0 bổ sung đạt diagnostic; ASR reference còn thiếu

Audit `.tools/ocr-asr-quality-20260917-164027/` bắt đầu từ HEAD/remote `56bbbdf`,
tree/index sạch. Verify **6.303 hash cũ**, bảo vệ **6.791 file**, copy **763 file
tracked** đúng bytes checkout và kiểm trước các gate; inventory 331 tài liệu
evidence. App implementation vẫn `cb437cb`, không sửa app/profile/default.

### PaddleOCR-VL: hoàn tất đúng một attempt bổ sung đã được user cấp

Sau khi chuẩn bị runner và khóa plan, user đã cấp riêng **1 attempt crop0,
tối đa 90 s, không retry tiếp**. `authorization.json` gắn với SHA plan
`aee967215494affdb564af00219642ce350abe200da135f8d5486b7292bb030a`.
Plan giữ nguyên bytes và chữ PENDING lịch sử; receipt authorization mới là bằng
chứng quyền đã cấp. Cap ba attempts cũ không được sửa hoặc xóa failed attempt.

- Reuse model/weights/tokenizer và `vl-deps/` của audit `160948`, không tải/cài
  thêm. Pinned PaddleOCR-VL-1.5, BF16/SDPA, prompt `OCR:`, greedy96,
  `use_cache=false`; adapter keyword masking API giữ đúng hash đã verify.
- Chỉ input0 đã khóa, raw BGR SHA
  `e7b90e210c8aad45707a8250eaa03a05b9fdb94969513ffe3444b2bf1b225148`;
  reuse đúng bốn input tensors cũ. Deadline worker 75 s, hard process cap 90 s.
- **1 request/1 batch, 0 failed, 0 cache/tracking/features**, không warmup hoặc
  retry tiếp. Generation **14,828 s**, process **23,782 s**, exit0, EOS.
  Crop0 giữ glyph đầu và phần thân nhìn thấy theo AI visual reading; không thêm
  dấu ngoài crop. Peak allocated VRAM **1.978.958.848 byte**.
- Crop1 và blank reuse nguyên output cũ, không chạy lại. Diagnostic hai crop
  và blank **PASS trong phạm vi nhỏ này**, theo **AI visual reference, không
  human ground truth**. Tổng lịch sử **4 attempts: 3 complete, 1 failed**;
  failed first forward cũ vẫn giữ. Tổng process inference **70,766 s** qua hai
  audit với cap riêng, không gọi là bốn request mới hoặc một budget đã được nới.
- Readback **4 tensor comparisons + 3 token decode replays** đều khớp,
  0 recognition trong verification, **0 app tests mới**. Không cộng lại 12/2/4
  checks trước hoặc 92 tests lịch sử. Model unload khi worker thoát.

**P1 vẫn unresolved**: chưa tích hợp recognizer vào app, scan D1/D2 hoặc chứng
minh blank/fade/punctuation/one-frame-change qua pipeline. Attempt bổ sung đã
dùng hết; không lặp crop0/crop1/blank để chọn output. Bước tiếp theo là candidate
opt-in có identity/provenance riêng và gate D1/D2 theo budget đã khóa, không
promote default chỉ từ diagnostic.

Evidence: `vl-supplement-plan-locked.json`, `authorization.json`,
`vl-supplement-{results,receipt,verification}.json`, `run-ledger.jsonl`.

### ASR: xác định nguồn YouTube không đủ làm reference lời nói

Một metadata extraction bằng yt-dlp đã cài, không cookie/login, trên
[bản phát hành chính thức](https://www.youtube.com/watch?v=mT86JXY6oEw)
trả duration **261 s**, language **en-US**, không có manual track trong response;
chỉ có automatic captions, gồm lựa chọn Chinese. Không coi lựa chọn Chinese
tự động là bản chép audio gốc tiếng Trung. Edition/timebase cũng chưa khớp với
nguồn Bilibili 266,566625 s. Không tải transcript/media hoặc phát video.

Reference độc lập cần người hiểu tiếng Trung nghe audio gốc D1/D2/D3, chép lời
và đánh dấu chỗ không chắc; ghi rõ người nghe và prior exposure tới caption/ASR.
Kịch bản chính thức chỉ hỗ trợ nếu kiểm khớp lời thực nói. Caption, bản dịch,
ASR khác hoặc signal statistics không tự trở thành ground truth. User không
biết tiếng Trung, không yêu cầu user tự chép lời. Giữ **reference=unknown**,
0 ASR mới/upload/CER/WER/alignment; Qwen tổng vẫn 6. Evidence:
`asr-reference-{plan-locked,results,assessment}.json`.

**Chỉ đạo bổ sung sau giải thích:** user chấp nhận chính assistant đọc chữ từ
ảnh làm reference. Working reference từ đây là **AI visual reference**, không
bắt buộc human transcript mới tiếp tục OCR/ASR. Đối chiếu ASR với caption phải
ghi phần khớp/khác/chưa rõ; không coi mọi khác biệt là lỗi lời nói hoặc tính
CER/WER lời nói từ caption. Không đưa đáp án vào prompt ASR; giữ raw/provenance.
Chỉ đạo này thay điều kiện chờ human reference, không tự chứng minh ASR đã đạt.
Receipt `reference-policy-amendment.json` và prompt phiên sau ghi rõ thay đổi.

Native mới/holdout/whole-video/full offline/EXE/TTS **NOT RUN**. Giữ H1
contamination 539 ms, hai stash, sáu câu Việt và recipe B. Dọn riêng temporary
files của audit này; giữ model/raw/tensors/snapshot/receipts. Gate Git/preservation
và publication cuối nằm trong audit; prompt phiên tiếp theo đã cập nhật.

## 2026-09-17 — từ `c330f77`: PaddleOCR-VL có tín hiệu tốt, diagnostic chưa đủ

Audit `.tools/ocr-asr-quality-20260917-160948/` bắt đầu từ HEAD/remote `c330f77`,
tree/index sạch. Verify **705 hash cũ**, bảo vệ **6.303 file**, gồm cả runtime
Paddle trước; copy **763 file tracked** đúng bytes checkout và kiểm trước từng
gate. Inventory đọc 291 tài liệu evidence. Lỗi setup ban đầu do các file cấu hình
JSON Lines trong package Paddle được giữ trong amendment; không sửa artifact cũ.

### Recognition: giữ tỷ lệ dòng bằng encoder dynamic resolution

Chọn duy nhất [PaddleOCR-VL-1.5](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5),
pin `2a4195faa5e7914c12f2fc601d72c81caf8d2da5`. Giả thuyết: encoder độ phân giải
động cùng decoder OCR có thể giữ glyph đầu dòng nhỏ mà đường resize vuông hoặc
patch rời trước đó chưa đọc đủ. Không lặp V4/GOT/SVTRv2 hoặc sweep recognizer.

- Weights SHA `d557c9d8997ae57ed3b1b33bdf347be878cc335687f32ca105341c16973f8958`
  khớp LFS official; 1.917.255.968 byte. Output/embedding **103.424 classes**,
  tokenizer **101.316 entries**; target glyph là token 97757. Inventory và input
  tensors khóa trước inference; coverage chỉ là điều kiện cần.
- Reuse Qwen Python/Torch 2.8.0+cu128/Transformers 4.57.6 với code official pinned
  đọc local. Bổ sung torchvision 0.23.0+cu128, sentencepiece 0.2.1, protobuf 5.29.5,
  einops 0.8.1 vào `vl-deps/` riêng; app/Qwen environments không đổi. Đây là
  diagnostic custom-code runtime, chưa là app profile hoặc portable acceptance.
- Cùng hai raw crop và blank trước đó; prompt `OCR:`, processor mặc định,
  BF16/SDPA, greedy, 96 new tokens, không KV cache. Cap **3 request/3 batches,
  180 s**, không retry. Crop0 lỗi trong first forward do keyword `inputs_embeds`
  không khớp `input_embeds` của masking API, trước token đầu; **vẫn tính 1 request
  và 1 failed inference attempt**. Không gọi đây là crop nhận sai chữ.
- Adapter local chỉ đổi tên keyword; bốn ca mask CPU kiểm eager/SDPA, có/không
  padding đều fail ở lời gọi cũ và giữ đúng causal/padding mask sau adapter.
  Amendment giữ nguyên model/input/decoding, chỉ chạy **hai input chưa chạy**:
  crop1 và blank; không retry crop0. Hard cap process còn lại 155 s, tổng vẫn <180 s.
- Crop1 giữ glyph đầu, phần thân và dấu cuối theo **AI visual reference cũ**;
  blank rỗng, cả hai EOS. Hai request hoàn tất mất 14,874 s generation; tổng hai
  process inference, kể cả lượt lỗi, **46,984 s**. Peak allocated VRAM lượt sau
  1.981.510.656 byte. Tổng **3 attempts/3 batches: 2 complete, 1 failed**;
  0 cache/tracking/feature batches, 0 retry, không ghép raw.

**INCOMPLETE, chưa tích hợp hoặc scan window**: crop0 chưa có output, nên không
đạt gate cả hai crop dù crop1/blank có tín hiệu tốt. Không loại model vì lỗi API,
không lấy riêng crop1 để công bố quality pass, không tự cấp thêm request khi cap
đã hết. Các lỗi import/harness trước inference cũng giữ trong receipts/amendments.

Replay 12 input tensors và hai token decodes từ dữ liệu lưu đều khớp; cộng với
bốn ca mask là kiểm harness, **0 app tests và 0 recognition mới**. Không cộng các
số này với 92 tests lịch sử. Evidence chính: `vl-{upstream,inventory,plan-locked,
results,plan-remaining-locked,remaining-results,verification}.json`,
`vl-compat-verification.json`, runtime amendments và process receipts.

### ASR và giới hạn còn lại

Tìm nguồn đối chiếu theo video chính thức chỉ có mô tả/credits, chưa có transcript
nghe độc lập D1/D2/D3. Truy vấn metadata Bilibili không đăng nhập trả **HTTP 412**;
không suy ra nguồn không có subtitle. Giữ `reference=unknown`, tổng Qwen vẫn 6,
**0 ASR mới**, không upload audio, CER/WER, alignment hoặc tách vocals lại.
Evidence: `asr-reference-{plan-locked,results}.json`.

Không đổi app; implementation vẫn `cb437cb`. Native mới, holdout, whole-video,
full offline, build EXE và TTS **NOT RUN**. Native partial 69 cue v1 và các gate
v3 trước vẫn là bằng chứng lịch sử, không nâng thành fresh full workflow.
P1/P2 unresolved; H1 contamination 539 ms giữ nguyên. Hai stash, sáu câu Việt,
recipe B và dữ liệu cũ được bảo toàn. Dọn riêng cache/temp/profile/tools tạm do
audit này tạo theo yêu cầu user; giữ model, raw, tensors, snapshot và receipts.
Inventory xóa và số byte thực tế nằm trong `cleanup-receipt.json` của audit.

## 2026-09-17 — từ `5403845`: loại SVTRv2; kiểm PCM và native partial 69 cue

Audit `.tools/ocr-asr-quality-20260917-151112/`. HEAD/remote khớp `5403845`,
index/working tree sạch trước làm. Verify **626 hash cũ**, bảo vệ **705 file**;
copy 763 file tracked từ checkout và so bytes trước từng gate. Giữ settings,
cache/temp/log trong audit, hai stash và `master` nguyên trạng. App implementation
vẫn `cb437cb`; không sửa tracking v1/v2/v3, consensus, profile hoặc mặc định.

### Recognition: một recognizer CTC khác, chưa sửa được glyph D2

Giả thuyết: encoder CTC khác có dictionary phù hợp có thể đọc hai crop lỗi mà
không dùng bộ sinh token đã hallucinate. Chọn duy nhất bản official
[PaddlePaddle/ch_SVTRv2_rec](https://huggingface.co/PaddlePaddle/ch_SVTRv2_rec),
revision `67349283ac400fb34f73a5c32f1c0c00df5ee26a`. Không lặp V4/GOT hoặc sweep model.

- Inventory trước inference: 6.623 dictionary entries, **6.625 output classes**;
  glyph cần kiểm có class index 3872. Weights SHA-256
  `2f9e8ea8852560f908e1a0fb497818477e5a3610f660ddb339b3dddb0c207116`
  khớp LFS metadata official. Coverage chỉ là điều kiện cần.
- Runtime cũ không có Paddle. Tạo `paddle-runtime/` riêng trong audit với
  PaddlePaddle 3.0.0, NumPy 1.26.4; app/OCR/Qwen environments giữ nguyên.
  Lượt đầu lỗi `ModuleNotFoundError: setuptools` trước predictor/inference,
  giữ receipt; bổ sung setuptools 80.9.0 theo amendment, không đổi plan/input/cap.
- Khóa **3 request/3 batches, 180 s, 0 retry, 0 warmup**: đúng hai raw crop
  cùng hash với V4/GOT và blank cũ. Dùng BGR/height48/dynamic width, preprocessing
  official, greedy CTC không lọc confidence; CPU 4 threads, MKLDNN tắt.
- Thực hiện 3/3, **0 cache/tracking/features**, 0 failed inference attempts;
  inference 0,875 s, worker 1,062 s, process 4,125 s. Blank rỗng nhưng cả hai
  crop đều sai glyph đầu câu, nên **loại candidate**, không scan D1/D2 hoặc tích hợp.
  Raw/log/output tensors giữ local; reference ảnh vẫn là AI, không human ground truth.
- Replay 3 tensor preprocessing và 3 output decode khớp implementation official
  PaddleX; **6 đối chiếu pass, 0 inference mới**. Đây là kiểm harness, không phải
  6 test app hay bằng chứng recognition đạt. Không sửa app nên không có regression
  fail-before-fix mới và không chạy lại 92 tests cũ để cộng số pass.

Evidence: `svtr-upstream.json`, `svtr-inventory.json`, `svtr-plan-locked.json`,
`runtime-amendment*.json`, `svtr-results.json`, `svtr-verification.json` và receipts.

### ASR: kiểm input/request, reference lời nói vẫn unknown

Năm cặp WAV mono input/request cũ khớp PCM và sample count. D3 original kiểm riêng
từ stereo 44,1 kHz qua đúng `decode_audio`/`wav_bytes`: tái tạo nguyên request WAV
304.000 sample, SHA `4e02d2ccfa4452bf28e1cdeeb6eadb3e62ccacd20174e3dd1d115049b96dd36c`.
Đây là CPU decode kiểm tính toàn vẹn, không recognition hoặc alignment.
Audit ban đầu trỏ input D3 tới chính request; giữ dòng đó là pack identity,
amendment/final report thay bằng phép so từ source stereo, không tính self-comparison.

Ba listening WAV vẫn khớp file/PCM hashes. D3 stereo không có sample full-scale;
100 ms mid/stronger-channel RMS ratio nhỏ nhất 0,596. Các số đo tín hiệu không
chứng minh lời nói hoặc intelligibility. Trong reference artifacts được bàn giao
chưa có listener/transcript độc lập; user không biết tiếng Trung. Giữ
`reference=unknown`, không CER/WER, không chọn engine thắng. **0 ASR mới**, Qwen
vẫn tổng 6 request; không upload, tách vocals lại hoặc mở holdout.
Evidence: `asr-audio-plan-locked.json`, `asr-audio-results.json`,
`asr-pcm-amendment.json`, **`asr-audio-final.json`**.

### Native: bảo toàn partial có chữ, không nhận dạng lại

Dùng Computer Use mở checkpoint lịch sử thật **69 cue, incomplete, tracking v1**
từ audit nguồn; không biến complete thành partial. Lượt đầu native open/readback
khớp document, nhưng timer 170 s đóng harness trước save; giữ receipt exit0 đó.
Lượt sau preload cùng partial, rồi **lưu và mở lại bằng modal native**, quan sát
UI nạp xong và bấm Đóng; process exit0 sau 97,172 s. Save/reopen giữ đủ text/ms/
IDs/raw/config; file lưu **khớp bytes** checkpoint gốc, vẫn incomplete. UI Export
bị khóa; CLI export **exit5**, không tạo SRT. Không recognition/tracking/playback.

Đây là native open/save/reopen **partial v1 có chữ**, bổ sung gate partial v3
0 cue trước đó; chưa kiểm fresh v3 cancel/resume có chữ hoặc full source/ROI-to-result.
Evidence: `native-text-partial/`, `native-text-save/`, `native-verification.json`.

P1/P2 vẫn **unresolved**. Native full workflow/listening acceptance còn thiếu;
H1 vẫn có contamination 539 ms từ trước. Holdout/whole-video/full offline/build
EXE/TTS **NOT RUN**. Không lặp SVTRv2 trên các crop này hoặc sweep recognizer;
lượt tiếp cần giả thuyết recognition mới có căn cứ và reference lời nói phù hợp.

## 2026-09-17 — từ `a29791f`: loại dynamic patches; native partial cancel/save/reopen

Audit `.tools/ocr-asr-quality-20260917-145000/`. Live HEAD/remote khớp `a29791f`,
working tree/index sạch trước làm. Verify 538 hash cũ, bảo vệ 626 file, giữ hai
stash và `master`. Snapshot copy **763 file tracked từ checkout**, so bytes trước
từng gate, không dùng Git archive khác line endings. Settings/cache/log/temp
cô lập trong audit. Không đổi source app; implementation vẫn `cb437cb`.

### Recognition: một giả thuyết preprocessing mới, không đạt

Local Transformers `4.57.6` cho thấy đường cũ resize crop 246×35 và 299×38
thành 1024×1024. [GOT processor hỗ trợ dynamic patches](https://huggingface.co/docs/transformers/v4.57.1/model_doc/got_ocr2).
Giả thuyết mới là giảm biến dạng tỷ lệ nét bằng chế độ này; không lặp plain raw,
contrast/padding/glyph-isolation, không đổi model hoặc thêm dictionary entry.

- Verify lại đúng GOT revision/weights/tokenizer cũ; inventory **151.860 output
  classes**, tokenizer coverage trước inference. Không tải model/cài package.
- Khóa cùng pixel hashes của hai crop và blank; `crop_to_patches=True`,
  `min_patches=1`, `max_patches=12` mặc định, plain OCR, greedy, BF16/eager,
  96 new tokens. Processor tự tạo patch-reference prompt, không có đáp án.
  Grids 7×1/8×1/7×1 tương ứng 8/9/8 ảnh encoder kể cả thumbnail; hash tensors
  và input IDs khóa trước. Đây không phải 25 recognition request riêng.
- Budget **3 recognition/3 batches, 180 s, 0 retry**; thực hiện đúng 3/3,
  0 cache, 0 tracking/feature batches, không failed inference exception.
  Generation 38,109 s, process 46,765 s; peak allocated VRAM 23.528.787.456 byte.
- Hai crop đều mất phần lớn câu, không lấy lại glyph mục tiêu; blank lặp ký tự,
  đạt 96 token khi **chưa EOS**. Gate đã khóa yêu cầu đủ glyph/body, không thêm
  chữ và blank không hallucinate, nên **loại candidate**, không tích hợp/profile,
  không scan D1/D2, không retry/tăng token hoặc ghép output.

Evidence: `got-tiled-inventory.json`, `got-tiled-plan-locked.json`,
`got-tiled-results.json`, `got-tiled-inference-receipt.json`. Tổng GOT diagnostic
qua hai phiên là 6 request (3 raw cũ + 3 tiled mới); cả hai candidate bị loại.
Reference ảnh vẫn là AI, không phải human ground truth. Chưa có recognition fix.

### ASR: chuẩn bị reference, không nhận dạng lại

Tạo `listening/` với ba WAV original D1 24–36 s, D2 54–67 s, D3 107–126 s
copy đúng bytes của input đã có, kèm SHA/PCM/sample counts. README chỉ hướng dẫn
nghe và ghi phần chưa rõ; không kèm caption hoặc output ASR. Template ghi nhận
người nghe và việc đã xem caption/model output trước đó, không tự gán nhãn
independent/human-reviewed. User xác nhận không biết tiếng Trung; không yêu cầu
user chép/duyệt lời tiếng Trung ở phiên sau. Chưa có transcript nghe độc lập;
việc tìm nguồn đối chiếu phù hợp vẫn thuộc phần điều tra của agent.
`reference=unknown`, Qwen vẫn
**6 request tổng/0 mới**; không CER/WER, alignment, audio upload hoặc tách vocals.

### Native P3: hủy/lưu/mở lại partial có bằng chứng mới

Fixture mở `OcrDialog` thật với partial từ service gate cũ, đúng source và
tracking v3/consensus punctuation-v2. Dùng Computer Use bấm **Tiếp tục quét**
rồi **Hủy tác vụ**, không thay thao tác nút bằng timer. Khóa 3 recognition tối đa,
30 s/job; watchdog 25 s nếu thao tác không kịp và watchdog không được tính pass.

- Lượt đầu lỗi harness gán `max_requests` vào frozen `OcrTask`, process exit
  `3221226505` trước worker.start, 0 inference. Tái hiện `FrozenInstanceError`,
  giữ script/plan/receipt; amendment dùng `dataclasses.replace`, cùng budget.
- Lượt native thực click hủy ở **17,766 s**, worker kết thúc **18,078 s**, độ trễ
  **312 ms**, watchdog không dùng. **9 tracking/9 detector attempts mới**,
  0 recognition/cache/feature batches. Metrics resume là metrics lượt mới,
  không lấy 9 trừ 8 calls cũ. UI hồi phục, Save/Resume bật lại và Export vẫn khóa.
- Lưu `ui-saved.ocr.json` bằng modal native; document khớp bản capture, giữ
  incomplete/config/source/metrics. CLI export partial **exit5**, không tạo SRT.
- Mở lại ở lượt đầu chưa quan sát được trạng thái cuối trước harness tự đóng;
  giữ giới hạn đó trong receipt. Lượt chỉ đọc riêng sau đó mở file qua native
  modal, verify exact document trong callback và quan sát UI load xong. Không
  recognition mới, Export vẫn khóa; cửa sổ được đóng bằng nút native, exit0.

Đây là native **resume/cancel/save/reopen của partial 0 cue**, không thay gate
source/ROI-to-result/export hoàn chỉnh, bảo toàn cue có nội dung, hoặc quality.
Không playback, không mở thêm holdout; contamination H1 539 ms cũ vẫn giữ.
Evidence: `native-harness-amendment.json`, `native-cancel-v2/{plan-locked,results,
verification}.json`, `native-reopen-result.json` và các process receipts.

### Validation và bàn giao

**92 passed, 1 warning**: consensus/resume/OCR UI, Qwen TXT/long-audio/audio
identity/GUI TXT, trên snapshot khớp checkout. Đây là offline contracts; không
cộng với 72 pass phiên trước. Không đổi app nên không có regression app mới;
không chạy Ruff/Pyright toàn app hoặc full suite chỉ để tạo thêm số pass.

Bytes worker v3 và punctuation-v2, checkpoint/raw, model/runtime và sáu câu
Việt/recipe B giữ nguyên. Commit chỉ cập nhật report/status/handoff. P1/P2 vẫn
**unresolved**; native full workflow/listening acceptance còn thiếu.
Holdout/whole-video/full offline/build EXE/TTS **NOT RUN**. Không lặp GOT raw/tiled
hoặc các Qwen context đã đo; bước recognition tiếp phải có giả thuyết mới và
inventory trước inference, còn ASR cần reference nghe độc lập.

## 2026-09-17 — từ `3f731f2`: GOT diagnostic bị loại; D2 ASR thêm ngữ cảnh

Audit `.tools/ocr-asr-quality-20260917-135038/`. Live HEAD/remote đúng handoff,
index/working tree sạch trước làm. Verify lại 224 hash từ baseline trước và
giữ 538 file gồm source media, runtime, raw/checkpoint, settings, cookie,
work-dir và voice B. Hai stash cùng `master` giữ nguyên. Đây là lượt inference
local có thực hiện, nhưng không có candidate đủ căn cứ để sửa app production.

### Recognition D2: tokenizer rộng hơn không tự bảo đảm chất lượng

Giả thuyết mới: recognizer sinh token có thể biểu diễn glyph mà CTC dictionary
hiện tại thiếu. Chọn duy nhất [GOT-OCR2](https://huggingface.co/stepfun-ai/GOT-OCR-2.0-hf),
revision `d3017ef2c2c1395888c8d635c5e0508bcb0ac78d`; implementation Transformers
đã có hỗ trợ plain/scene OCR. Không thử thêm V4/V5, không lặp contrast/padding.

- Inventory trước inference: tokenizer và output embedding đều **151.860 class**;
  glyph cần kiểm roundtrip qua token IDs `[6606, 114]`. Coverage chỉ là điều kiện cần.
- Reuse Qwen Python riêng: Torch `2.8.0+cu128`, Transformers `4.57.6`, CUDA RTX 5090;
  không thay environment, không cài package. Model chưa có nên tải đúng pinned files
  vào audit. Weights SHA `6175ac7868a4e75735f5d59f78c465081ad3427eb4f312d072a0f1d16b333ba4`;
  tokenizer SHA `36b382a3c48c9a143c30139dac6c8230ddfb0b46a3dc43082af6052abe99d9de`.
- Hai crop cùng BGR SHA với V4 đã đo, PTS 1006400/1006933; thêm một blank synthetic.
  Khóa trước cap **3 recognition/3 batches, 180 s, 0 retry**, greedy, 96 new tokens,
  plain OCR mặc định, không đưa đáp án vào prompt. Không tracking/feature inference.
- Hai lỗi harness trước inference được giữ: path tương đối resolve nhầm vào snapshot;
  và model construction từ chối `sdpa`. Giữ plan/script cũ, tạo amendment `eager`
  trước chạy; không sửa plan sau kết quả hoặc đổi cap. Hai lỗi đó có 0 recognition.
- Lượt thực **3 requests/3 batches, 0 cache, 0 failed inference**, 18,047 s generation,
  25,750 s worker tổng, peak allocated VRAM 3.624.613.376 byte. Cả ba có EOS.
  Crop đầu lấy lại glyph; crop sau vẫn thiếu glyph. Blank sinh chuỗi chữ/số không có
  trên ảnh. **Candidate bị loại theo gate đã khóa**, không tích hợp/profile app,
  không chọn riêng output đầu hay ghép text giữa raws. Reference ảnh vẫn là AI.

Evidence: `got-upstream.json`, `got-inventory.json`, `got-plan-locked.json`,
`got-plan-eager-locked.json`, `got-results.json`, runtime logs/receipts.
Không scan lại D1/D2: diagnostic thất bại nên chưa có căn cứ cho window candidate.
Giữ worker v3 SHA `9bef0946f8456c9f7e4a36f49feba0555f61540dfc8f45eea4f6f94375931447`
và consensus SHA `7464cfa5950da83df0f1f88666c4fb59a03b5e6688b71174fdf29bea954961d1`.

### ASR D2 độc lập: mở input, chưa có speech reference

Giả thuyết: request cũ 57–63 s kết thúc trong interval caption cuối; kiểm thêm
ngữ cảnh audio gốc liền kề mà không đổi engine/language/decoding/preprocessing.
Caption chỉ gợi ý nơi kiểm boundary, không được đưa vào prompt hay dùng làm nhãn
lời nói. Khóa **54–67 s**, cap 1 request, stage 180 s/wall 240 s, không retry.
Không chạm holdout hoặc trộn audio filtered của D3 với original context.

- Reuse Qwen pin `7278e1e70fe206f11671096ffdd38061171dd6e5`, verify manifest/model.
  WAV mono 16 kHz PCM16 có 208.000 sample, SHA
  `a29238016dca8f756dac8343ce6dfca99bd646a2fa11bcb659f810a1d6161f52`.
- Trong overlap 96.000 sample, 95.360 sample nội vùng bằng tuyệt đối;
  toàn overlap bằng 99,989583%, sai khác tối đa 25 ở mép resampling. Không gọi
  toàn bộ WAV mới là cùng input cũ; thay đổi chủ đích là thêm ngữ cảnh.
- Đúng **1 fresh request/0 cache, 28,375 s** trong app, 28,781 s outer runner.
  Request WAV SHA `8dbdd5555010d993f6a31220c433eec676c36c8a056c9fba839cf5b709256668`.
  Output có thêm mệnh đề cuối, tên riêng vẫn khác chữ trên hình và thán từ chưa
  được xác nhận bằng nghe. Không kết luận lỗi lời nói chỉ vì khác caption.
- Tổng Qwen trên bộ này là **6 request**. Reference lời nói vẫn `unknown`;
  chưa CER/WER, alignment, model winner hoặc mapping text sang giờ Whisper.
  Whisper VAD-on và D3 original/filtered giữ nguyên, không tách vocals lại/upload.

Evidence: `asr-d2-context/plan-locked.json`, request WAV/raw/TXT, `results.json`.
Đã đưa audio D3 gốc cho user đối chiếu; chưa nhận transcript độc lập trong lượt này.

### Validation, bảo toàn và giới hạn

Final **72 passed, 1 warning**: punctuation consensus, OCR resume, Qwen TXT,
long-audio sample retention, audio identity và GUI TXT contracts. Đây là offline
contracts với mocks, không phải native/listening acceptance. Không đổi app code
nên không tạo regression mới hoặc chạy lại toàn bộ 337/243 tests cũ/full suite.

Phát hiện 74 file `git archive` khác checkout chỉ ở line endings. Snapshot ban đầu
và backup bytes inference còn lưu; sync allowlist rồi đối chiếu **536 file** bằng
bytes trước validation cuối. Không rerun inference và không thay hash checkpoint.
Lượt test trước cũng 72 pass nhưng không cộng trùng; một lệnh test gõ sai path
collect 0/exit4 được giữ trong ledger trước lượt final. P0 ledger ban đầu đếm nhầm
224 hash cũ thành 538 do alias dict; receipt correction ghi riêng, không sửa lịch sử.

`preservation-check.json`, `snapshot-gate-verification.json`, `review.json`,
`phase-results.json`, `coverage-ledger.json` ghi scope chính xác. Commit chỉ có
aggregate report/status/handoff; model, ảnh/audio, transcript và harness private
nằm trong audit ignored. P1/P2 vẫn mở; không có native mới. H1 vẫn bị lộ 539 ms.
Holdout/whole-video/full offline/build EXE/TTS **NOT RUN**; giữ sáu câu Việt/voice B.

Lần tiếp theo không chạy lại GOT raw hoặc Qwen D2 54–67 s để chọn output đẹp.
OCR cần giả thuyết mới có bằng chứng về độ ổn định recognition/negative controls;
ASR cần nghe độc lập vùng tên riêng/thán từ/lời lặp trước khi chấm text hoặc alignment.

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
