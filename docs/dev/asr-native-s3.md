# ASR S3 — Soniox v5 và ElevenLabs Scribe v2

Triển khai trên baseline S2 `d21251a5d1be3d4baceec5a3e8d6869ceb4877c5` (bao gồm code
S2 `96470bf7`). Hai engine native được chọn tường minh; mặc định và preset Whisper/gateway
S1 không đổi. Không dùng Qwen để tạo speaker, không triển khai S4–S6.

## Cấu hình và sử dụng

GUI: chọn `Soniox v5 [API]` hoặc `ElevenLabs Scribe v2 [API]` trong tab Nhận dạng hoặc
Cài đặt. Mỗi provider có API Base, key riêng và công tắc nhãn người nói ẩn danh. Model được
ghim tường minh là `stt-async-v5` / `scribe_v2`; config model khác bị từ chối, không đổi
model trả phí âm thầm. S3 cho chọn Chinese hoặc tự nhận diện ngôn ngữ; không quảng cáo
đã nghiệm thu phương ngữ hay ASR tiếng Việt.

```powershell
uv run --frozen videocaptioner config set soniox.api_key <soniox-key>
uv run --frozen videocaptioner transcribe clip.mp4 --asr soniox --language zh -o subtitles.json
uv run --frozen videocaptioner config set scribe.api_key <elevenlabs-key>
uv run --frozen videocaptioner process clip.mp4 --asr scribe --language zh --no-scribe-diarize
```

Hai section CLI `soniox.*`, `scribe.*` có `api_key`, `api_base`, `model`, `diarize`.
Các flag `--soniox-api-key/base/model`, `--scribe-api-key/base/model` và cặp
`--[no-]soniox-diarize`, `--[no-]scribe-diarize` dùng được với `transcribe` và `process`.
Env tương ứng `VIDEOCAPTIONER_SONIOX_*` / `VIDEOCAPTIONER_SCRIBE_*`; boolean diarize được parse
thành boolean thật. Thứ tự CLI > env > file > GUI > default được giữ. GUI chỉ mirror key,
endpoint/model; công tắc GUI không tự thay hành vi CLI. Đổi endpoint không thừa kế key; các
key cũ được giữ trong map theo endpoint để khôi phục khi quay lại. Không dùng key Whisper/LLM/TTS
cho engine native. Không đọc credential hoặc media từ checkout khác.

`Check service` chỉ gọi GET theo yêu cầu người dùng: Soniox `/v1/models`, ElevenLabs `/v1/user`.
Kết quả chỉ chứng minh request đọc dịch vụ/auth đó; ElevenLabs có thể từ chối key thiếu quyền
đọc user dù key có quyền ASR. Probe không upload audio, không suy quyền model/inference,
timestamp hoặc speaker từ catalog; payload tài khoản/catalog được bỏ đi. Worker giữ contextvars,
hủy được request đang chờ và `wait()` khi thu hồi. Mở settings không gọi network/model.

## Hợp đồng đã đối chiếu ngày 2026-09-07

Nguồn chính thức; không dùng catalog làm bằng chứng inference:

| Provider | Request và response | Giới hạn áp dụng trong app |
| --- | --- | --- |
| Soniox | Bearer key; multipart `/v1/files` → JSON `/v1/transcriptions` → GET status → GET `/{id}/transcript`; `tokens.text/start_ms/end_ms/speaker`, ghép subword theo ranh chữ/space provider | Toàn file, <=300 phút; cap ứng dụng 1.000.000.000 byte. Docs quota ghi storage tổng 10 GB và 1.000 file, không suy đó là cap một upload |
| Scribe | `xi-api-key`; multipart `/v1/speech-to-text`, `model_id=scribe_v2`, `diarize`, `tag_audio_events=true`, `timestamps_granularity=word`, `language_code=zh` khi chọn Chinese; words `type/text/start/end/speaker_id`, giây → ms | Toàn file, <=10 giờ, cap ứng dụng 3.000.000.000 byte; API reference nói dưới 5 GB nhưng overview nói 3 GB, nên dùng mức bảo thủ 3 GB |

[Soniox models](https://soniox.com/docs/stt/models),
[create](https://soniox.com/docs/api-reference/stt/transcriptions/create_transcription),
[upload](https://soniox.com/docs/api-reference/stt/files/upload_file),
[transcript](https://soniox.com/docs/api-reference/stt/transcriptions/get_transcription_transcript),
[quotas](https://soniox.com/docs/stt/async/limits-and-quotas),
[token schema](https://soniox.com/docs/sdk/python-SDK/Full-SDK-reference/types).
[Scribe request/schema](https://elevenlabs.io/docs/api-reference/speech-to-text/convert),
[overview/limits](https://elevenlabs.io/docs/overview/capabilities/speech-to-text),
[service probe](https://elevenlabs.io/docs/api-reference/user/get).

Giữ model ID đúng kế hoạch, không cần SDK mới/dependency mới. Quyền model, credit/quota thực tế
của tài khoản chỉ xác minh được bằng request phù hợp. Không tạo token hoặc mua credit.
Không bật speaker library, speaker roles, multichannel, dịch của Soniox, no-verbatim, keyterms
hay entity detection. Audio events không đi vào subtitle speech/TTS. Multipart dùng tên trung
tính và MIME từ header audio, không gửi local path/prompt/transcript dư thừa. File lớn được
stream từ disk; fingerprint đọc theo block, không đọc nhiều giờ audio vào RAM. FFprobe có
deadline 30 s và subprocess env được lọc; request bị chặn trước upload nếu vượt cap/duration
(app yêu cầu tối thiểu 100 ms). Không tự chia thành nhiều job hoặc nối speaker giữa file/chunk.

## Vòng đời, retry, hủy và tài nguyên remote

`NativeJobState` tách stage/status local và trạng thái remote. Soniox chờ các state docs
`queued/processing/completed/error`; unknown state, lỗi parser hoặc timing đều dừng để review.
Mỗi job deadline 3.600 s; HTTP timeout 120 s/connect 10 s, riêng Scribe đồng bộ dùng deadline
job. GET poll/result tối đa 3 attempt khi 429/5xx/lỗi kết nối, backoff hữu hạn và Retry-After
bị chặn 10 s/deadline; polling bình thường tăng từ 0,5 s tới 5 s. Hủy callback khoảng 100 ms,
cancel async task/socket và đợi cleanup xong; không để request background tiếp tục ở máy.

POST upload/submit/recognition **không tự retry**, kể cả 429. Timeout, 5xx hoặc response mất ID
có thể đã được provider nhận: báo acceptance không chắc chắn và không tạo job mới. Soniox
`client_reference_id` chỉ là tracking và không cần unique theo docs, nên không coi là idempotency.
App không scan/xóa tài nguyên của tài khoản để recovery. Lỗi được phân theo stage và HTTP code,
không echo raw error body/key/transcript/local path hoặc ghi remote IDs vào cache.

Soniox cleanup chỉ thử DELETE đúng transcription/file do request hiện tại vừa tạo. Job đang
processing có thể trả 409; khi đó giữ input file, báo remote có thể tiếp tục/chịu phí và cần
kiểm tra console. Không xóa input của job chưa biết đã được nhận hay chưa. Khi job đã terminal
hoặc đã xóa, có thể xóa file. Mỗi DELETE có hạn 3 s, không lặp vô hạn. Upload mất phản hồi không
có ID thì báo không chắc chắn về cleanup. Tài liệu Soniox nêu tự xóa file/transcript sau 30 ngày;
không coi đó là hủy inference.
[Delete semantics](https://soniox.com/docs/api-reference/stt/transcriptions/delete_transcription).

Scribe dùng request đồng bộ, không có remote job ID để hủy in-flight. Khi response cung cấp
`transcription_id` hợp lệ, app thử xóa đúng transcript qua endpoint docs; khi thiếu ID hoặc
cleanup lỗi, báo giới hạn storage cleanup. DELETE transcript sau thành công không phải hoàn
tiền hoặc hủy inference. Hủy local/timeout có thể vẫn chịu phí; UI nêu giới hạn trước chạy.
[Scribe delete](https://elevenlabs.io/docs/api-reference/speech-to-text/delete).

## Metadata và timing

`ASRDataSeg(..., metadata=None)` giữ constructor cũ. `ASRMetadata` immutable có provider,
scope UUID local theo **request**, speaker optional và timing provenance native/edited.
Speaker công khai trong pipeline/editor là `provider:scope:label`; không dùng remote job ID,
không coi label 1 của hai request là cùng người. Cache hit khôi phục đúng scope của kết quả
đã lưu. Known/unknown, speaker trở lại và nhiều segment overlapping được giữ độc lập.
Nhãn anonymous không suy tên, tuổi, giới, quan hệ, người nghe hoặc cách xưng hô.

Parser kiểm tra finite/nonnegative/start<=end/audio bounds trước quy đổi canonical integer ms;
speech lexical zero-duration bị từ chối. Transcript phải khớp đầy đủ token text theo thứ tự;
thiếu timing, mất/trùng/đổi chữ, token translation không được yêu cầu hay kiểu token lạ đều
dừng review toàn kết quả. Space được gắn vào text lân cận mà không tạo timing; punctuation
giữ nguyên. Soniox ghép Latin subword liên tiếp chỉ khi không có ranh space; CJK giữ span
character/subword provider. Không chia đều thời lượng hoặc ép timing không-overlap của S2
lên các người nói cloud. Audio events nằm trong `ASRData.events`, tách khỏi lời thoại.

Split native chỉ gom các span đã đo liên tiếp, cùng metadata/speaker, có ranh pause/dấu câu
và giới hạn độ dài; không gọi fuzzy matcher hoặc nội suy word timing. Một token dài không có
ranh đo bên trong được giữ nguyên. Không tối ưu lại timing/punctuation của dữ liệu này. Merge
khác speaker/source (gồm known↔unknown) bị từ chối. Optimizer native dùng từng cue một request
và kiểm tra khóa association; copy giữ metadata. Translator nhận metadata typed để bảo toàn
association và cache fingerprint, nhưng **prompt dịch chưa dùng quan hệ/xưng hô** (S4).

GUI pipeline và CLI process truyền ASRData trong RAM thay vì reimport SRT. JSON subtitle và
bảng subtitle giữ `asr_metadata`; JSON có events dùng envelope `asr-native-v1` với `cues/events`.
SRT/ASS/TXT thông thường không giữ speaker; không tự thêm nhãn speaker vào chữ. Có thể chọn
JSON khi cần mở lại với metadata. Table handoff sang editor dùng JSON khi có metadata/events.

Editor tái sử dụng `EditorCue.speaker` và `EditCueSpeakerCommand`; thêm metadata provenance và
events tùy chọn trong JSON, giữ `editor-project-v1`. Import/save/load chấp nhận overlap giữa
cue có ASR provenance, giữ cue ID/timing; guard non-overlap cũ vẫn áp dụng cho cue thông thường.
Nhãn/timing/text sửa qua CommandStack; timing sửa thủ công được đánh dấu edited và undo khôi
phục provenance cũ. Nút split editor hiện chỉ có vị trí thời gian, chưa có vị trí chữ rõ ràng,
nên **từ chối split cue native để review**, không tự chia chữ/nội suy rồi gọi là đo thật.
Normal save vẫn JSON + SRT; ASS chỉ qua Save as ASS. Timeline giữ các cue overlap nhưng preview
text overlay hiện chọn một active cue như trước; export SRT giữ tất cả cue, chưa đánh giá chất
lượng đọc/chồng dòng của renderer trên hội thoại thật.

## Cache và giới hạn acceptance

Cache `NativeASR:v1-<sha256>` theo audio bytes/provider/endpoint/model/language/diarize/
audio-event/timing/speaker policy. Không đọc cache Whisper legacy hoặc cache S2. Không trộn
bật/tắt diarization; key API không nằm trong cache key, value hoặc repr config. Chỉ cache
response fields parser cần sau validation; cache hit vẫn parse/validate. Cache data local chứa
text/timing theo policy hiện có của app; không track cache/media/log trong Git.

Offline test/mock không chứng minh model online hay diarization chính xác. Không có key native
trong worktree/env của phiên này; không nghiệm thu Soniox/Scribe online hoặc media/API từ EXE.
Các khoản còn thiếu S2 giữ nguyên: **GPT gateway→SRT chưa nghiệm thu; phồn thể Qwen strict chưa
đạt acceptance**. Local alignment Qwen và EXE startup S2 đã đo ở baseline, không suy thêm từ S3.
Input S4 là metadata optional scoped + speaker editable và cache/association được bảo toàn;
chưa có bảng nhân vật/addressee/xưng hô, tự gán giọng TTS, pyannote hoặc benchmark S6.

Gate cuối và danh sách file trong [bàn giao implementation](asr-implementation-2026-09.md).
