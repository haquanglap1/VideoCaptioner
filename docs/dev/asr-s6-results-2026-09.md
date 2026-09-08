# S6 — kết quả đo ASR, 2026-09-08

Lượt tiếp sau báo cáo này đã đo sentence/stress, pilot CTC và sửa guard interval:
đọc [kết quả sau S6](asr-s6-followup-2026-09.md). Các số bên dưới giữ nguyên tập và
thời điểm đo cũ; artifact mới nhất là TimingGuard trong báo cáo tiếp nối.

**Chưa đạt nghiệm thu sản phẩm; OCR vẫn tạm dừng.** Đã đo bộ local, sửa các lỗi ứng
dụng tìm được và kiểm tra EXE. Không đánh dấu model căn thời gian đã đạt từ unit test,
không tự đổi engine mặc định, commit/push hoặc bỏ các mục chưa có bằng chứng.

## Dữ liệu và cách chấm

User chọn **corpus công khai + clip hiện có**. AliMeeting Eval lấy từ
[OpenSLR 119](https://www.openslr.org/119/), CC BY-SA 4.0. Lưu một archive dùng chung
dưới `build/asr-session-evidence/datasets/AliMeeting-Eval/`; không bung cả bộ nhiều GB.
Archive **3.673.718.355 byte**, SHA-256
**dc47343b2474b5ebcf458927e878155f6ddeb59c85e685b3645c32a1f9578d92**.
CRC64 **5690990898831359168** khớp header OSS, gzip integrity pass. Giả định ban đầu
về multipart ETag không đúng; không tải lại dữ liệu, đã kiểm tra bằng CRC64 đúng theo
[tài liệu OSS](https://www.alibabacloud.com/help/en/oss/user-guide/data-verification).

- **32 clip / 66,9079 phút**, từ tám bản ghi; 21.469 ký tự tham chiếu, 1.673 utterance.
- Kênh đầu của far-field microphone, PCM16 mono/16 kHz; không average tám kênh,
  denoise hoặc sửa chữ. Cửa sổ 105–150 s không cắt utterance tham chiếu.
- 16 clip có bốn speaker, bốn clip có ba speaker, 12 clip có hai speaker.
  Nói chồng chiếm **20,53% thời gian có lời nói**; giữ overlap khi chấm.
- TextGrid kết thúc ở cuối vùng gán nhãn, có thể sớm hơn audio. Không shift/scale
  nhãn để ép duration bằng nhau. Stress giữ full audio, đánh dấu đuôi ngoài vùng nhãn.
- CER bỏ punctuation/annotation markup đã biết; giữ script, chữ hoa/thường và số.
  Reference nối theo thời gian, **không phải cpCER chính thức của AliMeeting**.
  CER chỉ có giá trị trong phạm vi chính sách này và thể loại meeting đã đo.

Máy đo: RTX 5070 12 GB, driver 616.64; Ryzen AI 9 HX 370, 12 core/24 thread;
Python 3.12.13, Windows. Các model trong job chạy tuần tự trên GPU. Đây là benchmark
engine từ source; không nhầm với một lệnh GUI/EXE chạy trọn toàn pipeline 32 clip.

## Nhận dạng và timing

Hai Qwen dùng cấu hình ứng viên chunk tối đa 30 s, cắt ở khoảng lặng theo policy hiện
có; không đổi default 120 s của app. Faster-Whisper dùng large-v3 đã cài, CUDA/float16,
VAD `silero_v4_fw` ở 0,4, padding mặc định 900 ms, không prompt/denoise.

| Engine | Có transcript đầy đủ | CER trên cùng 28 clip | Gate timing |
| --- | --- | --- | --- |
| Qwen 0.6B | 28/32 | **22,00%** | Strict aligner: **0/28 đạt**; bốn clip không vào alignment vì recognition chưa xong |
| Qwen 1.7B | 28/32 | **21,04%** | Strict aligner: **0/28 đạt**; bốn clip không vào alignment |
| Faster-Whisper large-v3 | 32/32 | **36,74%** | Native word SRT: **5/32 có toàn bộ interval hợp lệ**; 27 clip có interval cần review |

Cùng bốn clip bị loại ở hai Qwen: một timeout 180 s, ba clip không tìm được khoảng
lặng phù hợp để chia 30 s. Tập 28 clip chung chỉ chứa **81,11% ký tự tham chiếu**;
không tính các clip thiếu output thành CER 0. CER Faster-Whisper trên đủ 32 clip là
**40,48%**, khác phạm vi so sánh chung phía trên.

Wall time gồm kiểm tra/load/điều phối của batch: Qwen 0.6B **706,703 s**, Qwen 1.7B
**689,391 s**; process Faster-Whisper **1.365,828 s**. Hai Qwen có một lần khởi động lại
runtime cho các clip độc lập sau timeout, không retry clip thất bại. Không lấy các số
này làm phép so tốc độ thuần model hoặc tính chi phí trên các phút audio chưa xử lý.

Timing đo được trên **30 utterance khớp text duy nhất**, thuộc năm clip Faster-Whisper
có word timing hợp lệ: median lỗi đầu/cuối **310 ms**, p95 **680 ms** (nearest-rank).
Coverage chỉ 30/1.673 utterance toàn corpus; đây không phải nghiệm thu timing toàn bộ
video, cũng không phải nhãn chuẩn cho từng chữ. Bộ chấm không nội suy điểm nằm giữa word.

## Diarization và sửa cửa sổ cuối

Trước sửa, 21/32 response qua kiểm tra giới hạn media; 11 response có span kéo dài
**9–379 ms** vào vùng đệm cuối. Đã đối chiếu checkpoint bằng cách đọc metadata pickle
không thực thi và đọc code runtime: segmentation window 10 s, bước 10% = 1 s,
`skip_aggregation=True`, cửa sổ cuối được zero-pad.

Adapter mới kiểm tra span theo **cửa sổ phân tích hữu hạn của model**, tính từ số mẫu
PCM, kể cả input ngắn hơn 10 s và phần dư dưới 1 ms. Raw span giữ nguyên; association
chỉ lấy giao với cue nguồn đã hợp lệ trong media. Không đổi timestamp từ/cue, không
clamp/swap/interpolate/drop token, không đổi ngưỡng coverage 80%, không sửa runtime/model.
Policy metadata/cache: `overlap-conservative-model-window-v2`.

Replay cùng raw cũ: **32/32 được tiếp nhận** theo model window. Với reference cues
dùng riêng để kiểm tra association: 691 assigned, 927 overlap, 24 unknown, 31 ambiguous.
Đây không phải kết quả speaker của ASR đầu-cuối, và assigned không đồng nghĩa đúng danh tính.

Chấm raw bằng pyannote.metrics trong UEM của audio, giữ overlap: DER **20,66%** không
collar; **14,90%** với collar tổng 250 ms quanh biên. Raw không bị sửa để chấm hoặc
publish. Không coi speaker accuracy hoặc xưng hô đã đạt chỉ từ các số này.

## Stress và clip của user

- Public stress **26,2308 phút**: Qwen 1.7B/chunk 120 s **exit 5 / 443,969 s**,
  inference failure, chưa output/review. Cache giữ bốn chunk đã xong; vùng lỗi
  464,2–581,65 s. Thử riêng vùng đó ở chunk 30 s: 5/5 recognition xong trong 31,813 s
  gồm load, chưa alignment. Không gọi toàn bài stress đã pass.
- Clip user: 60 s đầu của video 111,333 s, resolve đường dẫn gốc từ evidence đã có.
  Qwen 1.7B còn sáu vị trí timing lỗi như 0.6B. RMS chunk 30 s không tìm được khoảng
  ngắt; thử hai chunk tại gap âm thanh Community-1 đã đo (29.013 ms) vẫn fail strict
  ở cả hai chunk. Giữ raw/review, không triển khai fallback này vào app.
- Giảm riêng VAD padding Faster-Whisper 900 → 100 ms không cải thiện rõ, còn đổi chữ;
  giữ preset. Không lấy khoảng xuất hiện caption hình ảnh làm acoustic timing.

Đối chiếu text đã lưu với bản chép caption có sẵn của agent (94 ký tự, không phải
nhãn audio độc lập): Qwen 0.6B **12 lỗi / 12,77% CER**, Qwen 1.7B **6 / 6,38%**,
Faster-Whisper **7 / 7,45%**. Thử speech-gap vẫn 6 / 6,38%. Không đọc ảnh hoặc suy
timing mới để tính những số này. Reference có hai dấu hỏi, các bản ASR chỉ có một;
CER lexical không phản ánh lỗi câu hỏi thành câu khẳng định này.

Rà soát chín cặp ASR→Việt đã có: bản dịch nhìn chung đi theo input ASR, nhưng truyền
tiếp lỗi tước hiệu, thuật ngữ sinh vật, sắc thái câu hỏi và ý bị níu lại thành được
đồng hành. Không lấy tính đầy đủ của response làm bằng chứng bản Việt đúng với video.

## Những lỗi ứng dụng đã sửa

- LLM response còn thiếu/sai sau ba lần phải fail batch; không điền source rồi cache
  như dịch thành công. Namespace cache `complete-llm-response-v1`, không xóa cache user.
- Gom cue trước local speaker association khi chỉ có tối đa một speaker trong toàn
  khoảng nối. Replay clip user: 30 → 9 cue, 15 → 0 cue một chữ; word mode, context,
  bản dịch, token IDs, override và timestamp gốc giữ nguyên. Không nối qua người nói.
- Xử lý model window của Community-1 như trên, giữ validation riêng cho cue nguồn.
- CLI `transcribe`/`process` nhận `--asr faster-whisper`, `--fw-program`,
  `--fw-model-dir`, `--fw-model`, `--fw-device`. Tôn trọng executable được chọn,
  không âm thầm thay bằng binary khác trên PATH; không đổi dependency.
- `process --no-split` không yêu cầu word timestamp chỉ để dịch/optimize.
  Faster-Whisper sentence timing không bị bước điều chỉnh display timing cũ dịch biên.

## Validation và EXE

Full offline sau sửa model window: **1.187 pass / 5 skip / 51 deselect / 114,72 s**.
Sau sửa cuối chỉ giữ nguyên biên native Faster-Whisper: regression **red → green**,
toàn ASR/CLI **587 pass / 13 deselect / 38,88 s**. Ruff pass, pyright 0/0, translations
sync. Skip giữ QtMultimedia offscreen/TTS/service; không tính thành online pass.

Artifact cuối: **`dist/VideoCaptioner-ASR-S6-Review-20260908/`**, nguyên onedir.

1. Spec duy nhất; PyInstaller **exit 0 / 208,719 s**, sáu warning optional/platform,
   0 error, sáu upstream SyntaxWarning; **218 module/PYZ khớp source**.
2. EXE **31.164.611 byte**, local **2026-09-08 19:28:13**, SHA-256
   **c9604ea57d8e34bfb267f5191ec6b719e5cb72eec206d4d4d2a483d51e730426**.
   Onedir **575 file / 237.665.683 byte**. Artifact gốc giữ nguyên sau kiểm thử.
3. GUI sống **25,844 s**, đóng đúng PID bằng WM_CLOSE, **exit 0**.
4. EXE `process` trên WAV user: native Faster-Whisper → dịch replay → SRT Việt:
   **exit 0 / 29,25 s / 9 cue**. Quan sát child dùng `--one_word 0 --sentence` và
   model directory đúng khi executable directory không có trên PATH. Dịch chỉ replay
   bản gateway đã đo trước, khớp lexical source từng cue; **không inference LLM/API mới**.
   SRT Việt SHA-256 **26276d34db29d40af782f26a908052c1d6f5b94c60a7f3ad9fe09bdaef015347**
   giống hệt bản đã render/kiểm tra trước, nên không render lại để tích gate.

EXE thêm smoke ở clip `R8007_M8011-c03` từng có 23 word interval không dương:
sentence mode **exit 0 / 69,938 s**, 58 cue đều dương/trong bounds. Một clip này không
chứng minh sentence mode đã đạt cả corpus. Gắn identity từ đúng input được bảo vệ
trong fixture rồi chạy EXE `local-diarize`: **exit 0 / 31,219 s**, giữ 58 cue/text/timing/IDs
và identity; 17 assigned, 40 overlap, một ambiguous. Không giả đây là auto-binding
identity của nhánh Faster-Whisper hoặc nghiệm thu độ đúng speaker.

## Dịch online và phần còn thiếu

Job gateway cũ: **gpt-5.6-terra**, endpoint `https://api.videocaptioner.cn/v1`, timeout
300 s; 9 cue ASR thật, một request / 159,11 s, provider báo 11.190 token. Giữ đúng phạm vi
source/API gate này; lỗi chữ ASR còn truyền vào bản Việt. Key đã xóa cùng owner process.

Đã chuẩn bị phép đo riêng 12 câu reference Trung (384 ký tự, ba nhãn speaker). Ô key
kín kết thúc chưa có key: **0 request**, chưa có bản Việt hoặc điểm chất lượng cho
phép đo đó. Không xin Scribe vì user đã loại khỏi scope, không đổi model/route trả phí.

Còn thiếu để khép nghiệm thu: phương án timing thay thế cho Qwen được đo thật; nhãn
tên/số, chất lượng dịch/xưng hô có reference phù hợp, phút sửa tay; stress thành công;
độ phủ thể loại/phương ngữ. Meeting corpus và clip ngắn hiện có không tự thay các mục đó.
CTC preflight cũ thiếu ký tự trong vocab; chưa tải weight/inference, không dùng unknown,
đổi script hay bỏ chữ để lách thiếu coverage.

Evidence chính: `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`.
Xem `reports/s6-measurements.json`, `reports/model-window-replay.json`,
`reports/community-uem-diagnostic.json`, `s6/*/`, `s6-final-build/reports/`,
`s6-translation-reference/reports/`. Không lặp model/API/build gate đã pass khi chưa
có thay đổi hoặc giả thuyết mới. [Prompt tiếp tục ASR](asr-completion-next-session-prompt.md).

Đã chuyển 10 mục build/test tạm (1.824 file / 356.069.728 byte) vào Thùng rác;
source snapshot và diagnostics được nén/so hash trước đó. Giữ artifact và media.
Gỡ junction của `s6-final-build/smoke-app` bị bộ duyệt tự động chặn với thông báo
`blocked by policy`; host/link này còn nguyên. Không xóa artifact đích hoặc dùng lệnh
khác để vượt chặn. Đây không phải phần tải/inference còn chạy.

## File trong thay đổi chưa commit

- `videocaptioner/core/asr/`: `faster_whisper.py`, `transcribe.py`, `native_result.py`,
  `local/diarization.py`, `local/pipeline.py`, `local/profiles.py`.
- `videocaptioner/core/translate/llm_translator.py`.
- `videocaptioner/cli/`: `main.py`, `config.py`, `validators.py`,
  `commands/transcribe.py`, `commands/process.py`.
- `tests/`: `test_asr/test_acceptance_metrics.py`, `test_asr/test_diarized_cues.py`,
  `test_cli/test_faster_whisper_paths.py`, `test_translate/test_llm_completion.py`.
- `scripts/asr_acceptance.py`, `README.md`, `status.md`.
- `docs/dev/`: `asr-s6-results-2026-09.md`, `asr-completion-next-session-prompt.md`,
  `asr-implementation-2026-09.md`, `asr-vietnamese-next-session-prompt.md`,
  `ocr-next-session-prompt.md`; `docs/plans/video-subtitle-ocr-integration-plan.md`.
