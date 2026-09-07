# Prompt phiên tiếp theo — S5.2: chốt hybrid API và liên kết nguồn trước S6

Tiếp tục tại checkout user chỉ định (worktree `VideoCaptioner-ASR-S3`), nhánh
`codex/asr-s3-native`. Khi user dùng prompt này để bắt đầu phiên mới, thực hiện công việc bên dưới,
không chỉ lập kế hoạch. Lưu prompt trong commit bàn giao không tự khởi chạy phiên mới.

Ưu tiên nghiệm thu API còn thiếu và củng cố lỗi có tái hiện, kế thừa local-hybrid đã chạy thật.
Chưa mở benchmark corpus S6, chọn engine mặc định, auto voice, tag/release hay PR. Dừng review sau
phạm vi này. Quyền commit/push trong phiên bàn giao không áp dụng tự động cho phiên tiếp theo.

## 1. Baseline và đọc tài liệu

- **Code S5.1:** `8599965b7931d8c555a55cfa379b4a2e2cee9238`, đúng **12 file** trong manifest.
  Parent `80f6e360878fe6e16e81bef6360d3d2ca61e9951`; code S5 `3a7c231` là ancestor.
  HEAD có commit tài liệu bàn giao sau code; không nhầm HEAD với baseline S5/master.
- Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`, `docs/dev/architecture.md`,
  `docs/dev/asr-local-s5.md`, phần bàn giao S5.1 và roadmap trong
  `docs/dev/asr-implementation-2026-09.md`. Đọc `asr-alignment-s2.md`, `asr-native-s3.md`,
  `asr-context-s4.md`, `asr-s41.md` khi rà contract tương ứng. Tài liệu domain đều dưới `docs/dev/`.
- Trước sửa: `git status --short --branch`, `git log`, kiểm tra code S5.1 là ancestor. Giữ mọi
  thay đổi/untracked của user; không reset/clean/stash để dọn. Dùng `rg` tìm call site trước sửa.
- Ưu tiên xem `core/asr/local/`, `transcribe.py`, `aligned_api.py`, `metadata.py`, `review.py`,
  `cli/commands/local_diarize.py`, editor adapters/commands, GUI local config và worker lifecycle.

## 2. Bằng chứng phải kế thừa đúng

- **Full offline cuối: 1.088 passed / 4 skipped / 51 deselected, 118,40 s, exit 0**; 22 test S5.1
  mới. CLI **104 passed**, ruff pass, pyright **0 errors/0 warnings**, translations/diff-check pass.
  4 skip TTS/service; QtMultimedia native playback pass. Không lấy offline/mock làm online acceptance.
- Gate trung gian có Settings subprocess crash Windows **3221225477**, stderr trống; Scribe mock
  deadline **10 ms** có `closed=False` khi chưa vào transport. Ba case riêng với faulthandler pass,
  full cuối chạy không có build/runtime song song pass. **Chưa xác định nguyên nhân hai flake**;
  tải nền là điều kiện quan sát, chưa phải kết luận hay fix.
- Python **3.12.13**, FFmpeg và venv phù hợp có sẵn trên máy. Worktree không có `.venv` riêng ở
  mốc bàn giao; dùng interpreter đã có và xác minh import đúng checkout. Không sync/cài global,
  thay `pyproject.toml`/`uv.lock` hoặc đưa Torch/Transformers/pyannote vào venv Qt.
- Qwen **0.6B/1.7B** đã inference thật source/EXE trên public Chinese **4,204 s**, strict alignment
  → JSON/SRT; **13 measured token IDs**, word output 13 cue, sentence output 1 cue **400–3680 ms**.
- **Community-1 đã tải và inference thật**, không còn chỉ là dependency import. Mẫu pyannote public
  **30 s → 13 span / 2 speaker**, public Chinese 4,204 s → 1 speaker, silence 3 s → 0 span.
  Waveform memory chạy thành công; inference dùng offline/telemetry/socket guards và không token.
- Community-1 load đầu **75,094 s**, cold/warm inference mẫu 30 s **1,688/0,485 s**; Torch peak
  allocation **1.708.632.064 byte**, RSS tree warm **1.944.559.616 byte**. Đây không phải tổng
  VRAM/NVML hay benchmark so model. Restart load **25,968/9,421 s**, shutdown **0,907–0,922 s**.
- Cancel thật Community-1 startup/inference **1,531/1,563 s**, Qwen/aligner inference
  **1,187/1,344 s**, cleanup process/reader/lease pass. Process khác bị GPU busy khi owner vẫn
  ready; không unload/kill owner. Manual speaker override qua CommandStack undo/redo/roundtrip pass.
- **Full local-hybrid Qwen 0.6B → alignment → Community-1 pass source và EXE**: source 13 token
  assigned; EXE JSON/SRT **1 cue / 13 token IDs, 400–3680 ms**, exit 0. EXE `local-diarize` dùng
  timed Qwen JSON/SRT có sẵn đều exit 0, 13 assigned cue; không ASR/upload lại.
- Timed JSON/SRT tổng hợp theo reference tutorial giữ **11 cue: 1 unknown / 3 ambiguous / 7 overlap**,
  giữ text/timing/IDs, JSON/editor roundtrip và scope riêng mỗi job. Đây là text tổng hợp kiểm thử
  association, không phải transcript ASR của mẫu. Window spot-check giữ speaker quay lại và overlap;
  **lượt thoại rất ngắn đầu clip khác RTTM reference**, giữ ambiguous. Chưa đo DER/speaker accuracy.

## 3. Runtime và artifact phải giữ

- Qwen/aligner: **`build/S5-Qwen-Runtime-20260907-R2/`**. Không chọn nhầm bản S5 đầu không có bridge
  cuối. Community-1 ready: **`build/S51-Community1-Runtime-20260907/`**. Thư mục
  `build/S5-Pyannote-Dependencies-20260907/` chỉ là dependency import, không phải model ready.
- Community-1 pin **`3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`**, **8 model file / 32.832.557 byte**.
  Manifest SHA-256 **`8af6543a4f173c8a3c19c84c802c57a4f4ded1ccf242ad23c2fee6b675068447`**;
  lock diarization SHA-256 **`6be6c010d7eae3b52c03dc14996121a4c2fda22e0e76850aae1e8eca46aa28a2`**.
  pyannote 4.0.7, Torch/Torchaudio 2.9.1+cu128, TorchCodec 0.8.1. Qwen dùng recipe S2 riêng.
- **Không cần xin lại HF token để inference runtime đã cài.** Chỉ khi thực sự tải vào đích mới,
  user tự có quyền model và nhập token qua GUI password/getpass; truyền RAM/stdin riêng. Không lấy
  token/key từ chat cũ, lịch sử, checkout khác, artifact, log hoặc environment chung. HF token
  không phải credential gateway/Soniox/Scribe. Không tự chấp nhận điều kiện hoặc đổi dịch vụ cloud.
- Các runtime này là venv cài tại máy, **chưa portable**. Không move/copy venv rồi gọi đó là runtime
  portable. Nếu thiếu trên máy mới, báo thiếu và tiếp tục phần độc lập, không dùng helper scratch
  như dependency bắt buộc. Không nâng pin/API/dependency nếu chưa xác minh nguồn chính thức/lý do.
- Artifact **`dist/VideoCaptioner-ASR-S51-Review-20260907-Final/`**, duy nhất `VideoCaptioner.spec`.
  Build exit 0, **6 WARNING optional/platform, 0 ERROR, 6 SyntaxWarning upstream**. EXE
  **31.150.810 byte**, local **2026-09-07 17:55:01**, SHA-256
  **`5c2cc4ad873d7acbc0ccb9a94ce942e87a41c3bc8ba0c68c6e36af8df25f73c8`**.
  **216 module / 33 resource** khớp source; không bundle GPU. GUI hidden 25 s, WM_CLOSE exit 0,
  không process sót/startup error. Local-hybrid được đo từ bản sao binary/resources vào scratch mới,
  giữ nguyên artifact/AppData gốc. Không rebuild chỉ để chốt Git hoặc thay tài liệu.
- Giữ tất cả artifact S4/S4.1/S5/S5.1, AppData/media/output bên trong và mọi runtime cũ. Build mới
  phải dùng tên/output/cache/scratch mới. Giữ `.env`, cookies, work-dir và log của user.

## 4. Công việc ưu tiên của phiên mới

### A. Nghiệm thu API còn thiếu, khi có đúng quyền/credential

- Kiểm tra cấu hình hiện có tại checkout và hỏi nhập kín đúng credential khi cần; không tự tìm
  lại key trong phiên cũ. Dùng public audio ngắn phù hợp hoặc media user chỉ định/chấp thuận.
  Thiếu key/service: tiếp tục B/C độc lập và ghi rõ chưa nghiệm thu, không chặn cả phiên.
- Đo riêng gateway có timing (`whisper-1`) → Community-1, và gateway text-only
  (`gpt-4o-transcribe`) → strict Chinese alignment S2 → Community-1 → JSON/SRT. Xác minh provider/
  endpoint/model được chọn; không đổi model trả phí ngầm. Local health phải pass trước upload.
- Scribe v2 native: probe quyền và inference là hai gate riêng; chỉ inference khi user cấp đúng
  credential. Giữ timing/speaker/audio events/native review/remote cleanup. Không trộn nhãn local
  lên native. Soniox có response lỗi cũ thì dùng review local, không resubmit audio để vượt parser.
- `gpt-4o-mini-transcribe` từng HTTP 429 tại gateway: không retry hàng loạt, suy key sai hoặc tự
  đổi provider từ status này. Catalog/probe pass không chứng minh inference của mọi model.
- Đo source và EXE bằng actual app pipeline, giữ kết quả stage đầy đủ và ghi rõ request nào có
  thể phát sinh phí. Không xuất prefix như toàn-job success; không nội suy/clamp/bỏ token 0 ms.

### B. Liên kết đúng audio khi mở lại JSON/review

- S5.1 đã có snapshot file/config cho job hybrid đang chạy. **JSON/SRT mở lại chưa có fingerprint
  audio để tự chứng minh thuộc recording gốc**; `local-diarize` hiện dựa vào user chọn đúng audio.
- Tái hiện trường hợp chọn nhầm audio cùng duration hoặc nguồn đổi sau khi lưu review/JSON.
  Nếu bổ sung identity, dùng metadata typed tùy chọn và fingerprint nội dung/canonical audio,
  không ghi absolute path, credential hoặc transcript vào identity/cache key. Áp cùng definition
  giữa recognition, alignment, diarization và resume; giữ chunk offset/tail/toàn-job coverage.
- JSON cũ/SRT không có identity phải vẫn mở được nhưng không được báo đã xác minh audio. Mismatch
  có identity phải dừng trước inference/API; cho user chọn lại đúng nguồn, không silent reassociate.
  Không tự thêm timing giả, xóa provenance hoặc migration phá schema đang dùng.
- Giữ `strict-raw-v1`, `local-asr-review-v1`, `asr-review-v1`, cue/token IDs, raw và overrides
  riêng. Pending diarization sau review phải rõ ràng; export timing không thành full hybrid success.
  Mọi user edit qua CommandStack; resume/reopen không tự upload lại.

### C. Chẩn đoán có bằng chứng, giữ nguyên contract đã nghiệm thu

- Rà crash Settings/timeout test nếu tái hiện: thu faulthandler/exit/stack tối thiểu không nhạy cảm,
  tách harness/môi trường/source. Không sửa Qt/framework hoặc nới timeout chỉ để che fail; không
  gọi rerun pass là fix. Khi chạy full, tránh build/GPU job song song để giảm yếu tố nhiễu.
- Với speaker đầu clip sai reference: chỉ phân tích smoke hiện có, không đổi threshold/model/
  exclusive output để ép đủ speaker. Giữ regular overlap, union span, ≥80% đúng một speaker;
  multiple/overlap/coverage thấp giữ unknown/review. Coverage không phải acoustic probability.
- Không suy danh tính/giới/quan hệ/người nghe/voice; không nối scope hai request. Giữ confirmed
  override và directed rules/lock S4 qua split/optimize/translate/JSON/editor/cache.
- S4.1: LLM timeout 1–600/default120; chọn300 tường minh cho `gpt-5.6-terra`; request-owned socket,
  cancel/join hữu hạn, snapshot config/credential/source, context request v2/persistence v1.
  Selection translation chỉ đổi display_text trong selection, không timing/TTS/voice/context lock.
- Heavy IO/model/subprocess nằm ngoài Qt main thread. Mở settings không download/probe/inference;
  GUI đổi engine không mang cờ local ẩn sang native. GPU lease giữa S2/S5/VieNeu và process app
  không kill/unload job khác. QThread không terminate; queued signal cũ không sửa state job mới.
  Normal editor save vẫn `editor-project-v1` JSON + SRT; ASS chỉ qua Save as ASS.

## 5. Validation và bàn giao

- Test gần mọi lỗi đã sửa, bao gồm source mismatch/legacy input/review/override/IDs/cache association,
  script/CJK/names/numbers/silence/invalid timing/tail, whole-job speaker/unknown/overlap, timeout,
  cancel/GPU busy/cleanup. QThread test phải wait; cô lập settings/config/cache/review/media/GPU lease.
- Chạy ruff, pyright, CLI, translations/diff-check; full offline nếu đổi metadata/runtime/lifecycle.
  Báo rõ pass/fail/skip/deselect; giữ riêng offline, dependency import, health và inference/API thật.
  Không rerun full/build khi chỉ đổi tài liệu và gate snapshot cũ vẫn áp dụng.
- Nếu cần artifact mới, dùng duy nhất spec và đích mới; kiểm tra source bytecode/resource, không
  bundle GPU vào base Qt, exit/warnings, size/time/SHA-256, GUI startup/WM_CLOSE/cleanup và workflow
  từ chính EXE. Nếu dùng artifact cũ để kiểm tra runtime, tạo bản sao binary/resources vào scratch
  riêng, không dùng AppData/media/log của artifact gốc làm dữ liệu kiểm thử.
- Cập nhật status, implementation, hướng dẫn và manifest theo bằng chứng. Media/transcript/raw
  response/credential/build/runtime không vào Git. Không phụ thuộc helper ignored để hiểu kết quả.
- Giữ riêng các khoản chưa đo: **hybrid API cloud, Scribe online, GPT gateway→alignment→SRT,
  phồn thể strict, speaker accuracy và xưng hô do người đọc chấm**. Chỉ đổi trạng thái có phép đo
  tương ứng. Dừng review và đề xuất bước sau; không tự khởi chạy S6 hoặc commit/push.
