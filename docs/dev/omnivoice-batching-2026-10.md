# OmniVoice P1 → P1b → P2–P4 — 2026-10-02

Baseline `c6676cc`, hai stash giữ nguyên. Audit mới:
`.tools/omnivoice-upgrade-20261002/`. Không đổi bản cài trên ổ E,
không cài package/tải model, commit hoặc push.

## P1: preset và reference prompt cache

- GUI/CLI có `balanced` (32 bước/FP16 mặc định) và `more-steps`
  (64 bước/FP16, thử nghiệm). CLI: `--omnivoice-quality-preset`.
  `steps` tường minh trong config cũ vẫn có hiệu lực ở `balanced`.
  Không kết luận 64 bước hay FP32 tốt hơn khi chưa nghiệm thu nghe.
- Prompt cache JSON dưới app cache, tách khỏi WAV cache. Key bind SHA audio,
  transcript, recipe (gồm tokenizer), model/code revision, worker, dtype và
  preprocessing. Checksum, schema, shape/range tokens và RMS được kiểm;
  cache hỏng được bỏ qua và encode lại. Không dùng pickle và không giữ model
  GPU qua các job. Prompt được khôi phục vào CPU; model tự chuyển token khi sinh.
- Generation seed được reset trước từng lần generate, độc lập prompt encoding.
  Cache WAV bind effective steps/dtype/preprocessing/recipe/worker/reference.
- Offline: 47 tests OmniVoice pass trước test structural-cache bổ sung;
  158 tests CLI + quality/cache pass sau bổ sung. Không cộng các suite overlap.
  Ruff toàn app/tests pass (cache ghi gặp ACL, kiểm code vẫn pass),
  Pyright toàn app 0/0, translations sync. Panel render đã kiểm layout.
- GPU thật RTX 5090: đúng ba job, mỗi job hai câu cố định, Nữ 01/seed0/1x.
  Cold32 và warm32 giống byte cả hai WAV. Prompt miss/hit/hit;
  64-step tạo hai WAV mới. Cả ba worker/lease đóng sạch.
  E2E lần lượt 34,391 / 30,921 / 32,313 giây; model load khoảng 1,86–2,00s.
  Cold prompt 15,422s; warm prompt dưới độ phân giải timer. Khởi tạo CUDA
  chuyển sang inference đầu ở lượt warm (16,219s), nên không diễn giải
  riêng thời gian encode tiết kiệm được thành tăng tốc toàn job.
- Artifact/GPU receipts và audio so sánh giữ tại audit. Nghe chủ quan/đủ từng
  từ/độ giống giọng chưa được nghiệm thu; WAV hợp lệ không chứng minh lexical.

## P1b: batch inference

[API ghim](https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/omnivoice/models/omnivoice.py)
nhận `generate(text=list[str])`. `BaseTTS` ThreadPoolExecutor chỉ gửi request;
worker OmniVoice giữ model và pipe riêng, nên số luồng không phải batch GPU.

Giữ một worker/model/reference cho job, mặc định batch1. Thử batch1/2/4,
giới hạn thêm tổng chiều dài và padding. Giữ nguyên scheduler sequential:
speed1/natural_max_speed1/gap80ms/max_delay1000ms/rewriteFalse, không cắt lời,
tăng tốc hoặc kéo dài video. Sau phản hồi ban đầu chưa nghe, user đánh giá
**“batch 1 ổn nhất”**. Giữ batch1 mặc định; batch2/4 vẫn thử nghiệm, không tuyên
bố tương đương chất lượng. Tiếp tục P2 sau gate EXE P1b.

### Mapping, cache, seed và lỗi

- Provider override đường gom câu: không dùng ThreadPoolExecutor để giả làm
  batch. Một job giữ một model/reference/language/generation config. Câu được
  gom theo thứ tự và giọng, tối đa 1/2/4; `max(len(text)) * count <= 600`
  mặc định để hạn chế padding. Câu vượt ngân sách chạy nguyên vẹn một mình.
- Pipe có một chủ sở hữu; mỗi batch có request ID, mỗi câu có item ID.
  Runtime kiểm ID/count và WAV mono24k PCM16 có đủ frame trước khi copy ra.
  Kết quả từng câu được trả ngay; callback hủy/timeout sẽ dừng worker, các WAV
  đã trả vẫn được orchestrator giữ/cache và đưa vào review.
- Lỗi generate cả batch được tách đôi, tối đa cây `2*N-1` lần gọi; lỗi item
  riêng không làm mất các item còn lại. Sau OOM, worker giữ trần batch nhỏ hơn
  cho các request còn lại trong job. Không lặp item đã hoàn thành. Nếu batch1
  vẫn lỗi, câu đó FAILED, không xuất video thiếu lời. Cảnh báo fallback vào report.
- Cache hit được loại trước TTS; lời trùng dùng cùng WAV mà vẫn giữ các cue ID,
  mốc timeline và số lần phát. WAV hỏng được retry riêng; không sinh lại peer
  đã có cache. Không sửa scheduler/timing hoặc normalization lời nói.
- RNG policy **`ordered-batch-v1-first-valid-wav`**: reset seed trước mỗi lần
  generate; RNG được chia sẻ trong batch. Chỉ kỳ vọng lặp lại trong cùng ordered
  request/shape, không kỳ vọng serial và batch có cùng bytes. Key bind batch cap,
  character budget, seed, fallback policy và worker SHA, cùng identity P1.
  Cache giữ realization hợp lệ đầu tiên của từng text dưới policy đó; cache
  miss một phần hoặc OOM có thể tạo WAV khác một lần chạy cold đủ batch.
  Không gọi fallback WAV là output batch4 cố định. Worker metrics ghi SHA của
  cohort và số item thực tế ở mỗi lần generate, không ghi transcript.
- GUI tách control batch GPU; số luồng TTS bị disable khi chọn OmniVoice.
  CLI `--tts-concurrency` vẫn tương thích nhưng không tăng worker/model OmniVoice.

### Phép đo đã khóa trước

RTX 5090 / 32.607 MiB VRAM, cùng model/reference Nữ 01/tiếng Việt,
32 steps/FP16/seed0/speed1. Có đúng 3 job (batch1/2/4), mỗi job một warmup
riêng rồi **cùng 8 câu tổng hợp**, tổng 27 WAV gồm warmup. Không WAV cache,
không sweep; request threads đều 12. Một worker GPU tại một thời điểm.

| Batch thực tế | Số gọi generate đo | Sinh audio (s) | Synthesis wall (s) | Câu/s | Audio s / inference s | Peak allocated (GiB) | Peak reserved (GiB) | Toàn job (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 8 | 4,827 | 4,875 | 1,641 | 5,453 | 2,002 | 3,443 | 34,969 |
| 2 | 4 | 2,500 | 2,563 | 3,121 | 10,424 | 2,102 | 2,295 | 32,250 |
| 4 | 2 | 1,797 | 1,828 | 4,376 | 14,597 | 2,300 | 2,584 | 31,266 |

Batch4 nhanh hơn khoảng **2,69 lần ở phần generate** trên corpus này.
Đây là một lượt mỗi cấu hình, không phải thống kê nhiều lượt hoặc cam kết cho
câu dài/video thật. CUDA allocated là peak bộ nhớ tensor của worker; reserved
là pool allocator, không phải VRAM toàn hệ thống hay mức có thể suy ra bằng
cách cộng/trừ các cột. Prompt cold ở batch1 làm allocator giữ pool lớn hơn.

| Batch | Verify (s) | Worker startup gồm import/load (s) | Model load (s, nằm trong startup) | Prompt (s) | Warmup (s) |
| --- | --- | --- | --- | --- | --- |
| 1 | 1,750 | 11,437 | 1,906 | 14,735 (miss) | 1,687 |
| 2 | 1,828 | 11,328 | 1,859 | 0,016 (hit) | 16,171 |
| 4 | 1,828 | 11,109 | 1,906 | 0,016 (hit) | 16,125 |

Khởi tạo CUDA ở cold prompt chuyển sang warmup khi prompt hit. Cột generate
đều đã làm nóng GPU và sinh WAV mới; không lấy prompt/WAV cache hit để tuyên bố
tăng tốc inference. Toàn job gồm cả verify/import/load/prompt/warmup/cleanup,
nên không có mức tăng 2,69 lần cho toàn job ngắn này.

Đủ **24/24 WAV đo**, đúng text/order/count ở data path, mono24k PCM16, cùng
reference, không lỗi/OOM thật; ba worker/lease đóng sạch. Hai câu batch1 trùng
corpus P1 có SHA giống baseline 32-step trước đó. Không chứng minh model đã đọc
đúng từng từ hay giữ giọng chủ quan. OOM fallback chỉ được kiểm bằng stub lỗi,
không cố làm đầy VRAM thật.

### Offline và artifact

- 412 tests liên quan OmniVoice/dubbing/CLI/QThread/UI pass; 12 tests batch/CLI
  sau guard backoff bổ sung pass. Các suite overlap, không cộng dồn.
- Kiểm fake pipe thực bằng subprocess: item lỗi, sai ID, timeout, callback hủy,
  giữ WAV đã hoàn thành, worker và GPU lease đóng. Worker stub kiểm actual list,
  count mismatch, OOM, giảm trần lần nữa, invalid audio và không lặp item thành công.
- Cache miss/hit/corruption và duplicate cue mapping kiểm qua orchestrator thật.
  Existing sequential/FFmpeg checks giữ đủ text, gap80ms/trễ tối đa1000ms,
  speed1 và không cắt audio khi overflow.
- Ruff toàn app/tests pass (`--no-cache` tránh ACL cache cũ); Pyright 0/0.
  Source panel render không cắt control batch/preset. Native playback chưa test.
- P1 EXE: PyInstaller exit0/165,187s; 31.559.539 bytes,
  SHA `7c0c66746b689f6156935c412d42e78ba5a87259aa3de9c1aba6c8c06e123e09`.
  Frozen preset64: 2 WAV fresh → 2 hit/0 TTS; hai MP4 cùng SHA,
  speed1/không rewrite/không trễ; GUI20s/exit0, zero owned children.
- P1b EXE: PyInstaller exit0/155,110s; 31.565.752 bytes,
  SHA `607cb2b1ef13591f2ce0075423739569cd7d974fc69ae2dd76014c6a6dc7dcd0`.
  8 WAV fresh batch4 khớp bytes source batch4 → 8 cache hit/0 TTS; hai MP4
  cùng SHA `4b018a0a59bb81117f688b1fbb62a707bc3e758b785d8c9bd536b9f2e6388ee1`.
  Đúng8 cue/text/order/1x/gap/duration, không rewrite/trễ/lỗi; GUI20s/exit0,
  zero owned children. Bộ99.315 files model/runtime giữ cùng inventory stage.

Audio cần nghe: `p1b-listening/review-batch-{1,2,4}.wav` trong audit, mỗi file
gồm mẫu giọng rồi tám câu đúng thứ tự `p1b-corpus.json`. User ưu tiên batch1;
mặc định **32-step/FP16, batch1** giữ nguyên. Không thay trạng thái OCR/ASR cũ.

## P2: preview lời đọc tiếng Việt

- **Chuẩn bị lời đọc trước TTS** tạo kế hoạch source-bound trên QThread, chưa
  sinh WAV. Managed runtime vẫn nạp để xác minh và chụp identity; đóng ngay
  sau chuẩn bị. User mở/sửa/lưu kế hoạch bằng luồng review hiện có.
- Nút gợi ý chỉ thay nội dung ô lời đọc đang chọn; bấm Áp dụng mới đổi review.
  Không tự áp dụng khi chạy job; subtitle/source/timing/cue ID không đổi.
  Cho phép số nguyên đến999.999.999, thập phân dấu phẩy, một allowlist đơn vị
  và viết tắt. Dấu câu giữ nguyên; ngày/giờ, số0 đầu và dấu chấm phân nhóm
  mơ hồ giữ nguyên và có cảnh báo để duyệt. Không hứa chuẩn hóa mọi loại số.
- CLI `dub ... --prepare-review plan.json` tạo preview; sửa lời qua review rồi
  `dub ... --review approved.json` xác minh binding trước khi synthesize.
- 194 tests liên quan pass sau sửa lifetime QApplication của test mới;
  12 tests P2 cuối gồm QThread prepare/join pass; Ruff/Pyright 0/0.
  Log lần đầu52 fixture errors được giữ, do test hủy QApplication sớm làm
  QConfig object đã bị xóa, không phải52 lỗi behavior production.
- GPU source: đúng2 câu đã duyệt, batch1/32step/1x, subtitle giữ SHA/bytes;
  2 WAV mới/0 lỗi/0 rewrite/0 tăng tốc/0 trễ. Preview không gọi inference.
  Chất lượng nghe của hai câu đã chuẩn hóa chưa được user nghiệm thu riêng.
- P2 EXE exit0/168,297s, 31.571.479 bytes,
  SHA `97b374b8a54f277b0ccf15868e44280784cbb71078abfccce559c58fa21cc310`.
  Prepare không sinh WAV; resume đúng2 câu đã duyệt; lần sau2 hit/0 TTS;
  MP4 cùng SHA, nguồn giữ nguyên, worker đóng sạch. GUI20s/exit0/zero children.

## P3: pitch và nghỉ thêm ở cuối nhóm

- Pitch ±6 semitone, mặc định0; dùng FFmpeg `rubberband=tempo=1` với formant
  preserved. Không dùng atempo để ép khung, không cắt đầu/đuôi câu.
  [API filter chính thức](https://ffmpeg.org/ffmpeg-filters.html#rubberband).
- Nghỉ thêm mặc định0. Dấu kết thúc nhóm `, ; :` thêm1 lần giá trị; `. ? ! …`
  thêm2 lần, tối đa1000ms. Chỉ nối PCM zero sau đủ frame gốc; không cắt câu
  tại dấu câu nội bộ khi chưa có alignment. Ngắt bên trong vẫn do model xử lý.
- Đo WAV sau pitch/pause rồi chuyển scheduler cũ. Gap80ms, trễ1000ms, speed1
  và overflow review của job kiểm chứng giữ nguyên. Neutral giữ byte WAV và
  cache identity P1b/P2; nonzero bind effects policy/pitch/pause vào cache key.
- 111 tests OmniVoice/sequential pass, gồm real FFmpeg tone: tần số đúng
  pitch+2 trong sai số2Hz, duration2s sai số≤1ms; zero tails giữ toàn bộ frame.
  48 tests cache/UI bổ sung pass sau khi sửa fixture QApplication session;
  hai lượt chọn sai tên/path test và lượt fixture lỗi được giữ trong audit.
  Ruff/Pyright pass. UI panel đã render/kiểm.
- GPU: đúng2 WAV mới trên lời P2 đã duyệt, pitch+2/basepause120ms/batch1/1x;
  mỗi WAV dài hơn baseline đúng240ms trong sai số2ms. Video giữ nguồn/cue/
  lời đã duyệt; không rewrite, tăng tốc, trễ hay orphan worker. Chưa nghiệm
  thu nghe riêng pitch, không tăng default pitch hoặc pause.
- P3 EXE exit0/162,594s, 31.575.978 bytes,
  SHA `b3b6ce6111d2d585aebbda6a17948fba1108fa01c6f1452186bc27fa10bc281d`.
  Frozen prepare →2 fresh →2 cache/0 TTS, cùng SHA MP4,
  speed1/không rewrite/trễ/lỗi; GUI20s/exit0, zero owned children.

## P4: chép lời mẫu, thu microphone, văn bản thành WAV/SRT

- Chép lời mẫu dùng Faster-Whisper đã cài theo settings/model-dir, kiểm đủ
  model.bin/config/tokenizer trước khi chạy, không tải model. Snapshot tùy chọn
  trên UI; xử lý qua QThread và runner subprocess có timeout/cancel/GPU lease
  đang dùng trong app. Chỉ tái dùng runner, không chạy Qwen hoặc pipeline cũ.
  Transcript là bản nháp; giữ nguồn, từ chối kết quả trễ khi audio đã thay đổi,
  không tự lưu voice profile. User duyệt/sửa rồi Lưu giọng riêng.
- Microphone chỉ mở khi bấm Thu mẫu; giới hạn3–10s, có nút Dừng, tự dừng10s.
  Chọn PCM16 được thiết bị hỗ trợ, giữ bản thu gốc, lưu giọng vẫn đi qua worker
  chuẩn hóa cũ. Cancel/đóng panel dừng recorder và thu hồi worker. Test không
  bật microphone thật; hardware/native capture vẫn cần user kiểm tra.
- Văn bản → WAV + SRT: mỗi dòng không rỗng là một cue, giữ cả câu lặp.
  Dùng provider/cache/orchestrator đo WAV hiện có, `sequential_slots` ở1x với
  gap80ms và `EditorCue`/`project_to_tts_asr` cho mốc ms. Không có video/timeline
  đầu vào để kéo dài hay ép lời. Không áp dụng rewrite tự động.
  Xuất tên mới; không ghi đè WAV/SRT đã có. Giữ approved.txt và từng đoạn trong
  thư mục `<stem>-parts-*` cạnh output, kể cả khi lỗi/hủy; không xuất file thiếu câu.
- CLI: `omnivoice speak approved.txt -o speech.wav`; chọn giọng/preset/batch/
  pitch/pause bằng flags OmniVoice hiện có. `omnivoice transcribe-reference
  reference.wav -o draft.txt --model large-v3` chỉ dùng model local đã có.
- Offline bộ liên quan cuối **446 passed / 0 skipped**, 2 dependency warnings;
  sau sửa cách truyền tên model, **10 tests P4 pass** (overlap, không cộng dồn).
  Ruff toàn app/tests pass; Pyright0/0; translations sync. Recorder test bằng
  PCM giả lập; QThread được join, panel mở không kích hoạt microphone.
- ASR source lần đầu lỗi argument **trước nạp model/inference**: binary ghép
  `faster-whisper-` vào giá trị `-m`, nên đường dẫn tuyệt đối bị sai. Đổi về
  tên model + model-dir đúng API đang cài, không đổi binary/runtime/weights.
  Giữ cả log cũ và v2. Lượt inference source duy nhất trả draft trong27,140s
  từ reference AI Nữ01/large-v3/CUDA; không coi draft là lexical acceptance.
- Source text/audio đúng2 WAV mới, output5570ms, hai cue nguyên lời cách80ms,
  số frame khớp SRT đến≤1ms, worker/lease đóng. Không chạy microphone thật,
  không mở lại OCR/ASR pilot hoặc thay gate chất lượng lịch sử.
- Frozen P4 đầu bắt lỗi wrapper CLI nhận hai argument trong khi dispatcher chỉ
  gửi args; chưa gọi ASR/TTS. Sửa theo `_run_dub`, thêm2 test qua `main()`;
  **166 tests CLI/P4 pass**,21 tests TTS core pass, Ruff/Pyright0/0. Giữ nguyên
  artifact `omni-p4` lỗi CLI và logs; không coi GUI smoke của nó là pass workflow.

## Artifact cuối và các gate còn mở

- `dist/VideoCaptioner-20261002-omni-final/VideoCaptioner-20261002-omni-final.exe`.
  Phân phối nguyên thư mục onedir kèm models, không chỉ chép EXE.
  PyInstaller exit0/155,625s,6 WARNING/0 ERROR. Warning cùng nhóm baseline:
  urllib3 emscripten thiếu `js`; curl_cffi/yt_dlp_ejs không thu data;
  hidden imports tzdata/sip; bỏ AppKit của macOS trên Windows.
  Không cài thêm dependency để giấu warning.
- EXE **31.597.917 bytes**, timestamp **2026-10-02 12:12:58 +07:00**, SHA256
  `63bd50187338e6e3940055341553b1a580c145f35a8cb35bf779891c09decb99`.
- Final frozen ASR reference65,578s trả draft; text/audio39,719s gồm startup,
  tạo2 cue/5570ms, gap80ms, SRT≤1ms. WAV giống byte source,
  SHA `562b89486bf52430b09ee3cba846fb088bc966bf3fface83f673765a4b0d3f09`.
  CLI tự tìm model/runtime cạnh EXE; không dùng runtime path của máy dev.
- GUI chính artifact mở20s rồi đóng exit0; cả hai workflow/GUI zero owned
  children. Panel nguồn đã render/kiểm layout; không gọi đó là native record/playback.
- **99.315 files** model/runtime khớp size inventory stage đã verify. Có
  Faster-Whisper runtime + large-v3/tiny, Qwen, OmniVoice, VieNeu runtime/model,
  OCR-v6-medium; không có Community-1 riêng. Không re-stage/download model,
  không sửa bản cài E hoặc settings user; dùng work/cache riêng trong audit.
- User ưu tiên batch1. Nghe từng từ/độ giống giọng cho mọi câu,64-step,pitch,
  microphone hardware/native record, video thật dài còn mở. OOM thật chưa
  ép trên GPU; fallback/cancel/timeout kiểm offline với worker/subprocess thật
  và lỗi giả lập. Không nâng batch mặc định hoặc kết luận chất lượng ASR/OCR cũ.

Receipts chính: `p1-gpu.json`, `p1b-gpu.json`, `p1b-artifact.json`,
`p2-gpu.json`, `p2-artifact.json`, `p3-gpu.json`, `p3-artifact.json`,
`p4-source.json`, `final-build.json`, `final-artifact.json`, `final-gui.json`
và `final-state.json` trong audit. Không commit/push/deploy.

## Bàn giao bộ test thực tế sang E

Theo yêu cầu user tiếp theo, tạo bộ độc lập tại
`E:\Game\Translate video\VideoCaptioner-20261002-omni-final\`, có shortcut
`Test OmniVoice 20261002.lnk` ở thư mục cha. Bản cũ ở gốc và dữ liệu user giữ nguyên.
Dùng lại đúng EXE đã verify, không rebuild hoặc stage/download model mới.

- **99.917 files / 42.786.740.700 bytes** kiểm SHA256 sau copy (601 file app,
  99.315 file model/runtime và manifest). EXE giữ SHA nêu trên.
- Settings test riêng khóa batch1/32-step FP16/1x, natural_max_speed1,
  sequential/delay1000ms/rewriteFalse/pitch0/pause0. Không chuyển dữ liệu riêng.
- Một câu GPU fresh từ E mới: CLI exit0, WAV2,640s, PCM khớp source; ghi nhận
  worker Python và model directory nằm trong chính bộ E mới. Không dùng cache
  WAV cũ hoặc runtime F để làm bằng chứng relocation.
- GUI20s/exit0, zero owned children; settings readback đúng.117.036 mục của bản
  cũ giữ metadata; settings/cookies/EXE cũ giữ SHA trước/sau.
- Audit `.tools/omnivoice-delivery-20261002/`: delivery.json, verification.json,
  closeout.json, README_TEST.txt và NEXT_SESSION.txt. Hai file TXT được đặt
  ở E gốc với hậu tố OMNIVOICE_20261002 để user mở/test và tiếp tục phiên sau.
- Plan chưa xong100% về nghiệm thu. P3 còn giới hạn pause cuối nhóm; native
  capture/playback, video dài và chất lượng đọc rộng hơn cần evidence thực tế.

## File thay đổi phiên triển khai

- `README.md`
- `VideoCaptioner.spec`
- `docs/dev/omnivoice-batching-2026-10.md`
- `docs/dev/omnivoice-voices-2026-10.md`
- `status.md`
- `tests/conftest.py`
- `tests/test_dubbing/test_vietnamese_text.py`
- `tests/test_omnivoice/test_batch.py`
- `tests/test_omnivoice/test_effects.py`
- `tests/test_omnivoice/test_provider.py`
- `tests/test_omnivoice/test_quality_cache.py`
- `tests/test_omnivoice/test_tools.py`
- `videocaptioner/cli/commands/dub.py`
- `videocaptioner/cli/commands/omnivoice.py`
- `videocaptioner/cli/config.py`
- `videocaptioner/cli/main.py`
- `videocaptioner/core/dubbing/engine.py`
- `videocaptioner/core/dubbing/orchestrator.py`
- `videocaptioner/core/dubbing/vietnamese_text.py`
- `videocaptioner/core/tts/omnivoice/config.py`
- `videocaptioner/core/tts/omnivoice/effects.py`
- `videocaptioner/core/tts/omnivoice/prompt_cache.py`
- `videocaptioner/core/tts/omnivoice/provider.py`
- `videocaptioner/core/tts/omnivoice/reference.py`
- `videocaptioner/core/tts/omnivoice/runtime.py`
- `videocaptioner/core/tts/omnivoice/text_audio.py`
- `videocaptioner/core/tts/tts_data.py`
- `videocaptioner/resources/omnivoice/worker.py`
- `videocaptioner/ui/common/config.py`
- `videocaptioner/ui/components/dubbing_review_dialog.py`
- `videocaptioner/ui/components/omnivoice_panel.py`
- `videocaptioner/ui/components/omnivoice_recorder.py`
- `videocaptioner/ui/task_factory.py`
- `videocaptioner/ui/thread/dubbing_thread.py`
- `videocaptioner/ui/thread/omnivoice_tools_thread.py`
- `videocaptioner/ui/view/dubbing_interface.py`
