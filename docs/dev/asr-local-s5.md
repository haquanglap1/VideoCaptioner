# S5 — Qwen local và hybrid diarization

Baseline bàn giao `1bf4dd0`, code S4.1 `db23299`, nhánh `codex/asr-s3-native`.
S5 thêm engine được chọn tường minh; mặc định Bijian, Faster-Whisper và cấu hình S1–S4.1 giữ nguyên.
Không chọn preset mặc định mới, tự gán voice hoặc làm benchmark corpus S6.

## Cài đặt và chọn model

Môi trường Qt giữ nguyên dependency project. Có hai recipe Windows CPython 3.12 riêng:

| Runtime | Dependency chính được khóa | Model |
| --- | --- | --- |
| Qwen | qwen-asr 0.0.6; Torch/Torchaudio 2.8.0+cu128; Transformers 4.57.6 | Qwen3-ASR 1.7B, 0.6B, ForcedAligner 0.6B |
| Diarization | pyannote-audio 4.0.7; Torch/Torchaudio 2.9.1+cu128; TorchCodec 0.8.1 | Community-1 |

Qwen dùng lại **recipe lock S2**, đã đo cả recognition và alignment, nhưng cài vào một thư mục mới.
Không sửa runtime S2 hoặc VieNeu. Pyannote dùng recipe riêng để không nâng dependency Qwen/Qt.
Lock transitive có hash nằm trong `videocaptioner/resources/local_asr/`; PyInstaller bundle recipe,
không bundle Torch, Torchaudio, Qwen, pyannote hoặc model weights vào base Qt.
SHA-256 lock Qwen: `944abf936c65e6f587848553987d40e324cf830660c7f357938fb813a9a05e62`;
lock diarization: `6be6c010d7eae3b52c03dc14996121a4c2fda22e0e76850aae1e8eca46aa28a2`.

```powershell
# Cài cả hai model nhận dạng và aligner; đích phải CHƯA tồn tại.
uv run --frozen python scripts/build_local_asr_runtime.py `
  --output build/qwen-local-new --models qwen-0.6b qwen-1.7b aligner

uv run --frozen videocaptioner local-asr probe --root build/qwen-local-new `
  --models qwen-0.6b qwen-1.7b aligner

uv run --frozen videocaptioner transcribe clip.mp4 --asr qwen-local --language zh `
  --qwen-model qwen-1.7b --qwen-runtime build/qwen-local-new -o subtitles.json
```

CLI/EXE cũng có `local-asr install --root NEW --models ...`, `local-asr status` và `local-asr probe`.
`status` chỉ kiểm tra file/manifest; `probe` verify hash và nạp model, rồi đóng process, chưa inference.
Cài đặt dùng `uv venv` + `uv pip sync --no-config --require-hashes`; máy cần `uv` và NVIDIA CUDA phù hợp.
Đây là **venv cài tại máy**, phụ thuộc Python nền của uv, chưa phải bộ portable chép sang máy khác.

GUI: chọn **Qwen3-ASR [Tại máy]** ở Nhận dạng/Cài đặt, chọn 1.7B hoặc 0.6B, ngôn ngữ Chinese.
**Quản lý mô hình** có ba bước riêng: nhận dạng, căn thời gian, phân biệt người nói; chọn stage để
kiểm tra file, nạp thử, chọn thư mục đã cài hoặc cài vào thư mục mới. Cài một Qwen từ GUI gồm model
được chọn và aligner. Muốn cả hai trong cùng runtime, dùng lệnh phía trên. Mở settings/manager không
nạp model, download hoặc gọi API. Công việc chạy trong worker, có tiến độ stage và nút hủy.

Root Qwen: `--qwen-runtime`, config `local_asr.runtime_root`, GUI hoặc
`VIDEOCAPTIONER_QWEN_RUNTIME`; fallback `<ROOT_PATH>/runtime/local-qwen`.
Root pyannote tương ứng `--diarization-runtime`, `local_asr.diarization_root`,
`VIDEOCAPTIONER_DIARIZATION_RUNTIME`, fallback `<ROOT_PATH>/runtime/local-diarization`.
`ROOT_PATH` theo `config.py`: checkout nguồn, user data khi pip, thư mục EXE khi frozen.
Recipe trong package dùng được ở cả ba chế độ. GUI không mirror công tắc hành vi sang CLI.

## Revision, điều kiện tải và offline

Đối chiếu nguồn chính thức ngày 2026-09-07, giữ model nguyên bản cho API `qwen-asr==0.0.6`:

| Model | Commit SHA | License |
| --- | --- | --- |
| Qwen/Qwen3-ASR-1.7B | `7278e1e70fe206f11671096ffdd38061171dd6e5` | Apache-2.0 |
| Qwen/Qwen3-ASR-0.6B | `5eb144179a02acc5e5ba31e748d22b0cf3e303b0` | Apache-2.0 |
| Qwen/Qwen3-ForcedAligner-0.6B | `c7cbfc2048c462b0d63a45797104fc9db3ad62b7` | Apache-2.0 |
| pyannote/speaker-diarization-community-1 | `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` | CC-BY-4.0 |

[Qwen repository/API](https://github.com/QwenLM/Qwen3-ASR),
[1.7B pinned files](https://huggingface.co/Qwen/Qwen3-ASR-1.7B/tree/7278e1e70fe206f11671096ffdd38061171dd6e5),
[0.6B pinned files](https://huggingface.co/Qwen/Qwen3-ASR-0.6B/tree/5eb144179a02acc5e5ba31e748d22b0cf3e303b0),
[Community-1 model card/conditions](https://huggingface.co/pyannote/speaker-diarization-community-1),
[pyannote package metadata](https://pypi.org/project/pyannote-audio/4.0.7/).

Community-1 có gated access. User tự chấp nhận điều kiện trên Hugging Face và nhập read token qua
ô password GUI hoặc `getpass` khi cài CLI. Không có flag token; không lấy token từ settings/checkouts
khác, argv, environment chung hoặc log. Token đi qua stdin riêng của process download, không lưu.
Public Qwen tải với token tắt; file tải được so hash LFS/git blob của revision và lưu inventory SHA-256.
Manifest kiểm tra recipe/lock/bridge/revision/file bắt buộc, size và hash khi probe/chạy Qwen.
Thiếu file, đang cài, cài lỗi được báo riêng. Builder không overwrite hoặc xóa runtime cũ.

Inference chỉ đọc snapshot local, bật HF/Transformers offline, tắt telemetry pyannote/HF và chặn
socket connect trong sidecar. Model revision cố định suốt stage/job. Không tự download/update khi lỗi.

## Timing và review

Qwen `transcribe(..., language="Chinese", return_time_stamps=False)` trả text trước. Recognition
và alignment dùng đúng cùng WAV PCM16 mono 16 kHz, chunk không overlap, toàn bộ sample/tail được giữ.
Package Qwen có giới hạn recognition 1.200 s mỗi input; app chọn mặc định **120 s**, cho phép
**1–240 s**, dưới giới hạn direct ForcedAligner **300 s**. Tìm silence boundary bằng policy S2;
không có boundary an toàn thì dừng review, không fuzzy dedup, cắt chữ hay tự tạo timestamp.
S5 gọi direct aligner, không dùng auto timestamp/chunking wrapper của Qwen ASR.

Tắt `fix_timestamp` nội suy, giữ `strict-raw-v1`: integer ms, finite, 0 ≤ start < end ≤ duration,
không overlap, lexical coverage nguyên thứ tự và giữ script/tên/số/dấu câu. Kết quả generation
không kết thúc bằng EOS bị từ chối để tránh chấp nhận text đã cắt bởi giới hạn output.
Không gọi `optimize_timing` trên local/hybrid. Alignment không chứng minh ASR đúng ngữ nghĩa.

`local-asr-review-v1` giữ text toàn job, chunk offset/coverage, raw predictions, ID token, revision,
pending diarization và overrides riêng. Dùng lại **Mở bản review ASR**, CommandStack undo/redo và
`asr-review --set-timing ...` của S4.1. JSON cũ `asr-review-v1` vẫn mở được. Resume validate toàn bộ
timing/coverage local, không inference hoặc upload. Acoustic rejection cần user review/override,
không bị xóa chỉ bằng mở lại JSON. Nếu model đổi/mất lexical text thì chỉ sửa timing không đủ để pass.
Các chunk chưa align được giữ text với timing missing để user kiểm tra, không tạo giờ giả.

Review có diarization pending chỉ xuất timing; GUI/CLI báo rõ. Sau khi lưu JSON, chạy
`local-diarize` với âm thanh gốc để làm bước speaker, không nhận dạng/upload lại.

## Hybrid và metadata người nói

```powershell
# Nhận dạng gateway; local health phải pass trước khi bắt đầu request trả phí.
uv run --frozen videocaptioner transcribe clip.mp4 --asr whisper-api --language zh `
  --whisper-model whisper-1 --local-diarize --diarization-runtime build/diarization-new -o speakers.json

# Cài Community-1 sau khi user đã có quyền; token nhập ẩn, không truyền qua argv.
uv run --frozen videocaptioner local-asr install --root build/diarization-new --models community-1

# Dùng kết quả timed JSON/SRT đã có, không gửi request ASR mới.
uv run --frozen videocaptioner local-diarize subtitles.json --audio clip.mp4 `
  --runtime build/diarization-new -o speakers.json
```

Gateway text-only vẫn qua alignment S2 trước. Community-1 chạy **toàn recording** để clustering
speaker toàn job, không nối label từ các chunk độc lập. Dùng regular diarization có overlap;
không dùng exclusive output để làm biến mất chồng lời. Audio đã được decode vào memory để tránh
phụ thuộc decoder TorchCodec trong pyannote trên Windows.

Policy `overlap-conservative-v1`: gộp union các span cùng speaker, dùng coverage thời gian cue làm
độ tin cậy tất định (không phải xác suất acoustic). Chỉ gán khi đúng một speaker phủ ≥80% cue.
Nhiều speaker liên tiếp → ambiguous; cùng lúc → overlap; ít/không coverage → unknown. Các trường
hợp này giữ speaker chưa rõ cùng candidates/status trong JSON, không cache dưới namespace success.
Không sửa giờ, tách chữ, suy danh tính/giới/quan hệ/người nghe hoặc tự gán voice.

`ASRMetadata` thêm optional recognition/alignment/diarization typed; timing có aligned/imported
để không gọi forced alignment hoặc SRT nhập tay là native cloud timing. Speaker ID dùng
`pyannote:<job-scope>:<label>`; request mới dùng scope mới. Native Soniox/Scribe hoặc local labels
đã có bị từ chối replacement ngầm. Manual speaker override giữ riêng, không làm mất provenance.
ID, metadata, scope/override đi qua JSON/editor/split/optimize/translate; context/rule S4 vẫn cần
user/evidence xác nhận. Normal editor save giữ `editor-project-v1` JSON + SRT, ASS chỉ khi chọn.

Cache recognition/alignment/diarization tách namespace, phụ thuộc audio/model/revision/options/
policy/source association. Credential/path không vào key; cache hit vẫn validate. Review không
publish như ASR thành công. SRT không giữ metadata, nên dùng JSON khi còn sửa speaker/context.

## GPU và lifecycle

Một OS lease theo user ngăn Qwen/aligner/pyannote/VieNeu của các process app mới giữ GPU đồng thời.
Recognition đóng process trước khi aligner nạp, aligner đóng trước diarization. VieNeu đang idle
nhưng còn model thì báo busy để user Stop; không tự unload active job hoặc kill process khác.
Ứng dụng bên ngoài/EXE cũ không tham gia lease: CUDA OOM vẫn được báo rõ, không đổi model ngầm.

Sidecar có loading/ready/busy/error, health pin identity, deadline **1–3600 s**, mặc định **180 s**
mỗi stage; `--local-timeout`, `local_asr.timeout`. Install có deadline hữu hạn và poll cancel.
Subprocess ẩn, env được lọc, chỉ đóng process tree thuộc job; reader được join. Worker giữ contextvars,
dấu hủy còn sau `QThread.finished`, supervisor giữ worker đến lúc xong, không terminate QThread.

## Củng cố S5.1

Job hybrid chụp cấu hình và sao chép nguồn vào thư mục tạm riêng trước recognition. Recognition,
alignment và diarization cùng dùng bản sao đó; sửa/thay file gốc sau bước chuẩn bị không đổi audio
của job đang chạy. Nguồn đổi trong lúc sao chép bị từ chối; copy có deadline 600 s và kiểm tra hủy
mỗi block 1 MiB. Cần thêm dung lượng tạm bằng kích thước input; thành công/lỗi/hủy đều dọn đúng
bản sao của job. Guard Windows so sánh stat của handle/path với baseline riêng vì `ctime` của
hai API có thể khác nhau ngay cả khi file không đổi.

`local-diarize` kiểm tra bounds của cue và nhãn native/local đã có trước khi nạp model. JSON/SRT
nhập lại vẫn cần user chọn đúng audio gốc; schema hiện tại không lưu fingerprint audio để chứng minh
hai file thuộc cùng recording. Không nhận dạng/upload lại để đoán nguồn. Policy coverage/overlap,
token/cue ID, review và stage provenance giữ nguyên.

Mỗi response runtime đều kiểm tra protocol/model/revision, ngoài health lúc startup. Hash model
có điểm hủy mỗi block 1 MiB; hủy không bị đổi thành lỗi manifest missing. GUI chỉ áp lựa chọn local
diarization vào job Qwen/Whisper API; chuyển engine khác giữ preference đã lưu nhưng không mang
cờ đang ẩn vào job. CLI vẫn từ chối yêu cầu local diarization tường minh cho engine không hỗ trợ.

S5.1 giữ nguyên pin/recipe và runtime cũ. Source Qwen 0.6B/1.7B trên cùng clip public tiếp tục qua
strict alignment → JSON/SRT, mỗi bản **13 cue/token, 400–3680 ms**; toàn lượt lần lượt **59,266 /
42,609 s**, gồm verify/load/alignment trong lúc có build nền, không phải benchmark tốc độ.
Tại mốc củng cố ban đầu, chưa có quyền/token Community-1 nên chưa cài/chạy model thật. Nghiệm thu
bổ sung sau khi user cấp quyền được ghi bên dưới. Model card chính thức vẫn yêu cầu user tự
chấp nhận điều kiện; public card, dependency import và test giả không thay thế quyền tải/model.

## Bằng chứng và giới hạn

### Nghiệm thu Community-1 bổ sung trong S5.1

Sau khi user cấp quyền tải và nhập token qua GUI password, installer đã cài Community-1 vào
runtime mới `build/S51-Community1-Runtime-20260907/`, giữ nguyên recipe/pin và runtime cũ.
Manifest/hash verify pass: **8 file / 32.832.557 byte**, revision
`3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`. Inference chạy với snapshot local, HF offline,
telemetry tắt và socket guard bật, không truyền token vào process inference.

[Mẫu WAV 30 s](https://github.com/pyannote/pyannote-audio/blob/main/tutorials/assets/sample.wav)
và [RTTM tham chiếu](https://github.com/pyannote/pyannote-audio/blob/main/tutorials/assets/sample.rttm)
của pyannote được dùng cho smoke nhỏ; không mở corpus S6. Model thật trả **13 span / 2 speaker**,
giữ regular diarization có overlap. Clip Trung public Qwen 4,204 s có **1 speaker**; silence 3 s
có **0 span**. Đường waveform memory đã inference thành công, vượt mức dependency import S5.

| Phép đo Community-1 | Kết quả |
| --- | ---: |
| Load đầu của lượt đo | 75,094 s |
| Inference đầu / warm trên mẫu 30 s | 1,688 / 0,485 s |
| Torch peak allocation của process | 1.708.632.064 byte |
| RSS process tree sau warm | 1.944.559.616 byte |
| Restart load | 25,968 / 9,421 s |
| Shutdown | 0,907–0,922 s |
| Cancel startup / inference, gồm cleanup | 1,531 / 1,563 s |

Peak Torch không phải tổng VRAM/NVML; các lượt khác trạng thái cache, không dùng so tốc độ model.
Process/reader/lease được giải phóng sau close/cancel. Qwen 0.6B → strict alignment → Community-1
từ source pass **13 cue/token assigned**, toàn lượt **86,110 s**.

Cancel inference thật Qwen/aligner **1,187/1,344 s**, gồm cleanup; một process khác nhận GPU busy
khi Community-1 vẫn ready, không tác động owner. Manual speaker override qua CommandStack
undo/redo và JSON/editor roundtrip giữ stage provenance đã nhận từ model thật.

Nhập JSON/SRT với 11 cue tổng hợp theo timing reference: **1 unknown, 3 ambiguous, 7 overlap**,
text/timing/cue IDs giữ nguyên, JSON/editor roundtrip pass và hai job có scope khác nhau. Window
spot-check giữa các lượt thoại giữ speaker quay lại/overlap/silence unknown; lượt thoại ngắn đầu
clip khác reference và bị giữ ambiguous. Không gọi kết quả này là speaker accuracy đã đạt.

EXE S5.1 Final cũng đã chạy full local-hybrid → JSON/SRT: **1 cue 400–3680 ms, 13 token IDs**,
exit 0 trong **51,719 s**. `local-diarize` từ Qwen timed JSON/SRT đều exit 0, **13 assigned cue**,
không ASR/upload lại. Chạy bản sao binary/resources trong scratch mới để giữ AppData/artifact gốc;
không rebuild và không thay runtime Qwen S5 R2. Đây là runtime cài tại máy, chưa portable.

Community-1/local-hybrid đã có smoke thật; **hybrid API cloud, Scribe online, GPT gateway→alignment→
SRT, phồn thể strict, speaker accuracy và xưng hô do người đọc chấm** vẫn chưa nghiệm thu.

### Bằng chứng Qwen và giới hạn tại thời điểm bàn giao S5

RTX 5070, 12.227 MiB VRAM theo nvidia-smi. Qwen CUDA thật trên
[audio Trung public của Qwen](https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_zh.wav),
4,204 s; cả 0.6B/1.7B nhận dạng → strict alignment → JSON/SRT **13 cue pass**.

| Đo trong lượt source | 0.6B | 1.7B |
| --- | ---: | ---: |
| Load đầu của lượt đo (s) | 82,953 | 11,312 |
| Inference cold / warm (s) | 2,813 / 0,672 | 0,984 / 0,360 |
| Peak Torch allocated bytes | 1.876.073.984 | 4.698.543.616 |
| RSS tree sau inference warm (bytes) | 2.297.565.184 | 2.316.873.728 |
| Toàn recognition + strict alignment (s) | 50,141 | 31,062 |

Các lượt có trạng thái disk/CUDA cache và tải nền khác nhau; không suy model 1.7B nhanh hơn nói chung.
Peak là allocation Torch, không phải tổng VRAM process/NVML. Restart/shutdown thực đã chạy;
host không import GPU libraries. Đây là smoke chức năng, không phải benchmark corpus/ngôn ngữ.
Hai lượt restart bổ sung: 0.6B load **13,141/14,657 s**, 1.7B **19,485/18,312 s**;
shutdown **0,890–0,938 s**, không còn process/reader. Cancel trong startup thật **1,250 s**,
không còn process do job sở hữu. Các phép đo này chạy cùng thời gian build và không dùng để so tốc độ model.

Phồn thể của cùng câu và silence có text tiếp tục bị strict raw validator từ chối; **phồn thể
chưa đạt acceptance**. Dependency pyannote 4.0.7/Torch 2.9.1 CUDA import pass, nhưng máy báo thiếu
DLL decoder TorchCodec; adapter dùng waveform memory theo upstream. Chưa có token/quyền tải
Community-1 trong phiên: **diarization model inference, speaker accuracy và hybrid API thật chưa nghiệm thu**.
Scribe online, GPT gateway→alignment→SRT và chất lượng xưng hô do người đọc chấm vẫn còn thiếu.
Gate code/artifact cuối và manifest file được ghi trong status/implementation; startup/local JSON
không thay thế media/API thật. Không commit/push hoặc chuyển S6.
