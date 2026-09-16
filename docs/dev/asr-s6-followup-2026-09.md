# Sau S6 — sentence mode và ứng viên CTC

**ASR chưa hoàn tất nghiệm thu; OCR vẫn dừng.** Lượt này tiếp tục từ `63941a8`,
giữ toàn bộ thay đổi chưa commit và artifact S6-Review. Không chọn default mới,
commit/push, gọi lại API đã đo hoặc thay model/runtime đang cài.

Evidence mới nằm dưới job S6 cũ: `s6-followup-20260908-204000/`. Các report trước
đó giữ nguyên. [Báo cáo S6 trước](asr-s6-results-2026-09.md) vẫn là nguồn cho benchmark
word mode/Qwen cũ, DER và frozen workflow.

## Phạm vi phép đo mới

- User giải phóng GPU sau khi preflight thấy khoảng 11/12 GB đang dùng bởi tác vụ khác.
  Agent không đóng ứng dụng của user. Chỉ dispatch khi có hơn 5 GB VRAM trống;
  Faster-Whisper và pilot CTC chạy tuần tự.
- Dùng lại 31 clip AliMeeting chưa đo sentence và bài stress 26,2308 phút. Clip
  `R8007_M8011-c03` dùng kết quả frozen cũ, không inference lại. Không chép hoặc tải lại
  archive/audio. Kiểm tra hash/mtime của input riêng với trạng thái inference.
- Faster-Whisper large-v3, CUDA/float16, VAD `silero_v4_fw`, threshold 0,4, padding
  900 ms; `--one_word 0 --sentence`, width 30. Command được tạo bởi engine source
  hiện tại. Đây là batch engine với cấu hình sentence, không phải 32 lệnh EXE/GUI
  trọn pipeline. Không gán identity bằng fixture rồi gọi đó là auto-binding.
- Một lỗi setup helper dùng nhầm phép truy cập Path xảy ra trước dispatch, 0 inference.
  Receipt giữ ở `sentence/setup-failure.json`; lượt thật ở `sentence-run02/` riêng.

## Kết quả sentence và stress

| Phạm vi | Kết quả |
| --- | --- |
| 32 clip, gồm một output frozen kế thừa | 1.093 cue; **31/32** clip có mọi interval dương/trong bounds; không overlap cue liền kề |
| CER cùng 28 clip so sánh Qwen | **36,78%** (6.405 / 17.413); word mode cũ **36,74%**, không cải thiện chữ đáng kể |
| CER đủ 32 clip | **40,53%** (8.701 / 21.469); giữ script/case/numbers/overlap, không phải cpCER |
| Timing ở biên câu đo được | 35/1.673 utterance (**2,09%** coverage), median **185 ms**, p95 **530 ms** |
| Độ đọc của cue | 55 cue một ký tự lexical; 100 cue dưới 500 ms; sáu cue không giao vùng utterance tham chiếu cần review |
| Stress 26,2308 phút | Có 617 cue, tất cả interval dương/trong bounds; 4.784 ký tự hypothesis so với 10.715 ký tự reference |

Phần timing chỉ chấm full utterance khớp duy nhất, đúng biên cue native, không nội suy.
Tập này khác 30 utterance ở word mode cũ; không dùng 185 ms so với 310 ms để tuyên bố
cải thiện trên cùng tập. Cue ngoài vùng nhãn chỉ là ứng viên review, chưa là nhãn
hallucination được kiểm tra độc lập.

Stress có CER thô **64,94%**; đuôi **22.897 ms** chưa có nhãn nên điểm full hypothesis
không phải chất lượng toàn audio đã nghiệm thu. **Pass tạo output/interval, chưa pass
chất lượng stress hoặc pipeline sản phẩm.** Kết quả Qwen stress cũ vẫn fail riêng.
Batch process **exit 0 / 1.949,984 s**, RSS đỉnh **3.645.988.864 byte**; đây là tổng
31 clip mới + stress, không có thời gian độc lập từng clip và không so tốc độ thuần model.

Cue thứ ba của `R8008_M8013-c04` là **10.870 → 10.870 ms**. Raw giữ nguyên; không bỏ
cue đó hoặc kéo dài để đổi tỷ lệ 31/32 thành 32/32. Xem `sentence-score/summary.json`,
`per-clip.json` và `sentence-run02/input-verification.json` (64 file input/reference
giữ hash/mtime).

## Alignment thay thế

[Contract CTC](asr-ctc-candidate-2026-09.md) đã được viết trước download/inference.
SenseVoiceSmall có nguyên ký tự của 91 mẫu preflight; các head wav2vec2/MMS được
kiểm tra vẫn thiếu coverage. Weight 936.291.369 byte đã khớp SHA-256; một bản riêng
trong evidence, không cài package hoặc cập nhật runtime project.

Pilot dùng encoder theo nguồn pin, CTC log-probability nguyên bản và decoder CTC
torchaudio 2.8; target trực tiếp từng ký tự nguyên script. Lưới native 60 ms, origin
−30 ms được chốt trước inference, không clamp hoặc kéo blank vào chữ. Lưu emissions,
frame path và raw span trước strict/audio validation. Mốc hình học dương không chứng
minh acoustic timing đúng. Nhãn TextGrid chỉ cho phép chấm biên utterance phù hợp.

Pilot load strict đủ **917 tensor / 233.999.167 parameter**, worker **5,312 s** gồm
load **2,625 s** (không gồm Python import), host process **exit 0 / 9,0 s**;
VRAM allocated peak **1.167.120.384 byte**. Raw gồm tám acoustic chunk, tính cả
negative control; không phải benchmark tốc độ với Qwen/Faster-Whisper.

| Input pilot | Strict / RMS | Chẩn đoán acoustic |
| --- | --- | --- |
| Phồn thể, 13 ký tự | Đều qua guard | Chỉ 9/13 target có frame argmax hỗ trợ; bốn chữ phồn thể có log-probability thấp, native greedy dùng giản thể |
| Clip user 60 s, transcript Qwen 94 ký tự | Đều qua guard | Native greedy chỉ ra hai ký tự; **99,8%** frame chọn blank, chỉ **2/94** target có frame argmax hỗ trợ |
| Meeting `R8001_M8004-c01`, năm chunk Qwen cũ | Strict 4/5; cả strict + RMS chỉ 1/5 | Một raw span **−30 → 30 ms**; ba chunk khác có chữ rơi vào vùng RMS ≤ 32 |
| Silence control, 13 target | Strict qua, RMS chặn | 0/13 target có frame argmax hỗ trợ |

**Không nghiệm thu acoustic alignment, không tích hợp backend.** CTC constrained
path vẫn đặt được chữ vào interval có âm lượng nhạc nền; kết quả này cho thấy phải
tách structural/RMS pass khỏi bằng chứng nhận diện từng chữ. Không đặt threshold
confidence tùy ý sau kết quả để vượt gate; không đổi giản/phồn thể hoặc frame origin.
`ctc-acoustic-diagnostic.json` chỉ đọc emissions đã lưu, không inference lại.

Preflight cho giả thuyết chia ngắn hơn phát hiện hai transcript speech-gap cũ không
khớp lexical hoàn toàn với transcript Qwen nguyên 60 s. **Chưa chạy thử ngắn mới**;
không nhầm việc chuẩn bị giả thuyết với một phép so chỉ thay chunking đã pass.

## Tên/số và reference tiếng Việt

Đã chọn 21 nhãn từ reference của chín clip: 17 số/đơn vị và bốn tên riêng/nền tảng/
công ty/lễ hội. Giữ index utterance, speaker label, vị trí ký tự và hash reference.
Chưa có nhãn danh tính nhân vật phim hoặc quan hệ xưng hô được xác nhận.

Phép dò literal trên toàn transcript cùng clip thấy Qwen 0.6B/1.7B có 17/18 nhãn
có output; ba nhãn không chấm vì recognition chưa hoàn tất. Faster-Whisper word và
sentence cùng 13/21 nhãn hiện đúng dạng chữ. **Đây không phải entity accuracy**:
có thể trùng ở utterance khác và chưa chấm speaker/location của entity.

Rà soát các cờ vắng chữ: sáu trường hợp Faster-Whisper dùng chữ số 11/8/9/150/20
với cùng giá trị tham chiếu; không gọi đó là sáu lỗi giá trị số. Một trường hợp lược
đơn vị ngày nhưng đoạn sau vẫn nói một tháng, một tên nền tảng không có trong
transcript. Giữ CER lexical nguyên cách chấm; không đổi script trong ASR/alignment
để xóa lỗi. Xem `entity-labels.json`, `entity-presence-diagnostic.json` và
`entity-manual-review.json`.

`translation-reference-rubric.json` có bản Việt tham khảo và checklist nghĩa cho
đúng 12 cue reference đã chuẩn bị: giữ quan điểm đối lập, phủ định, câu hỏi xác nhận,
màu xanh dương/vàng, tuổi và chức năng chụp ảnh; không đoán quan hệ nhân vật. Đây là
**rubric agent soạn, chưa được kiểm định độc lập**, không output gateway, không đưa
vào translation cache. Lượt gateway reference vẫn `cancelled-no-key`, **0 request**.
Endpoint/model/timeout/scope còn hiệu lực: VideoCaptioner gateway, gpt-5.6-terra,
300 s/request, tối đa ba request, không upload audio.

## Guard ứng dụng và EXE mới

`FasterWhisperASR._make_segments()` nay chặn `start >= end` trước cả lọc marker,
ở cả sentence/word mode. Lỗi dừng toàn kết quả; không trả prefix hoặc xóa cue để
publish. Không thay model, timerange còn lại, cache key/cache user hoặc policy CTC.
Đây chỉ là guard interval không dương, không tuyên bố đã kiểm định mọi lỗi timing
của Faster-Whisper. Thêm `tests/test_asr/test_faster_whisper_timing.py`.

- Regression **6 fail + 2 pass → 8 pass**; ASR/CLI **595 pass / 13 deselect / 43,80 s**.
- Ruff pass. Pyright **0 error / 0 warning**, 220 file, 9,281 s khi trỏ đúng Python
  đã cài của project. Lượt đầu chọn nhầm `.venv` không tồn tại ở checkout nên báo
  thiếu dependency; không đổi package để xử lý lỗi môi trường này.
- Không lặp full offline, translation sync hoặc online/media inference sau guard;
  không có thay đổi translation, dependency, runtime resource hoặc backend CTC trong app.

Artifact mới: **`dist/VideoCaptioner-ASR-S6-TimingGuard-20260908/`**, nguyên onedir.

1. PyInstaller từ spec duy nhất: **exit 0 / 215,141 s**, sáu warning optional/platform,
   không error, sáu upstream SyntaxWarning. **218 module/PYZ khớp** source.
2. EXE **31.164.833 byte**, local **2026-09-08 21:32:15**, SHA-256
   **cdfecfafe7009129e2446923ddbe515db8b121b06f2b72808031ee2ccb4a093a**.
   Onedir **575 file / 237.665.905 byte**; bản gốc giữ nguyên sau test.
3. GUI trên bản sao artifact đã so hash: sống **25,594 s**, WM_CLOSE đúng PID,
   **exit 0**. Bản copy/app data test ở `timing-guard-build/smoke-copy/`, không dùng
   AppData thật hoặc junction cũ bị chặn dọn.
4. Frozen replay bằng executable fixture tường minh: raw zero-duration ở sentence
   **exit 5 / 6,0 s**, word **exit 5 / 5,797 s**, đều không output. Raw hợp lệ
   **exit 0 / 5,625 s**, giữ nguyên 22 cue/text/timing. **Ba replay, 0 model inference,
   0 API request**; không tính fixture này thành workflow model/online mới trên EXE.

## Giới hạn còn mở

Chưa có ground truth từng chữ, chấm xưng hô theo quan hệ đã xác nhận, phút sửa tay
hoặc độ phủ thể loại/phương ngữ đầy đủ. Meeting corpus không thay thế phim. Pilot
alignment chưa được tích hợp vào app hoặc EXE; build/offline/API cũ không tự chứng
minh ứng viên mới. Giữ raw lỗi và điểm trước/sau, không dùng transcript complete
làm đồng nghĩa với timing/quality pass.
