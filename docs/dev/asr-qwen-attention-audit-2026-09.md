# Audit attention mask encoder Qwen sau S6

**ASR chưa đạt; OCR dừng.** Tiếp tục từ `669c0da`, giữ thay đổi tài liệu Parakeet
đang có; không commit/push. Đây là giả thuyết encoder mới, không lặp audit decoder
timestamp, frontend SenseVoice, preflight vocabulary hoặc benchmark cũ.

## Contract trước kiểm tra

Đầu mối từ [card CTC của JazerJu](https://huggingface.co/JazerJu/qwen3-asr-ctc):
tác giả báo audio encoder Qwen thiếu attention mask khi dùng SDPA/eager. Card của
bên thứ ba chỉ là đầu mối, không là xác nhận nguyên nhân lỗi S6. Mã Qwen đã lưu tại
pin `7c6daf77a2421100f5fb066495372c00129d39ff` có `_prepare_attention_mask`, nhưng
`Qwen3ASRAudioEncoder.forward` chỉ truyền `hidden_states` và `cu_seqlens` vào layer.

1. Evidence riêng `s6-qwen-attention-audit-20260909/` trong job Completion hiện có.
   Snapshot contract/helper/hash trước audit; mọi output tạo độc quyền, giữ raw cũ.
   Inventory bảo vệ kế thừa Parakeet, bổ sung source SDPA/config/bridge đã cài;
   so hash/mtime hiện tại, không lấy hash tài liệu cũ làm baseline mới.
2. Chỉ đọc source/config và CPU synthetic. Không load checkpoint, đọc/chuyển đổi
   audio, GPU inference, cài gói, sửa runtime/app/scorer/test hoặc API ASR/dịch.
   Nếu cần nguồn công khai, chỉ GET metadata/code/card, tối đa 10 file, 2 MB/file,
   8 MB tổng; pin trước tải code. Không tải tokenizer hoặc weight CTC của JazerJu.
3. Kiểm tra SDPA/eager thực tế trong runtime và các config encoder hiện có. Xác
   định khi nào một input có nhiều attention block; không nhầm convolution chunk
   với attention block hoặc chỉ suy vấn đề từ batch nhiều recording.
4. CPU kiểm tra attention/layer và encoder thu nhỏ với parameter synthetic cố định:
   một block, hai block khác độ dài, perturb riêng block sau, so với chạy từng block
   độc lập. Mask tham chiếu dựng trực tiếp từ khoảng `cu_seqlens`; giữ dropout 0,
   không thay dtype/scale/weights giữa các nhánh. Ghi sai số, mask đã truyền và
   shape/lens; synthetic pass không là acoustic parity hoặc nghiệm thu ASR.
5. Candidate chỉ nối mask block vốn có trong upstream vào encoder layer, trong RAM
   của helper riêng. Không đổi timestamp decoder, lưới 80 ms, text, script, chunking,
   confidence hoặc policy strict. Không patch file package hoặc model đang cài.
6. Chỉ cân nhắc acoustic probe khi CPU xác nhận sai khác thực thi có liên quan và
   config/runtime hiện tại đi qua đường đó. Phải chốt contract acoustic riêng trước
   dispatch: input/target/model hash, thay đổi duy nhất, raw/logits, negative control,
   GPU lease/deadline và giới hạn số inference. Không dùng audit này tự gọi ASR pass.

Không lặp full/static app/build/GUI hoặc scoring cũ. Reference dịch vẫn cần key mới
nhập kín; chưa gọi API. Các tiêu chí stress, phồn thể, xưng hô, phút sửa tay và
genre/dialect còn mở.

## Contract acoustic sau CPU

`run03/cpu-results.json` xác nhận SDPA/eager bỏ qua phân đoạn `cu_seqlens` khi mask
vắng; perturb block sau làm đổi output block trước. Candidate mask khớp chạy mỗi
block độc lập trong sai số đã ghi, và giữ output một block. Config cả ba model có
`n_window=50`, `n_window_infer=800`; audio dài có nhiều attention block ngay khi
batch chỉ có một recording. Đây là cơ sở chạy probe mới, chưa xác nhận cải thiện.

- Tối đa **ba forward ForcedAligner**: user 60 s với nguyên target Qwen 94 ký tự;
  chunk đầu meeting `R8001_M8004-c01` 29.550 ms/107 ký tự đã khóa; negative control
  là 60 s silence synthetic với cùng target user. Không gọi recognition hoặc dịch.
  Phồn thể cũ 4,204 s chỉ có một block, không lặp inference không đổi cấu hình đó.
- Dùng đúng checkpoint aligner `c7cbfc2048c462b0d63a45797104fc9db3ad62b7` đã cài;
  so inventory/hash weight, config, tokenizer. Không tải weight/head/package mới.
  Giữ BF16, SDPA, frontend, transcript, chunk và raw decoder/lưới 80 ms như cũ.
- Chỉ nối `_prepare_attention_mask(hidden_states, cu_seqlens)` tới layer trong RAM;
  ghi trace mask/block của encoder thật. Không sửa file runtime hoặc raw cũ. Lưu
  logits 5.000 class tại mọi vị trí timestamp (BF16 mở rộng lossless sang FP32),
  input token IDs và span trước validation. Không LIS/clamp/swap/drop/interpolate.
- Đối chứng user/raw meeting lấy output cũ, không chạy lại nhánh nguyên bản. Chỉ
  candidate có logits mới; không giả có paired logits baseline hoặc quy mọi thay
  đổi vào mask nếu môi trường khác chưa được loại trừ. Ghi runtime versions/seed.
- Snapshot contract/helper/input/weight trước dispatch. Chỉ chạy khi không có
  worker ASR sống và VRAM trống ít nhất 5.000 MiB, giữ GPU lease, deadline 180 s,
  không retry. Dừng process do helper tạo, đóng lease và kiểm tra preservation.
- Chấm strict/RMS trên raw mới; báo riêng lỗi hình học, negative control, thời gian
  và peak VRAM. Target ASR không là ground truth acoustic; margin logits không có
  ngưỡng đã hiệu chuẩn. Dù strict pass vẫn chưa đủ nghiệm thu chất lượng/timing.
  Nếu còn lỗi, không mở rộng corpus hoặc đưa patch vào app từ probe này.

## Kết quả CPU và phạm vi lỗi

**Xác nhận thiếu nối mask trong encoder SDPA/eager đang cài.**
[Source Qwen pin](https://github.com/QwenLM/Qwen3-ASR/blob/7c6daf77a2421100f5fb066495372c00129d39ff/qwen_asr/core/transformers_backend/modeling_qwen3_asr.py)
tạo `cu_seqlens` nhưng không gọi `_prepare_attention_mask` trước layer. Hàm SDPA
của Transformers **4.57.6** đang cài không dùng các keyword cumulative lengths;
do đó khi mask vắng, attention có thể đi qua ranh giới block. Bridge S5 chọn SDPA
tường minh cho ASR và aligner. Chưa chạy FlashAttention 2 hoặc kiểm tra acoustic
recognition trong lượt này; không suy mọi sai số S6 cùng một nguyên nhân.

- **12 case attention + 24 case encoder synthetic**, FP32/BF16 × SDPA/eager.
  Perturb riêng block sau làm output block đầu thay đổi tối đa **0,065918–0,161133**
  ở các case attention nhiều block; khi truyền mask, thay đổi block đầu bằng **0**.
- Candidate so với oracle chạy từng block độc lập: sai số lớn nhất attention
  **7,45e-9**, encoder **6,52e-9**. Tám case encoder một block giữ output từng bit.
  Encoder dùng chiều 32 và parameter synthetic; không phải checkpoint thật.
- Không phải mọi output encoder random nhiều block đều khác rõ hơn sai số số học.
  Không dùng giả định đó để chứng minh lỗi: bằng chứng là wiring source, perturbation
  attention có kiểm soát và oracle độc lập. Giữ mọi số đo trong `cpu-results.json`.
- Config ba model đang cài cùng `n_window=50`, `n_window_infer=800`. Synthetic
  6.000 mel frame có tám attention block; 801 frame đã có hai block. Không nhầm
  convolution chunk một giây với attention window khoảng tám giây.

Lượt CPU đầu **exit 1 / 38,984 s** tại assertion CUDA visibility trước các case:
biến CUDA rỗng không vô hiệu hóa thiết bị trong môi trường này. `run02` dùng `-1`,
nhưng **exit 1 / 10,703 s** do assertion quá mạnh về output encoder random nói trên.
Giữ helper/log cả hai. `run03` sửa riêng assertion của diagnostic, giữ oracle/mask/
perturbation checks; **exit 0 / 11,078 s**, validation pass, **301 file bảo vệ** giữ
hash/mtime. Không load weight hoặc chạy acoustic ở cả ba lượt CPU.

## Probe acoustic đã chạy

Chỉ dùng ForcedAligner cũ với mask nối trong RAM; không tải JazerJu CTC hoặc thay
model/default/runtime. Checkpoint **1.835.544.544 byte**, SHA-256
**`47831d0e82f96b20e9034dba01a075ee06436654719f6a68289e49f1b65ce0e7`**,
inventory đủ chín file khớp trước load. Giữ `qwen-asr==0.0.6`, torch
**2.8.0+cu128**, Transformers **4.57.6**, BF16/SDPA và decoder raw 80 ms.

**Hai input speech vẫn fail strict; không mở rộng hoặc tích hợp candidate.**

| Input mới | Item | Zero / reversed / overlap / ngoài bounds | Item có cờ | Gate |
| --- | --- | --- | --- | --- |
| User 60 s, nguyên target 94 ký tự | 94 | **2 / 2 / 1 / 0** | **5** | Strict fail; RMS chưa chạy |
| Meeting chunk đầu 29,550 s | 107 | **7 / 1 / 4 / 0** | **12** | Strict fail; RMS chưa chạy |
| Silence 60 s, target user | 94 | **58 / 8 / 25 / 13** | **87** | Bị strict chặn; RMS chưa chạy |

Các cờ có thể giao nhau. Silence bị chặn bằng hình học, **không gọi RMS pass/fail**
hoặc suy đây là bằng chứng energy guard mới. Không sửa/bỏ span để gọi guard tiếp.
User trước có sáu item có cờ theo audit cũ, candidate còn năm; không gọi đây là
cải thiện timing accuracy, vì chưa có ground truth từng chữ. Không chấm lại raw cũ.

Raw mới giữ toàn bộ endpoint trên lưới 80 ms. So riêng endpoint với raw cũ cùng
text: user **19/188** endpoint đổi (delta −3.200 đến +640 ms); meeting **17/214**
(−2.400 đến +160 ms). Model/input/config đã khóa, nhưng không có paired logits
baseline và không lặp nhánh cũ, nên đây không là thử nghiệm acoustic parity đầy đủ.

Hook giữ logits **5.000 class** ở 188/214/188 vị trí timestamp trước decoder, cùng
input IDs; BF16 mở rộng lossless sang FP32 để lưu NPY. User/meeting/silence có
**4 / 2 / 4** vị trí đồng hạng argmax. Margin chưa hiệu chuẩn, chưa chứng minh
precision gây lỗi; không tự đổi dtype, giải tie hoặc sửa timestamp từ logits này.
Trace encoder thật xác nhận **8 / 4 / 8 block**, mask BF16 đúng shape.

Host **exit 0 / 16,953 s**; worker **4,235 s** gồm load **2,532 s**. Ba forward
lần lượt **1,297 / 0,109 / 0,203 s**, peak allocated **2.321.947.648 byte**.
Đây là probe có hook, không benchmark tốc độ ASR. Preflight không có worker ASR;
VRAM vượt ngưỡng 5.000 MiB, GPU lease/process đóng. **340 file bảo vệ** giữ hash/mtime.

Validator ban đầu thiếu NumPy ở Python checkout chính, fail import trước làm việc.
Đã dùng Python runtime có sẵn, **không cài package hoặc inference lại**. Validation
exit 0; giữ bốn SyntaxWarning pydub và cảnh báo FFmpeg không trên PATH. Validator
đọc raw, không gọi FFmpeg/chuyển đổi audio; RMS không được chạy vì strict fail.

## Evidence và bàn giao

Evidence dưới `build/asr-session-evidence/VC-ASR-Completion-20260908-140534/`
`s6-qwen-attention-audit-20260909/`:

- `contract-before-cpu.md`, `source-scope.json`, `run03/cpu-results.json`,
  `run03/cpu-validation.json`, `cpu-summary.json`, `setup-corrections.json`.
- `acoustic/contract-before-dispatch.md`, `cases.json`, `dispatch.json`,
  `load.json`, `*.timestamp-logits.npy`, `*.input-ids.npy`, `*.raw.json`,
  `results.json`, `process.json`, `validation.json` và log/setup receipt.

**Ba acoustic forward mới (hai speech, một silence), 0 weight download, 0 API
ASR/dịch.** Discovery chỉ đọc web công khai; không tải thêm metadata/code/model
vào helper hoặc thực thi code từ card. Không đổi app/scorer/tests/dependency,
media/AppData/runtime/artifact; chỉ thêm evidence và tài liệu. Kế thừa gate 595
ASR/CLI và TimingGuard, không lặp full/static app/build/GUI hoặc scoring cũ.

Đây là lỗi wiring có bằng chứng, nhưng sửa wiring riêng chưa đủ đưa alignment
qua contract. Candidate giữ trong helper; không đổi bridge/runtime từ kết quả
chưa đạt. Không lặp probe này, sweep dtype/window hoặc dùng cùng bằng chứng để
dispatch tiếp. Một giả thuyết khác cần contract riêng; hướng CTC mới vẫn cần
coverage/provenance/acoustic. **ASR chưa đạt; OCR dừng.** Dịch reference chưa key
mới, phồn thể/stress, xưng hô, phút sửa tay và genre/dialect vẫn mở.
