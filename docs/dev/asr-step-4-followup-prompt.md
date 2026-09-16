# Prompt session tiếp theo — củng cố S4.1 trước S5

Tiếp tục VideoCaptioner trên working tree user chỉ định, nhánh `codex/asr-s3-native`.
Triển khai và kiểm thử đến hết phạm vi S4.1 dưới đây; không chỉ lập kế hoạch.
Mục tiêu là dùng được các luồng đã thử online trong app và xử lý lỗi có thể review,
trước khi mở rộng sang local ASR/diarization S5.

## Baseline phải xác minh

- **Code S4 đã commit:** `8558082945575d551a4c38cdc4943c395254a583`, chứa 37 file (code,
  tests, tài liệu S4 và prompt S4 cũ). Commit S3 là `327c214bcc749f49f160e89594d3c95902698403`.
  HEAD còn có commit tài liệu bàn giao này. Không nhầm HEAD S2 `d21251a` hoặc mặc định master đã có S4.
- Chạy `git status --short --branch`, `git log`, kiểm tra commit S4 là ancestor. Giữ nguyên mọi
  thay đổi/file untracked nếu user có sửa sau bàn giao. Không reset/clean/stash/checkout đè để làm sạch.
- Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`, `docs/dev/architecture.md`,
  `docs/dev/asr-context-s4.md`, `docs/dev/asr-native-s3.md`, `docs/dev/asr-alignment-s2.md`,
  `docs/dev/asr-implementation-2026-09.md`; khi sửa editor đọc `docs/dev/video-editor.md`.
  Prompt S4 cũ là lịch sử yêu cầu, không phải mô tả Git hiện tại. Dùng rg tìm call site trước sửa.
- Gate code S4: **910 passed, 5 skipped, 51 deselected** (105.38 s), ruff pass, pyright 0/0,
  sync translations/diff-check pass. Trước commit đã chạy lại ruff/pyright/sync và xác minh 21
  module source khớp bytecode của artifact đã test; không rerun full suite vì source chưa đổi.
- EXE review `dist/VideoCaptioner-ASR-S4-Review-20260907/`: build exit 0, 6 warning optional/platform,
  0 ERROR; EXE 31,057,002 byte, SHA-256
  `08dd40819c91152c7fd778b4f81036101ee6db43208844089efc595f58fda252`.
  Đã smoke hidden Qt 25 s, WM_CLOSE exit 0, không process sót. **Artifact đã có AppData và media/output
  user: không rebuild đè, xóa hoặc dùng nó làm thư mục scratch.** Build S4.1 phải có tên/scratch riêng.

## Bằng chứng thật và vấn đề còn lại

1. **Whisper gateway:** audio Trung 111.333 s, `whisper-1` qua API VideoCaptioner chạy 9.00 s,
   trả 30 segment hợp lệ, JSON/SRT/editor roundtrip pass. 142 word spans có 11 span 0 ms;
   không nghiệm thu word timing. SRT dùng timestamp **segment do API cung cấp**, không suy từ word.
   Không có speaker trong response. Hai checkpoint tên/thuật ngữ trên video vẫn bị nhận sai.
2. **GPT STT gateway:** `gpt-4o-transcribe` nhận dạng text trong 4.11 s, không timing/speaker.
   `gpt-4o-mini-transcribe` HTTP 429 hai lượt; chưa xác định chính xác nguyên nhân.
   **GPT transcription→alignment→SRT vẫn chưa nghiệm thu**. Catalog không chứng minh mọi model inference được.
3. **Soniox native:** đã upload/poll/result thật trên hai clip, mỗi clip trả 4 nhãn speaker.
   Clip Anh 260.551 s có 3 lexical token start=end; clip Trung 111.333 s có 2 token start=end.
   Parser dừng đúng policy, cleanup job-owned remote thành công. Raw response chỉ được giữ bằng
   harness test tạm: **app chưa có luồng bảo toàn kết quả lỗi để review/resume mà không upload lại**.
   Không dùng các JSON prefix mẫu để claim toàn clip đã pass.
4. **Dịch Việt gpt-5.6-terra:** user chọn model này; gateway xác nhận request/response cùng ID.
   Default request deadline S4 là 120 s: có batch timeout. Harness retry riêng 300 s lấy được phần
   còn thiếu. Lượt xuất full SRT Việt 30 cue dùng một request mất **131.56 s**, cần timeout riêng 300 s.
   Chưa đưa cấu hình này vào app; không coi việc harness override là đã sửa code.
5. Đã xuất đủ 30 cue Việt + song ngữ từ segment Whisper, giữ cue IDs/timing (12.560–104.180 s),
   đặt sidecar cạnh bản video Trung. Hai lỗi tên có chữ trên video được sửa có bằng chứng trước dịch;
   đây là bản xem thử, chưa chấm ASR/diarization/xưng hô bằng người đọc.
6. **S4 context:** typed/frozen models, evidence/override/lock, scoped mapping, directed rules,
   immutable job snapshot, cache, GUI/CLI và JSON persistence có code/offline test. Các lượt online
   mới chủ yếu dùng unknown proposals, chưa nghiệm thu hiệu quả rule có user xác nhận.
7. **Stale editor:** guard hiện hash toàn project, nên playhead/track thay đổi cũng bỏ bản dịch.
   Shutdown tab phụ đề chờ worker để tránh Qt abort, nhưng còn cần review việc chờ dài trên UI thread.
8. Request mẫu 30 cue tiêu tốn 16,230 prompt tokens dù nguồn rất ngắn; payload có nhiều thông tin
   unknown/review lặp. Cần kiểm tra và giảm phần lặp mà vẫn giữ ngữ cảnh/evidence cần thiết.

Report/media test ở các thư mục ignored dưới `dist/VideoCaptioner-ASR-S4-Review-20260907/work-dir/`:
tìm các thư mục `soniox-test-*`, `soniox-terra-test-*`, `gateway-stt-test-*`, `full-srt-vi-*`.
Chỉ đọc đúng dữ liệu liên quan. Không đưa transcript, frames, raw response hoặc đường dẫn riêng vào Git.
Không dựa vào script tạm còn tồn tại; chuyển logic cần dùng sang core/UI đúng kiến trúc.

## Phạm vi S4.1 phải thực hiện

### A. Timeout/model/context của dịch trong app

- Thêm cấu hình request timeout/deadline có validation và giới hạn hữu hạn vào schema chung,
  nối GUI/CLI/SubtitleConfig/translator; giữ backward compatibility và default cũ nếu không cấu hình.
  Cho user dùng 300 s với `gpt-5.6-terra` mà không phải chạy harness. Không đổi model/endpoint ngầm.
- Chụp credential và các setting của job một lần; worker dùng cùng snapshot. Timeout/cancel phải
  đóng socket, join công việc thuộc job, không để response muộn cập nhật UI/state mới.
  Không tự retry POST vô hạn hoặc coi timeout là provider chưa nhận/chưa tính phí.
- Thu gọn payload: bỏ lặp thông điệp unknown/review, chỉ gửi dữ liệu cần thiết cho selection và
  bằng chứng/ngữ cảnh nguồn. Đo kích thước/token bằng nguồn tổng hợp; không đánh đổi context 1–9 cue,
  mapping/rules/lock, quote/narration/third-person và dữ liệu bảo mật. Không thêm LLM brief ngẫu nhiên
  vào cache key hoặc để worker tự tạo quan hệ riêng. Bump policy/fingerprint khi semantics thay đổi.

### B. Review kết quả ASR có token timing không hợp lệ

- Giữ kết quả recognition tối thiểu trong typed review state/local storage riêng trước khi validation
  thất bại làm mất dữ liệu. Tách kết quả cần review khỏi cache ASR thành công. Giữ scope/cue/token
  association và provenance, không persist credential/headers/remote identifiers không cần thiết.
- GUI báo vị trí token lỗi, ngữ cảnh và lý do; cho xem/lưu lại kết quả nhận dạng, mở lại để review
  mà không gọi lại provider. Có đường chỉnh timing **tường minh bởi user** rồi validate/resume local,
  lưu dấu edited/override và undo/redo qua CommandStack. Không gọi timing đã sửa là native nguyên bản.
- CLI có cách báo/tạo artifact review rõ ràng và resume dữ liệu đã sửa khi phù hợp; giữ exit-code
  semantics của lỗi chưa được xử lý. Không xuất SRT full một phần rồi báo success.
- **Không bỏ guard để ép pass:** không tự clamp/nội suy/chia đều duration, bỏ chữ, gộp token qua
  speaker/request khác hoặc dựng word time từ segment. Nếu có fallback cấp câu thì chỉ dùng timing
  cấp câu hợp lệ mà provider thực sự trả, với lựa chọn/granularity rõ ràng; Soniox token-only không
  được âm thầm coi là đã có sentence timestamps. Raw token 0 ms vẫn phải review trước acceptance.
- Không upload/resubmit audio để vượt một lỗi parser có response local; chỉ cleanup tài nguyên
  đúng job. Native Soniox POST acceptance/cancel/409 guards giữ nguyên.

### C. Sửa guard stale và lifecycle UI liên quan

- Fingerprint dùng để nhận kết quả dịch phải phụ thuộc đúng source/cue IDs/timing/speaker/context/
  target text cần bảo vệ và danh tính project; playhead, zoom hoặc state hiển thị không liên quan
  không được làm mất kết quả. Đổi rules/lock/source/translation mới vẫn phải từ chối response stale.
- Review cancel/close/app quit ở SubtitleThread, RetranslateThread và editor: không block main thread
  lâu, không terminate QThread để che lỗi, không để QThread bị hủy khi còn chạy. Hủy không ghi output
  một phần, signal cũ không reset/overwrite worker mới. Giữ contextvars qua submit_with_context.
- Dịch lại selection không đổi các cue ngoài selection, voice/TTS text hoặc timing. User rename label
  không đổi ID; normal editor save vẫn editor-project-v1 JSON + SRT, ASS chỉ qua Save as ASS.

## Validation và handoff

- Tạo synthetic regression cho shape lỗi đã đo: zero-duration whole word/subword/CJK, known/unknown
  speakers, overlapping speech; raw-review roundtrip/resume/edit/undo, cache fail không là cache success,
  không resubmit, cancel/deadline/cleanup. Không copy câu thật hoặc key vào fixture.
- Test timeout setting cũ/mới, snapshot giữ timeout/credential ổn định, response quá hạn/cancel/stale;
  1–9 cue đủ context, source quote/title/omitted subject/third person, scope/cặp rules khác nhau.
- Test playback/zoom không vô hiệu bản dịch, còn sửa ngữ cảnh/text thì có; QThread test phải wait.
  Test không ghi AppData/settings thật, cache riêng, subprocess env scrubbed, UTF-8 Windows.
- Chạy ruff, pyright, toàn CLI, các test ASR/translate/subtitle/editor/UI/thread gần thay đổi, sync
  translations và full offline vì có thay schema/context/worker. Python 3.10–3.12, dependency theo
  uv.lock; không cài global. Nếu dùng interpreter sẵn, xác minh import đúng working tree.
- Key từ phiên trước **không được lưu trong repo/settings và không nằm trong prompt này**. Không
  tìm/copy key từ checkout khác, log, lịch sử task hoặc script tạm. Nếu cần online, dùng credential
  user cấu hình/cung cấp an toàn cho phiên hiện tại; chỉ dùng media user đã cho phép và số lượt thử
  hữu hạn. Thiếu key không cản code/offline. Không coi offline/mock là online acceptance.
- Build duy nhất VideoCaptioner.spec, tên và scratch S4.1 mới. Verify bytecode/resources từ artifact
  cuối; báo exit/warnings, size/time/SHA-256, startup/cleanup riêng và workflow thực đã/chưa chạy.
  Không overwrite bản S4 đã có AppData/video/SRT user. QM không sửa tay; thiếu lrelease ghi rõ.
- Cập nhật status/implementation theo bằng chứng, hướng dẫn dùng review/timeout và liệt kê file đổi.
  Giữ rõ Scribe online, GPT alignment/phồn thể, speaker accuracy và chất lượng xưng hô còn thiếu.

Dừng ở **S4.1** để user review. Không tự làm S5/S6, Qwen ASR/pyannote, tự gán voice, benchmark
toàn corpus hoặc đổi engine mặc định. **Không commit/push/tag/release** trong session mới nếu user
chưa yêu cầu riêng; việc submit S4 ở phiên trước không phải quyền tự submit các phiên sau.
