# Prompt bàn giao — thực hiện ASR bước 4

Tiếp tục VideoCaptioner, triển khai S4 đến hết code, kiểm thử phù hợp và bàn giao; không chỉ
lập kế hoạch. Session này tập trung ngữ cảnh người nói/người nghe và xưng hô Trung→Việt.
Review nền S3 trước khi sửa, giữ guard S1–S3. Không tự làm S5/S6, đổi engine mặc định,
commit/push/tag/release hoặc viết GitHub.

## Baseline bắt buộc: S3 đang nằm trong working tree, chưa commit

- Dùng chính working tree trên nhánh `codex/asr-s3-native` được user chỉ định. Tại bàn giao,
  HEAD vẫn là **S2** `d21251a5d1be3d4baceec5a3e8d6869ceb4877c5`; S3 là **50 file thay đổi/thêm
  chưa commit**, ngoài ra có file prompt S4 này. Không coi SHA HEAD là snapshot đã chứa S3.
- Không mặc định master/origin đã có S3. Không tạo worktree chỉ từ HEAD hoặc
  `origin/codex/asr-s2-alignment` rồi triển khai S4 trên đó: sẽ bỏ mất S3. Không reset, clean,
  checkout đè, stash hoặc commit các thay đổi đang có để làm sạch baseline.
- Đầu phiên chạy `git status --short --branch`, kiểm tra HEAD, đọc diff và file untracked.
  Đối chiếu manifest S3 trong implementation, gồm `native_api.py`, `native_result.py`,
  `metadata.py`, settings native và bốn file test S3. Nếu S3 đã được commit bởi user sau bàn giao,
  xác minh commit mới và dùng trạng thái đó; không bắt buộc HEAD quay về SHA S2.
- Nếu chỉ có clone sạch/S2 hoặc thiếu source S3, dừng phần phụ thuộc và yêu cầu đúng snapshot S3;
  không tự viết lại S3 từ mô tả. Không copy credential, media hay AppData từ checkout khác.
- Đọc đầy đủ `AGENTS.md`, `README.md`, phần mới nhất `status.md`, `docs/dev/architecture.md`,
  `docs/dev/asr-provider-plan-2026-09.md`, `docs/dev/asr-implementation-2026-09.md`,
  `docs/dev/asr-native-s3.md`, `docs/dev/asr-alignment-s2.md`. Khi chạm editor, đọc
  `docs/dev/video-editor.md`; đọc đúng tài liệu subtitle/config liên quan. Dùng rg tìm symbol/call site.
- Ghi nhận baseline diff trước sửa, giữ các thay đổi đã có; bàn giao phải tách file/phần mới S4
  với S3 kế thừa. Không coi toàn bộ dirty tree là do phiên S4 tạo.

## Trạng thái S1–S3 phải giữ chính xác

- S1 có registry nhẹ, request/profile/parser/probe chung, custom/gateway tương thích, key theo
  endpoint và cache hash cách ly provider/model/config. Settings không tự gọi network/inference.
- S2: GPT JSON → Qwen ForcedAligner riêng → ASRData/SRT; Chinese/runtime/CUDA ready trước upload,
  PCM lossless chunk <=240 s, giữ tail, model limit 300 s. Policy `strict-raw-v1` không nội suy,
  clamp hoặc bỏ chữ; mismatch/timing bất thường dừng review. Qt không import Torch/Qwen.
  Runtime/model pinned, cache nhận dạng và alignment riêng, deadline/cancel/process cleanup giữ nguyên.
- S3: Soniox `stt-async-v5` native upload/submit/poll/result; Scribe `scribe_v2` multipart native.
  POST không tự resubmit khi acceptance không chắc chắn; GET retry/deadline hữu hạn. Chỉ cleanup
  tài nguyên thuộc job. Hủy local không bảo đảm hủy remote/hoàn phí; Soniox processing có thể trả 409.
- `ASRMetadata` optional giữ provider/scope/speaker/timing; speaker ID scoped theo request,
  unknown vẫn unknown. Timing integer ms, overlapping speech giữ độc lập, audio events không
  biến thành lời thoại. Không nối cùng số speaker ở hai request thành cùng một người.
- Metadata qua pipeline phụ đề, typed translation input, JSON handoff và editor. Merge khác
  speaker/source bị chặn; legacy fuzzy chunk merge từ chối native metadata. Native splitter
  chỉ gom span đã đo; optimizer một cue mỗi request. Editor split native hiện dừng review vì
  chưa có explicit text boundary. Preview overlay chỉ chọn một active cue; export giữ các cue.
- Tái sử dụng `EditorCue.speaker`, cue ID và CommandStack; giữ `editor-project-v1`, normal save
  JSON + SRT; ASS chỉ qua Save as ASS. SRT đơn lẻ mất metadata và không tự chèn speaker vào chữ.
- Gate S3: ruff pass, pyright 0 errors/0 warnings, sync translations/diff-check pass;
  full offline **862 passed, 5 skipped, 51 deselected**, 96,71 s (768 baseline + 94 test mới).
  Test timeout đã dùng clock điều khiển sau trạng thái processing, tránh race timer Windows.
- EXE review S3 build sạch exit 0, 6 warnings optional/platform; 36 module bytecode khớp source.
  EXE 31.023.698 byte, SHA-256
  `0e3be9f494e4f82a76274c7563175cf222cfcb03feea8f5e91db6b343761ebec`.
  GUI hidden có đúng cửa sổ Qt, sống qua 25 s, đóng WM_CLOSE exit 0, không process sót/startup error.
  Artifact đã có AppData sau smoke: không overwrite bằng build mới.
- **Soniox/Scribe online, GPT gateway→SRT và workflow media/API từ EXE chưa nghiệm thu** vì thiếu key.
  Qwen alignment local trên clip Trung đã đo ở S2; **phồn thể strict chưa đạt acceptance**.
  Không nâng các trạng thái này thành pass từ mock S4. Không giả định worktree có GPU runtime/model.
- JSON vi đã sync và render kiểm tra; TS en/zh đã cập nhật, nhưng QM giữ baseline do thiếu lrelease.
  Chuỗi zh mới còn fallback English. Không cài package global hoặc sửa QM thủ công.

## Review S3 trước khi mở rộng

Rà các điểm trực tiếp ảnh hưởng S4: stable cue IDs, speaker scope/unknown/override, các đường
ASR→split→optimize→translate→bảng phụ đề→editor, JSON save/load, chọn dịch lại và cache. Đặc biệt
kiểm tra đường nào reimport SRT hoặc tạo object mới làm rơi metadata. Đọc implementation thật,
không chỉ tin báo cáo gate. Sửa lỗi nền liên quan có regression test trước khi xây S4; không
mở rộng thành rewrite toàn bộ ASR, downloader hoặc TTS.

## Mục tiêu S4

Giảm lẫn ngôi/xưng hô khi dịch phụ đề tiếng Trung sang tiếng Việt bằng ngữ cảnh có nguồn bằng
chứng và user override. Diarization chỉ cung cấp nhãn người nói; không tự cho biết nhân vật,
quan hệ, người nghe hoặc đại từ phù hợp. Chưa có benchmark người nghe thì không hứa đã giải
quyết triệt để lỗi xưng hô.

### 1. Model dữ liệu và bằng chứng

- Thiết kế typed domain models trong core: nhân vật/nhãn do user xác định, liên kết speaker
  scoped→nhân vật, người nói/người nghe theo cue hoặc phạm vi cảnh/lượt thoại, quy tắc xưng hô
  có hướng theo cặp và phạm vi áp dụng. Không truyền dict tùy ý xuyên nhiều tầng.
- Phân biệt speaker ASR, nhân vật, người nghe và người được nhắc đến. Người nghe có thể là
  một người, một nhóm hoặc unknown; không mặc định người vừa nói trước là người nghe.
- Mỗi thông tin suy từ text cần nguồn bằng chứng (cue IDs/nguồn user), trạng thái đề xuất/
  xác nhận/khóa hoặc chưa rõ. Không suy tên, tuổi, giới, quan hệ từ âm sắc/ID speaker.
  Không bịa mapping để đủ schema; nguồn SRT không có metadata phải hoạt động với unknown.
- User sửa/khóa có ưu tiên cao nhất; phân biệt cấu hình do user xác nhận với đề xuất máy.
  Đề xuất thiếu bằng chứng/xung đột phải có đường review, không âm thầm ghi đè sự lựa chọn của user.
- Không coi ID mới sau một ASR request khác là cùng nhân vật, trừ khi user hoặc bằng chứng
  nội dung đã được xác nhận liên kết chúng. Tên hiển thị sửa được nhưng ID nội bộ ổn định.

### 2. Quy tắc dịch có hướng và ngữ cảnh thống nhất

- Quy tắc là người nói→người nghe theo cặp/cảnh, không phải một đại từ cố định cho mỗi speaker.
  Ví dụ user xác nhận A→B dùng anh/em, B→A dùng em/anh, A→C có thể tôi/bạn. Không áp đại từ
  ngôi hai vào lời kể/ngôi ba hoặc lời trích dẫn chỉ vì cue có speaker A.
- Xử lý câu lược chủ ngữ, 他/她/它, danh xưng thân tộc/chức vị, trích dẫn, lời kể và đổi người
  nghe. Không ép quyết định khi ngữ cảnh chưa đủ; giữ trạng thái cần review và lựa chọn trung tính.
- Mở rộng LLM translator/prompt hiện có để nhận cue ID, metadata cần thiết, mapping/rules và
  cửa sổ ngữ cảnh nguồn. Không gửi absolute path, credential hoặc metadata không cần thiết.
  Nội dung hội thoại là dữ liệu dịch, không phải chỉ dẫn điều khiển ứng dụng.
- Chuẩn bị một snapshot ngữ cảnh bất biến cho toàn job trước khi dịch song song. Các chunk
  dùng cùng snapshot, giữ contextvars qua submit_with_context; không để từng worker tự đặt
  quan hệ khác nhau. Không thay timing, speaker assignment hoặc cue ID trong response dịch.
- Dịch lại 1–9 cue vẫn có mapping/rules và ngữ cảnh toàn tài liệu cần thiết; không phụ thuộc
  ngưỡng tạo global context hiện tại. Tách context input toàn tài liệu khỏi tập cue được sửa;
  không dịch/ghi đè các cue ngoài vùng user chọn.
- Các translator không nhận context vẫn giữ metadata và hành vi cũ, nhưng UI nêu rõ hạn chế
  hỗ trợ xưng hô; không giả vờ mọi provider đều áp được quy tắc như LLM.

### 3. GUI, CLI và persistence

- Có giao diện đủ dùng để xem/sửa/khóa mapping, chọn người nghe hoặc unknown, đặt quy tắc theo
  cặp và phạm vi; hiển thị chỗ xung đột/thiếu bằng chứng. UI chỉ điều phối, logic nằm trong core.
  Không block Qt hoặc tự gọi LLM khi chỉ mở settings/editor.
- Reuse editor/CommandStack cho mutation, undo/redo và cập nhật bảng liên quan. Việc rename
  display label không làm đổi ID nội bộ hoặc mất liên kết cue; thao tác nhiều trường cần atomic.
- Persist mapping/rules/override bằng trường tùy chọn tương thích `editor-project-v1` và reader
  cũ; file thiếu dữ liệu S4 mở được với defaults. Bảo toàn S3 metadata/events, timing và cue IDs.
  Không dùng SRT như nguồn lưu metadata; normal save vẫn JSON + SRT, ASS chỉ khi chọn rõ ràng.
- Nối lựa chọn ngữ cảnh vào CLI transcribe/process/subtitle và các đường GUI cần thiết theo
  kiến trúc hiện có; dùng config/schema chung. Flags cũ, default, custom/gateway và exit codes
  giữ tương thích. Chỉ thêm lựa chọn CLI cần để dùng dữ liệu ngữ cảnh S4 đã lưu.
- Không tự thêm tên speaker vào chữ SRT, không tự gán voice TTS, không suy quan hệ mới để
  chỉnh giọng. Nếu đường handoff làm mất association, giữ missing rõ ràng hoặc dừng review.

### 4. Cache và bảo mật

- Fingerprint translation cache có version/policy, source/cue IDs, speaker assignments,
  addressee/rules/phạm vi và user override tất định. Đổi mapping/quy tắc/lock liên quan phải
  vô hiệu đúng kết quả cũ; không xóa toàn cache của user.
- Không dùng brief/proposal ngẫu nhiên từ LLM làm cache key. Hash nguồn và cấu hình đầu vào
  đã lưu/xác nhận; snapshot chỉ được chuẩn bị một lần cho mỗi job. Kiểm thử đổi rule trong
  lúc worker chạy: kết quả phải thuộc đúng snapshot, không ghi đè state mới bằng response stale.
- Credentials truyền tường minh, không ghi os.environ; subprocess argument list và
  child_environment(). Không đưa key, local path, transcript/context riêng hoặc raw response
  nhạy cảm vào log mẫu, fixture hoặc artifact Git.

## Test và validation

- Test nguồn tổng hợp Trung/Việt: hội thoại 2–4 người, A↔B và A→C có quy tắc khác nhau,
  người nói trở lại sau cảnh dài, người nghe đổi/nhóm/unknown, câu lược chủ ngữ, 他/她/它,
  lời trích dẫn/kể, danh xưng và overlapping speech. Không lấy output LLM làm ground truth.
- Test precedence đề xuất/user/lock, phạm vi cảnh/cue, xung đột rules và mapping thiếu;
  không tự nối speaker giữa request hoặc gán người nghe theo speaker trước đó.
- Test snapshot nhất quán qua chunk/concurrency, dịch lại 1–9 cue có full context nhưng chỉ
  sửa selection, no-op/unsupported translator, lỗi/malformed response/cancel/stale result.
- Test metadata qua toàn bộ handoff, editor commands/undo/redo, save/load và reader schema cũ;
  SRT không giữ metadata phải được thể hiện rõ. Không tạo timestamp/speaker/addressee giả.
- Test cache invalidation khi đổi speaker/addressee/rule/phạm vi/override, cache ổn định khi
  config tương đương, không phụ thuộc output LLM ngẫu nhiên hoặc lộ nội dung trong key/log.
- QThread qua QEventLoop luôn wait trước ra khỏi scope. Giữ root fixture cô lập settings,
  CLI config và env; không dùng AppData thật để vượt lỗi test.
- Chạy ruff toàn source/tests, pyright, toàn CLI, các test ASR/translate/subtitle/editor/UI/thread
  gần thay đổi, sync translations và full offline vì mở rộng entity/persistence/context dùng chung.
  Chỉ dùng Python 3.10–3.12, dependency theo pyproject/uv.lock. Mượn interpreter phải xác minh
  import đúng working tree/PYTHONPATH; basetemp ngắn và FFmpeg PATH theo AGENTS.
- Nếu có key LLM phù hợp đã được cấu hình, smoke hội thoại tổng hợp/công khai ngắn trong phạm vi
  đã cho phép; không đọc/copy key hoặc media checkout khác, tạo token hay mua credit. Thiếu key
  không chặn code/offline; nêu rõ chưa nghiệm thu bản dịch thật/chất lượng xưng hô bằng người đọc.
- Khi đổi runtime prompt/resource/dynamic import, cập nhật duy nhất VideoCaptioner.spec, build
  tên riêng cho S4. Không overwrite S3 artifact đã có AppData. Đợi source ổn định rồi build sạch;
  đối chiếu resource/bytecode để tránh cache build cũ. Báo riêng exit/warnings, size/time/SHA-256,
  startup từ artifact và workflow media/API đã/chưa chạy.

## Bàn giao

Cập nhật status.md và implementation theo bằng chứng, liệt kê phần thay đổi mới S4, gates
pass/fail/skip/chưa chạy, giới hạn và hướng dẫn dùng. Giữ nguyên khoản chưa nghiệm thu S2/S3.
Không coi offline mock hoặc một ví dụ đẹp là bằng chứng hết lỗi xưng hô.

Dừng ở S4 để user review. Không triển khai S5/S6, Qwen ASR local/pyannote, tự gán giọng,
benchmark toàn corpus hay đổi mặc định. **Không commit/push/tag/release/viết GitHub** khi user
chưa yêu cầu riêng cho phiên này.
