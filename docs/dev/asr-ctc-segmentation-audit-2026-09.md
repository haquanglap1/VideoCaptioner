# Kiểm tra CTC với cửa sổ audio ngắn

**Chưa nghiệm thu ASR; OCR vẫn dừng.** Tiếp tục từ `2f8e0a8`, kế thừa
[pilot trước](asr-ctc-candidate-2026-09.md). Không đổi backend hoặc runtime sản phẩm.

## Contract trước phép đo

Giả thuyết: chạy encoder SenseVoice trên nguyên 60 giây góp phần gây blank collapse.
[Hướng dẫn upstream tại revision đã pin](https://github.com/FunAudioLLM/SenseVoice/blob/4482962437ce8ebd1f0ac5b6793d2f82d2e2955d/README.md)
yêu cầu chia audio dài trước encoder và minh họa VAD tối đa 30 giây. Đây là cơ sở
thử nghiệm, chưa chứng minh nguyên nhân. Kiểm tra nguồn frontend/encoder đã lưu
không thấy sai khác về PCM scale, fbank/LFR/CMVN hoặc thứ tự bốn prompt embedding.

- Một audio user 60 giây / 960.000 sample đã được cho phép; dùng WAV cũ, không
  tải lại, chuyển đổi, denoise, OCR hoặc dùng caption để chọn biên.
- Chỉ thay cửa sổ acoustic: bốn lát PCM liền nhau, mỗi lát 240.000 sample / 15 giây.
  Giữ weight, frontend, `zh`/`woitn`, dtype float32, dither 0, CTC blank và decoder.
- Transcript target giữ đúng toàn bộ 94 ký tự Qwen 1.7B nguyên 60 giây; không nhận
  dạng Qwen lại, không chia target theo transcript speech-gap cũ, không đổi script.
- Lưu emissions riêng từng cửa sổ trước decoder. Ghép emissions theo thứ tự audio,
  chạy một CTC path cho nguyên target. Mỗi cửa sổ phải có đúng 250 frame; nếu khác,
  dừng trước alignment, không resize/interpolate để ép trùng lưới.
- Lưới giữ `start = frame * 60 - 30`, `end = (last_frame + 1) * 60 - 30` ms.
  Mỗi bước nối nằm đúng bội của 60 ms. Không thêm/xóa frame, suppress blank, kéo
  khoảng blank vào chữ, clamp/swap/drop token hoặc thay threshold sau kết quả.
- Báo riêng support argmax trong span, greedy text, lexical edit distance đối với
  target (không gọi đó là CER ground truth), strict/RMS và các token qua biên cửa sổ.
  Những điểm này chưa là độ chính xác timing từng chữ; không có nhãn audio độc lập
  từng chữ cho clip user. Silence/phồn thể/meeting cũ được kế thừa, không chạy lại.
- Tối đa bốn acoustic inference, không retry. Chỉ dispatch khi không có worker ASR
  khác và có ít nhất 5 GB VRAM trống, giữ GPU lease và deadline 180 giây.
- Bản nguyên 60 giây dùng emissions/raw/diagnostic đã lưu làm đối chứng. Giữ report
  cũ; snapshot contract, hash/helper/input và raw mới trong thư mục evidence riêng
  `VC-ASR-Completion-20260908-140534/s6-alignment-audit-20260908/`.

Chỉ cân nhắc công việc tiếp theo từ kết quả thực; một đường CTC hợp lệ vẫn không
đủ đưa backend vào app, chốt phồn thể, xưng hô, stress hoặc chọn engine mặc định.

## Kết quả phép đo đã chạy

Contract được snapshot/hash trước dispatch. Bốn cửa sổ đều có đúng 250 frame;
ghép 1.000 frame nguyên bản, target vẫn 94 ký tự. Load strict 917 tensor /
233.999.167 parameter, torch/torchaudio 2.8.0+cu128. Host **exit 0 / 8,437 s**,
worker **4,203 s** gồm load **3,140 s**; peak CUDA allocated **1.011.769.344 byte**.
Đây là thời gian pilot, không phải benchmark toàn pipeline hoặc so tốc độ engine.

| Đối chứng / cửa sổ | Kết quả acoustic |
| --- | --- |
| Nguyên 60 s, emissions cũ | 2/94 target có frame argmax hỗ trợ; 99,8% blank |
| Bốn cửa sổ 15 s, emissions mới | **37/94** target có frame argmax hỗ trợ; **96,2% blank** |
| 0–15 / 15–30 / 30–45 / 45–60 s | Blank lần lượt **98,0% / 96,4% / 90,4% / 100%** |

Greedy mới có 38 ký tự lexical, cách target ASR 57 edit; **target không phải ground
truth** nên không gọi đây là CER chất lượng nhận dạng. Strict và RMS cùng pass,
không token nào kéo qua biên cửa sổ; **57 target vẫn không có frame argmax hỗ trợ**.
Kết quả cho thấy segmentation ảnh hưởng emissions nhưng chưa giải quyết collapse,
đặc biệt cửa sổ cuối vẫn toàn blank. Chưa xác định được nguyên nhân riêng của các
đoạn còn mất lời; không suy từ nhạc nền/RMS thành chứng minh model nghe đúng.

**Không đạt acoustic alignment, không tích hợp backend.** Không mở rộng corpus,
thử thêm kích thước cửa sổ tùy tiện, đổi prompt/script/threshold hoặc sửa raw để
đổi trạng thái. Giữ gate phồn thể, silence và meeting cũ riêng; không inference lại.
Model/runtime và raw cũ được kiểm tra hash/mtime trước/sau; process và GPU lease đã
đóng. Artifact EXE cũ không được build hoặc smoke lại trong lượt này.

Evidence mới: `dispatch.json`, `contract-at-dispatch.md`, `window-*.emissions.npy`,
`raw.json`, `path.npz`, `diagnostic.json`, `validation.json`, `preservation.json`.
Raw SHA-256 **9711ddf1a2968443abc08d01b453c16adcb6c7b3e2a1f442470c60a1c7529ef2**.
Chỉ bốn acoustic inference mới; scoring dùng dữ liệu đã lưu, **0 API request**.
Một cảnh báo deprecation torchaudio trong worker; pydub báo thiếu FFmpeg trên PATH
của scorer nhưng scorer đọc PCM WAV trực tiếp, không gọi FFmpeg hoặc convert audio.

## Chấm nhãn tên/số theo vị trí văn bản

Thêm `scripts/asr_entity_acceptance.py`, dùng đúng 21 nhãn reference cũ ở chín clip.
Không bổ sung nhãn sau khi xem hypothesis. Thay dò literal toàn clip bằng vị trí
biên trên **mọi đường Levenshtein có chi phí nhỏ nhất**; chỉ chấm khi cả hai biên
duy nhất. Nếu nhiều vị trí, báo ambiguous/unscored, không chọn đường tối ưu tỷ lệ pass.
Reference hash, utterance index, speaker nhãn và character offset đều được kiểm tra.

Sáu dạng digits đã được review ở lượt trước được ghi thành rubric tường minh trước
chấm. Không normalize lại ASR/CER, không bỏ đơn vị hoặc tự giải thích mọi số tương
đương. Hai nhãn công ty giữ chính tả corpus, không là danh tính đã xác nhận bên ngoài.

| Engine | Nhãn định vị được | Khớp tại vị trí | Còn lại |
| --- | --- | --- | --- |
| Qwen 0.6B | 18/21 | **15 exact** | 2 khác dạng, 1 bị lược; 3 thiếu recognition hoàn tất |
| Qwen 1.7B | 18/21 | **15 exact** | 2 khác dạng, 1 bị lược; 3 thiếu recognition hoàn tất |
| Faster-Whisper word | 21/21 | **11 exact + 6 dạng số tương đương** | 1 khác dạng, 3 bị lược |
| Faster-Whisper sentence | 21/21 | **11 exact + 6 dạng số tương đương** | 1 khác dạng, 3 bị lược |

Lượt này không có nhãn ambiguous; không suy corpus khác cũng có biên duy nhất.
Hai nhãn số mà phép dò cũ tìm thấy ở nơi khác trong clip không còn được tính khớp
cho lần xuất hiện đã gán nhãn. Trường hợp thiếu đơn vị ngày chỉ là khác dạng cục bộ;
ngữ cảnh kế tiếp vẫn nói một tháng, chưa chứng minh sai giá trị số. Giữ report literal
cũ và report mới riêng, không thay bảng CER lịch sử.

Đây là **độ khớp văn bản của tập nhãn chọn sẵn**, chưa phải entity accuracy toàn
corpus, word timing, speaker attribution hoặc kiểm định âm thanh độc lập. Không tính
18/21 và 21/21 như cùng tập để chọn model. Evidence: `entity-contract-before-score.json`,
`entity-localization.json`; không model/API mới, mọi file nguồn đã đọc giữ hash/mtime.

## Validation và phần còn mở

- Bộ chấm mới: 12 test synthetic pass, gồm 225 cặp chuỗi đối chiếu với liệt kê toàn
  bộ edit path, nhãn lặp, nhãn ở sai vị trí, chèn chữ tại biên, lược chữ, đổi script,
  rubric số giữ đơn vị, nhãn sai/stale và giới hạn cấp phát matrix.
  Lượt cuối **12 pass / 0,35 s**, hai import warnings; ruff cho hai file mới pass,
  pyright scorer **0 error / 0 warning** với Python project chỉ rõ. Pyright còn
  nhắc checkout không có `.venv` riêng và có bản tool mới; không cài/đổi dependency.
- Chỉ thay dev scorer/tests/tài liệu. Không đổi code app, dependency, resource,
  engine mặc định, strict policy, dịch hoặc runtime. Gate ASR/CLI 595 pass,
  pyright app và EXE TimingGuard cũ được kế thừa; không rerun full/static app/build.
- Alignment phồn thể và clip có nhạc vẫn chưa có ứng viên acoustic đủ bằng chứng.
  Một phép đo tiếp chỉ hợp lệ khi có giả thuyết/contract mới, không lặp batch đã chạy.
- Chưa có nhãn/chấm tên-số đầy đủ, quan hệ xưng hô đã xác nhận, timing từng chữ,
  phút sửa tay hoặc đủ genre/dialect. Corpus meeting không thay nghiệm thu phim.
- Reference dịch vẫn cần key mới nhập kín cho job; không tìm lại credential cũ.
  Giữ scope 12 câu / tối đa ba request, endpoint/model/timeout trong prompt bàn giao.
  Chưa có key không là API pass; stress quality cũ vẫn fail, OCR vẫn dừng.
