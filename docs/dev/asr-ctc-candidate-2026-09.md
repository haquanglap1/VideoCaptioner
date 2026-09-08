# Ứng viên alignment CTC sau S6

Đây là contract thử nghiệm, **chưa phải backend sản phẩm hoặc nghiệm thu timing**.
Giữ Qwen/ForcedAligner/Community-1 đang cài, engine mặc định và `strict-raw-v1`.
Không dùng OCR, đổi script, thay chữ đồng âm, unknown hoặc sửa timestamp sau suy luận.

## Preflight trước tải weight

Đã kiểm tra 91 mẫu: 32 reference AliMeeting, 56 transcript Qwen đã hoàn tất và ba
mẫu có sẵn (Qwen clip user, bản chép caption cũ, reference phồn thể). Reference caption
chỉ kiểm tra vocab; không cung cấp acoustic timing hoặc thay transcript ASR.

- SenseVoiceSmall: 25.055 piece, 25.052 piece thường; có nguyên ký tự lexical của
  cả 91 mẫu. Đây là kiểm tra tập ký tự, chưa phải điểm acoustic hay chất lượng.
- `wbbbbb/wav2vec2-large-chinese-zh-cn`: 5.169 mục; thiếu coverage.
- MMS-1b-all: kiểm tra riêng head `cmn-script_simplified` (4.495 mục) và
  `yue-script_traditional` (2.299 mục); cả hai thiếu coverage. Không gộp vocab/head
  hoặc dùng head Quảng Đông để giả nghiệm thu tiếng Quan thoại phồn thể.

Ứng viên chọn cho pilot: [FunAudioLLM/SenseVoiceSmall](https://huggingface.co/FunAudioLLM/SenseVoiceSmall),
revision `3847d57b6bdf2dd8875cb1508d2af43d80a16bf7`. Weight `model.pt`:
936.291.369 byte, SHA-256 `833ca2dcfdf8ec91bd4f31cfac36d6124e0c459074d5e909aec9cabe6204a3ea`.
Tokenizer SHA-256 `aa87f86064c3730d799ddf7af3c04659151102cba548bce325cf06ba4da4e6a8`.
Đã pin trước download; chỉ tải một bản vào evidence riêng.

Nguồn encoder: [SenseVoice `4482962`](https://github.com/FunAudioLLM/SenseVoice/blob/4482962437ce8ebd1f0ac5b6793d2f82d2e2955d/model.py),
SHA-256 `562fcc3b46246440a21578414509e8fa142e3bac913502abeeed122b9ac919ec`.
Nguồn frontend/tokenizer/CTC: [FunASR `130e57a`](https://github.com/modelscope/FunASR/tree/130e57a6fdb9661e2b0cc59199fb31ef81f2b9e9).
Giữ bản license và receipt cho từng file. Code SenseVoice có MIT; model card dẫn tới
`MODEL_LICENSE` riêng của FunASR, không gán license code cho weight.

## Contract pilot đóng băng trước inference

1. PCM16 mono 16 kHz từ đúng input đã giữ hash. Không denoise, tách giọng, time stretch
   hoặc cắt theo caption. Corpus dùng lại audio chunk/offset của recognition đã lưu;
   không gọi Qwen lại. Audio user chỉ 60 s đã được cho phép; phồn thể dùng mẫu cũ.
2. Acoustic encoder và CTC projection theo nguồn pin, load toàn bộ tensor với
   `strict=True`, không bỏ/mapping weight để ép load. Chạy riêng bằng Python 3.12,
   torch/torchaudio 2.8 đã có; không cài gói hoặc sửa runtime project.
3. Frontend 80 mel, Hamming 25 ms, hop 10 ms, LFR 7/6 và CMVN model. Chọn dither 0
   cho phép đo tất định. Prompt `zh`, `woitn`; bốn frame prompt loại khỏi acoustic
   sequence theo kiến trúc trước alignment. Cấu hình frontend này phải ghi trong raw.
4. Target là từng ký tự lexical nguyên bản, ánh xạ trực tiếp tới piece ID thường
   của CTC head; roundtrip phải giữ từng ký tự. Không áp SentencePiece normalization,
   đổi case/script, romanization, unknown, wildcard hoặc gộp hai character vào cùng
   interval. Punctuation được nối lại theo contract strict hiện tại, không đổi timing.
5. Dùng `log_softmax` acoustic chưa sửa và Viterbi CTC của torchaudio 2.8, blank ID 0.
   Giữ cả blank và frame path/raw log-probability; không zero/suppress blank, không
   phân phối khoảng blank vào chữ, không kéo dài span để dễ đọc. Nhánh timestamp sẵn
   có của SenseVoice có sửa blank và clamp nên không dùng làm kết quả thử nghiệm này.
6. Ánh xạ frame theo lưới native cố định: `start = first_frame * 60 - 30` ms,
   `end = (last_frame + 1) * 60 - 30` ms. Giữ cả giá trị âm/vượt audio nếu có;
   validator phải chặn. Không clamp, swap, interpolate, drop token hoặc chỉnh offset
   sau khi thấy kết quả. 60 ms là lưới emission, không phải sai số đã được nghiệm thu.
7. Lưu raw trước validation. Báo riêng: load/acoustic inference, lexical coverage,
   interval strict, kiểm tra năng lượng acoustic hiện có, confidence chưa hiệu chuẩn
   và timing trên full utterance khớp duy nhất ở đúng biên đo được. Nhãn utterance
   không biến thành ground truth từng chữ. Negative control silence phải giữ riêng.
8. Chỉ triển khai vào sản phẩm sau khi có bằng chứng phù hợp. Một đường CTC monotonic
   hợp lệ về hình học không chứng minh text đúng, speaker đúng hoặc timing đủ tốt.

Kiểm tra constructor bằng CPU trước inference tìm thấy `SinusoidalPositionEncoder`
trong nguồn pin không gọi `nn.Module.__init__`; `.eval()` lỗi thiếu `_modules`.
Pilot khởi tạo phần bookkeeping `nn.Module` cho class không có parameter này,
giữ nguyên hàm positional encoding/encoder và vẫn yêu cầu load mọi tensor strict.
Receipt `positional-module-check.json` giữ lỗi trước sửa; chưa load weight/audio ở phép
kiểm tra đó. Adapter lấy các định nghĩa encoder đã đọc từ AST của nguồn pin, bỏ
decorator đăng ký FunASR; không thực thi downloader hoặc import tùy ý từ model card.

Evidence: `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`
`s6-followup-20260908-204000/alignment-preflight/`. Report trước/sau giữ riêng.

## Kết quả pilot

**Chưa đạt acoustic acceptance.** Mẫu phồn thể và clip user 60 s qua interval/RMS
nhưng chỉ lần lượt 9/13 và 2/94 target có frame argmax hỗ trợ. Clip user có 99,8%
frame blank; greedy output chỉ hai ký tự. Meeting c01 có một span âm và ba chunk
khác vướng energy guard; silence control bị chặn đúng. Không mở rộng corpus hoặc
đưa adapter vào sản phẩm từ các kết quả này. Không sửa timestamp/script hoặc thêm
ngưỡng confidence tùy ý để đổi trạng thái thành pass.

Xem [báo cáo sau S6](asr-s6-followup-2026-09.md). Emissions/path/raw được lưu trước
validation. Hai snapshot `contract-at-download.md` và `contract-at-dispatch.md`
khớp hash trong receipt đã ghi trước download/inference, tách khỏi phần kết quả mới.
