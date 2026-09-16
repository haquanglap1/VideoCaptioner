# Audit tính tương đương của harness acoustic

**ASR chưa đạt nghiệm thu; OCR vẫn dừng.** Kế thừa kết quả
[4 × 15 giây](asr-ctc-segmentation-audit-2026-09.md), không chạy lại phép đo đó.

## Contract kiểm tra

Trước khi đề xuất acoustic inference mới, kiểm tra giả thuyết harness khác upstream:
frontend dùng torchaudio trực tiếp có tương đương `WavFrontend` đã pin hay không;
các định nghĩa encoder từ SenseVoice có khác bản FunASR cùng revision frontend hay
không. Chỉ đọc code công khai và tính feature trên CPU, **không load weight, chạy
encoder, tải model, đổi runtime hoặc tạo timestamp mới**.

- Nguồn FunASR pin `130e57a6fdb9661e2b0cc59199fb31ef81f2b9e9`; tải thêm tối đa
  hai file code nhỏ `funasr/utils/fbank.py`, `funasr/models/sense_voice/model.py`
  vào evidence riêng, giữ URL/hash. Không thực thi import/downloader của nguồn mới.
- Dùng lại PCM16/16 kHz đã giữ hash: user nguyên 60 giây và bốn lát 15 giây,
  phồn thể và năm chunk meeting của pilot. Thêm silence và dữ liệu synthetic để
  kiểm tra biên LFR. Không chuyển đổi media hoặc tạo bản sao audio.
- So feature của pipeline pilot với toàn lớp `WavFrontend` cũ bằng cùng dither 0;
  đầu vào lớp là PCM / 32768 và lớp nhân lại 32768. So thêm LFR với phép ghép frame
  bằng vòng lặp độc lập, gồm left/right padding. Giữ fbank, CMVN và lưới cũ.
- AST comparison bỏ docstring/decorator để tìm khác biệt thực thi. Bản sửa duy nhất
  được phép khi so là `nn.Module.__init__` của positional encoder đã ghi ở pilot;
  mọi khác biệt khác phải được báo, không sửa để ép parity.
- Giữ raw/emissions/report/helper cũ; output mới tạo độc quyền trong
  `VC-ASR-Completion-20260908-140534/s6-acoustic-parity-20260908/`. So hash/mtime
  input và source trước/sau. Một audit parity pass không là acoustic/ASR pass và
  không tự cho phép thêm backend/window sweep.

## Kết quả parity

**Không tìm thấy sai khác frontend để giải thích blank collapse.** Kiểm tra CPU
**54/54** trường hợp có feature khớp từng bit, sai số lớn nhất **0**: 12 trường hợp
PCM hiện có/silence và 42 độ dài synthetic quanh biên LFR. So riêng PCM scale,
LFR bằng vòng lặp độc lập, CMVN và độ dài output. Không load weight hoặc chạy encoder.
Process **exit 0 / 10,844 s**, phần tính/so feature **0,625 s**, stderr rỗng.

[Fbank wrapper của FunASR](https://github.com/modelscope/FunASR/blob/130e57a6fdb9661e2b0cc59199fb31ef81f2b9e9/funasr/utils/fbank.py)
gọi thẳng `torchaudio.compliance.kaldi.fbank` khi torchaudio có sẵn. So toàn lớp
`WavFrontend` ở dither 0 xác nhận các tham số và đường scale trong pilot tương
đương trên các input đã kiểm tra. Đây không phải hai thư viện fbank độc lập; LFR
có phép ghép frame độc lập để tránh chỉ so cùng một implementation với chính nó.
Dither 0 là lựa chọn tất định đã ghi trong contract pilot; không âm thầm đổi nó.

So AST bảy định nghĩa encoder: sáu khớp sau khi bỏ docstring/decorator và bỏ riêng
constructor positional đã sửa bookkeeping ở pilot. Khác biệt còn lại trong
[`SenseVoiceEncoderSmall.forward`](https://github.com/modelscope/FunASR/blob/130e57a6fdb9661e2b0cc59199fb31ef81f2b9e9/funasr/models/sense_voice/model.py)
là truyền `maxlen=xs_pad.shape[1]` cho sequence mask. Pilot chạy một input không
padding mỗi lần, nên độ dài tensor bằng `max(ilens)`; khác biệt này không thay
mask của những lần chạy đó. Giữ nguyên AST khác biệt trong report, không sửa code
để làm hai cây giống nhau. Weight repo không kèm `model.py`, nên đây là đối chiếu
hai nguồn upstream đã pin, không giả là code nằm trong checkpoint.

**Không dispatch acoustic mới từ audit này.** Parity không chứng minh model nghe
đúng, không xác định nguyên nhân duy nhất của collapse và không giải quyết yếu
acoustic ở chữ phồn thể. Kế thừa 37/94 support và các gate thất bại cũ; không đổi
threshold, prompt, script, timestamp, backend hoặc engine mặc định.

## Mở rộng nhãn số/đơn vị từ reference

Đọc reference của **32 clip**, dùng grammar tường minh cho số kèm đơn vị thời gian,
tiền, tuổi, độ dài hoặc tỷ lệ. Tìm **125 ứng viên ở 23 clip**; agent rà ngữ cảnh
reference trước khi đọc hypothesis để chấm. Các từ như “một chút”, “cùng nhau”,
“bánh trung thu”, lớp học và mã tuyến tàu không được tính nhầm thành số thời gian/tiền.
Giữ toàn bộ 46 mục ngoài phạm vi/chưa chấm cùng lý do; trong đó có một số tiền
ngập ngừng chưa xác định được giá trị, không âm thầm coi là không có entity.

Rubric đóng băng **79 nhãn tại 11 clip**, gồm 14 nhãn trùng bộ cũ và **65 vị trí
mới**. Sửa đúng hai span reference bị regex cắt ngắn để giữ phần thập phân chưa
xác định hoặc “hơn”; không sửa reference gốc. Thời gian/speaker của utterance chỉ
là provenance, không biến thành nhãn từng chữ hoặc speaker attribution của ASR.
Số trần, classifier-only, tên riêng và stress nằm ngoài grammar này: chưa đủ phạm
vi tên/số toàn corpus. Rubric do agent rà, chưa kiểm định âm thanh độc lập.

Giữ scorer cũ trên **mọi edit path tối thiểu**, không chọn tie theo match. Dạng
digits chỉ được chấp nhận bằng danh sách tường minh, giữ đơn vị; range/approximation
không tự đổi thành số đơn. Policy lexical cũ bỏ ký hiệu `%`, nên số phần trăm chỉ
còn digits không được tự tính thành tương đương hoặc lỗi giá trị. Đây là giới hạn
đã ghi **trước scoring**, không thay CER hay text/timing ASR để sửa số liệu.

| Engine | Tổng nhãn | Khớp tại vị trí | Khác / lược | Ambiguous | Recognition chưa đủ |
| --- | --- | --- | --- | --- | --- |
| Qwen 0.6B | 79 | 40 exact | 5 / 5 | 4 | 25 |
| Qwen 1.7B | 79 | 48 exact | 4 / 1 | 1 | 25 |
| Faster-Whisper word | 79 | 25 exact + 24 dạng digits | 2 / 8 | 20 | 0 |
| Faster-Whisper sentence | 79 | 24 exact + 24 dạng digits | 1 / 8 | 22 | 0 |

25 nhãn chưa chấm ở Qwen thuộc ba clip `R8007_M8010-c02/c03/c04` thiếu recognition
đầy đủ từ batch cũ. Không gọi Qwen lại hoặc chấm output một phần.

Trên **cùng 54 ID** có transcript đầy đủ ở cả bốn nhánh: Qwen 0.6B khớp **40**,
Qwen 1.7B **48**, Faster-Whisper word/sentence cùng **40**. Ambiguous lần lượt
**4 / 1 / 10 / 10**; phải giữ riêng, không biến thành pass hoặc mẫu đã chấm chắc chắn.
Không dùng tỷ lệ chỉ trên các nhãn định vị được như một phép so cùng mẫu.
Các nhãn lặp được giữ từng lần xuất hiện, không dò literal ở nơi khác để cộng điểm.

Đây là **đối chiếu văn bản trên rubric số/đơn vị xác định**, không phải độ chính xác
giá trị số, acoustic timing, speaker, xưng hô hay chất lượng ASR đã nghiệm thu.
Report 21 nhãn và bảng CER cũ giữ nguyên; không cộng hai bộ nhãn có phần giao nhau.

## Evidence và validation

Evidence mới: `s6-acoustic-parity-20260908/` trong job Completion cũ. Contract CPU
snapshot/hash trước audit; rubric số/reference/hash scorer snapshot trước scoring.

- `frontend-parity.json`, `encoder-ast-parity.json`, AST diff và
  `source-receipts.json`: hai code file mới tổng **46.109 byte**, không tải weight.
- `numeric-candidates-reference-only.json`, `numeric-contract-before-score.json`,
  `numeric-localization.json`: phân loại 125 ứng viên, 79 nhãn và mọi ambiguity.
- `audit-validation.json`: partition nhãn đầy đủ, mỗi engine chấm đúng cùng danh
  sách đã khóa; **67 file nguồn** giữ hash/mtime và **51 file được bảo vệ ở audit
  trước** còn khớp, gồm model/runtime/raw/audio. Các inventory có thể giao nhau,
  không cộng thành số file duy nhất. Scoring mới **5,45 s** wall time, không inference.
- **0 model inference, 0 API request.** Không thay code app, dev scorer/tests cũ,
  dependency, resource, runtime hay artifact. Kế thừa gate ASR/CLI 595 pass và EXE
  TimingGuard; không rerun test/static app/full/build/GUI để tăng số pass.

Vẫn cần giả thuyết acoustic có bằng chứng mới trước dispatch khác. Alignment
phồn thể, stress quality, nhãn tên/quan hệ xưng hô, phút sửa tay và genre/dialect còn
mở. Reference dịch chưa có key mới; giữ scope/endpoint/model cũ, không tìm credential.
