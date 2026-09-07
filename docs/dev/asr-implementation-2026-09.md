# Kế hoạch thực thi ASR tiếng Trung → phụ đề tiếng Việt

Ngày: 2026-09-07. User đã chấp nhận hướng trong
[kế hoạch nghiên cứu](asr-provider-plan-2026-09.md). Tài liệu này chia hướng đó thành các
gói có thể triển khai và nghiệm thu riêng. Trạng thái cập nhật 2026-09-07: **S5.2 đã có identity
recording và GPT gateway→strict alignment→Community-1→JSON/SRT thật từ source/EXE**. Whisper
hybrid source pass, lượt Whisper API từ EXE HTTP 429. S5.1 đã đo Qwen/Community-1 local-hybrid.
Native online, phồn thể strict, chất lượng speaker/xưng hô và Qt teardown còn thiếu nghiệm thu.
S6 chưa triển khai; S5.2 dừng review, chưa commit/push. Xem [hướng dẫn S5.2](asr-s52.md).
Theo yêu cầu riêng đầu phiên S4, 50 file S3 được commit `327c214` và push lên
`origin/codex/asr-s3-native` trước khi sửa S4. Sau các lượt review/online và xuất SRT xem thử,
user yêu cầu submit: **code S4 đã chốt tại `8558082945575d551a4c38cdc4943c395254a583`**.
S4.1 đã được triển khai theo [followup trước S5](asr-step-4-followup-prompt.md), rồi chốt code
`db23299370f311395fae39069f0983739d259250` theo yêu cầu user. Xem
[bàn giao S4.1](#bàn-giao-s41--2026-09-07), [hướng dẫn sử dụng](asr-s41.md) và
[prompt S5 đã thực hiện](asr-step-5-prompt.md). Xem [hướng dẫn S5](asr-local-s5.md).
Theo yêu cầu submit/push sau review, **code S5 đã chốt tại
`3a7c231a53069fefc58b34e95d7cc9ba10dac846`**. Commit tài liệu bàn giao sau code thêm
[prompt phiên S5.1](asr-step-5-followup-prompt.md). S5.1 đã củng cố contract bên dưới;
Community-1/local-hybrid đã có smoke thật sau khi user cấp quyền tải. Chưa triển khai S6.
Theo yêu cầu commit/push sau review, **code S5.1 đã chốt tại
`8599965b7931d8c555a55cfa379b4a2e2cee9238`** trên `codex/asr-s3-native`.
[Prompt S5.2](asr-step-5-2-prompt.md) bàn giao nợ API/liên kết nguồn trước S6; lưu prompt không
khởi chạy phiên mới hoặc cấp quyền commit/push cho thay đổi tiếp theo.

Prompt S2 đã thực hiện: [bàn giao yêu cầu](asr-step-2-prompt.md).
Hướng dẫn và giới hạn: [runtime alignment S2](asr-alignment-s2.md).
Prompt S3 đã thực hiện: [yêu cầu S3](asr-step-3-prompt.md).

## Bàn giao S5.2 — 2026-09-07

Baseline **27be883**, code S5.1 **8599965** là ancestor, nhánh `codex/asr-s3-native` sạch lúc bắt đầu.
Không commit/push/tag/release/PR/S6; không đổi dependency, model pin, runtime hoặc artifact cũ.

### Hành vi và regression

- Optional `AudioIdentity` cấp tài liệu: PCM16 little-endian mono 16 kHz toàn recording, SHA-256
  và sample count, gồm tail dưới 1 ms; không path/key/transcript. Legacy checksum/schema vẫn mở.
- Snapshot nguồn Whisper/native, identity từ PCM Qwen/GPT, giữ qua review/resume/JSON/editor/
  table export và pipeline clone. Diarization mismatch trước cache/model; cache association v2
  tách trạng thái nguồn/pending. Không gán lại legacy thành verified hoặc trộn nhãn native/local.
- Baseline pipeline chạy cùng reproducer offline dùng hai tone 1 s khác nội dung đã vào fake
  model và chấp nhận; mã mới dừng mismatch với **0 model load**. Lossless container/rename pass,
  changed source/tail/malformed identity fail. Đây là test tổng hợp, không speaker/API acceptance.
- GUI chọn audio ở worker có cancel/retain/stale signal; CLI `asr-review --audio` và guard không
  overwrite audio. User timing edit giữ CommandStack/overrides/IDs; pending đi qua JSON/editor,
  chỉ xóa ở kết quả diarization. Save project vẫn JSON + SRT, ASS không đổi.
- GPT dùng aligner runtime S5 khi chọn root tường minh, fallback locator S2 cũ khi không chọn;
  verify/hash/health trước upload. Giữ recognition toàn job trước alignment, raw/tail/chunk IDs
  khi fail; không resume thành success nếu thiếu text trên audible input. Không đổi strict policy.

### API/runtime thật

Public Qwen Chinese **4,204 s / 67.263 sample**, cùng endpoint **https://api.videocaptioner.cn/v1**,
provider `videocaptioner`, hai model tường minh. Catalog HTTP 200 chứa model được yêu cầu; không
dùng catalog làm bằng chứng inference. Source không đọc cache, EXE dùng scratch cache ban đầu trống.
S2 vẫn retain stage values trong scratch khi cache reads tắt. Key chỉ password/RAM/named pipe
local với current-user ACL, không file/argv/env; owner/readers đã thoát. Không tìm credential cũ.

| Gate | Kết quả |
| --- | --- |
| Source Whisper → Community-1 → JSON/SRT | **exit 0**, 43,390 s; 1 cue 0–4000 ms, 1 speaker, identity, pending false |
| Source GPT → strict alignment → Community-1 → JSON/SRT | **exit 0**, 70,859 s; 1 cue 400–3680 ms, 13 token IDs, 1 speaker, cùng identity |
| EXE GPT full hybrid → JSON/SRT | **exit 0**, 58,312 s; cùng timing/13 token IDs/identity; SRT export 0,359 s |
| EXE Whisper full hybrid | **HTTP 429 / exit 5**, 39,187 s, không output. Chưa nghiệm thu thành công |
| EXE local-diarize trên timed Whisper JSON từ source | **exit 0**, 10,157 s; identity/pending đúng, không ASR/upload lại |
| EXE local-diarize trên SRT legacy | **exit 0**, 9,609 s; vẫn unverified, không tạo identity |
| EXE JSON + audio sai cùng duration + missing runtime | **exit 5** do mismatch trước runtime, 0,406 s, không output |
| EXE review tổng hợp invalid/override/reopen/wrong audio | **5/0/0/5** đúng kỳ vọng; raw/edited/IDs/identity/pending giữ nguyên; không upload |

Hai runtime dùng nguyên trạng **S5 Qwen R2** và **S5.1 Community-1**, pin/recipe không đổi; host
không import GPU libraries, không bridge process còn lại. Không dùng thời gian smoke so tốc độ,
DER, chất lượng speaker hoặc ngôi. Whisper theo policy retry hữu hạn S1 hiện có tối đa 3 attempt;
không chạy thêm command để ép HTTP 429 thành pass. Không gọi Soniox/mini, không có key Scribe.

### Offline và chẩn đoán

- Full offline sau sửa preflight: **1.116 passed / 4 skipped / 51 deselected, 131,78 s, exit 0**.
  Sau đó thêm guard destination trùng `--audio`, **CLI cuối 106 passed, 2,58 s**; fixture identity
  cô lập cache sau rà cuối **24 pass, 3,44 s**. **30 test mới**: 24 core, 4 UI, 2 CLI. Ruff pass,
  pyright **0 errors/0 warnings**, translations sync/diff-check pass. Python 3.12.13 có sẵn,
  `--pythonpath` chỉ đúng venv; không uv sync/install. 4 skip TTS/service; native Qt playback pass.
- Full đầu **2 fail / 1.114 pass**: snapshot chạy trước preflight text-only (đã sửa) và crash
  Settings **3221225477**. Faulthandler chỉ có `<no Python frame>`; WER: **sip.cp312-win_amd64.pyd**,
  exception **0xc0000005**, offset **0x13a26**. PyQt5 5.15.11, sip 12.18.0, QFluentWidgets 1.8.4.
  Không có build/GPU job song song. 4 case chẩn đoán preflight/Settings/Scribe cancel-timeout pass;
  3 subprocess với marker import/assertions/atexit (2 nguyên trạng, 1 explicit teardown) pass.
  **Chưa xác định nguyên nhân**, không sửa Qt/framework hoặc nới mock timeout để che lỗi.
- S2 retain cache values dù tắt cache reads khiến fixture mới ghi 2 entry tổng hợp. Đã dùng
  cache RAM trong fixture, đối chiếu exact key/value/store-time rồi xóa đúng 2 entry do test tạo;
  rerun xác nhận chúng không xuất hiện lại. Không xóa cache khác. Settings/review/GPU lease và
  media kiểm thử vẫn dùng tmp/scratch; QThread được wait. Không gọi offline/mock là API inference.

### Artifact và GUI

- **`dist/VideoCaptioner-ASR-S52-Review-20260907-Final/`**, spec duy nhất, output/cache/temp mới.
  PyInstaller **exit 0, 6 WARNING optional/platform, 0 ERROR, 6 SyntaxWarning upstream**.
  **218 module / 39 resource** khớp source (kể cả TS và script sidecar data); không Torch/Qwen/
  pyannote trong base Qt. So code object sau chuẩn hóa filename; không dùng marshal reference
  encoding làm false mismatch. Script sidecar là data đúng thiết kế, không phải module PYZ thiếu.
- EXE **31.161.859 byte**, local **2026-09-07 19:11:44**, SHA-256
  **`457613169d3bd5ac262130ca83f783c4cd4148d08317ab7126c5359b48f91649`**.
  Onedir trước GUI **580 file / 237.667.163 byte**; phân phối nguyên folder. API từ bản sao
  binary/resources riêng cùng hash; không dùng media/AppData/log của artifact cũ làm scratch.
- Startup artifact mới **25,047 s**, **1 Qt window**, RSS **101.412.864 byte**; WM_CLOSE exit 0,
  0 process còn lại, binary unchanged. **Teardown log chưa sạch**: cùng một lỗi InfoBar được ghi
  lặp ở stderr/log: `BottomInfoBarManager has been deleted`, eventFilter qfluentwidgets line 432,
  sau thông báo update. Bản sao S5.1 Final tái hiện cùng lỗi, 25,047 s / exit 0 / 0 process sót.
  Chưa chứng minh nó gây crash SIP của Settings. Không gọi gate GUI hoàn toàn sạch hoặc đã sửa Qt.
- Đã xem render review VI bằng Qt Windows native; Qt worker + FFmpeg kiểm tra audio public pass.
  Offscreen không render chữ, không dùng để kết luận layout. Không rebuild sau các gate artifact.

**Dừng review.** Còn mở: Whisper API từ EXE sau HTTP 429; Scribe online; Qt/SIP/InfoBar teardown;
phồn thể strict; speaker accuracy và xưng hô do người đọc chấm. Không tự chuyển S6. Giới hạn và
lệnh tái hiện ở [S5.2](asr-s52.md); không cần helper ignored để hiểu hoặc dùng tính năng.

### Manifest S5.2 so với baseline 27be883

**35 file sửa/thêm**, chưa commit. Không media/AppData/build/runtime/credential, không đổi dependency hoặc AGENTS/CLAUDE.

```text
README.md
VideoCaptioner.spec
docs/dev/asr-implementation-2026-09.md
docs/dev/asr-local-s5.md
docs/dev/asr-s52.md
resource/translations/VideoCaptioner_en_US.ts
resource/translations/VideoCaptioner_vi_VN.json
resource/translations/VideoCaptioner_zh_CN.ts
resource/translations/VideoCaptioner_zh_HK.ts
status.md
tests/test_asr/test_alignment.py
tests/test_asr/test_audio_identity.py
tests/test_cli/test_asr_review.py
tests/test_ui/test_audio_identity.py
videocaptioner/cli/commands/asr_review.py
videocaptioner/cli/commands/local_diarize.py
videocaptioner/cli/main.py
videocaptioner/core/asr/aligned_api.py
videocaptioner/core/asr/alignment/audio.py
videocaptioner/core/asr/asr_data.py
videocaptioner/core/asr/audio_identity.py
videocaptioner/core/asr/local/diarization.py
videocaptioner/core/asr/local/pipeline.py
videocaptioner/core/asr/local/review.py
videocaptioner/core/asr/native_api.py
videocaptioner/core/asr/review.py
videocaptioner/core/asr/transcribe.py
videocaptioner/core/editor/adapters.py
videocaptioner/core/editor/models.py
videocaptioner/core/editor/project_store.py
videocaptioner/core/subtitle/editing.py
videocaptioner/resources/translations/VideoCaptioner_vi_VN.json
videocaptioner/ui/components/asr_review_dialog.py
videocaptioner/ui/thread/audio_identity_thread.py
videocaptioner/ui/view/subtitle_interface.py
```

## Bàn giao S5.1 — 2026-09-07

Code và bằng chứng S5.1 được chốt thành **`8599965b7931d8c555a55cfa379b4a2e2cee9238`**,
parent `80f6e36`, sau yêu cầu submit/push của user. Các giới hạn “không commit/push” trong
các mục nghiệm thu bên dưới mô tả thời điểm làm việc trước yêu cầu chốt Git này.

### Bổ sung sau khi có quyền tải Community-1

User nhập credential qua ô password GUI; installer truyền RAM/stdin riêng, không lưu token vào
settings/source/argv/env/log. Runtime mới **`build/S51-Community1-Runtime-20260907/`**, giữ nguyên
mọi runtime/artifact cũ. Manifest verify **8 file / 32.832.557 byte**, revision
`3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`, lock diarization S5 không đổi; manifest SHA-256
**`8af6543a4f173c8a3c19c84c802c57a4f4ded1ccf242ad23c2fee6b675068447`**.

- Community-1 health/inference thật pass bằng waveform memory, offline/telemetry/socket guards
  bật. Public pyannote tutorial 30 s → **13 span / 2 speaker**; Qwen Chinese 4,204 s → **1 speaker**;
  silence 3 s → **0 span**. Nguồn/audio hash và output chỉ ở scratch ignored; liên kết public và
  bảng phép đo nằm trong [hướng dẫn S5](asr-local-s5.md#nghiệm-thu-community-1-bổ-sung-trong-s51).
- Load đầu **75,094 s**; cold/warm inference 30 s **1,688/0,485 s**. Torch peak allocation
  **1.708.632.064 byte**, RSS tree warm **1.944.559.616 byte**, không phải tổng VRAM/NVML.
  Restart load **25,968/9,421 s**, shutdown **0,907–0,922 s**; cancel startup/inference thật
  **1,531/1,563 s**, process/reader/lease cleanup pass. Không dùng làm benchmark so model.
- Cancel inference Qwen/aligner thật **1,187/1,344 s**; process thứ hai bị GPU busy trong khi
  Community-1 owner còn ready, không kill/unload owner. Manual speaker override qua CommandStack
  undo/redo và JSON/editor roundtrip giữ nguyên diarization provenance từ model thật.
- Qwen 0.6B → strict alignment → Community-1 source pass, cache tắt, **13 cue/token assigned**,
  toàn lượt **86,110 s**. Timed JSON/SRT tổng hợp từ reference tutorial đi qua diarization thật,
  mỗi bản **11 cue: 1 unknown / 3 ambiguous / 7 overlap**, giữ text/timing/IDs và JSON/editor;
  hai job có scope khác nhau. Không coi text tổng hợp là ASR transcript hay cache success.
- Window spot-check theo RTTM giữ hai speaker quay lại, overlap và silence unknown; **đoạn thoại
  đầu ngắn chưa khớp reference, association ambiguous**. Speaker accuracy tổng quát vẫn thiếu;
  chưa đo DER hoặc mở corpus S6.
- **Workflow từ EXE pass**: dùng bản sao riêng của binary/resources S5.1 Final, SHA-256 vẫn
  **`5c2cc4ad873d7acbc0ccb9a94ce942e87a41c3bc8ba0c68c6e36af8df25f73c8`**, không dùng artifact/
  AppData gốc làm scratch. Full Qwen → alignment → Community-1 → JSON/SRT exit 0, **1 cue
  400–3680 ms / 13 token IDs**, **51,719 s**. `local-diarize` từ Qwen timed JSON/SRT có sẵn
  đều exit 0, **13 assigned cue**, **11,328/11,204 s**, không nhận dạng/upload lại.
- Chỉ cập nhật 4 tài liệu (kể cả README), không đổi code/test/recipe; không rerun full hay rebuild. Gate source
  **1.088 pass / 4 skip / 51 deselect**, CLI104, ruff/pyright/translations vẫn áp dụng. Bằng chứng
  không thay thế **hybrid API cloud, Scribe online, GPT gateway→alignment→SRT, phồn thể strict,
  speaker accuracy hoặc xưng hô do người đọc chấm**. Không commit/push/S6.

### Giai đoạn củng cố trước khi có quyền tải

Baseline **80f6e36**, nhánh `codex/asr-s3-native` sạch ban đầu; code S5 **3a7c231** là ancestor.
Không commit/push/S6. Giữ dependency Qt, recipe/revision, runtime và artifact cũ.

### Sửa lỗi có tái hiện

- Hybrid trước đây mở lại path sau recognition: test thay nội dung file giữa hai stage chứng minh
  diarization nhận recording khác. Nay chụp config và source riêng cho toàn job, có kiểm tra nguồn
  đổi trong lúc copy, deadline/cancel/cleanup. Không thay text, timing hay policy alignment.
- Windows/Python 3.12 có thể trả `ctime` khác nhau giữa `fstat` và `Path.stat`: chẩn đoán file
  tổng hợp có **299/300** lượt khác biệt. Guard mới so mỗi API với baseline riêng và đối chiếu
  identity file, tránh từ chối nguồn ổn định. Regression mô phỏng khác biệt này đã pass.
- Cue quá duration hoặc có nhãn native trước đây đi đến nạp GPU rồi mới bị từ chối; nay validate
  trước runtime/cache. Giữ nguyên manual override, unknown/overlap và policy ≥80%.
- Response sau inference trước đây chỉ cần `ready`, không so identity; nay so protocol/model/
  revision mỗi response. Hủy verify model được kiểm tra mỗi block 1 MiB và giữ đúng lỗi cancel.
- GUI giữ cờ local diarization ẩn khi chuyển sang Soniox/Scribe/Bijian/Faster-Whisper, khiến core
  từ chối job. Snapshot nay chỉ áp cờ cho Qwen/Whisper; preference đã lưu vẫn còn khi quay lại.
  CLI explicit unsupported combination vẫn bị chặn, không trộn native/local labels.
- **22 regression mới** (16 core + 6 GUI), bên cạnh test S5 đã có. Test snapshot/config/nguồn,
  input invalid, identity, cancel/hash và chuyển engine dùng dữ liệu/transport tổng hợp;
  không coi chúng là Community-1 inference hoặc API acceptance.

### Validation offline

**Full mã cuối 1.088 pass / 4 skip / 51 deselect, 118,40 s, exit 0**, chạy không có build/runtime
song song. **CLI 104 pass, 2,09 s**; gần phần cuối **26 pass, 4,55 s**; ruff pass, pyright **0/0**,
translations sync và diff-check pass. Python 3.12.13, đúng checkout, venv/FFmpeg có sẵn; không
sync/install dependency Qt. 4 skip TTS/service, native QtMultimedia playback pass. QThread wait,
settings/config/cache/review/GPU lease dùng isolation hiện có.

Lượt full đầu phát hiện guard `ctime` mới; sửa xong **1.082 pass** trước bổ sung regression GUI.
Full sau GUI có **2 fail / 1.086 pass**: Settings subprocess exit **3221225477**, stderr trống;
Scribe mock deadline **10 ms** có `closed=False` (transport chưa vào). Ba case chẩn đoán riêng
với faulthandler pass, rồi full tuần tự phía trên pass. Không đổi code native/Settings để ép gate;
**chưa xác định nguyên nhân crash Qt hoặc gọi flake timeout là đã sửa**. Build/runtime chạy đồng
thời ở lượt fail là điều kiện quan sát, chưa phải kết luận nguyên nhân.

### Runtime và artifact

- Nguồn chính thức [Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
  vẫn yêu cầu tự chấp nhận điều kiện, hỗ trợ offline và waveform memory. Giữ revision
  `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` cùng pyannote 4.0.7. Phiên không được cung cấp
  quyền/token; không tìm credential, tải model hoặc tự chấp nhận điều kiện. Locator xác nhận
  thư mục dependency S5 không phải model ready. Không có nghiệm thu Community-1/hybrid API mới.
- Qwen 0.6B/1.7B thật từ source, cache tắt, cùng audio public **4,204 s**: recognition → strict
  alignment → JSON/SRT **13 cue/token, 400–3680 ms** mỗi bản, **59,266/42,609 s** toàn lượt.
  Không GPU module trong host, không còn bridge Qwen sau job. Dùng runtime S5 R2 nguyên trạng;
  thời gian có build nền, không dùng so tốc độ hay chất lượng model.
- Artifact mới `dist/VideoCaptioner-ASR-S51-Review-20260907-Final/`, duy nhất spec. Build exit 0,
  **6 WARNING optional/platform, 0 ERROR, 6 SyntaxWarning upstream**; thêm warning upstream
  pkg_resources và pydub PATH lúc phân tích. Source smoke thực đã có FFmpeg đúng PATH.
  EXE **31.150.810 byte**, local **2026-09-07 17:55:01**, SHA-256
  **`5c2cc4ad873d7acbc0ccb9a94ce942e87a41c3bc8ba0c68c6e36af8df25f73c8`**.
  **216 module / 33 resource** đã so source/bytes; không bundle GPU libraries. Onedir trước smoke
  **580 file / 237.650.489 byte**. Bản S5.1 đầu giữ riêng, không dùng làm bản nghiệm thu.
- **Workflow thực từ EXE Final pass**, Qwen 0.6B/1.7B trên cùng public audio → strict alignment
  → JSON → SRT, mỗi bản **1 cue 400–3680 ms / 13 token IDs**, các command exit 0. Toàn transcribe
  **37,562/27,500 s**, export SRT **0,360/0,390 s**; parse lại khớp text/timing. `local-diarize`
  với JSON native tổng hợp dừng **exit 5 / Existing diarization** trước runtime missing, không
  ghi output partial. Không process EXE sót. Đây không phải Community-1/hybrid API hoặc portable
  runtime. Harness đầu đặt `--config` trước subcommand sai vị trí nên exit 2, chưa inference;
  đã sửa harness và chạy lại command đúng, không đổi source/artifact.
- **GUI startup Final pass**: hidden launch sống **25 s**, 1 Qt window đúng PID, WM_CLOSE →
  **exit 0**, RSS **100.052.992 byte**, **0 process sót / 0 Traceback-ERROR-CRITICAL**. Không
  rebuild artifact sau khi có AppData. Đây là startup gate, không xóa crash Settings ngắt quãng.

**Chưa đủ điều kiện nghiệm thu để chuyển S6**: Community-1 model inference và hybrid API,
speaker accuracy, Scribe online, GPT gateway→alignment→SRT, phồn thể strict, xưng hô do người đọc
chấm vẫn thiếu. JSON/SRT cũ không có fingerprint audio để tự xác minh recording khi nhập lại;
user vẫn phải chọn đúng audio gốc cho `local-diarize`.

### Manifest S5.1 so với baseline 80f6e36

**12 file** trong commit code S5.1 **8599965**; README được cập nhật ở lượt nghiệm thu Community-1
bổ sung. Prompt S5.2 và cập nhật trạng thái chốt Git thuộc commit tài liệu bàn giao sau code.

```text
README.md
docs/dev/asr-implementation-2026-09.md
docs/dev/asr-local-s5.md
status.md
tests/test_asr/test_local_s51.py
tests/test_ui/test_local_asr.py
videocaptioner/core/asr/local/audio.py
videocaptioner/core/asr/local/diarization.py
videocaptioner/core/asr/local/pipeline.py
videocaptioner/core/asr/local/runtime.py
videocaptioner/core/asr/transcribe.py
videocaptioner/ui/common/local_asr_settings.py
```

## Bàn giao S5 — 2026-09-07

Baseline **1bf4dd0** sạch trên `codex/asr-s3-native`; code S4.1 **db23299** là ancestor.
Giai đoạn triển khai theo [prompt S5](asr-step-5-prompt.md) dừng review, không commit/push/tag/release
hoặc làm S6. Sau đó user yêu cầu submit/push: code S5 được chốt thành
**`3a7c231a53069fefc58b34e95d7cc9ba10dac846`**; prompt và trạng thái submit thuộc commit tài liệu sau đó.
Giữ `pyproject.toml`/`uv.lock`, AGENTS/CLAUDE và toàn bộ artifact/media/AppData S4–S4.1.
Hướng dẫn đầy đủ: [Qwen local/hybrid S5](asr-local-s5.md).

### Code và gate cuối

- Qwen 1.7B/0.6B chọn tường minh; recognition và strict alignment S2 chạy tuần tự, model SHA
  riêng, runtime/lock có hash. Installer dùng đích mới, verify inventory/revision; không cài vào Qt.
  Community-1 có runtime riêng và nhập token an toàn; không tự chấp nhận điều kiện gated.
- Local diarization toàn job, overlap/coverage policy tất định; unknown/ambiguous giữ review,
  provenance 3 stage tách biệt, scope không nối request ngầm. JSON/editor/override/context S4 giữ
  association. `local-diarize` chạy trên kết quả timed đã có; không upload hoặc nhận dạng lại.
- `local-asr-review-v1` raw + chunk + override, dùng lại GUI/CLI/CommandStack S4.1; review không
  vào success cache. Deadline/cancel/reader join/process ownership và GPU lease S2/S5/VieNeu.
  Model manager chạy worker, không nạp/download khi mở; settings cũ và engine mặc định giữ nguyên.
- **Full offline mã cuối: 1.066 passed / 4 skipped / 51 deselected, 144,10 s, exit 0**.
  **Toàn CLI cuối: 104 passed, 2,96 s, exit 0**. 79 test S5 mới, cùng toàn bộ regression S1–S4.1.
  QtMultimedia native playback chạy pass trong lượt này, nên skip giảm từ 5 xuống 4; 4 skip là
  TTS/service và 51 deselect theo integration/slow/llm. Không coi skip/mock thành runtime acceptance.
- Ruff toàn source/tests và builder pass; pyright **0 errors/0 warnings**; sync translations,
  TS XML và diff-check pass. Python **3.12.13**, import đúng worktree, FFmpeg/toolchain có sẵn.
  Không sync/cài dependency Qt. Tests cô lập settings/config/cache/review/GPU lease; QThread wait.
- Đã xem render settings/manager tiếng Việt. JSON vi đồng bộ cả bundle/fallback; TS en/zh cập nhật,
  QM không sửa vì thiếu lrelease. Chuỗi zh mới fallback English.
- Một full trung gian có subprocess Settings crash `3221225477`, chưa xác định nguyên nhân;
  test riêng và hai full tiếp theo đều pass. Không claim đã sửa lỗi Qt ngắt quãng. Lượt đầu dùng
  chung GPU lease với smoke thật đã được khắc phục bằng fixture lease riêng cho mỗi test.

### Runtime thật và giới hạn

Qwen **0.6B và 1.7B** đã cài/download pin vào runtime S5 mới và chạy audio Trung public **4,204 s**
qua recognition → strict alignment → JSON/SRT, **13 measured token spans pass** từ source.
Cold/warm inference **2,813/0,672 s** và **0,984/0,360 s**; Torch peak allocation
**1.876.073.984 / 4.698.543.616 byte**. Có khác biệt cache/tải nền; đây là smoke nhỏ, không phải
benchmark so chất lượng/tốc độ hai model. Restart/shutdown **0,890–0,938 s**, cancel startup thật
**1,250 s**, không còn process/reader. Chi tiết RAM/load và nguồn public nằm trong hướng dẫn S5.

Pyannote 4.0.7 + Torch 2.9.1 CUDA **dependency import pass**, nhưng Community-1 chưa tải vì không
có token/quyền được cung cấp trong phiên. TorchCodec báo thiếu DLL decoder; bridge dùng waveform
memory theo upstream. **Community-1 model inference, local/hybrid speaker accuracy và hybrid API
thật chưa nghiệm thu**. Scribe online, GPT gateway→alignment→SRT và chất lượng xưng hô bằng người đọc
vẫn thiếu. Phồn thể và silence có text tiếp tục bị raw strict validator từ chối; không xóa nợ
phồn thể bằng mock hoặc bằng việc Qwen recognition giản thể đã pass.

### Gate artifact cuối

1. Duy nhất `VideoCaptioner.spec`, output/cache/scratch S5 riêng mới. Bản review cuối:
   **`dist/VideoCaptioner-ASR-S5-Review-20260907-Final/`**. PyInstaller **exit 0,
   6 WARNING optional/platform, 0 ERROR**, thêm
   **6 SyntaxWarning upstream**. Warnings: `js`, `curl_cffi`, `yt_dlp_ejs`,
   `tzdata`, `sip`, AppKit macOS; không coi chúng là GPU inference.
2. EXE **31,148,265 byte**, timestamp local **2026-09-07 17:23:00**,
   SHA-256 **`1717175295241e722a3e5a516d903b85668a3372417260bf0e776e3f303fe9f3`**. Trước smoke: **580 file /
   237,647,944 byte**. Phân phối nguyên onedir. Bytecode **215/215
   module** (cả nested code) khớp source; **34 resource** prompt/recipe/translations khớp bytes;
   không có Torch/Torchaudio/Qwen/pyannote/TorchCodec trong PYZ.
3. **Frozen local review pass**: timing tổng hợp lỗi → **exit 5**, không SRT; explicit override →
   JSON/reopen/SRT đều **exit 0**, giữ raw/token/scope/edited. Install trộn runtime bị từ chối
   **exit 2 trước khi hỏi token**. Không model/API request trong các command review này.
4. **Qwen từ chính EXE pass**: 0.6B/1.7B nhận dạng audio public qua strict alignment, JSON → SRT
   bằng CLI EXE đều **exit 0**. Chế độ câu gom thành **1 cue, 400–3680 ms**, giữ **13 token IDs**
   trong JSON; SRT reopen khớp text/timing. Thời gian transcribe **70,766 / 22,421 s**, bao gồm
   load/verify/alignment, không phải chỉ inference. Dùng runtime cài tại máy và FFmpeg sẵn có,
   **không chứng minh portable runtime hoặc cloud API từ EXE**.
5. **Startup GUI Final pass**: hidden launch sống **25 s**, đúng Qt window/PID, WM_CLOSE →
   **exit 0**, RSS **101,220,352 byte**, **0 process artifact sót**, **0 startup
   Traceback/ERROR/CRITICAL**. Harness đầu dùng điều kiện sai về prefix title đã được sửa theo
   title Qt thực rồi chạy lại; không sửa source hoặc rebuild sau khi artifact có AppData.

Artifact S5 đầu được giữ riêng vì có một module CLI trước guard cuối. Final đã verify lại toàn
source và resource. Artifact S4 vẫn SHA-256
`08dd40819c91152c7fd778b4f81036101ee6db43208844089efc595f58fda252`; S4.1 Final vẫn
`2ab4c85035ba64fd59fe96d5686b75ac00139644936bd960a206a419803e4284`.
Không dùng các artifact cũ làm scratch, không sửa/xóa media/AppData của chúng. Reports/synthetic
JSON/public audio/screenshots chỉ ở scratch ignored S5, không đưa transcript/path riêng vào Git.

### Manifest S5 so với baseline 1bf4dd0

**53 file sửa/thêm trong commit code S5 `3a7c231`**. Prompt S5.1 và cập nhật trạng thái submit thuộc
commit tài liệu bàn giao tiếp theo. Không có media/AppData/build/dist hoặc dependency Qt trong manifest.

```text
README.md
VideoCaptioner.spec
docs/dev/architecture.md
docs/dev/asr-implementation-2026-09.md
docs/dev/asr-local-s5.md
resource/translations/VideoCaptioner_en_US.ts
resource/translations/VideoCaptioner_vi_VN.json
resource/translations/VideoCaptioner_zh_CN.ts
resource/translations/VideoCaptioner_zh_HK.ts
scripts/build_local_asr_runtime.py
status.md
tests/conftest.py
tests/test_asr/test_local_s5.py
tests/test_cli/test_local_asr.py
tests/test_ui/test_local_asr.py
videocaptioner/cli/commands/asr_review.py
videocaptioner/cli/commands/local_asr.py
videocaptioner/cli/commands/local_diarize.py
videocaptioner/cli/commands/transcribe.py
videocaptioner/cli/config.py
videocaptioner/cli/main.py
videocaptioner/cli/validators.py
videocaptioner/core/asr/alignment/runtime.py
videocaptioner/core/asr/local/__init__.py
videocaptioner/core/asr/local/diarization.py
videocaptioner/core/asr/local/installer.py
videocaptioner/core/asr/local/pipeline.py
videocaptioner/core/asr/local/profiles.py
videocaptioner/core/asr/local/review.py
videocaptioner/core/asr/local/runtime.py
videocaptioner/core/asr/metadata.py
videocaptioner/core/asr/review.py
videocaptioner/core/asr/transcribe.py
videocaptioner/core/entities.py
videocaptioner/core/tts/vieneu/runtime_manager.py
videocaptioner/core/utils/gpu_lease.py
videocaptioner/resources/local_asr/bridge.py
videocaptioner/resources/local_asr/diarization.in
videocaptioner/resources/local_asr/diarization.json
videocaptioner/resources/local_asr/diarization.lock
videocaptioner/resources/local_asr/download.py
videocaptioner/resources/local_asr/qwen.json
videocaptioner/resources/local_asr/qwen.lock
videocaptioner/resources/translations/VideoCaptioner_vi_VN.json
videocaptioner/ui/common/config.py
videocaptioner/ui/common/local_asr_settings.py
videocaptioner/ui/components/WhisperAPISettingWidget.py
videocaptioner/ui/components/asr_review_dialog.py
videocaptioner/ui/components/local_asr_cards.py
videocaptioner/ui/components/transcription_setting_card.py
videocaptioner/ui/task_factory.py
videocaptioner/ui/thread/local_asr_thread.py
videocaptioner/ui/view/setting_interface.py
```

## Mục tiêu sản phẩm đã chốt

- Nghe video tiếng Trung, ưu tiên phổ thông. Không cần ASR tiếng Việt.
- Tạo phụ đề có timestamp; phân biệt người nói khi có thể và giữ ngôi/xưng hô khi dịch sang Việt.
- Dùng được model bên thứ ba qua videocaptioner.cn; đồng thời có cloud trực tiếp và local.
- Giữ pipeline, config/CLI hiện có, millisecond canonical và `editor-project-v1`.
- Không đổi engine mặc định chỉ dựa trên quảng cáo hay benchmark của nhà cung cấp.

## Thứ tự thực hiện

| Gói | Nội dung | Phụ thuộc | Điều kiện hoàn thành |
| --- | --- | --- | --- |
| S1 (offline hoàn tất) | Nền API tương thích và preset videocaptioner.cn/Groq/OpenAI/Custom | Code hiện có | Request/probe/parser theo capability, cache cách ly, config cũ hoạt động; text-only có giới hạn rõ ràng; gate offline |
| S2 (code/offline + GPT gateway smoke S5.2) | Nhận dạng text-only → alignment tiếng Trung → SRT | S1 | GPT gateway→strict alignment→SRT đã qua source/EXE trên clip public ngắn; phồn thể chưa đạt |
| S3 (code/offline, chờ native API) | Soniox v5 và Scribe v2, timestamp + speaker native | S1 | ASR mới đưa speaker xuyên split/optimize/translate input/editor; save/load speaker không mất |
| S4 (code/offline; chờ nghiệm thu ngôn ngữ) | Quan hệ người nói/người nghe và xưng hô Trung→Việt | S3; đường hybrid nối sau S5 | Mapping theo cặp/cảnh, user override, dịch lại và cache nhất quán; chưa có benchmark người nghe/xưng hô |
| S5 (local-hybrid + gateway S5.2, dừng review) | Qwen3-ASR local và diarization pyannote cho local/gateway | S2; reuse speaker contract S3 | Qwen/Community-1 source/EXE; GPT hybrid source/EXE; Whisper source pass, EXE HTTP 429; còn thiếu chất lượng/Qt teardown |
| S6 | Benchmark, chọn preset mặc định và nghiệm thu EXE | S2–S5 | Có kết quả thực trên video Trung, CER/timing/speaker/xưng hô, artifact và workflow thật |

Mốc nghiên cứu A được tách thành xác minh tài liệu trong S1 và smoke API thật khi có credential
phù hợp. Thiếu credential không ngăn hoàn thành phần offline, nhưng online phải ghi chưa nghiệm thu.
S3 có thể được ưu tiên trước S2 sau S1 nếu cần sớm luồng có timestamp/speaker native. Thứ tự
này không yêu cầu chạy nhiều agent hoặc nhiều task đồng thời.

## S1 — task đầu được giao thực hiện

### S1.1. Kiểm tra hiện trạng và chốt hợp đồng API

Đọc AGENTS/README/status mới nhất, architecture và tìm call site bằng rg. Rà soát:

- `core/asr/whisper_api.py`, `transcribe.py`, `base.py`, `chunked_asr.py`.
- `core/llm/check_whisper.py`, `client.normalize_base_url`.
- `core/entities.py`, `ui/common/config.py`, `ui/task_factory.py`.
- Settings view/WhisperConnectionThread, CLI config/parser/validators/commands.
- Test ASR, probe, settings và config precedence; PyInstaller import/resource khi cần.

Đối chiếu lại tài liệu provider trước khi viết request. Dữ kiện đã xác minh:

| Profile | API Base | Model cần ưu tiên | Giao thức đầu ra |
| --- | --- | --- | --- |
| VideoCaptioner API | `https://api.videocaptioner.cn/v1` | `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe` | Whisper legacy hoặc JSON text theo model |
| Groq | `https://api.groq.com/openai/v1` | `whisper-large-v3`, `whisper-large-v3-turbo` | verbose_json với words/segments |
| OpenAI | `https://api.openai.com/v1` | Whisper và GPT transcription theo tài liệu hiện hành | Capability tường minh, không suy từ tên provider |
| Custom | User nhập | Model ID nhập tay | Cho chọn request profile có kiểm soát; giữ đường Whisper-compatible cũ |

Nguồn: [gateway](https://docs.videocaptioner.cn/models?type=audio&model=gpt-4o-transcribe),
[Groq](https://console.groq.com/docs/speech-to-text),
[OpenAI](https://developers.openai.com/api/docs/guides/speech-to-text).
Catalog/GET models không phải bằng chứng inference hoặc timestamp hoạt động.

### S1.2. Capability và kết quả nhận dạng

- Thêm dataclass/registry nhẹ dưới `core/asr/`, không phụ thuộc Qt/Torch.
- Tách provider, model và request profile. Khai báo response formats, timestamp levels,
  language/hints, giới hạn upload và hỗ trợ speaker khi đã có tài liệu.
- Không thiết kế plugin framework lớn hoặc thay toàn bộ factory nếu chưa cần.
- Dùng result trung gian có text và timing tùy chọn khi cần; bảo toàn API `transcribe()->ASRData`
  cho đường phụ đề có timing. Không tạo timestamp 0 hoặc chia đều từ để ép text-only vào ASRData.
- Model mới nhập tay không bị loại chỉ vì chưa nằm trong preset; có override kiểu Whisper/JSON
  với validation rõ ràng. Không đoán mọi model cùng chữ “transcribe” có capability giống nhau.

### S1.3. Request/parser và probe dùng chung logic

- Whisper/Groq giữ verbose_json và chọn timestamp theo yêu cầu/khả năng thực tế.
- GPT text-only gửi JSON, không gửi verbose_json/timestamp không được hỗ trợ.
- Probe dùng cùng builder/parser; có thể báo “nhận dạng thành công, model không trả timestamp”.
  Probe không bị chặn bởi guard dành riêng cho xuất SRT, và không khai báo SRT đã hỗ trợ.
- Đường tạo phụ đề của model đã biết là text-only phải preflight trước upload: báo thiếu
  alignment (S2). Nếu response thực bất ngờ thiếu timing, báo lỗi domain dễ hiểu, không KeyError.
- Handle words-only/segments-only/empty/silence/malformed; word timing thiếu không được báo đã có.
  Có thể dùng segment timing cho chế độ câu nếu hợp lệ, nhưng phải báo downgrade rõ ràng.
- MIME/extension khớp bytes thực; kiểm tra file size thực trước khi gửi. Dùng filename trung tính.
- Timeout hữu hạn, retry có giới hạn; không retry vô hạn 401/403/404/400 hoặc tự đổi provider.
  Giữ contextvars khi chạy song song; không tăng phạm vi sang rewrite toàn bộ cancellation.

### S1.4. GUI/CLI và cấu hình

- Preset gợi ý base/model; giữ `--asr whisper-api` và các `whisper_api.*` cũ.
- Mở lại settings không reset model/custom URL/key. Đổi provider không tự gửi key cũ sang host mới;
  không xóa credential đã lưu. Nếu bổ sung key config, có defaults và precedence tương thích.
- Có model nhập tay và chỉ dẫn timing dễ hiểu. Tiếng Trung là ưu tiên gợi ý của tính năng mới,
  không overwrite ngôn ngữ user đang lưu.
- Nút probe chạy worker, không network khi mở settings. Giữ kết nối và kiểm tra chức năng riêng.
- UI text mới qua tr()/TS và sync translations; không sửa tay QM.

### S1.5. Cache và log

- Fingerprint có version, audio/config tất định, endpoint đã chuẩn hóa không có secret,
  model, language/prompt và timing/request mode; không lẫn cùng model ở hai gateway.
- Không đưa API key vào key/log. Prompt được hash, không nằm thô trong tên cache hay dòng cache log.
- Không đọc cache legacy có thể lẫn endpoint cho đường mới; không xóa toàn bộ cache của user.
- Credential truyền tường minh; không ghi os.environ; subprocess dùng child_environment().

### S1.6. Test matrix bắt buộc

| Nhóm | Ca kiểm thử có ý nghĩa |
| --- | --- |
| Request | Whisper/Groq timestamp đúng; GPT JSON không có tham số sai; language auto/zh; custom profile; base không lặp `/v1` |
| Response | words/segments/text-only/empty/malformed; seconds→ms; thiếu timing là lỗi domain hoặc kết quả text rõ ràng |
| Probe | Reuse request policy; text-only thành công không bị báo lỗi auth; phân biệt transcription với subtitle readiness |
| Preflight | Text-only không upload khi yêu cầu subtitle chưa có aligner; quá byte limit không gửi request vô ích |
| Cache | Đổi host/model/prompt/timing tạo key khác; cấu hình tương đương cho key ổn định; không lộ secret/prompt |
| Config/UI | Settings cũ giữ nguyên; custom URL/model; CLI precedence; đổi host không tái dùng key tự động; QThread wait |
| Lỗi | 401/403, 404 model/route, 413, 429, timeout/5xx, retry hữu hạn, không log raw response nhạy cảm |

Dùng dữ liệu giả ngắn, không lấy transcript riêng làm fixture. Offline contract test không
thay thế API thật. Kiểm tra test/import thực sự dùng source của worktree, không vô tình dùng
editable install trỏ về checkout gốc. Môi trường project phải là Python 3.10–3.12.

Gate: ruff `videocaptioner/ tests/`, pyright `videocaptioner/`, CLI tests, ASR/probe/settings tests
gần thay đổi, sync translations. Chạy full offline nếu thay core shared đáng kể. Dùng fallback
interpreter/basetemp như AGENTS khi gặp ACL; không ghi AppData thật để vượt lỗi môi trường.

Nếu thêm runtime import/resource, kiểm tra spec và smoke artifact tên riêng theo AGENTS.
S1 không mặc định rebuild/overwrite bản phân phối của user; báo rõ phạm vi gate artifact đã chạy.

### Giới hạn và bàn giao S1

S1 chưa tạo SRT từ GPT text-only, chưa cài Qwen/pyannote, chưa tích hợp Soniox/Scribe native,
chưa sửa xưng hô hay mặc định engine. Chức năng mới dùng được là cấu hình provider, request/probe
đúng model và đường ASR có timestamp tương thích; S2 hoàn thiện phụ đề cho text-only.

Hoàn tất code và gate offline trước khi báo thiếu token. Nếu có credential đã được cấu hình cho
đúng provider, chỉ smoke audio công khai/tổng hợp ngắn trong phạm vi kế hoạch được duyệt; không
copy key vào prompt/fixture, không dùng media user chưa chọn, không tạo token hay nạp tiền.
Ghi source/routing/model, pass/fail/skip và usage tối thiểu không nhạy cảm; không claim online pass
chỉ từ catalog. Thiếu credential thì ghi rõ, không dừng toàn bộ implementation vì lý do đó.

Task đầu cập nhật status.md khi có code/behavior/validation bền vững; báo file đổi, tests,
online chưa chạy, và các đầu việc S2. Không commit/push/tag/GitHub. Dừng ở S1 để user review.

## Bàn giao S1 — 2026-09-07

### Hành vi đã triển khai

- `api_profiles.py` giữ registry nhẹ, không import SDK/Qt: provider, model, request profile,
  format/timestamp, language/prompt, speaker (false trong S1) và byte limit. `auto` chỉ nhận biết
  các model ID khai báo tường minh; ID khác dùng Whisper legacy để giữ config cũ. User có thể chọn
  `whisper`/`json-text` cho alias riêng. Không suy capability từ chuỗi con “transcribe”.
- `api_transcription.py` là request/parser/transport chung. Whisper/Groq yêu cầu segment hoặc
  word+segment theo chế độ; GPT dùng JSON, không gửi timestamp. `TranscriptionResult` giữ text và
  words/segments tùy chọn; ASRData vẫn canonical ms. Text-only được probe nhưng đường subtitle
  preflight chặn trước đọc/chia audio/upload vì chưa có alignment. Không mở flow TXT riêng ở S1.
- Parse words-only, segments-only và silence; response sai kiểu, timestamp thiếu/âm/NaN/đảo chiều
  là lỗi domain. Khi đòi word nhưng chỉ có segment, dừng với hướng dẫn chọn chế độ câu; không âm
  thầm báo có word timestamp. Probe nêu mức timing quan sát được, không echo transcript.
- Signature bytes quyết định WAV/MP3/FLAC/M4A và MIME; multipart dùng filename trung tính.
  Byte cap 25.000.000 trước gửi (gateway/custom là cap bảo thủ của app, chưa đo quota tài khoản).
  Timeout connect/pool 10 s, read/write 120 s; tối đa 3 lần với backoff 0,5/1 s chỉ cho 429,
  5xx hoặc lỗi kết nối/timeout. Không retry 400/401/403/404/413, không theo redirect; lỗi hiển thị
  không chứa body provider. Timeout là theo thao tác I/O, không phải deadline tuyệt đối toàn job.
- Cache `WhisperAPI:v2-<sha256>` tách audio SHA-256, endpoint chuẩn hóa, provider/model,
  language, effective prompt, request/timing profile. Không đọc cache legacy; không xóa cache user.
  Key/prompt/endpoint không xuất hiện trong cache key/log. Credentials truyền tường minh.
- Cả hai mặt settings có preset/profile, model nhập tay và hint timing qua tr(). Chuyển preset
  giữ cấu hình từng preset, giữ key theo endpoint; đổi URL thủ công cũng cách ly key. Ngôn ngữ
  đã lưu không đổi. Chỉ bấm probe mới chạy worker chung trong `ui/thread/`, giữ contextvars.
- CLI giữ key/flag/exit code cũ, thêm `--whisper-provider`, `--whisper-request-profile`, config
  `whisper_api.provider`/`request_profile` và env tương ứng (thêm env model). Thứ tự ưu tiên cũ
  vẫn giữ; đổi base/provider từ lớp cao hơn không thừa kế key endpoint cũ. Chuỗi lệnh `config set`
  đổi provider/base cũng giữ key cũ trong kho riêng và không gửi nó sang endpoint mới.
- Không thêm dependency, GPU runtime, subprocess, dynamic import hay loại resource mới.
  Spec hiện có collect_submodules toàn package và bundle cả thư mục translations; không cần đổi
  spec/build EXE ở S1. Các TS ghi source mới (zh còn unfinished/fallback English); tiếng Việt dùng
  JSON runtime đã đồng bộ, không sửa tay/compile lại QM.

### Bằng chứng kiểm thử

- Dùng interpreter Python 3.12.13 có sẵn từ môi trường project; worktree chưa có `.venv`, không
  cài/sync dependency. Đã xác nhận `videocaptioner.__file__` nằm trong worktree; đặt `PYTHONPATH`
  tới worktree và pyright `--venvpath` tới môi trường có sẵn. Không sửa checkout nguồn.
- `ruff check videocaptioner/ tests/`: pass. `pyright videocaptioner/`: 0 error, 0 warning.
- Toàn bộ CLI và ASR/probe/settings mới được chạy riêng; full offline cuối:
  **720 passed, 5 skipped, 51 deselected**, 76,48 s, Qt offscreen, FFmpeg có sẵn được thêm vào
  PATH của process test, basetemp ngắn và settings/cache test cô lập.
- 5 skip: một QtMultimedia playback cần backend native, bốn test TTS cần credential ngoài.
  51 deselected mang marker integration/slow/llm. Warning còn lại: pydub/audioop deprecation.
- Full offline đã tìm ra và giúp sửa hồi quy import SDK OpenAI từ metadata/config lúc startup;
  guard `test_lightweight_config_import_does_not_load_provider_sdks` hiện pass.
- Test mới có HTTP MockTransport qua SDK thật cho multipart/probe, matrix HTTP 400/401/403/404/
  413/429/5xx/302, timeout/kết nối, không lộ body trong traceback; cache không đọc legacy;
  preflight không upload, CLI exit 5; preset/custom/language/key isolation; worker được wait().
- Đã xem bản render settings tiếng Việt (offscreen có nạp font Windows) với preset gateway,
  model GPT và thông báo cần alignment. Đây là UI offline, không phải nghiệm thu inference.
- `scripts/sync_translations.py --check`: pass sau sync JSON. `git diff --check`: pass.

### Phạm vi online và đầu vào S2

Đã đọc lại tài liệu [OpenAI timestamp](https://developers.openai.com/api/docs/guides/speech-to-text)
và [Groq upload/format](https://console.groq.com/docs/speech-to-text). Công cụ web không tải được
trang docs gateway trong lượt triển khai; preset/request gateway dựa trên dữ kiện đã chấp nhận
trong tài liệu nghiên cứu và prompt bàn giao, chưa xác minh inference mới.

**Online chưa chạy**: worktree không có settings ASR và biến môi trường ASR không có key;
không đọc/copy credential checkout nguồn. Không coi mock, catalog hay probe giả là E2E.
Chưa build EXE, chưa nghiệm thu video Trung→Việt hoặc chi phí/chất lượng/timing API thật.

S2 nhận `TranscriptionResult` (text + timing tùy chọn) và builder/parser này làm đầu vào; bổ sung
aligner tiếng Trung chạy riêng, pin revision, validate word/character spans canonical ms, offset
chunk và đoạn không align được. Chỉ bỏ guard subtitle khi có aligner đã nghiệm thu. Cần key gateway
đúng quyền model và clip Trung công khai/tổng hợp ngắn để đo JSON→alignment→SRT thật. Chưa tự làm S2.

### Danh sách file trong thay đổi S1

- `README.md`
- `docs/dev/asr-implementation-2026-09.md`
- `docs/dev/asr-provider-plan-2026-09.md`
- `docs/dev/asr-step-1-prompt.md`
- `docs/dev/asr-step-2-prompt.md`
- `resource/translations/VideoCaptioner_en_US.ts`
- `resource/translations/VideoCaptioner_vi_VN.json`
- `resource/translations/VideoCaptioner_zh_CN.ts`
- `resource/translations/VideoCaptioner_zh_HK.ts`
- `status.md`
- `tests/test_asr/test_api_contract.py`
- `tests/test_cli/test_whisper_profiles.py`
- `tests/test_ui/test_whisper_profiles.py`
- `videocaptioner/cli/commands/transcribe.py`
- `videocaptioner/cli/config.py`
- `videocaptioner/cli/main.py`
- `videocaptioner/core/asr/api_profiles.py`
- `videocaptioner/core/asr/api_transcription.py`
- `videocaptioner/core/asr/transcribe.py`
- `videocaptioner/core/asr/whisper_api.py`
- `videocaptioner/core/entities.py`
- `videocaptioner/core/llm/check_whisper.py`
- `videocaptioner/resources/translations/VideoCaptioner_vi_VN.json`
- `videocaptioner/ui/common/config.py`
- `videocaptioner/ui/common/whisper_settings.py`
- `videocaptioner/ui/components/WhisperAPISettingWidget.py`
- `videocaptioner/ui/components/WhisperProfileCards.py`
- `videocaptioner/ui/task_factory.py`
- `videocaptioner/ui/thread/whisper_connection_thread.py`
- `videocaptioner/ui/view/setting_interface.py`

## Bàn giao S2 — 2026-09-07

### Phạm vi và validation

Triển khai từ đúng commit S1 `43bb76f45d8dc12cd107fbcbd92c7e21ab811cc3`, không lấy master
làm baseline. Không sửa checkout gốc. Giai đoạn implementation dừng trước commit/push; sau đó
user yêu cầu commit/push và chuẩn bị prompt S3. Commit code S2 là
`96470bf7c60eb7598f61eb7d450327011f9f19c8`. Code S2 dùng factory CLI/GUI hiện có,
runtime Qwen riêng và policy strict; chi tiết thiết kế, cài đặt, cache/cancel, phép đo và giới hạn
nằm ở [ASR alignment S2](asr-alignment-s2.md).

- Ruff toàn `videocaptioner/ tests/` và hai script runtime/builder: pass.
- Pyright toàn `videocaptioner/`: **0 error, 0 warning**.
- Gate gần thay đổi gồm toàn CLI, ASR contract/alignment và settings: **193 passed** trước
  test regression vòng đời worker cuối. Full offline cuối có cả regression mới: **768 passed,
  5 skipped, 51 deselected**, 83.74 s. 5 skip/51 deselect giữ ý nghĩa như S1 (native playback,
  TTS/service ngoài và marker integration/slow/llm); warning còn lại audioop deprecation.
- `scripts/sync_translations.py --check`: pass; `git diff --check`: pass.
- Dùng Python 3.12.13 của môi trường project có sẵn, đã xác minh import source đúng worktree;
  không sync/thay dependency Qt. Pyright trỏ venv đó. Test Qt offscreen, config/env/cache cô lập,
  basetemp ngắn, PATH FFmpeg có sẵn. Cache/media/build/log mới nằm ngoài Git.
- Test bao phủ JSON wire không timestamp, parser→aligner→SRT/cache, language/runtime/health
  preflight trước đọc/upload, lỗi cache/coverage/timing/silence/mismatch, punctuation/names/numbers/
  giản-phồn thể, chunk offset/overlap/tail, async retry/cancel in-flight, manifest/lifecycle và
  contextvars. Test worker completion cũ không được wait/reset worker mới trên Qt main thread.
- Runtime CUDA đã build/download model pin thành công. Local smoke thật tạo SRT từ clip Qwen
  Trung công khai 4.204 s; phồn thể của clip bị policy strict từ chối. Worker Qt local probe
  thật đã lên ready/đóng sạch, Qt process không có Torch/Qwen; đã xem render settings tiếng Việt
  với font Windows. Đây chưa phải workflow qua EXE.

**Chưa nghiệm thu GPT gateway→SRT** vì worktree/env không có key ASR. Không copy credential/media
từ checkout nguồn, không suy inference từ catalog/mock. Chưa benchmark chất lượng trên video dài,
names/numbers/phồn thể hoặc corpus có nhãn, chưa đo p95; chưa làm pipeline dịch Việt/API thật.
Runtime là venv cài tại máy, chưa portable/installer; base EXE cần runtime riêng.

### Gate artifact S2

1. **PyInstaller exit 0**, duy nhất `VideoCaptioner.spec`, tên
   `VideoCaptioner-ASR-S2-Review-20260907`. Build clean thành công; rebuild cuối cập nhật regression
   worker trên đúng output do session tạo, đã kiểm tra chưa có AppData trước ghi đè.
   Có **6 WARNING**, không có ERROR: optional urllib3 WebAssembly `js`, optional `curl_cffi`/
   `yt_dlp_ejs`, hidden import `tzdata`/`sip`, AppKit macOS. Hai SyntaxWarning trong modelscope
   upstream. Không coi những cảnh báo này là đã kiểm chứng mọi workflow tùy chọn.
2. **Artifact tồn tại**: `dist/VideoCaptioner-ASR-S2-Review-20260907/` (phân phối nguyên onedir).
   EXE 30,985,630 byte, timestamp máy `2026-09-07 09:04:20`; SHA-256
   `133d04bb8c926b330363fc49a0790704c34c555ba2e8a15e054e3056a55d5cb6`.
   Onedir trước smoke: 572 file / 237,070,845 byte. Đã đối chiếu bytecode các module S2 chính
   (kể cả nested code) với source và recipe runtime với source; không có Torch/Qwen/Torchaudio
   trong PYZ. Artifact là bản review/dev, không phải release; không chép riêng EXE.
3. **Smoke GUI từ chính artifact pass**: với FFmpeg có sẵn trên PATH của process smoke,
   cửa sổ `Trợ lý phụ đề Kaka -- VideoCaptioner` hiện; sau 25 s process vẫn sống, working set
   110,977,024 byte. Đóng đúng process do smoke tạo bằng CloseMainWindow; kiểm tra không còn
   process EXE/sidecar của lượt thử. AppData của artifact mới tách biệt dữ liệu user; log chỉ
   có version check, không có import/resource error trong startup đã quan sát.
4. **Workflow media/API từ EXE chưa nghiệm thu**; gateway GPT→SRT và dịch Việt chưa chạy vì thiếu
   key. Runtime Qwen/SRT thật và Qt local health ở trên là phép đo từ source, không gộp thành
   acceptance E2E của EXE. Base artifact không chứa runtime GPU/model.

### Danh sách file S2

```text
README.md
VideoCaptioner.spec
status.md
docs/dev/asr-implementation-2026-09.md
docs/dev/asr-alignment-s2.md
runtime/alignment/bridge.py
runtime/alignment/requirements.in
runtime/alignment/requirements-win-py312.lock
runtime/alignment/runtime-manifest.json
scripts/build_alignment_runtime.py
videocaptioner/core/asr/aligned_api.py
videocaptioner/core/asr/alignment/__init__.py
videocaptioner/core/asr/alignment/audio.py
videocaptioner/core/asr/alignment/contract.py
videocaptioner/core/asr/alignment/runtime.py
videocaptioner/core/asr/api_profiles.py
videocaptioner/core/asr/api_transcription.py
videocaptioner/core/asr/transcribe.py
videocaptioner/core/llm/check_whisper.py
videocaptioner/cli/commands/transcribe.py
videocaptioner/ui/components/WhisperAPISettingWidget.py
videocaptioner/ui/components/WhisperProfileCards.py
videocaptioner/ui/thread/alignment_thread.py
videocaptioner/ui/thread/transcript_thread.py
videocaptioner/ui/thread/subtitle_pipeline_thread.py
videocaptioner/ui/view/setting_interface.py
videocaptioner/ui/view/transcription_interface.py
tests/test_asr/test_alignment.py
tests/test_ui/test_whisper_profiles.py
resource/translations/VideoCaptioner_en_US.ts
resource/translations/VideoCaptioner_zh_CN.ts
resource/translations/VideoCaptioner_zh_HK.ts
resource/translations/VideoCaptioner_vi_VN.json
videocaptioner/resources/translations/VideoCaptioner_vi_VN.json
```

### Đầu vào S3

Tại thời điểm bàn giao S2, S3 chưa triển khai. Có thể dùng `ASRData`/canonical ms, registry/request/parser S1 và contract
alignment S2; metadata speaker chưa thêm. Không giả định word/character alignment là speaker
identity. Trước khi nghiệm thu GPT→SRT cần key gateway đúng quyền model và bộ clip Trung được
user cho phép; cần đánh giá tiếp độ phủ policy strict/phồn thể trước chọn mặc định sản phẩm.

## Bàn giao S3 — 2026-09-07

Code chạy từ baseline `d21251a5d1be3d4baceec5a3e8d6869ceb4877c5`, không phải master;
nhánh review `codex/asr-s3-native`, không commit/push/tag/GitHub. S2 ancestor đã xác minh.
Thiết kế, nguồn provider đã đọc, cấu hình, lifecycle, metadata/cache và giới hạn được ghi trong
[ASR native S3](asr-native-s3.md).

### Validation

- Python **3.12.13**, dùng interpreter project có sẵn và PYTHONPATH trỏ đúng worktree; đã xác minh
  `videocaptioner.__file__`. Không sync/thay dependency, không đọc credential/media checkout nguồn.
- Ruff toàn `videocaptioner/ tests/` pass; pyright toàn source **0 errors, 0 warnings**.
- Toàn CLI cùng native ASR/pipeline/settings mới: **171 passed**. Full offline cuối:
  **862 passed, 5 skipped, 51 deselected**, 96,71 s; thêm **94 test** so với baseline 768.
  Marker `not integration and not slow and not llm`; Qt offscreen, FFmpeg có sẵn, basetemp ngắn,
  config/env/cache test giữ cơ chế cô lập. Skip gồm native playback và TTS cần service/API;
  warning full suite còn audioop deprecation. Không tính skip/offline thành online acceptance.
- Rà render settings tiếng Việt với font Noto Sans SC trong app resources: sửa chiều cao QLabel
  cho phần giải thích dài; **17 tests settings/UI pass** sau sửa layout này. Chỉnh layout cuối
  không đổi core đã full-test. JSON vi được đồng bộ, TS en/zh cập nhật. Máy thiếu `lrelease`
  trên PATH/môi trường project; không cài package hay sửa QM thủ công. QM giữ bản baseline,
  chuỗi zh mới hiện fallback English; Vietnamese JSON mới có trong artifact.
- Test request/parser/cancel của cả hai provider, poll backoff/deadline, job failed, malformed/missing
  timing/IDs, ambiguous submit không lặp, giới hạn bytes/duration, tiếng Trung/tên/số/dấu câu,
  subwords, silence/events, unknown speakers và overlap. Cancel trước upload, trong từng stage,
  giữa upload→submit, cleanup 409 không xóa input của job đang chạy; Scribe chỉ xóa transcript ID
  response vừa trả. HTTP/body/key không lọt vào error output.
- Test cache fingerprint/invalidation/scope, CLI precedence/boolean/key isolation, settings không
  network, contextvars và QThread wait. Pipeline giữ speaker/events qua split/merge/optimize/translate,
  editor import/save/load/undo/redo; regression unknown speaker không đổi provenance và legacy fuzzy
  chunk merge không làm mất metadata. Giữ guards S1/S2 qua suite baseline.
- Regression cuối tách connection failure khỏi timeout thay vì phân loại theo chuỗi lỗi;
  **67 native API tests pass** trước full suite cuối. Một test deadline 20 ms từng fail do timer
  Windows cho mock kịp completed; đã dùng clock điều khiển, chỉ hết hạn sau khi thấy processing.
  Full suite cuối ở trên đã pass với regression và test clock mới.
- `sync_translations.py --check` và `git diff --check` pass. Các file validation log/media/cache/
  screenshot/build chỉ ở vùng ignored của worktree, không track.

### Giới hạn và đầu vào S4

Không có native key cấu hình trong worktree/env nên **Soniox/Scribe online chưa chạy**. Không
đổi việc này thành pass từ probe/catalog/mock. **GPT gateway→SRT và phồn thể S2 vẫn chưa nghiệm thu**;
không nạp/copy runtime Qwen từ checkout khác. Runtime alignment vẫn riêng, không bundle GPU vào Qt.

Cloud xử lý toàn file; ngoài cap sẽ dừng, không tự chia/chắp speaker. Metadata unknown giữ unknown;
overlap giữ mọi cue, nhưng overlay preview chỉ chọn một active cue. Split editor native hiện dừng
review vì thiếu text boundary tường minh; user vẫn sửa text/timing/speaker qua CommandStack.
Optimizer native một cue mỗi request tránh dịch chuyển association giữa người nói, nhưng có thể
tăng số request/độ trễ so với batch cũ. Không đổi prompt dịch theo quan hệ hay tự gán giọng.
S4 có thể dùng metadata typed, ID scoped và speaker override đã persist, chưa có bảng nhân vật/
người nghe/quy tắc xưng hô hoặc benchmark chất lượng.

### Gate artifact S3

1. **PyInstaller exit 0**, `VideoCaptioner.spec --clean --noconfirm`, tên
   `VideoCaptioner-ASR-S3-Review-20260907`. **6 WARNING, 0 ERROR**: optional WebAssembly `js`,
   `curl_cffi`/`yt_dlp_ejs` data collection, hidden imports `tzdata`/`sip`, AppKit macOS.
   Lượt build tăng dần từng giữ bytecode UI cũ; artifact bàn giao đã build sạch lại và được
   đối chiếu **36 module thay đổi (cả nested code) khớp source cuối**, cùng JSON vi bundle/fallback.
   Không có Torch/Qwen/Torchaudio trong PYZ, không bundle GPU runtime/model.
2. **Artifact tồn tại**: `dist/VideoCaptioner-ASR-S3-Review-20260907/`, nguyên thư mục onedir.
   EXE **31.023.698 byte**, timestamp máy **2026-09-07 10:13:24**, SHA-256
   `0e3be9f494e4f82a76274c7563175cf222cfcb03feea8f5e91db6b343761ebec`.
   Trước smoke: **572 file / 237.121.067 byte**. Chỉ thay output do phiên này tạo, kiểm tra chưa có
   AppData trước rebuild; không đụng artifact/data của user hoặc phân phối riêng file EXE.
3. **Smoke startup từ chính artifact pass**: process sống qua **25 s**, working set **99.835.904 byte**.
   Launcher chạy hidden; EnumWindows đúng PID xác minh cửa sổ Qt
   `Trợ lý phụ đề Kaka -- VideoCaptioner`. Gửi WM_CLOSE vào chính cửa sổ đó, **graceful exit 0**,
   **0 process artifact sót**, log **0 Traceback/ERROR/CRITICAL**. Env child lọc OPENAI_*/
   VIDEOCAPTIONER_*, dùng FFmpeg đã có; AppData mới nằm riêng trong artifact.
4. **Workflow media/API từ EXE chưa nghiệm thu**. Chưa có key Soniox/Scribe trong worktree/env;
   các test provider là offline MockTransport. Không gộp startup với recognition/timing/speaker
   thật, GPT gateway→SRT hoặc benchmark chất lượng phồn thể/timing/diarization.

### Danh sách file S3

```text
README.md
VideoCaptioner.spec
docs/dev/asr-implementation-2026-09.md
docs/dev/asr-native-s3.md
resource/translations/VideoCaptioner_en_US.ts
resource/translations/VideoCaptioner_vi_VN.json
resource/translations/VideoCaptioner_zh_CN.ts
resource/translations/VideoCaptioner_zh_HK.ts
status.md
tests/test_asr/test_native_asr.py
tests/test_asr/test_speaker_pipeline.py
tests/test_cli/test_native_asr.py
tests/test_ui/test_native_asr.py
videocaptioner/cli/commands/process.py
videocaptioner/cli/commands/subtitle.py
videocaptioner/cli/commands/transcribe.py
videocaptioner/cli/config.py
videocaptioner/cli/main.py
videocaptioner/cli/validators.py
videocaptioner/core/asr/asr_data.py
videocaptioner/core/asr/chunk_merger.py
videocaptioner/core/asr/metadata.py
videocaptioner/core/asr/native_api.py
videocaptioner/core/asr/native_profiles.py
videocaptioner/core/asr/native_result.py
videocaptioner/core/asr/transcribe.py
videocaptioner/core/editor/adapters.py
videocaptioner/core/editor/commands.py
videocaptioner/core/editor/models.py
videocaptioner/core/editor/project_store.py
videocaptioner/core/entities.py
videocaptioner/core/optimize/optimize.py
videocaptioner/core/split/split.py
videocaptioner/core/subtitle/editing.py
videocaptioner/core/translate/base.py
videocaptioner/resources/translations/VideoCaptioner_vi_VN.json
videocaptioner/ui/common/config.py
videocaptioner/ui/common/native_asr_settings.py
videocaptioner/ui/components/NativeASRSettingWidget.py
videocaptioner/ui/components/transcription_setting_card.py
videocaptioner/ui/task_factory.py
videocaptioner/ui/thread/native_asr_thread.py
videocaptioner/ui/thread/subtitle_pipeline_thread.py
videocaptioner/ui/thread/subtitle_thread.py
videocaptioner/ui/thread/transcript_thread.py
videocaptioner/ui/view/home_interface.py
videocaptioner/ui/view/setting_interface.py
videocaptioner/ui/view/subtitle_interface.py
videocaptioner/ui/view/transcription_interface.py
videocaptioner/ui/view/video_editor_interface.py
```

## Bàn giao S4 — 2026-09-07

Triển khai trực tiếp trong working tree S3 user chỉ định, không tạo checkout/worktree mới.
Đầu phiên xác minh HEAD S2 `d21251a` + đúng 50 file S3 dirty và prompt S4 untracked; đã đọc diff,
manifest/source metadata/native/settings/tests. User yêu cầu riêng commit/push S3 trước:
`327c214` gồm đúng 50 file, push nhánh `codex/asr-s3-native` thành công. Trong giai đoạn triển khai,
prompt S4 được giữ nguyên untracked và code dừng review. Sau đó user yêu cầu submit/push:
commit S4 **`8558082`** gồm 36 file S4 và prompt S4 có sẵn, không đổi nội dung prompt cũ.

### Code và review nền

- Hướng dẫn sử dụng/schema, policy, scope, dữ liệu có bằng chứng, snapshot và cache:
  [ASR context S4](asr-context-s4.md). Model immutable trong core; không suy danh tính/người nghe
  từ nhãn ASR. User/lock có ưu tiên; proposal thiếu cue evidence bị từ chối, xung đột phải review.
- Sửa nền S3: cue ID trước đây chưa đi xuyên ASR/JSON; JSON CLI input bị validator từ chối;
  manual load bảng làm mất events; speaker override có thể thêm prefix lặp và mất provenance
  sau handoff. Nay giữ cue ID + ASR provenance/override riêng, context/events qua JSON/editor.
  Native ID theo request scope để context cue cũ không tự bám request mới.
- LLM nhận snapshot toàn tài liệu trước chunking, mapping/rule resolve có hướng, source window và
  cue evidence. Selection 1–9 cue không bị ngưỡng global-context cũ; chỉ cập nhật selection.
  Prompt tách thoại khỏi chỉ dẫn ứng dụng, không trả/ghi metadata hay timing từ response.
- GUI có bảng nhân vật/cảnh/mapping/người nghe/quy tắc, evidence/status/lock và review; không
  network khi mở. Mutations qua CommandStack; editor dịch selection thành một composite command,
  undo/redo, không đổi TTS text/voice. Kết quả stale bị bỏ. CLI dùng chung context/schema.
- Fingerprint tất định có source, IDs, assignment, rule/scope/evidence/override/lock, policy/model/
  endpoint; không dùng brief LLM ngẫu nhiên. Không xóa toàn cache. Socket S4 có deadline/cancel,
  credential cố định theo job; không gửi raw body lỗi/context vào log. Transport cũ giữ cho
  translator không hỗ trợ context; UI nêu giới hạn hỗ trợ xưng hô.
- Context đã gắn thì re-segmentation dừng để review; không tự gán liên kết cho cue mới. Không thêm
  bộ tự đoán quan hệ bằng LLM, auto voice, S5/S6 hoặc thay engine mặc định.

### Validation source

- Baseline review mới chạy **27 tests pass** trước commit S3. Gate gần S4 trước guard shutdown cuối:
  **60 passed** (47 mới + 13 regression nền), gồm HTTP socket cancel, contextvars, 1–9 cue,
  stale state, precedence/scope, JSON/handoff, UI/CLI và editor undo/redo. Test QThread đều wait.
- Full offline cuối: **910 passed, 5 skipped, 51 deselected**, **105.38 s**. Baseline 862 + 48
  test S4, gồm guard đóng app chờ worker đang dịch; có tăng assertion test S3 để kiểm tra speaker override vẫn giữ nhãn ASR gốc.
  Full lần đầu tìm một kỳ vọng SRT legacy; đã giữ SRT cho table cũ không có ID/metadata/context,
  còn table có association dùng JSON, rồi full-test lại. Không đổi test legacy để che lỗi.
- Ruff toàn `videocaptioner/ tests/`: pass; pyright toàn source **0 errors/0 warnings**;
  sync translations pass. Full suite bao gồm toàn CLI, ASR/subtitle/translate/editor/UI/thread.
- Python **3.12.13**, dùng interpreter project có sẵn với `PYTHONPATH` đã xác minh import đúng
  working tree; pyright chỉ định venv đó. Không sync/cài/thay dependency. Qt offscreen, FFmpeg
  có sẵn trên PATH của process test, basetemp ngắn, fixture cô lập settings/config/env.
- Đã render dialog tiếng Việt 1080×700 với Noto Sans SC, kiểm tra bảng/quy tắc và cuộn ngang;
  JSON vi sync. TS en/zh cập nhật; thiếu lrelease nên QM giữ baseline, chuỗi zh mới fallback English.
- Worktree không có settings LLM và environment không có key LLM. **Chưa chạy bản dịch LLM thật**,
  chưa nghiệm thu chất lượng xưng hô/người nghe bằng người đọc. Mock không là ground truth.
  Giữ nguyên **Soniox/Scribe online, GPT gateway→SRT, workflow media/API EXE chưa nghiệm thu**;
  **phồn thể Qwen strict chưa đạt acceptance**. S2 local alignment/S3 startup là bằng chứng riêng.

### Gate artifact S4

**Bổ sung full SRT Việt theo yêu cầu xem thử (2026-09-07):** từ đủ 30 segment Whisper của clip
Trung, một request `gpt-5.6-terra` trả bản Việt trong 131.56 s. Lượt xuất có timeout riêng 300 s,
không đổi code/timeout app. Đã tạo SRT Việt + song ngữ + JSON/project và sidecar cạnh video;
parse lại đủ 30 cue, giữ nguyên từng cue ID/timestamp (12.560–104.180 s), không dùng word spans
0 ms hoặc thêm speaker giả. Hai lỗi tên/thuật ngữ có bằng chứng caption được sửa riêng trước
dịch, ghi nhật ký local; bản xuất vẫn để user review chất lượng. Đây là artifact xuất từ source,
không đổi gate EXE hay nghiệm thu chất lượng toàn bộ ASR/xưng hô. Không commit/push.

**Bổ sung STT gateway trên cùng clip Trung (2026-09-07):** kiểm tra ba model chuyên dụng trong
catalog bằng builder/parser S1 + SDK thật, cùng audio 111.333 s, zh/default prompt, không cache.
`whisper-1` nhận dạng trong 9.00 s, có 30 sentence spans hợp lệ và 142 word spans (11 duration 0).
Đã xuất toàn bản nhận dạng JSON/SRT bằng timestamp **cấp câu do API cung cấp**, coverage segment
khớp text response (bỏ whitespace), JSON/editor roundtrip pass; không có speaker. Word timing
chưa đạt gate, không sửa/interpolate các span 0 ms để xuất. `gpt-4o-transcribe` trả text trong
4.11 s, không timestamp/speaker; chưa chạy alignment. `gpt-4o-mini-transcribe` HTTP 429 hai lượt
(4.23 và 8.27 s); chưa đủ bằng chứng xác định nguyên nhân 429 hoặc inference của model này.
Hai checkpoint tên/thuật ngữ từ chữ trên video chưa khớp ở cả Whisper và GPT text, nên chưa chấm
chất lượng toàn clip hoặc chọn mặc định. Không test audio-chat/TTS; không đổi source, runtime,
dependency, EXE hoặc policy. Output riêng tư chỉ ở test folder ignored. Các lượt này không thay
thế nghiệm thu media/API từ process EXE hoặc GPT→alignment→SRT.

**Bổ sung clip Trung / model user chọn (2026-09-07):** Soniox zh/diarization xử lý 111.333 s
trong 7.05 s, response 185 token/4 nhãn speaker nhưng parser dừng hai token start=end tại
83.010 và 104.010 s. Giữ nguyên policy; cleanup remote thành công, không resubmit audio.
Toàn transcript được chuyển thành 17 đơn vị text-only có snapshot S4, không bịa timestamp,
và dịch bằng **`gpt-5.6-terra`** (request/response đều xác nhận tên model). Batch 12 đơn vị
timeout 120 s ở lượt đầu; 5 đơn vị có kết quả được cache. Một retry chẩn đoán đúng batch thiếu
với deadline 300 s pass sau 76.31 s, ghép đủ 17 bản dịch và giữ output thô để review. Không sửa
timeout trong app. File Việt/đối chiếu/text-only review lưu local; không coi đây là SRT full clip.
Mẫu native hợp lệ riêng trước lỗi: 80.970 s/17 cue/4 speaker. Spot-check hai frame thấy ASR sai
tên/thuật ngữ; cần review nguồn trước khi chấm lỗi xưng hô hoặc dùng bản Việt. Chi tiết riêng
nằm trong output test ignored; không đưa media/transcript/key/path riêng vào tài liệu Git.

**Bổ sung online sau bàn giao S4 (2026-09-07):** với key và video user chỉ định, đã đo Soniox
`stt-async-v5` toàn audio 260.551 s tiếng Anh, diarization bật/language auto/cache tắt.
Service probe và upload→submit→poll→result hoàn tất trong 13.59 s; response 471 token có 4
nhãn speaker, coverage khớp. **Parser/export toàn clip vẫn fail** vì ba lexical token start=end
(34.890, 102.510, 157.350 s); giữ nguyên guard, không tự sửa timestamp hoặc resubmit trả phí.
Cleanup job-owned remote thành công. Mẫu riêng trước lỗi, 33.150 s/6 cue/3 speaker, có JSON/SRT/
editor roundtrip pass; không gọi mẫu này là output full job thành công.

Gateway GET models HTTP 200 có 366 ID; `gpt-4o-mini` đã inference thật qua LLMTranslator S4,
dịch 6 cue mẫu Anh→Việt trong 3.81 s và giữ metadata. Context chỉ có unknown proposals, chưa
có quan hệ user xác nhận; chưa nghiệm thu hiệu lực directed rules hoặc chất lượng ngôi/xưng hô.
Các model khác mới có bằng chứng catalog. Không test Scribe hoặc GPT transcription/aligner;
phồn thể strict giữ nguyên khoản thiếu. Các phép đo API này chạy từ **source**, không thay thế
gate workflow media/API từ process EXE dưới đây. Không ghi key/transcript/media/path riêng vào Git.

1. Duy nhất `VideoCaptioner.spec`, tên `VideoCaptioner-ASR-S4-Review-20260907`, scratch build
   riêng `build/ASR-S4-Review-20260907`. Build sạch cuối **exit 0**, **6 WARNING, 0 ERROR**:
   optional WebAssembly `js`, `curl_cffi`/`yt_dlp_ejs` data, hidden imports `tzdata`/`sip`, AppKit
   macOS. Hai SyntaxWarning modelscope upstream như baseline. Build đầu còn bytecode trước
   guard shutdown; đã đối chiếu và rebuild sạch trên output S4 do phiên này tạo, chưa có AppData.
2. Artifact **`dist/VideoCaptioner-ASR-S4-Review-20260907/`**, phân phối nguyên onedir.
   EXE **31.057.002 byte**, timestamp **2026-09-07 11:31:30**, SHA-256
   `08dd40819c91152c7fd778b4f81036101ee6db43208844089efc595f58fda252`.
   Trước smoke **573 file / 237.192.253 byte**. Từ archive nhúng trong chính EXE, **21 module S4
   (kể cả nested code) khớp source cuối**; prompt `translate/conversation.md` và JSON vi ở hai
   vị trí khớp bytes. Không có Torch/Qwen/Torchaudio trong PYZ. SHA-256 EXE S3 vẫn nguyên baseline.
3. Smoke startup GUI hidden từ chính artifact: cửa sổ Qt "Trợ lý phụ đề Kaka -- VideoCaptioner",
   sống **25 s**, `WM_CLOSE` vào đúng PID/window → **exit 0**; không process artifact còn lại.
   Log **0 Traceback/ERROR/CRITICAL**. Stderr 103 byte chỉ là thông tin kiểm tra phiên bản
   (`0.0.0-dev` là bản review), không có lỗi import/resource. Harness lần đầu lỗi encoding khi
   in title tiếng Việt sau lúc EXE đã đóng; đã chạy lại UTF-8 và lưu kết quả đầy đủ. Không build
   đè artifact sau khi có AppData, không xóa AppData hay artifact S3.
4. **Workflow media/API từ EXE chưa nghiệm thu**, tương tự các khoản online và phồn thể giữ ở
   trên. Không suy nhận dạng/dịch/xưng hô/TTS từ startup hoặc offline mock.

### Manifest phần S4 (so với commit S3 `327c214`)

S3 kế thừa là toàn bộ 50 file trong commit đó. Danh sách dưới là 36 file thay đổi S4; prompt
`docs/dev/asr-step-4-prompt.md` có từ đầu phiên, giữ nguyên nội dung và được track kèm commit S4.
Tài liệu bàn giao S4.1 nằm ở commit tiếp theo, không đổi source snapshot `8558082`.

```text
docs/dev/asr-context-s4.md
docs/dev/asr-implementation-2026-09.md
README.md
resource/translations/VideoCaptioner_en_US.ts
resource/translations/VideoCaptioner_vi_VN.json
resource/translations/VideoCaptioner_zh_CN.ts
resource/translations/VideoCaptioner_zh_HK.ts
status.md
tests/test_asr/test_speaker_pipeline.py
tests/test_cli/test_conversation.py
tests/test_translate/test_conversation.py
tests/test_ui/test_conversation.py
VideoCaptioner.spec
videocaptioner/cli/commands/subtitle.py
videocaptioner/cli/commands/transcribe.py
videocaptioner/cli/config.py
videocaptioner/cli/main.py
videocaptioner/cli/validators.py
videocaptioner/core/asr/asr_data.py
videocaptioner/core/asr/metadata.py
videocaptioner/core/editor/adapters.py
videocaptioner/core/editor/commands.py
videocaptioner/core/editor/models.py
videocaptioner/core/editor/project_store.py
videocaptioner/core/entities.py
videocaptioner/core/prompts/translate/conversation.md
videocaptioner/core/split/split.py
videocaptioner/core/subtitle/editing.py
videocaptioner/core/translate/base.py
videocaptioner/core/translate/conversation.py
videocaptioner/core/translate/llm_translator.py
videocaptioner/resources/translations/VideoCaptioner_vi_VN.json
videocaptioner/ui/components/conversation_dialog.py
videocaptioner/ui/thread/subtitle_thread.py
videocaptioner/ui/view/subtitle_interface.py
videocaptioner/ui/view/video_editor_interface.py
```

## Bàn giao S4.1 — 2026-09-07

Baseline đúng **47d1cec** trên `codex/asr-s3-native`, working tree sạch lúc bắt đầu; commit code
S4 **8558082** là ancestor. Giai đoạn triển khai thực hiện đủ A–C của followup rồi dừng review,
không commit/push/tag/release hoặc làm S5–S6. Sau đó user yêu cầu submit: code S4.1 được chốt tại
**db23299370f311395fae39069f0983739d259250** (56 file). Commit bàn giao tiếp theo cập nhật status,
tài liệu này và thêm [prompt S5](asr-step-5-prompt.md); không đổi source/artifact đã kiểm thử.
[Hướng dẫn S4.1](asr-s41.md) mô tả config/CLI, schema review, override và lifecycle.

### Thay đổi và validation

- Deadline LLM translation/brief 1–600 s (mặc định 120), chọn 300 qua GUI hoặc `--llm-timeout`;
  schema/validation dùng chung, job chụp credential/config/nguồn trước khi chạy. Không đổi
  model/endpoint và không tự retry HTTP/network POST. Cancel đóng socket và join công việc của job.
- Payload policy `conversation-request-v2`, schema lưu vẫn `conversation-context-v1`; giữ
  glossary, selection/context windows và bằng chứng theo rules/lock/scope. 30 câu tổng hợp:
  **11.595 → 2.044 byte UTF-8 (−82,37%)** cho khối context. Không claim token, tiền hoặc chất lượng.
- Native response lỗi timing/coverage có typed/local `asr-review-v1` tách cache success;
  raw recognition được kiểm tra fingerprint, override `user` và CommandStack undo/redo. GUI/CLI
  mở lại và resume tại máy; lexical zero-time chưa sửa vẫn exit 5/không xuất prefix success.
  Giữ scope/cue/token IDs và overlap; group có override luôn `edited`. Không thay remote cleanup.
- Stale guard editor bỏ playhead/zoom/display state, bảo vệ source/context và target selection.
  Worker dừng hợp tác, không terminate QThread; UI giữ reference qua supervisor đến finished,
  app quit vẫn xử lý Qt events khi join. Old signals không reset worker mới; file output staging
  tránh publish trong lúc cancel. Giữ JSON+SRT normal save, ASS chỉ khi user chọn.
- **Full offline cuối: 986 passed / 5 skipped / 51 deselected, 92,17 s**, tăng 76 test so với
  baseline 910. Gồm toàn CLI và mọi domain gần sửa. Gate gần source cuối **427 passed**;
  ruff toàn source/tests pass; pyright **0 errors/0 warnings**; sync translations/diff-check pass.
  Python **3.12.13**, import đúng checkout, venv/FFmpeg có sẵn; không cài/sync/thay dependency.
- Tests tổng hợp whole word/subword/CJK, known/unknown/overlap, review roundtrip/edit/undo/resume,
  no-success-cache/no-resubmit, deadline/late-response/cancel/cleanup, 1–9 cue và stale source/lock,
  playback/zoom, output staging và QThread wait. Settings/config/env/cache/review cô lập.
- Full đầu tìm compatibility của `stop().executor`; đã giữ public state cũ và dùng private owner
  để join. Một regression cancel tìm deadlock khi chờ future đã bị hủy; collection/join đã sửa.
  Rà cuối thêm dấu hủy bền vững vì Qt xóa interruption flag trước khi GUI nhận queued signal;
  **30 tests UI/lifecycle pass**, rồi full cuối trên pass. Artifact Final dùng tên/scratch mới,
  giữ nguyên bản S4.1 đầu đã smoke và có AppData.
  5 skip: native QtMultimedia playback + 4 TTS/service. 51 deselect theo integration/slow/llm,
  warning offline là audioop deprecation. Không tính offline/mock/skip thành inference acceptance.
- Đã xem render dialog review và card timeout tiếng Việt; chỉnh label timeout hết cắt dòng.
  JSON vi sync cả hai vị trí; TS en/zh cập nhật. Thiếu lrelease, không sửa QM bằng tay;
  chuỗi zh mới dùng fallback English. AGENTS/CLAUDE và dependency lock giữ nguyên.

### Gate artifact riêng S4.1

1. Duy nhất `VideoCaptioner.spec`, tên **VideoCaptioner-ASR-S41-Review-20260907-Final**, scratch riêng
   `build/ASR-S41-Review-20260907-Final` và cache PyInstaller riêng. **Exit 0; 6 WARNING; 0 ERROR**.
   Warning: optional WebAssembly `js`, `curl_cffi`/`yt_dlp_ejs` data collection, hidden import
   `tzdata`/`sip`, AppKit macOS. Thêm **6 SyntaxWarning upstream** (4 pydub, 2 modelscope).
2. Artifact **`dist/VideoCaptioner-ASR-S41-Review-20260907-Final/`**, giữ nguyên onedir khi phân phối.
   EXE **31.093.132 byte**, timestamp local **2026-09-07 15:35:00**, SHA-256
   `2ab4c85035ba64fd59fe96d5686b75ac00139644936bd960a206a419803e4284`.
   Trước smoke **573 file / 237.245.477 byte**. Đối chiếu từ archive của chính EXE: **202 module**
   (bao gồm nested bytecode) khớp source cuối; prompt và JSON vi bundle/fallback khớp bytes;
   không có Torch/Qwen/Torchaudio. Không rebuild sau khi smoke tạo AppData.
3. **Frozen local resume pass**: `asr-review` trên JSON tổng hợp lỗi trả **exit 5**, không có SRT;
   explicit override→JSON trả **exit 0**, mở lại→SRT trả **exit 0**, giữ token ID/scope/edited và
   timing đúng override. `subtitle --help` từ EXE exit 0. Không có provider request hoặc FFmpeg
   trong các command resume này.
4. **Startup GUI từ artifact pass**: hidden launch, đúng cửa sổ Qt VideoCaptioner, sống **25 s**;
   working set **100.245.504 byte**, WM_CLOSE vào đúng PID/window → **exit 0**, **0 process sót**,
   **0 Traceback/ERROR/CRITICAL** trong startup logs/stderr. Stderr chỉ có kiểm tra phiên bản.
   **Workflow media/ASR/LLM API thật từ EXE chưa nghiệm thu**; local JSON và startup là gate riêng.

EXE S4 hiện có vẫn SHA-256 `08dd40819c91152c7fd778b4f81036101ee6db43208844089efc595f58fda252`.
Không ghi đè/xóa media, AppData, work-dir hay artifact S4. Validation log/screenshot/synthetic JSON
và helper của phiên S4.1 nằm trong scratch ignored riêng, không đưa vào Git.

### Giới hạn vẫn giữ

Không inference ASR/LLM thật trong phiên S4.1: checkout không có settings LLM và env key
LLM/native trống; không lấy key từ S4, checkout khác, log/script/lịch sử. Soniox online trước
đây đã nhận dạng nhưng full parser dừng token 0 ms; không dùng prefix cũ để claim full success.
**Scribe online, GPT transcription→alignment→SRT, phồn thể Qwen strict, speaker accuracy và chất
lượng ngôi/xưng hô được người đọc chấm vẫn còn thiếu**. Không làm benchmark corpus, tự gán voice,
Qwen ASR/pyannote, S5–S6 hoặc đổi mặc định.

### Manifest S4.1 so với baseline 47d1cec

56 file thay đổi/thêm mới trong **commit code S4.1 `db23299`**. Prompt S5 và cập nhật trạng thái
submit thuộc commit bàn giao tiếp theo. Không có media, credential, AppData, build/dist, QM hoặc
lockfile trong danh sách:

```text
README.md
VideoCaptioner.spec
docs/dev/architecture.md
docs/dev/asr-context-s4.md
docs/dev/asr-implementation-2026-09.md
docs/dev/asr-native-s3.md
docs/dev/asr-s41.md
resource/translations/VideoCaptioner_en_US.ts
resource/translations/VideoCaptioner_vi_VN.json
resource/translations/VideoCaptioner_zh_CN.ts
resource/translations/VideoCaptioner_zh_HK.ts
status.md
tests/conftest.py
tests/test_asr/test_review.py
tests/test_cli/test_asr_review.py
tests/test_cli/test_config.py
tests/test_subtitle/test_publication.py
tests/test_translate/test_request_policy.py
tests/test_ui/test_conversation.py
tests/test_ui/test_s41.py
videocaptioner/cli/commands/asr_review.py
videocaptioner/cli/commands/process.py
videocaptioner/cli/commands/subtitle.py
videocaptioner/cli/commands/transcribe.py
videocaptioner/cli/config.py
videocaptioner/cli/main.py
videocaptioner/core/asr/metadata.py
videocaptioner/core/asr/native_api.py
videocaptioner/core/asr/native_result.py
videocaptioner/core/asr/review.py
videocaptioner/core/editor/translation.py
videocaptioner/core/entities.py
videocaptioner/core/llm/owned_request.py
videocaptioner/core/llm/request_policy.py
videocaptioner/core/optimize/optimize.py
videocaptioner/core/prompts/translate/conversation.md
videocaptioner/core/split/split.py
videocaptioner/core/split/split_by_llm.py
videocaptioner/core/subtitle/editing.py
videocaptioner/core/subtitle/publication.py
videocaptioner/core/translate/base.py
videocaptioner/core/translate/conversation.py
videocaptioner/core/translate/factory.py
videocaptioner/core/translate/llm_translator.py
videocaptioner/resources/translations/VideoCaptioner_vi_VN.json
videocaptioner/ui/common/config.py
videocaptioner/ui/components/asr_review_dialog.py
videocaptioner/ui/task_factory.py
videocaptioner/ui/thread/subtitle_pipeline_thread.py
videocaptioner/ui/thread/subtitle_thread.py
videocaptioner/ui/thread/transcript_thread.py
videocaptioner/ui/thread/worker_lifecycle.py
videocaptioner/ui/view/setting_interface.py
videocaptioner/ui/view/subtitle_interface.py
videocaptioner/ui/view/transcription_interface.py
videocaptioner/ui/view/video_editor_interface.py
```

## Chi tiết các gói tiếp theo

### S2 — alignment tiếng Trung

Giao diện audio+text+language→word/character spans, offset canonical ms. Thử Qwen ForcedAligner
trong runtime riêng; ghim revision; chunk alignment theo giới hạn riêng (tài liệu hiện 5 phút),
không áp dụng mặc định ASR 10 phút. Validate khoảng lặng, tên/số, giản/phồn thể, từ không align
được; có review/fallback tường minh. Nối result S1 vào ASRData và SRT; smoke gateway clip Trung
khi có credential. Probe local health, shutdown/cancel, cold/warm, peak VRAM, offline sau tải.

### S3 — cloud với speaker

Adapter Soniox upload/submit/poll/result, Scribe multipart. Normalize words/token/audio events
và speaker; giữ stable speaker ID theo toàn job, không coi ID cùng số giữa chunk là cùng người.
Thêm metadata tùy chọn vào ASR và dữ liệu subtitle; rà split/merge/optimize/translate/editor;
không merge qua người nói. Reuse EditorCue.speaker + command hiện có; save/load JSON giữ speaker.
Test overlap, empty speakers, speaker count, cancel/poll/retry, mất kết nối và cache.

### S4 — ngôi và xưng hô Trung→Việt

Model dữ liệu cho nhân vật, speaker→addressee, quy tắc theo cặp/cảnh và nguồn bằng chứng.
User sửa/khóa có ưu tiên cao nhất. Dịch song song dùng cùng snapshot ngữ cảnh; dịch lại 1–9 cue
vẫn nhận mapping. Không suy vai trò/quan hệ từ âm sắc. Test lược chủ ngữ, 他/她/它, người nghe
thay đổi, lời trích dẫn, câu kể và character trở lại sau cảnh dài. Invalidate cache theo
mapping/override tất định; persist tương thích schema cũ; SRT nhãn speaker là tùy chọn hiển thị.

### S5 — local và hybrid

Tận dụng runtime S2 cho Qwen3-ASR nếu dependency tương thích. Benchmark 1.7B/0.6B, model manager
và health/shutdown ẩn. Thêm pyannote Community-1 độc lập: điều kiện tải/credential HF được xử lý
đúng, không đồng nghĩa được phép gửi audio ra cloud. Chạy toàn job hoặc clustering toàn job,
ghép word timeline với speaker spans, overlap để review. Dùng cho Qwen và gateway text-only.
Không để ASR và VieNeu cùng giữ GPU khi vượt budget VRAM; không import Torch vào Qt.

### S6 — nghiệm thu sản phẩm

Khoảng 30 clip Trung (60–90 phút) có nhãn do người kiểm tra, thêm stress video dài. Đo ASR thô
và toàn pipeline riêng: CER, tên/số, hallucination silence, median/p95 timing, DER/speaker
confusion, lỗi ngôi/xưng hô và phút chỉnh tay. So với Faster-Whisper hiện có; báo theo thể loại
và phương ngữ. Đo chi phí thật, upload/poll/alignment, cold/warm và RAM/VRAM. Build EXE tên
riêng, hash, startup và workflow từ artifact; không chỉ từ source. Chọn mặc định sau bằng chứng.

Khung 16–27 ngày trong nghiên cứu là ước lượng ban đầu; đánh giá lại sau S1/S2. Gói nào chưa
được triển khai hoặc chưa chạy online phải giữ trạng thái đó, không tự đánh dấu xong theo lịch.
