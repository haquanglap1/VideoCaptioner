# Kế hoạch thực thi ASR tiếng Trung → phụ đề tiếng Việt

Ngày: 2026-09-07. User đã chấp nhận hướng trong
[kế hoạch nghiên cứu](asr-provider-plan-2026-09.md). Tài liệu này chia hướng đó thành các
gói có thể triển khai và nghiệm thu riêng. Trạng thái cập nhật 2026-09-07: **S1–S3 có code
và gate offline; S2 đã đo alignment local thật trên clip Trung công khai**. GPT gateway→SRT,
phồn thể alignment S2 và native Soniox/Scribe online còn thiếu acceptance. S4–S6 chưa triển khai.
Code S2 đã commit theo yêu cầu user sau bàn giao; S3 đang dừng để review, chưa commit/push.

Prompt S2 đã thực hiện: [bàn giao yêu cầu](asr-step-2-prompt.md).
Hướng dẫn và giới hạn: [runtime alignment S2](asr-alignment-s2.md).
Prompt S3 đã thực hiện: [yêu cầu S3](asr-step-3-prompt.md).

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
| S2 (code/offline + local smoke, chờ gateway) | Nhận dạng text-only → alignment tiếng Trung → SRT | S1 | Runtime alignment riêng đã đo; còn thiếu key để nghiệm thu GPT gateway→SRT |
| S3 (code/offline, chờ native API) | Soniox v5 và Scribe v2, timestamp + speaker native | S1 | ASR mới đưa speaker xuyên split/optimize/translate input/editor; save/load speaker không mất |
| S4 | Quan hệ người nói/người nghe và xưng hô Trung→Việt | S3; đường hybrid nối sau S5 | Mapping theo cặp/cảnh, user override, dịch lại và cache nhất quán, có review trường hợp mơ hồ |
| S5 | Qwen3-ASR local và diarization pyannote cho local/gateway | S2; reuse speaker contract S3 | Chạy Windows tách Qt, pin model, đo VRAM/speed, giữ speaker trong toàn job |
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
