# Prompt phiên tiếp theo — S5 local ASR và hybrid diarization

Tiếp tục VideoCaptioner tại checkout user chỉ định, nhánh `codex/asr-s3-native`.
Khi user dùng prompt này để bắt đầu S5, triển khai và kiểm thử phạm vi dưới đây;
không chỉ lập kế hoạch. Việc lưu prompt trong commit bàn giao không tự khởi chạy S5.
Dừng để review sau S5; không làm S6 hoặc commit/push/tag/release nếu phiên mới chưa được yêu cầu riêng.

## 1. Xác minh baseline trước khi sửa

- **Code S4.1:** `db23299370f311395fae39069f0983739d259250`, gồm 56 file.
  Parent bàn giao S4 là `47d1cec`; code S4 là `8558082`; code S3 là `327c214`.
  HEAD có thể có commit tài liệu bàn giao sau code S4.1; không nhầm HEAD với code S2 hoặc master.
- Chạy `git status --short --branch`, `git log` và kiểm tra code S4.1 là ancestor của HEAD.
  Giữ nguyên mọi thay đổi/untracked của user. Không reset/clean/stash/checkout đè để làm sạch.
- Đọc đầy đủ `AGENTS.md`, `README.md`, mục mới nhất `status.md`, `docs/dev/architecture.md`,
  `docs/dev/asr-s41.md`, `docs/dev/asr-context-s4.md`, `docs/dev/asr-native-s3.md`,
  `docs/dev/asr-alignment-s2.md` và mục S4.1/S5 trong `docs/dev/asr-implementation-2026-09.md`.
  Đọc đúng phần local/hybrid của `docs/dev/asr-provider-plan-2026-09.md`; đây là kế hoạch có ngày,
  không thay thế việc xác minh tài liệu upstream hiện tại. Khi sửa editor/VieNeu, đọc domain tương ứng.
- Dùng rg tìm symbol/call site trước khi sửa: ASR factory/entities, alignment contract/runtime,
  native metadata/review, model settings/probes, CLI và workers/lifecycle, cùng PyInstaller spec.

## 2. Bằng chứng phải giữ nguyên

- S4.1 full offline cuối: **986 passed, 5 skipped, 51 deselected**, **92,17 s**; ruff pass,
  pyright **0 errors/0 warnings**, sync translations và diff-check pass. 5 skip gồm native
  QtMultimedia playback và 4 TTS/service; 51 deselect theo integration/slow/llm.
- Python **3.12.13**, interpreter/FFmpeg có sẵn; đã xác minh import đúng checkout. Không đổi
  `pyproject.toml`/`uv.lock` hoặc cài global. Checkout lúc bàn giao không có `.venv` riêng;
  tìm môi trường có sẵn phù hợp, không dùng Python 3.13/3.14 cho project.
- Artifact review cuối: **`dist/VideoCaptioner-ASR-S41-Review-20260907-Final/`**.
  PyInstaller exit 0, 6 WARNING optional/platform, 0 ERROR; thêm 6 SyntaxWarning upstream.
  EXE **31.093.132 byte**, timestamp local **2026-09-07 15:35:00**, SHA-256
  `2ab4c85035ba64fd59fe96d5686b75ac00139644936bd960a206a419803e4284`.
  202 module bytecode và prompt/JSON vi khớp source; không bundle Torch/Qwen/Torchaudio.
  GUI hidden 25 s, WM_CLOSE exit 0, 0 process sót/0 startup error markers.
- Frozen local review thực sự đã chạy: JSON tổng hợp lỗi timing → exit 5 và không có SRT;
  explicit override → JSON và mở lại → SRT đều exit 0. Đây là local JSON acceptance,
  **không phải ASR/LLM inference hoặc workflow video/API từ EXE**.
- Artifact S4 cũ **`dist/VideoCaptioner-ASR-S4-Review-20260907/`** chứa media/AppData/output user,
  SHA-256 EXE `08dd40819c91152c7fd778b4f81036101ee6db43208844089efc595f58fda252`.
  **Không rebuild đè, xóa, di chuyển hoặc dùng bất kỳ artifact đã có làm scratch.** Các bản S4.1
  đầu/Final cũng phải được giữ. Build S5 cần tên, output, cache và scratch riêng mới.
- Giữ S4.1: timeout 1–600 s/default 120, lựa chọn 300 cho `gpt-5.6-terra`; credential/config/source
  snapshot; request-owned socket/cancel/join; context request policy v2, persistence v1; review
  raw + override local; fingerprint theo dữ liệu liên quan; dấu hủy tồn tại sau QThread finished.
  Byte context tổng hợp giảm 82,37%, **không phải số đo token/chi phí**.

## 3. Phạm vi S5 cần triển khai

### A. Qwen ASR local trên runtime riêng

- Thêm engine local được chọn tường minh cho tiếng Trung, ưu tiên Qwen3-ASR 1.7B và có lựa chọn
  0.6B theo kế hoạch. Không thay Faster-Whisper hoặc engine mặc định; không đổi model ngầm khi lỗi/OOM.
- Xác minh model card/repository/docs chính thức hiện tại trước khi chốt API, giới hạn audio,
  dependency, license và revision. Pin từng model theo commit SHA, pin runtime/lock có hash;
  không dùng nhánh `main` làm revision runtime ổn định hoặc copy SHA của aligner sang ASR.
- Rà khả năng reuse runtime S2. Chỉ chia sẻ nếu dependencies tương thích và được kiểm thử;
  nếu xung đột, tạo runtime riêng. Không nâng Torch/Transformers/pyannote trong venv Qt hoặc
  overwrite runtime alignment/VieNeu đang dùng. Không import Torch/Qwen/pyannote vào Qt process.
- Builder/model manager có bước cài/tải chủ động vào thư mục mới riêng; public model tải bằng
  thao tác tường minh, verify manifest/revision và trạng thái ready/incomplete/failed. Không download,
  health/inference nặng hoặc gọi API khi chỉ mở settings. Không cài dependency global.
- Nhận dạng → text → alignment dùng contract ms strict S2 khi cần. Đo/cấu hình chunking đúng
  giới hạn upstream đã xác minh, giữ full coverage và tail, offset chính xác. Không tạo timestamp
  từ độ dài chữ, gọi `fix_timestamp` nội suy, clamp hay bỏ lexical token để ép thành công.
- Bổ sung typed provenance cho recognition/alignment/local timing khi cần; không gọi forced
  alignment là timestamp native từ cloud. Giữ API/entity/schema cũ tương thích, cue IDs ổn định.
  Reuse review S4.1 khi phù hợp; nếu cần mở rộng phải có schema/validation và kiểm thử roundtrip.

### B. Diarization local và đường hybrid

- Thêm `pyannote/speaker-diarization-community-1` như bước local độc lập, có lựa chọn tường minh.
  Xác minh dependency, model revision, license và yêu cầu quyền tải từ nguồn chính thức.
- Quyền tải/gated access không được suy từ việc public model card tồn tại. Không tự chấp nhận
  điều khoản thay user, không tìm token trong checkout khác/log/lịch sử, không ghi token vào
  argv/env chung/source/report. Nếu thiếu quyền/token, hoàn thiện code/offline và ghi rõ phần
  runtime còn thiếu; chỉ hỏi đúng thông tin cần thiết qua cơ chế nhập an toàn khi thật sự cần.
- Diarization chạy local, không âm thầm gửi audio sang dịch vụ cloud thứ hai. Dùng được với Qwen
  local và đầu ra ASR gateway có timing hợp lệ; gateway text-only phải qua alignment trước.
  Không gộp native Soniox/Scribe diarization với local speaker labels một cách ngầm định.
- Chạy toàn job hoặc có bước clustering toàn job để giữ scope speaker xuyên chunk. Không coi
  speaker số 1 của hai request/chunk độc lập là cùng người. Không suy danh tính, giới, quan hệ,
  người nghe, quy tắc xưng hô hoặc voice TTS từ diarization.
- Ghép word/cue timeline và speaker spans bằng policy overlap/confidence có version, tất định,
  có tests. Ambiguous/unknown/overlapping speakers phải có trạng thái review hoặc giữ unknown;
  không chọn đại để đủ schema, không sửa timing hoặc cắt chữ nhằm làm mất overlap.
- Giữ provenance nhận dạng, alignment và diarization tách bạch. Speaker/cue associations và
  override đã xác nhận phải sống qua split/optimize/translate/JSON/editor/cache; context cũ
  không tự bám sang request mới. Directed rules/lock của S4 vẫn do user/evidence xác nhận.

### C. Runtime, GPU và lifecycle

- Sidecar có health, ready/loading/busy/error rõ ràng, deadline/cancel hữu hạn, process ẩn,
  môi trường child được lọc và cleanup đúng process tree thuộc job. Giữ contextvars khi submit
  executor; không `QThread.terminate()` hoặc thả QThread đang chạy.
- Pin model revision cho toàn job, không update/xóa model đang được dùng. Đường source/pip/frozen
  đều đúng theo `config.py`. Phân biệt runtime cài tại máy với runtime portable đã kiểm thử;
  không gọi việc chép một Windows venv là phân phối portable thành công.
- Không để Qwen/aligner/pyannote và VieNeu đồng thời chiếm GPU vượt budget. Rà lifecycle/service
  hiện có, dùng điều phối rõ ràng: chờ có thể hủy hoặc báo busy/OOM hữu ích; không kill process
  khác của user hay âm thầm unload một job còn chạy. Không tạo framework GPU lớn ngoài nhu cầu S5.
- Đo trên phần cứng thực tế của phiên: cold/warm startup/inference, RAM/VRAM và shutdown/restart.
  Sau khi model đã tải đầy đủ, chạy được offline và không tự truy cập network trong inference.

### D. GUI/CLI/persistence

- Nối engine/model và tùy chọn local diarization vào factory/config/schema/CLI/GUI theo kiến trúc
  hiện có; không đưa business logic mới vào view. Settings cũ, key theo endpoint, engine mặc định,
  timeout/context và exit-code semantics S1–S4.1 phải giữ.
- Model manager/probe ở worker, UI có tiến độ/cancel và trạng thái thiếu runtime/quyền tải rõ ràng.
  Chỉ tải/gọi probe khi có thao tác chủ động. Báo riêng recognition, alignment và diarization readiness.
- Cache tách stage và có audio hash, model/revision/options/policy/source association; không cache
  kết quả cần review dưới namespace success. Không đưa credential/path riêng/random brief vào key/log.
- Mọi sửa text/timing/speaker/context đi qua CommandStack, giữ undo/redo và provenance. Dịch lại
  selection không đổi cue ngoài selection, timing, voice hoặc TTS text. Normal editor save vẫn
  `editor-project-v1` JSON + SRT; ASS chỉ qua Save as ASS. Không thêm PySide6 hoặc MPV.

## 4. Validation bắt buộc và giới hạn

- Synthetic regression cho native/S2/S4.1 compatibility, text/alignment coverage, zero/invalid
  timestamps, silence, offset/chunk/tail, giản/phồn thể, speaker unknown/overlap/returning speaker,
  association giữa chunk/request, manual override và review roundtrip/resume/undo.
- Test missing/incomplete runtime/model, pinned revisions, offline inference, timeout/cancel
  từng stage, late signal sau QThread finished, restart/shutdown và GPU busy/OOM. Test chỉ cleanup
  job-owned resources, env child scrubbed, không ghi AppData/settings/cache/media thật.
- Chạy ruff, pyright, toàn CLI và các suite gần code, sync translations/diff-check; chạy full
  offline vì thay core ASR/metadata/runtime. Python project 3.10–3.12, dependency theo lock.
  Mọi test QThread phải wait trước khi ra khỏi scope; phân biệt pass/fail/skip/deselect.
- Chạy functional smoke ngắn cho 0.6B/1.7B và diarization thật khi runtime/quyền tải sẵn sàng;
  chỉ dùng audio tổng hợp, nguồn public phù hợp hoặc media user đã cho phép. Đây là so sánh
  chức năng/performance có phạm vi nhỏ, **không phải corpus benchmark S6 hoặc chất lượng ngôn ngữ**.
- Các khoản cũ vẫn còn thiếu: **Scribe online; GPT gateway→alignment→SRT; phồn thể Qwen strict;
  speaker accuracy; chất lượng xưng hô do người đọc chấm; workflow media/API thật từ EXE**.
  Chỉ đổi trạng thái khoản nào có phép đo mới tương ứng. Không dùng mock hoặc local JSON để xóa nợ online.
- Không upload/resubmit audio chỉ để vượt lỗi parser đã có response local. Các dữ liệu test
  riêng trong artifact S4 chỉ được đọc đúng phần liên quan khi user cần; không copy transcript,
  frames, raw response, path riêng hoặc credential vào Git. Không phụ thuộc helper scratch còn tồn tại.
- Build qua **duy nhất `VideoCaptioner.spec`**, tên/scratch/cache S5 mới. Giữ nguyên artifact
  S4/S4.1 và AppData/media của chúng. Verify bytecode/resources từ artifact cuối, báo riêng build
  exit/warnings, size/time/SHA-256, startup/cleanup và workflow thực đã/chưa chạy. Base Qt không
  bundle/import GPU libraries; runtime/model riêng phải có hướng dẫn cài và giới hạn cụ thể.
- Cập nhật status/implementation, hướng dẫn dùng S5 và manifest file theo bằng chứng. Không gọi
  S5 đã nghiệm thu runtime nếu chỉ có code/offline; không tự chuyển sang S6, benchmark toàn corpus,
  chọn engine mặc định hoặc tự gán voice. **Dừng để review; không commit/push trong phiên mới.**
