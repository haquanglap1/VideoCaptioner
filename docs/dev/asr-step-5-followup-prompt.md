# Prompt phiên tiếp theo — S5.1: nghiệm thu local/hybrid trước S6

Tiếp tục VideoCaptioner tại checkout user chỉ định (worktree `VideoCaptioner-ASR-S3`),
nhánh `codex/asr-s3-native`. Khi user dùng prompt này để bắt đầu phiên mới, thực hiện công việc
bên dưới, không chỉ lập kế hoạch. Lưu prompt trong commit bàn giao không tự khởi chạy phiên mới.

Ưu tiên hoàn tất phần runtime/diarization còn thiếu của S5 và sửa lỗi được kiểm chứng.
Chưa mở benchmark corpus S6, chọn engine mặc định, auto voice, tag/release hoặc PR.
Dừng để review sau phạm vi này. Quyền commit/push ở phiên bàn giao trước không phải quyền
tự commit/push các thay đổi mới ở phiên tiếp theo.

## 1. Baseline và tài liệu

- **Code S5:** `3a7c231a53069fefc58b34e95d7cc9ba10dac846`, gồm đúng **53 file** trong manifest.
  Parent bàn giao S4.1: `1bf4dd07b2c06cc50cc31289a8ca5c73b2e2293b`.
  Code S4.1: `db23299370f311395fae39069f0983739d259250`.
  HEAD có thể có commit tài liệu bàn giao sau S5; không nhầm HEAD với code S4.1/master.
- Đọc đầy đủ `AGENTS.md`, `README.md`, mục mới nhất `status.md`, `docs/dev/architecture.md`,
  `docs/dev/asr-local-s5.md`, phần bàn giao S5 và roadmap trong
  `docs/dev/asr-implementation-2026-09.md`. Đọc `docs/dev/asr-step-5-prompt.md`,
  `docs/dev/asr-s41.md`, `docs/dev/asr-alignment-s2.md`, `docs/dev/asr-native-s3.md`,
  `docs/dev/asr-context-s4.md` khi rà contract tương ứng; đọc domain editor/VieNeu nếu sửa vào đó.
- Trước sửa: `git status --short --branch`, `git log`, xác minh code S5 là ancestor của HEAD.
  Giữ mọi thay đổi/untracked của user; không reset/clean/stash để làm sạch worktree.
- Dùng `rg` tìm call site trước sửa: `core/asr/local/`, metadata/review, ASR factory,
  config/CLI/GUI, `LocalASRThread`, `worker_lifecycle`, `gpu_lease`, runtime S2/VieNeu và spec.

## 2. Bằng chứng và artifact phải giữ

- Full offline mã cuối S5: **1.066 passed, 4 skipped, 51 deselected, 144,10 s, exit 0**.
  Toàn CLI **104 passed, 2,96 s**; ruff pass; pyright **0 errors/0 warnings**;
  sync translations, TS XML và diff-check pass. 79 test S5 mới. 4 skip là TTS/service;
  QtMultimedia native playback đã chạy pass trong lượt đó. Skip có thể khác theo backend của phiên mới.
- Một full trung gian có subprocess Settings crash Windows `3221225477`; test riêng và hai full
  tiếp theo pass. **Chưa xác định nguyên nhân crash ngắt quãng**, không ghi là đã sửa.
  Test GPU lease đã được cô lập theo từng test, không tranh lease với runtime thật.
- Python **3.12.13**, FFmpeg và venv project đã có trên máy; xác minh import đúng worktree trước
  test/build. Worktree không có `.venv` riêng ở mốc bàn giao; tìm interpreter có sẵn phù hợp.
  Không thay `pyproject.toml`/`uv.lock`, nâng GPU dependency vào Qt hoặc cài global.
- Artifact review cuối: **`dist/VideoCaptioner-ASR-S5-Review-20260907-Final/`**.
  PyInstaller **exit 0, 6 WARNING optional/platform, 0 ERROR**, thêm **6 SyntaxWarning upstream**.
  EXE **31.148.265 byte**, local timestamp **2026-09-07 17:23:00**, SHA-256
  `1717175295241e722a3e5a516d903b85668a3372417260bf0e776e3f303fe9f3`.
  **215 module / 34 resource** khớp source; không bundle GPU libraries. Onedir trước smoke
  **580 file / 237.647.944 byte**. GUI hidden **25 s**, WM_CLOSE exit 0, 0 process sót/0 startup errors.
- Qwen 0.6B/1.7B **đã inference thật từ source và EXE** trên audio Trung public 4,204 s.
  Source có **13 measured token spans**; EXE chế độ câu xuất JSON → SRT **1 cue 400–3680 ms**,
  giữ **13 token IDs** trong JSON; các command đều exit 0. Frozen review tổng hợp reject/resume pass.
  Đây là local media/ASR acceptance có phạm vi nhỏ, không phải cloud API hay benchmark chất lượng S6.
- Source inference cold/warm: **2,813/0,672 s** cho 0.6B, **0,984/0,360 s** cho 1.7B;
  Torch peak allocation **1.876.073.984 / 4.698.543.616 byte**. Lượt đo khác cache/tải nền,
  không suy so sánh tốc độ tổng quát hoặc tổng VRAM/NVML. Restart/shutdown sạch,
  shutdown **0,890–0,938 s**, cancel startup thật **1,250 s**. Chi tiết trong hướng dẫn S5.
- Runtime Qwen đã dùng: **`build/S5-Qwen-Runtime-20260907-R2/`** (cả hai ASR và aligner).
  Đây là venv cài tại máy, **không phải portable**. Bản S5 đầu không phải bản bridge cuối;
  không tự chọn nhầm `build/S5-Qwen-Runtime-20260907/`.
  **`build/S5-Pyannote-Dependencies-20260907/` chỉ kiểm thử dependency import/CUDA**,
  không có model Community-1 ready; không coi thư mục đó là runtime inference đã nghiệm thu.
  Các thư mục ignored có thể không còn trên máy khác; không phụ thuộc helper scratch.
- Giữ nguyên mọi artifact S4/S4.1/S5, kể cả bản đầu và AppData/media/output bên trong.
  S4 EXE: `08dd40819c91152c7fd778b4f81036101ee6db43208844089efc595f58fda252`;
  S4.1 Final: `2ab4c85035ba64fd59fe96d5686b75ac00139644936bd960a206a419803e4284`.
  Không rebuild đè, xóa, di chuyển hoặc dùng artifact đã có làm scratch. Nếu đổi code/recipe cần
  build/runtime mới, dùng tên/output/cache/scratch riêng và duy nhất `VideoCaptioner.spec`.

## 3. Công việc ưu tiên

### A. Community-1 và hybrid runtime thật

- Xác minh upstream hiện tại từ nguồn chính thức trước thay API/dependency/revision/license.
  Giữ pin đã có nếu không có lý do kiểm chứng để đổi. Qwen/aligner dùng lock S2 trong môi trường
  S5 riêng; pyannote có lock riêng. Không nâng chung Torch/Transformers/pyannote trong venv Qt.
- Community-1 revision hiện tại của app là `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`.
  Model card public không đồng nghĩa có quyền tải. User tự chấp nhận điều kiện Hugging Face;
  token chỉ nhập qua GUI password/getpass, truyền trong RAM/stdin riêng. Không hỏi token trong
  chat, argv, env chung; không tìm token trong checkout khác, artifact, log hoặc lịch sử.
- Nếu user chưa cung cấp quyền/token, tiếp tục kiểm tra và sửa phần offline độc lập, ghi rõ
  runtime còn thiếu. Chỉ đề nghị nhập an toàn khi thực sự cần; không tự chấp nhận điều khoản,
  đổi sang dịch vụ cloud hoặc coi thiếu quyền là model inference pass.
- Khi có quyền, dùng installer/model manager hiện có vào **đích mới**, verify manifest/hash/revision,
  health và inference thật. Pyannote dependency import từng báo thiếu DLL decoder TorchCodec;
  bridge dùng PCM waveform memory theo upstream. Kiểm chứng đường này bằng model thật,
  không coi dependency import hoặc việc đổi warning thành bằng chứng pipeline hoạt động.
- Thử ngắn bằng audio tổng hợp, public phù hợp hoặc media được user cho phép: Qwen → alignment →
  Community-1; timed JSON/SRT → `local-diarize`; speaker trở lại, unknown, overlap và toàn-job scope.
  Gateway có timing và gateway text-only → alignment chỉ thử API khi có đúng credential và
  nguồn audio được phép. Không resubmit audio nếu đã có response local chỉ để vượt lỗi parser.
- Sau download, kiểm tra inference offline không tự network/telemetry. Đo cold/warm load/inference,
  RAM/VRAM theo loại đo rõ ràng, cancel từng stage, restart/shutdown và không còn process thuộc job.
  Không lấy clip một speaker hoặc nhãn model tự sinh làm ground truth speaker accuracy.

### B. Rà các contract S5 và củng cố khi có lỗi tái hiện

- Recognition/alignment/diarization dùng cùng nguồn audio của job; kiểm tra snapshot/fingerprint
  khi nguồn thay đổi, chunk offset, full coverage và tail. Review giữ text toàn job và raw prediction,
  không bỏ lexical token, nội suy/clamp, gọi `fix_timestamp` hoặc đổi script để ép pass.
- Giữ `strict-raw-v1`, `local-asr-review-v1`, `asr-review-v1`, token/cue IDs và raw + override riêng.
  Pending diarization sau review phải được báo rõ; export timing không thành full hybrid success.
  Resume/reopen không upload lại. Mọi user edit text/timing/speaker/context qua CommandStack.
- `overlap-conservative-v1`: union span cùng speaker; gán chỉ khi đúng một speaker phủ ≥80% cue.
  Multiple/overlap/coverage thấp giữ trạng thái review hoặc unknown, không tự chọn cho đủ schema.
  Coverage thời gian không phải acoustic probability. Dùng regular diarization để giữ chồng lời.
- Scope toàn job không tự nối hai request; không trộn native Soniox/Scribe labels với local labels.
  Không suy danh tính/giới/quan hệ/người nghe/voice. Giữ stage provenance riêng, confirmed override,
  directed rules/lock S4 xuyên split/optimize/translate/JSON/editor/cache.
- Rà GUI đổi Qwen ↔ Whisper ↔ native, runtime/model missing/incomplete/failed, status theo stage,
  install sai family bị từ chối trước hỏi token, progress/cancel/close và queued signal sau finished.
  Mở settings không tải/probe/inference. Không để việc nặng hoặc widget mutation chạy sai Qt thread.
- Rà GPU lease giữa S2/S5/VieNeu và nhiều process app: busy có thông báo hữu ích, không kill hoặc
  unload job khác. Cleanup chỉ tài nguyên của job, reader/executor được join hữu hạn,
  môi trường child lọc credential; không QThread.terminate hoặc hủy object khi còn chạy.
- Tái hiện crash Settings nếu xảy ra; lưu bằng chứng tối thiểu không nhạy cảm, phân biệt lỗi harness,
  môi trường và source. Không đổi code hoặc tuyên bố fix chỉ vì rerun pass.
- Giữ S4.1: timeout LLM 1–600/default 120, chọn 300 tường minh cho `gpt-5.6-terra`; snapshot
  config/credential/source, request-owned socket/cancel/join, context request policy v2/persistence v1.
  Selection translation không đổi cue ngoài selection, timing, TTS text/voice hoặc context đã khóa.
  Normal editor save vẫn `editor-project-v1` JSON + SRT; ASS chỉ qua Save as ASS.

## 4. Validation và bàn giao

- Test gần mọi lỗi đã sửa, giữ regression S1–S5: scripts/CJK/name/number coverage, silence,
  invalid/zero timestamps, chunk/tail, whole-job speaker, unknown/overlap, override/review roundtrip,
  cache stage/model/revision/source association, config cũ, GPU busy/OOM, timeout/cancel/cleanup.
  QThread tests phải wait; settings/config/cache/review/media test phải cô lập dữ liệu user.
- Chạy ruff, pyright, toàn CLI, sync translations/diff-check; full offline nếu thay core metadata,
  runtime hoặc lifecycle. Tách rõ pass/fail/skip/deselect và offline với inference/API thật.
  Không rerun full/build chỉ để thay tài liệu khi snapshot code không đổi và gate còn áp dụng.
- Nếu đổi runtime resource/dynamic import hoặc source cần artifact mới, build bằng duy nhất spec
  với đích mới; verify bytecode/resources từ artifact cuối, size/time/SHA-256, build exit/warnings,
  hidden GUI startup/WM_CLOSE/cleanup và workflow thực từ chính EXE. Không bundle GPU vào base Qt.
- Giữ riêng các khoản còn thiếu: **Community-1 model inference/hybrid API, speaker accuracy,
  Scribe online, GPT gateway→alignment→SRT, phồn thể Qwen strict và xưng hô do người đọc chấm**.
  Chỉ đổi trạng thái khoản có phép đo tương ứng. Qwen local source/EXE đã pass không xóa các khoản đó.
- Cập nhật `status.md`, implementation, hướng dẫn và manifest theo bằng chứng. Không đưa media,
  transcript/raw response riêng, credential, absolute private path hoặc build/runtime vào Git.
  Dừng review và báo phần sẵn sàng/chưa đủ điều kiện cho S6; không tự khởi chạy S6 hoặc commit/push.
