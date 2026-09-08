# Hoàn thiện ASR theo mục tiêu speech-to-text

Ngày 2026-09-09, checkout ASR-S3, nền `669c0da`. User chốt ưu tiên: **nhận dạng
âm thanh đúng, nhanh và ổn định; phân biệt người nói là bổ sung**. Dịch tiếp tục
dùng gateway/gpt-5.6-terra đã chọn. Timestamp từng chữ không còn là điều kiện để
trả transcript hoặc công bố recognition thành công. OCR vẫn tạm dừng.

**Bổ sung mới nhất của user: đầu ra làm phụ đề vẫn cần timestamp câu/đoạn.**
LLM cần giữ các mốc đã đo từ audio khi dịch/chia/gộp cue; không thể suy chính xác
thời điểm lời nói chỉ từ văn bản. TXT dưới đây là đầu ra khi chọn chỉ lấy text và
bản bảo toàn khi timing thất bại, **chưa thay thế nghiệm thu SRT/ASS**.

## Đã xử lý trong lượt này

- Qwen có đường `recognize()` riêng. GUI chọn TXT và CLI xuất `.txt` chỉ chạy
  model nhận dạng; không tìm, verify, nạp hoặc gọi aligner/Community-1.
- Luồng xuất phụ đề chạy recognition trước khi kiểm tra aligner. Nếu aligner
  thiếu, sai manifest, lỗi load/inference hoặc trả span không hợp lệ, text hoàn
  chỉnh còn trong review và được GUI/CLI lưu thêm thành TXT cạnh output dự kiến.
  Nếu tên TXT đã có, dùng hậu tố số qua exclusive-create; giữ file của user.
- GUI nhận dạng riêng báo hoàn tất TXT, không ép mở editor sửa timestamp. GUI
  pipeline phụ đề vẫn dừng bước cần timing. CLI yêu cầu TXT trả exit 0; CLI yêu
  cầu SRT/ASS/JSON timed chưa tạo được output giữ exit 5 và báo vị trí TXT riêng.
  Nhờ đó script `process` không dịch/render một SRT cũ hoặc không tồn tại.
- Giữ text nguyên dấu/chữ/thứ tự. Không chuyển chunk boundaries thành timestamp
  lời nói, sửa raw span hoặc trả một `ASRData` có giờ giả. Recognition lỗi/hủy/
  thiếu chunk không được biến thành bản hoàn chỉnh. TXT không chứa speaker metadata.
- Không đổi checkpoint, frontend, chunk size, timeout, engine mặc định, cache
  recognition hoặc cấu hình LLM. Các lỗi nhận dạng/file dài đã đo vẫn cần xử lý.

CLI:

```powershell
uv run --frozen videocaptioner transcribe clip.wav --asr qwen-local --language zh `
  --qwen-model qwen-1.7b --qwen-runtime path/to/installed-runtime -o transcript.txt
```

GUI: Nhận dạng → chọn Qwen → định dạng TXT → bắt đầu. Model nhận dạng vẫn phải
đã cài; tự tải lúc bắt đầu chưa có, nằm ở bước tiếp theo. Nếu chọn SRT và timing
thất bại, bản TXT được giữ và review vẫn mở lại được bằng chức năng review hiện có.

## So sánh bằng dữ liệu đã đo

Nguồn: [S6](../dev/asr-s6-results-2026-09.md),
[sentence/stress](../dev/asr-s6-followup-2026-09.md) và
`VC-ASR-Completion-20260908-140534/reports/s6-measurements.json` trong evidence local.
Không chạy inference hoặc chấm CER lại để lập bảng này.

**CER là tỷ lệ lỗi ký tự, thấp hơn tốt hơn; không phải phần trăm audio nhận đúng.**
Tập so sánh chung gồm 28 clip meeting tiếng Quan thoại, 17.413 ký tự tham chiếu.
Giữ script/case/số và lời nói chồng; đây không phải cpCER chính thức của corpus.

| Model/config đã đo | CER cùng 28 clip | Transcript đầy đủ trên 32 clip | Nhận xét thực tế |
| --- | --- | --- | --- |
| Qwen 1.7B | **21,04%** | **28/32** | Chữ tốt nhất trong ba cấu hình đã đo; còn một timeout và ba lỗi chia audio |
| Qwen 0.6B | **22,00%** | **28/32** | Gần 1.7B trên meeting, dùng ít VRAM hơn; cùng bốn clip chưa hoàn tất |
| Faster-Whisper large-v3, word | **36,74%** | **32/32** | Hoàn tất recognition đủ corpus; lỗi timing cũ ghi riêng |
| Faster-Whisper large-v3, sentence | **36,78%** | **32/32** | Có biên câu native; chữ gần như word mode, chưa cải thiện quality |

Về timestamp trong app: Faster-Whisper có sentence/word timing; Qwen 0.6B/1.7B
nhận dạng text và cần ForcedAligner để tạo thời gian. API tùy model/profile:
Whisper có timed response, một số model transcription chỉ có text. Không phải
mọi model có timestamp native hoặc dùng được cho phụ đề ngay khi nhận dạng xong.

Trong report S6, trường `completed_valid_stage_output=5` của Faster-Whisper là
output **qua timing**, không phải số transcript nhận dạng thành công. Không dùng
trường đó để mô tả reliability speech-to-text; recognition có text ở 32 clip.

Clip user 60 s: CER chẩn đoán cũ Qwen 1.7B **6,38%**, Faster-Whisper **7,45%**,
Qwen 0.6B **12,77%**. Reference này là bản chép caption đã có, chưa kiểm định audio
độc lập; không dùng một clip để tuyên bố chất lượng mọi phim/phương ngữ.

Tốc độ trên RTX 5070 12 GB của lượt đo:

- 28 clip Qwen hoàn tất dài 105–150 s: median thời gian mỗi clip sau bước load
  là **17,032 s (1.7B)** và **17,008 s (0.6B)**. Chênh lệch này quá nhỏ để kết
  luận model nào nhanh hơn. Thời gian gồm điều phối/chunk, chưa phải kernel-only.
- Peak CUDA allocated trong receipt load: **4.698.543.616 byte (1.7B)** và
  **1.876.073.984 byte (0.6B)**; đây không phải toàn bộ VRAM/NVML của máy.
- Wall time batch Qwen 1.7B khoảng **689,4 s**, 0.6B **706,7 s**; Faster-Whisper
  word **1.365,8 s**. Batch Qwen có failure/restart, còn FWW gồm word timestamp;
  không lấy tỷ số này làm speedup recognition thuần hoặc dự báo tốc độ máy khác.
- Stress 26,23 phút: Qwen chưa hoàn tất; Faster-Whisper có text nhưng CER thô
  **64,94%**, có đuôi chưa nhãn. Có output chưa chứng minh ít bỏ lời trên file dài.

**Ứng viên ưu tiên cho máy hiện tại: Qwen 1.7B.** Chọn 0.6B khi cần ít VRAM hơn;
giữ Faster-Whisper large-v3 như lựa chọn có sentence timing và đã hoàn tất nhiều
file hơn. Đây là suy luận từ benchmark local, chưa đổi default của app.
SenseVoice/Parakeet/OmniASR/FireRed/head JazerJu chưa có phép so recognition tương
đương; không xếp hạng bằng coverage tokenizer. Community-1 là model người nói,
không phải model nhận dạng chữ; giữ báo cáo speaker riêng.

## Kế hoạch thực hiện theo thứ tự

### 1. Bảo toàn transcript, tách xuất TXT — đã sửa source

Phạm vi và hành vi như trên. Regression offline kiểm tra TXT không gọi aligner,
aligner thiếu vẫn giữ đủ text, không ghi đè TXT cũ, hủy/incomplete không thành
success, pipeline không tiếp tục khi thiếu timed subtitle.

Validation: **226 test local ASR/CLI/UI pass / 17,44 s**, trong đó 13 case mới.
Ruff/pyright app pass sau sửa import ordering. Chỉnh UI cuối bỏ modal timing
cho standalone recovery: **5 case pass / 2,36 s**; kiểm tra thêm task chạy lại
không giữ `ASRData` cũ. Không full
suite, tải weight, acoustic inference, API, build hoặc GUI EXE mới ở lượt này.
EXE TimingGuard cũ chưa chứa thay đổi; chưa gọi phiên bản đóng gói đã được sửa.
Việc này xử lý mất/chặn kết quả chữ khi aligner lỗi; **chưa sửa được Qwen timing
câu/đoạn để mọi input xuất SRT thành công**.

### 2. Timestamp câu/đoạn cho workflow phụ đề — ưu tiên kế tiếp

- Giữ nguyên yêu cầu interval dương, đúng media và text đầy đủ cho mỗi cue. LLM
  nhận text cùng start/end có nguồn từ audio; không được đặt giờ mới theo tốc độ
  đọc, chia đều duration hoặc tự đoán từ text.
- Tách kiểm tra timing câu khỏi timing từng chữ: internal word timing lỗi không
  tự động chứng minh cả biên câu sai. Cần thiết kế quy tắc lấy biên câu có cơ sở,
  lưu provenance/raw và chặn biên câu sai; không chỉ gom min/max để giấu outlier.
- Kiểm tra quy tắc mới bằng raw đã lưu trên clip user và các mẫu meeting có lỗi
  khác nhau trước; chỉ inference khi có thay đổi acoustic thực sự cần đo. Nếu
  chưa có biên đáng tin, giữ TXT/review và báo timed output chưa hoàn tất.
- Faster-Whisper sentence là đường có timing hiện tại; không tự chuyển engine
  hoặc lấy giờ của transcript khác gắn vào chữ Qwen mà chưa đối chiếu audio/text.
- Gate: chọn xuất SRT → có đủ text và timing câu/đoạn hợp lệ → chuyển nguyên dữ
  liệu cho LLM. Không tính TXT recovery thành pass của gate này. Word timestamp
  chỉ là yêu cầu riêng khi tính năng thật sự cần độ chi tiết đó.

### 3. Tự chuẩn bị model khi bắt đầu nhận dạng

- Xây `ensure selected model` trong core, dùng chung GUI/CLI. Chỉ tải model đang
  chọn và dependency cần cho tác vụ; TXT Qwen không kéo aligner hoặc Community-1.
  Mở settings chỉ hiển thị trạng thái. Lần sau dùng lại bản đã có.
- Dùng revision/hash cố định và kiểm tra file hoàn chỉnh; tải vào vị trí tạm do
  task sở hữu rồi activate. Không ghi đè runtime đang dùng. Có lock chống hai job
  cùng cài, báo dung lượng/tiến độ, hủy được và tiếp tục tải dở an toàn.
- Dùng runtime Python riêng theo recipe hiện có; không cài global hoặc đổi Qt
  dependencies. Thiếu `uv`/Python/GPU được báo trước khi nhận dạng.
- GUI bấm bắt đầu sẽ chuẩn bị model rồi tự tiếp tục đúng file/cấu hình đã chụp.
  Faster-Whisper dùng đúng executable/model directory được chọn. Không tự đổi model
  do lỗi tải/OOM. Community-1 chỉ tải khi user bật và cung cấp quyền/token hợp lệ.
- Gate: máy chưa có model → tải → nhận dạng; lần hai không tải; mất mạng/hủy/
  thiếu disk/file hỏng không thành ready. Kiểm tra bằng fixture tải nhỏ trước,
  một lượt tải thật chỉ khi cần xác minh tích hợp và chưa có model phù hợp tại máy.

### 4. File dài và tốc độ — giải quyết lỗi có sẵn

- Tách policy chia audio nhận dạng khỏi yêu cầu cửa sổ của aligner. Xử lý việc
  không tìm được khoảng lặng mà vẫn giữ đủ sample/lời nói; chọn cách chia từ đặc
  tính model/audio, không sửa text hoặc ghép chữ theo kết quả mong muốn.
- Xử lý timeout/EOS của job dài, giữ chunk đã hoàn tất, trạng thái phần thiếu rõ
  ràng, resume không inference lại chunk thành công. Không công bố partial là complete.
- Chỉ đo lại ba clip lỗi chia audio, một timeout và stress sau thay đổi liên quan;
  không lặp nguyên corpus để tích số pass. Giữ điểm cũ và mới riêng.
- Báo cold load, recognition, speaker và export riêng. Mục tiêu đề xuất trên máy
  hiện tại: nhận dạng sau load nhanh hơn audio ít nhất 4 lần (RTF ≤ 0,25), cold
  start hiển thị riêng; đây là mục tiêu, chưa là SLA đã đạt. Ưu tiên loại bỏ stage
  không cần cho TXT trước khi thay model/precision hoặc giữ GPU qua nhiều job.

### 5. Người nói tùy chọn

- Bật riêng sau khi recognition cơ bản ổn định; lỗi/thiếu model người nói không
  làm mất transcript. Giữ label ẩn danh, không đoán tên/quan hệ/xưng hô.
- Nếu chưa có timing để gắn text, trả track người nói riêng hoặc trạng thái chưa
  gắn; không giả gán từng chữ. Thiết kế nhận dạng theo turn cần phép đo riêng trên
  các mẫu overlap/returning speaker đã có trước khi chọn cho sản phẩm.
- Dùng evidence Community-1 cũ làm baseline; DER 20,66% không collar và 14,90%
  với collar 250 ms chưa đồng nghĩa speaker attribution của transcript đã đúng.

### 6. Đóng gói và nghiệm thu sản phẩm

- Sau khi bước 2–4 ổn: build onedir tên mới từ spec duy nhất; giữ artifact cũ.
- Từ EXE mới: chọn file → tự chuẩn bị model → TXT Qwen; Faster-Whisper sentence
  → SRT; hủy và mở lại. Bật người nói là phép thử riêng khi model ready.
- Xác nhận transcript đầy đủ, lỗi nhận dạng/speed trên phạm vi đã đo, output mở
  được và không mất dữ liệu. Không yêu cầu raw timestamp từng chữ của Qwen phải
  qua gate mới công nhận speech-to-text. SRT/render vẫn cần timing hợp lệ.
- Giữ dịch LLM hiện tại; không làm thêm benchmark dịch, tìm key cũ hoặc đổi route.
  Chỉ kiểm tra chuyển tiếp output đúng khi cần cho app. OCR chưa triển khai trong plan này.

## Giới hạn kiểm tra và file thay đổi

Mỗi lần chạy phải trả lời lỗi mới hoặc xác nhận code đã thay đổi. Kế thừa các
benchmark/EXE gate cũ; không tiếp tục preflight CTC hoặc sweep dtype/window theo
chuỗi audit trước khi chưa có nhu cầu sản phẩm cụ thể.

Code lượt này: `core/asr/api_transcription.py`, `core/asr/local/pipeline.py`,
`core/asr/transcribe.py`, `core/entities.py`, `cli/commands/transcribe.py`,
`ui/thread/transcript_thread.py`, `ui/view/transcription_interface.py` dưới
`videocaptioner/`; ba file `test_qwen_text_result.py` ở `tests/test_asr`,
`tests/test_cli`, `tests/test_ui`. Tài liệu: plan này, README, status và prompt
bàn giao. Giữ toàn bộ các thay đổi tài liệu audit trước. User sau đó yêu cầu
submit/push snapshot bàn giao chứa plan này; quyền đó không áp dụng cho thay đổi
mới của phiên tiếp theo. Các ghi chú chưa commit ở lịch sử là trạng thái lúc đo.
