# OCR/ASR quality-first — kết quả triển khai 2026-09-16

Đã bắt đầu triển khai P0–P4 từ plan local
`docs/plans/ocr-asr-quality-first-2026-09.md` của phiên trước.
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
