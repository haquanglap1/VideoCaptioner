# Prompt bàn giao — thực hiện ASR bước 3

Tiếp tục VideoCaptioner, triển khai S3 đến hết code, kiểm thử phù hợp và bàn giao; không chỉ
lập kế hoạch. User đã chấp nhận lộ trình S1–S6. Session này chỉ thực hiện S3: cloud ASR có
timestamp và speaker, Soniox v5 và ElevenLabs Scribe v2. Không tự làm S4–S6 hoặc đổi engine mặc định.

## Baseline và tài liệu

- Bắt đầu từ `origin/codex/asr-s2-alignment` của repo
  `https://github.com/haquanglap1/VideoCaptioner.git`; nhánh phải chứa commit code S2
  `96470bf7c60eb7598f61eb7d450327011f9f19c8` và file prompt này. Không mặc định master đã có S1/S2.
  Nếu user cung cấp SHA tip cụ thể, dùng đúng SHA đó và xác minh S2 là ancestor.
- Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`, `docs/dev/architecture.md`,
  `docs/dev/asr-provider-plan-2026-09.md`, `docs/dev/asr-implementation-2026-09.md` và
  `docs/dev/asr-alignment-s2.md`. Đọc đúng tài liệu subtitle/editor/config khi chạm domain đó.
- Chạy `git status --short --branch` trước sửa; tìm call site bằng `rg`. Giữ mọi thay đổi ngoài task.
  Có thể tạo worktree/nhánh riêng từ baseline trên; không reset/cherry-pick hàng loạt hay sửa
  checkout khác để xử lý baseline.

## Trạng thái S1/S2 phải giữ chính xác

- S1 có registry SDK-free, provider/request profiles, request/parser/probe dùng chung, config
  GUI/CLI và key theo endpoint, cache hash cách ly endpoint/model/config. Không network khi mở settings;
  startup config không kéo SDK/model nặng. Custom base/model/prompt/language vẫn tương thích.
- S2 có `AlignedAPI` cho GPT JSON → Qwen ForcedAligner riêng → ASRData/SRT. Ngôn ngữ Chinese
  và runtime/CUDA phải ready trước upload; chunk PCM lossless <=240 s, model limit 300 s, cắt ở
  silence; không dùng chunk 10 phút hoặc bỏ tail. Không timestamp giả, clamp, nội suy hoặc bỏ chữ.
- Runtime Windows Python 3.12 riêng, Qwen 0.0.6/Torch 2.8.0+cu128 có lock hash, model revision
  `c7cbfc2048c462b0d63a45797104fc9db3ad62b7`; job/probe offline sau tải, không import Torch/Qwen
  vào Qt, không trộn runtime VieNeu. Tắt nội suy `fix_timestamp` upstream; policy `strict-raw-v1`
  dừng toàn job để review khi timing/text/coverage không hợp lệ. Runtime hiện là venv cài tại máy,
  chưa portable/installer. Runtime/model/build không có trong Git; không giả định worktree mới có sẵn.
- S2 cache nhận dạng và alignment tách riêng. Async API có timeout/retry hữu hạn và hủy in-flight;
  sidecar có health/cancel/timeout/đóng process tree. Worker giữ contextvars; QThread phải `wait()`.
- Gate baseline: ruff pass, pyright 0 error/0 warning, sync translations pass, full offline
  **768 passed, 5 skipped, 51 deselected**. Skip gồm native playback/TTS ngoài; offline không phải E2E.
- Local alignment thật trên clip Qwen Trung công khai 4.204 s: 13 span 400–3680 ms, SRT tạo được,
  warm ~0.10 s, peak Torch allocation ~1.76 GiB. Câu lệch audio/silence bị chặn; bản phồn thể của
  cùng câu cũng bị strict validator chặn, **chưa đạt acceptance phồn thể**. Không hạ guard để ép pass.
- EXE S2 review build/startup pass; không bundle GPU runtime/model, chưa chạy workflow media/API
  từ EXE. **GPT gateway→SRT chưa nghiệm thu vì thiếu key**. Không đổi những trạng thái này thành pass
  chỉ vì S3 có mock hoặc một provider khác hoạt động. Chi tiết artifact/hash ở bàn giao S2.

## Mục tiêu S3

Nhận dạng audio/video tiếng Trung bằng API native Soniox v5 và Scribe v2, lấy timing thật cùng
speaker metadata khi provider cung cấp, rồi đưa metadata qua pipeline phụ đề và editor hiện có.
Không dùng alignment Qwen để giả tạo speaker. Không cần ASR tiếng Việt; dịch Việt giữ pipeline cũ.

### 1. Xác minh hợp đồng provider

Đọc lại tài liệu chính thức Soniox và ElevenLabs trước triển khai: model ID/quyền truy cập,
upload hoặc multipart, submit/poll/result, schema token/word/timestamp/speaker/audio event,
language, byte/duration limits, error/retry và cancel/delete. Không đoán endpoint từ ví dụ S1
hoặc coi `GET /models`/catalog là bằng chứng inference. Không ép native API vào route Whisper.
Nếu phải đổi model ID so với kế hoạch vì tài liệu hiện hành, ghi rõ bằng chứng và giữ user chọn rõ ràng.

### 2. Adapter native, job lifecycle và cancellation

- Soniox: upload → submit → poll có backoff/deadline → lấy kết quả. Phân biệt lỗi từng giai đoạn,
  failed/cancelled/timeout/succeeded. Không upload/submit lại vô hạn khi poll lỗi; tránh nhân đôi phí.
  Với submit không rõ đã được nhận hay chưa, dùng cơ chế idempotency/recovery provider hỗ trợ;
  nếu không có thì báo rõ trạng thái không chắc chắn, không tự tạo job mới.
- Scribe: multipart/header/model native đúng docs, parse word/audio event/speaker. Giữ event
  không phải lời nói tách khỏi lời thoại; không tự biến nhạc/tiếng cười thành subtitle speech.
- Phân biệt dừng chờ local với hủy job remote. Chỉ gọi endpoint cancel/delete được provider
  hỗ trợ cho job/file do app vừa tạo; không đụng tài nguyên không thuộc job. Nêu rõ phần remote
  có thể tiếp tục/chịu phí sau cancel nếu không hủy được.
- Credentials truyền tường minh, tách theo provider/endpoint; không dùng key gateway cho Soniox/
  ElevenLabs. Không ghi key vào env/argv/log; không gửi local path hoặc transcript dư thừa trong metadata.
- Worker/progress/cancel không block Qt. Executor dùng `submit_with_context`; subprocess nếu có
  dùng argument list + `child_environment()`. Không có request/inference chỉ vì mở settings.

### 3. Contract timing và speaker

- Bổ sung metadata tùy chọn có type vào ASR entity/result; giữ constructor/call site cũ dùng được.
  Chuẩn hóa timestamp theo đơn vị docs sang canonical integer ms; validate finite/nonnegative/
  start<=end/audio bounds, giữ chính sách overlap phù hợp lời chồng của cloud. Không lấy policy
  không-overlap của forced alignment một người nói rồi âm thầm làm mất overlapping speech.
- Ghép token/subword thành word/cue theo contract provider, giữ đúng text/timing/speaker và
  punctuation; không chia đều thời lượng. Dữ liệu thiếu timing phải có trạng thái review/lỗi rõ ràng.
- Speaker ID chỉ là nhãn anonymous. Giữ ổn định trong toàn job; không coi cùng số speaker ở
  hai request/chunk là cùng người. Ưu tiên provider xử lý toàn file khi giới hạn cho phép;
  nếu phải chia và chưa có bằng chứng liên kết thì namespace ID theo job/chunk, nêu hạn chế.
- Missing/unknown speaker, nhiều người nói và overlap phải biểu diễn được; không suy tên, tuổi,
  giới, quan hệ, người nghe hoặc xưng hô từ âm sắc/ID speaker.

### 4. Giữ metadata xuyên pipeline và editor

Rà mọi clone/copy/split/merge/optimize/translate adapter/import/export của ASR/subtitle, không
chỉ thêm trường vào dataclass. Không merge qua người nói; phần sửa text/timing vẫn giữ metadata
đúng nguồn. Nếu một phép biến đổi không giữ được association, dừng/review hoặc báo missing
tường minh, không gán speaker tùy tiện.

Tái sử dụng `EditorCue.speaker` và command hiện có; mọi mutation editor đi qua `CommandStack`.
Giữ `editor-project-v1`, canonical ms, cue ID ổn định, normal save JSON + SRT; ASS chỉ qua
Save as ASS. Test save/load metadata, undo/redo và import ASR vào editor. SRT thường không
bảo toàn metadata speaker; nhãn speaker trong chữ SRT chỉ khi user chủ động chọn, không tự chèn.

S3 bảo toàn speaker metadata để S4 sử dụng; chưa xây bảng nhân vật, addressee, xưng hô Trung→Việt,
chưa thay đổi prompt dịch theo quan hệ, chưa thêm tự gán giọng TTS hoặc pyannote.

### 5. Config/CLI/GUI, cache và test

- Cho chọn Soniox/Scribe tường minh và cấu hình/probe phù hợp; giữ mặc định/các flag/config S1/S2.
  Alias custom/gateway cũ không bị hiểu nhầm thành provider native. Phân biệt probe auth/service,
  nhận dạng và timestamp/speaker quan sát được; không hứa speaker chỉ dựa trên catalog.
- Cache có version/fingerprint theo audio/provider/endpoint/model/language/request options/
  speaker policy. Không trộn kết quả bật/tắt diarization; không log key, transcript, local path,
  raw error response hoặc remote job credential. Không đọc cache legacy lẫn endpoint.
- Test request/parser/error cho cả hai provider, tiếng Trung có tên/số/punctuation, silence/events,
  empty/unknown speaker, overlap, malformed/missing timing, giới hạn upload, job fail/timeout,
  poll lỗi tạm, cancel ở từng stage, submit không chắc chắn và retry hữu hạn.
- Test speaker stability/namespace giữa chunk, text không mất/trùng, metadata qua
  split/merge/optimize/translate/editor, save/load/undo, cache invalidation, key isolation,
  CLI precedence, mở settings không network và QThread lifecycle/contextvars. Thread qua QEventLoop
  luôn `wait()` trước ra khỏi scope; không thay fixture để ghi vào AppData thật.

## Validation và bàn giao

- Chạy ruff toàn source/tests, pyright, toàn test_cli, ASR/provider/UI/thread/subtitle/editor tests
  gần thay đổi, sync translations và full offline vì mở rộng entity shared. Dùng Python 3.10–3.12
  và dependency project theo AGENTS. Mượn interpreter thì xác minh `videocaptioner.__file__`/
  PYTHONPATH đúng worktree; basetemp ngắn nếu ACL/MAX_PATH.
- Nếu có credential được cấu hình đúng provider, smoke clip Trung công khai/tổng hợp ngắn trong
  phạm vi đã chấp nhận; ghi routing/model/timing/speaker/usage không nhạy cảm. Không đọc/copy
  credential hoặc media riêng ở checkout khác, không tạo token/mua credit. Thiếu key không ngăn
  hoàn thành code/offline; ghi rõ online chưa chạy. Không thay benchmark người nghe bằng mock.
- Nếu thêm runtime resource/dynamic import, cập nhật duy nhất `VideoCaptioner.spec`; build artifact
  tên riêng và báo riêng exit/warnings, size/time/SHA-256, startup từ artifact, workflow đã/chưa chạy.
  Không overwrite artifact/AppData của user, không commit model/runtime/build/cache/media/log.
- Cập nhật `status.md` và mục S3 trong implementation theo bằng chứng; liệt kê file đổi và
  gates pass/fail/skip/chưa chạy, giới hạn speaker/overlap, đầu vào S4. Giữ các khoản nghiệm thu
  còn thiếu của S2 rõ ràng; chỉ sửa hồi quy S1/S2 nếu cần S3 và có test chứng minh.
- Dừng ở S3 để review. **Không tự commit/push/tag/release/viết GitHub trong session mới**:
  yêu cầu commit/push trước đó chỉ dành cho bàn giao S2. Không tự triển khai S4–S6.
