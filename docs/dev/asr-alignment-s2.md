# ASR S2: JSON → căn thời gian tiếng Trung

S2 dùng `transcribe()` hiện có cho CLI/GUI. Profile JSON đi qua `AlignedAPI`; profile Whisper
vẫn đi qua `WhisperAPI`/`ChunkedASR`. Không đổi engine mặc định, provider/key/prompt/model đã lưu,
không thêm diarization hoặc engine ASR Qwen.

## Cài runtime riêng (Windows NVIDIA, Python 3.12)

Từ source checkout có dependency project, chạy rõ ràng theo yêu cầu người dùng:

```powershell
uv run --frozen python scripts/build_alignment_runtime.py --output build/alignment-runtime
$env:VIDEOCAPTIONER_ALIGNMENT_RUNTIME = (Resolve-Path build/alignment-runtime).Path
uv run --frozen videocaptioner transcribe input.mp4 --asr whisper-api `
  --whisper-provider videocaptioner --whisper-model gpt-4o-transcribe --language zh
```

Key gateway cấu hình bằng các cách S1 đang hỗ trợ. Không lấy key của endpoint khác.
GUI: mở app từ shell có biến runtime trên, chọn Whisper API / GPT / tiếng Trung, rồi bấm
**Kiểm tra căn thời gian** để kiểm tra local. Probe API cũ chỉ kiểm tra nhận dạng; không dùng
kết quả probe API để suy ra khả năng xuất SRT. Đóng probe giải phóng model; job nạp một process
riêng và giữ model đó cho toàn job.

Builder từ chối output đã tồn tại; khi build lỗi, chọn thư mục mới sau khi kiểm tra lỗi. Nó dùng
`uv venv --python 3.12`, `uv pip sync --no-config --require-hashes` và lock Windows riêng;
không sửa `pyproject.toml`, `uv.lock`, môi trường Qt hay runtime VieNeu. Đây là venv cài tại máy,
**chưa phải runtime portable để chép sang máy khác**. Python nền của uv cần còn tồn tại.
Manifest pin `qwen-asr==0.0.6`, Torch/Torchaudio `2.8.0+cu128`, model
`Qwen/Qwen3-ForcedAligner-0.6B` revision `c7cbfc2048c462b0d63a45797104fc9db3ad62b7`.
Dependency transitively cần cho package Qwen được khóa đầy đủ trong
`runtime/alignment/requirements-win-py312.lock`; không bật vLLM/FlashAttention.

Locator ưu tiên `VIDEOCAPTIONER_ALIGNMENT_RUNTIME`, sau đó `<ROOT_PATH>/runtime/alignment`:
source dùng project root, pip dùng user data root, frozen dùng thư mục EXE như `config.py`.
Base EXE chỉ bundle recipe dưới `_internal/runtime/alignment`; không bundle model/Torch.
Cài bằng source builder vào một thư mục riêng rồi truyền biến runtime cho EXE, hoặc cài vào
đúng `<exe-directory>/runtime/alignment`. Không chép riêng EXE ra khỏi onedir.

## Contract và policy

- Input: WAV PCM16 mono 16 kHz, text JSON và `zh`/Chinese rõ ràng. `auto`, Việt, Quảng Đông và
  các ngôn ngữ khác bị chặn trong S2, dù model upstream có thêm ngôn ngữ.
- Preflight nhẹ kiểm tra ngôn ngữ/manifest trước đọc/chia audio; trong worker, health nạp model
  và kiểm tra CUDA trước mọi upload. Thiếu runtime, đang cài, cài lỗi, startup lỗi và ready
  là các trạng thái khác nhau. Mở settings không tải/inference/network.
- Decode FFmpeg có hạn 600 s. Chunk ASR và alignment dùng **cùng WAV** tối đa 240 s, dưới giới
  hạn model 300 s. Với audio dài, tìm >=300 ms gần im lặng (-50 dBFS xấp xỉ, RMS <=104)
  trong 30 s cuối cửa sổ. Không có điểm cắt an toàn thì dừng review trước upload cả job.
  Chia không overlap, không fuzzy dedup chữ, giữ cả tail ngắn và sample cuối.
- Word/character span canonical integer ms. Bắt buộc finite, `0 <= start < end <= duration`,
  monotonic không overlap, chunk coverage liên tục. Không clamp, kéo dài cue hoặc chia đều thời gian.
  S2 bỏ `ASRData.optimize_timing()`; chế độ câu chỉ gom các span đã đo, dùng giờ đầu/cuối của span.
- **Tắt `Qwen3ForceAlignProcessor.fix_timestamp` nội suy mặc định** trong process riêng bằng
  adapter trả raw predictions. Span bất thường được giữ để validator từ chối, không được sửa.
- So khớp đầy đủ và tuần tự mọi ký tự lexical (chữ/số/apostrophe) với text gốc. Giữ nguyên
  case, tên/số, giản/phồn thể. Dấu câu/space gắn vào span lân cận mà không đổi thời gian.
  Punctuation-only, thiếu/trùng/đổi chữ, zero-length, thiếu thời gian, span trên gần im lặng
  (RMS <=32) hoặc text rỗng trên audio có năng lượng đều dừng bằng `AlignmentError`.
- Policy duy nhất `strict-raw-v1`: **dừng toàn job để review**, không xuất SRT một phần,
  không bỏ từ, không đổi model/provider trả phí ngầm. User kiểm tra audio/text hoặc chọn
  engine có timestamp; chưa có màn sửa text rồi align lại. Exception có reason an toàn,
  không nhúng transcript/path/raw response.
- Forced alignment không phải bộ kiểm chứng nội dung ASR. Một câu sai nhưng có acoustic pattern
  phù hợp vẫn có thể vượt các guard; RMS cũng không phân biệt lời nói với nhạc/nhiễu.
  Không coi acceptance của một clip là benchmark chất lượng hoặc cam kết bắt mọi hallucination.

## Cache, process và hủy

Cache nhận dạng `ASRText:v2-<sha256>` kế thừa fingerprint S1 theo audio/endpoint/provider/model/
language/prompt/profile. Cache alignment `alignment:v1-<sha256>` độc lập theo audio, text, language,
model/revision, cấu hình CUDA/bfloat16/sdpa và policy. Prompt/text được hash trong key; key API/path
không nằm trong tên cache hoặc log. Cache value vẫn chứa transcript/spans ở local theo policy cache
hiện có; không ghi chúng vào artifact Git. Cache hit vẫn phải validate spans và acoustic support.

S2 upload dùng cùng builder/parser và policy lỗi/retry S1, qua AsyncOpenAI trong event loop riêng
của worker để hủy được socket đang chờ. Mỗi attempt có deadline 120 s, tối đa 3 lần, chỉ retry
429/5xx/kết nối/timeout. Poll cancellation khoảng 100 ms, hủy task và đóng client trước trả về;
không retry sau cancel. Hủy local không bảo đảm provider hoàn tiền hoặc dừng inference đã nhận.
Whisper/probe S1 vẫn dùng transport đồng bộ như trước.

Sidecar dùng stdin/stdout protocol, request/result trong thư mục tạm riêng được cleanup. Không mở
port HTTP, không đưa transcript/key vào argv. Process chạy ẩn, mọi subprocess dùng
`child_environment()`; runtime job/probe đặt Hugging Face/Transformers offline. Timeout health/
alignment mặc định 180 s. Kết thúc/lỗi/hủy luôn đóng process tree do job tạo và join reader;
Windows cần đóng cả venv launcher và Python con. Không có process dùng chung với VieNeu.
Reader/worker giữ contextvars. QThread probe không overload `finished`; test luôn `wait()`.

## Bằng chứng runtime ngày 2026-09-07

Nguồn công khai: [example Qwen](https://github.com/QwenLM/Qwen3-ASR/blob/main/examples/example_qwen3_forced_aligner.py),
[audio Trung](https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_zh.wav).
Chạy local CUDA RTX 5070, network offline cho sidecar sau download. Không dùng media riêng.

- Audio 4.204 s, text mẫu từ example: 13 span hợp lệ, đầu 400 ms, cuối 3680 ms; xuất SRT thật.
- Lượt load đầu 65.86 s; các lần start sau 10.20–16.36 s. Cold inference 2.18–5.25 s;
  warm 0.09–0.10 s. Peak `torch.cuda.max_memory_allocated`: 1,893,466,624 byte (~1.76 GiB);
  đây là allocation của Torch, không phải tổng VRAM process/NVML.
- Câu cố tình lệch audio, silence với text và bản phồn thể của cùng câu đều bị strict validator
  từ chối vì raw spans có zero-length/overlap/bounds. **Phồn thể chưa đạt acceptance trên clip này.**
  Không đổi text thành giản thể để ép pass.
- Names/numbers, offset, overlap/tail và token coverage có test offline tổng hợp; chưa có corpus
  nghe/gán nhãn tiếng Trung cho timing median/p95, long-video, names/numbers hoặc phương ngữ.
- Gateway thật chưa chạy: không có ASR key cấu hình trong worktree/env. MockTransport kiểm tra
  wire/parser→alignment→SRT và lỗi/retry chỉ là test offline, không phải GPT→SRT E2E.

Nguồn đối chiếu: [OpenAI timestamp](https://developers.openai.com/api/docs/guides/speech-to-text),
[Qwen 5-minute limit](https://github.com/QwenLM/Qwen3-ASR),
[model revision](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B/tree/c7cbfc2048c462b0d63a45797104fc9db3ad62b7).
Trang docs gateway không tải được bằng web tool trong session; routing giữ contract S1 đã chốt.
