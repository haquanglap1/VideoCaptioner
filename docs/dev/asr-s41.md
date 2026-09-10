# S4.1 — deadline dịch và review ASR tại máy

S4.1 tiếp tục code S4 `8558082`, baseline bàn giao `47d1cec`, trên nhánh
`codex/asr-s3-native`. Không đổi engine/model/endpoint mặc định, không triển khai S5–S6.

## Deadline dịch

GUI: **Cài đặt → Dịch vụ dịch → Thời gian chờ yêu cầu dịch (giây)**, chọn **300** khi
dùng `gpt-5.6-terra`. Model vẫn phải được chọn riêng trong cấu hình LLM. Giá trị mặc định
cho settings cũ là **120 giây**, giới hạn **1–600**, chỉ nhận số nguyên hữu hạn.

CLI dùng cùng validation và giữ precedence CLI > env > config > default:

```powershell
uv run --frozen videocaptioner config set llm.request_timeout 300
uv run --frozen videocaptioner subtitle input.json --no-split --no-optimize `
  --translator llm --target-language vi --model gpt-5.6-terra --llm-timeout 300 -o translated.json
```

`--llm-timeout` cũng dùng được với `process`; env là
`VIDEOCAPTIONER_LLM_REQUEST_TIMEOUT`. GUI không tự ghi cấu hình hành vi sang CLI.
Deadline áp dụng cho từng request dịch/brief, cả khi context trống. Validation JSON có
tối đa ba lượt sửa có chủ đích; không tự retry HTTP/network POST hay đổi model khi timeout.
Hủy/timeout tại máy không bảo đảm dừng xử lý hoặc hoàn phí phía provider.

Worker chụp config, credential và nguồn trước khi chạy. Translator nhận credential tường minh,
không đọc lại singleton giữa các batch. Socket async thuộc job, không follow redirect; cancel
kiểm tra khoảng 100 ms, cancel/join task và đóng client trước trả về. Worker phụ đề GUI cũng dùng
cùng config/credential đã chụp cho split/optimize. Không ghi credential vào environment.

## Context gọn hơn

Schema lưu vẫn `conversation-context-v1`; policy request/fingerprint là
`conversation-request-v2`. Request giữ glossary nhân vật đã xác nhận, kết quả resolve theo
scope/cặp/lock, cửa sổ nguồn ±4 cue và bằng chứng liên quan kể cả cue ở xa. Selection 1–9 cue
vẫn nhận snapshot toàn tài liệu. Các trường unknown/rỗng dùng defaults mô tả một lần trong
prompt; thông báo proposal/conflict được nhóm theo lý do. Không gửi mọi proposal không liên quan
vào mỗi batch. Không dùng brief LLM ngẫu nhiên làm cache key.

Bộ tổng hợp 30 câu có proposal unknown: payload context JSON chuẩn hóa UTF-8 giảm
**11.595 → 2.044 byte (82,37%)**. Đây chỉ là khối context, không phải toàn prompt hoặc usage
model. Máy không có tokenizer tương ứng; không suy số token, hóa đơn hay chất lượng từ số byte.
Các test vẫn kiểm tra quote/narration, 他/她/它, danh xưng, chủ ngữ lược, nhóm người nghe và rule
theo hướng; không lấy output mock làm ground truth ngôn ngữ.

## Bảo toàn và sửa kết quả nhận dạng lỗi timing

Soniox/Scribe trả được transcript/token nhưng validator từ chối timing/coverage sẽ tạo
`asr-review-v1` riêng tại **AppData/asr-review/**. Vị trí root theo `config.py` cho source,
pip và frozen. File có UUID riêng; không ghi vào cache ASR thành công và không overwrite review
cũ. Response sai cấu trúc đến mức không có transcript/token để liên kết vẫn là lỗi protocol.

Review giữ text/token tối thiểu, timing gốc theo đơn vị provider, scope local, ID token,
speaker, model/ngôn ngữ và kiểu output đã chọn. Không giữ key, headers, endpoint, remote IDs
hoặc đường dẫn audio. Fingerprint kiểm tra recognition gốc khi mở lại; sửa raw timing trực tiếp
làm file không hợp lệ. Thay đổi được lưu riêng trong `overrides` với nguồn `user`.

GUI mở dialog sau lỗi, hoặc chọn **Nhận dạng → Mở bản review ASR** để mở lại JSON mà không
gọi provider. Bảng hiển thị chữ/ngữ cảnh, nhãn speaker, mốc gốc, mốc ms hiện tại và lý do lỗi.
Chọn token, nhập thời gian đã kiểm tra rồi **Áp dụng thời gian sửa**. **Hoàn tác/Làm lại** dùng
`CommandStack`. **Lưu bản review…** giữ cả dữ liệu gốc và override; **Kiểm tra và xuất…** chỉ
xuất sau khi toàn bộ response pass validator. JSON giữ cue ID, token association và provenance;
SRT không giữ các metadata này. Export không được thay chính file review đang mở.

CLI ghi rõ artifact và giữ **exit 5** cho nhận dạng chưa được xử lý. Có thể chọn vị trí bản sao:

```powershell
uv run --frozen videocaptioner transcribe clip.mp4 --asr soniox --language zh `
  --asr-review recognition.asr-review.json -o subtitles.json

# Mở/validate tại máy; vẫn exit 5 nếu còn lỗi, không xuất một prefix thành success.
uv run --frozen videocaptioner asr-review recognition.asr-review.json

# Ví dụ cú pháp, KHÔNG phải gợi ý sửa mốc của audio thật.
uv run --frozen videocaptioner asr-review recognition.asr-review.json `
  --set-timing token-000001:100:900 --save-review reviewed.asr-review.json -o reviewed.json
```

Lặp `--set-timing TOKEN_ID:START_MS:END_MS` cho từng token đã kiểm tra. CLI chỉ báo ID/vị trí/lý do,
không in transcript ra log mặc định. Sai tham số/range hoặc dùng cùng đường dẫn cho review và
subtitle output trả exit 2. Resume chỉ đọc local JSON: không cần audio, API key, FFmpeg hay upload.

Không tự clamp/nội suy/chia đều thời gian, bỏ chữ, nối speaker giữa request hoặc tạo word time từ
sentence. Soniox token-only vẫn cần xử lý mọi lexical token 0 ms. Chế độ câu có thể giữ point
timestamp trong cue cùng nguồn/speaker có span lời nói dương ở gần (tối đa 800 ms), dùng nguyên
mốc provider; thiếu/đảo/out-of-bounds hoặc không có anchor vẫn review. Bản review câu cũ được
validate/resume bằng cùng đường này mà không sửa raw hay tạo override. Đây là timing ghép câu,
không phải word timestamp đã được sửa. Group chứa override vẫn đánh dấu **edited**, giữ ID liên quan.
Known/unknown speaker và overlap vẫn được bảo toàn. Cleanup remote vẫn chỉ áp dụng tài nguyên
thuộc job; các guard POST acceptance/cancel/409 S3 không thay đổi.

## Stale state và vòng đời UI

Editor nhận bản dịch khi project identity, source/cue IDs/timing/speaker/provenance/context và
target text của selection còn khớp. Playhead, selection hiển thị, zoom, track/layer display,
rename project và TTS/voice không làm mất bản dịch. Đổi source/rule/lock hoặc sửa target được
bảo vệ sẽ loại response cũ. Selection chỉ đổi `display_text`, qua composite command có undo/redo;
không sửa cue khác, TTS text, voice hoặc timing. **More → Hủy dịch** hủy worker hiện tại.

SubtitleThread/RetranslateThread dừng hợp tác, không `terminate()` QThread. Hủy/đóng page trả về
ngay; supervisor giữ worker đến khi thật sự finished. App quit tiếp tục xử lý Qt events trong
lúc drain, không giữ main thread trong `wait()` dài. `wait(0)` chỉ thu hồi worker đã finished;
worker tự join executor/socket. Signal cũ/cancelled không reset job mới hoặc cập nhật widget đã
bị hủy. Dấu hủy riêng tồn tại sau khi QThread kết thúc, vì Qt có thể xóa interruption flag
trước khi GUI nhận signal đã xếp hàng. `submit_with_context` vẫn giữ task/stage khi chuyển sang pool.

Tab phụ đề chỉ publish nội dung khi toàn job thành công; output được render vào file tạm trước
điểm commit. Hủy trong lúc request/render staging không ghi output một phần. Cancel sau điểm
commit không rollback công việc đã hoàn thành. Normal editor save vẫn `editor-project-v1` JSON
và SRT; ASS chỉ qua Save as ASS.

## Ranh giới nghiệm thu

Offline dùng dữ liệu tổng hợp và transport giả; test không ghi settings/cache/review vào dữ liệu
thật. Runtime Python 3.12, toolchain có sẵn, không sync/cài dependency. Gate và artifact S4.1 ghi
trong `status.md` và implementation. QM không sửa tay; máy thiếu lrelease, chuỗi zh mới fallback
English. JSON tiếng Việt được sync vào source bundle và package fallback.

Chưa chạy request API thật trong phiên S4.1: worktree không có settings LLM và env LLM/native key
trống. Không lấy key từ artifact S4, checkout khác, log hoặc lịch sử. **Scribe online, GPT
transcription→alignment→SRT, phồn thể Qwen strict, độ chính xác speaker và chất lượng xưng hô do
người đọc chấm vẫn còn thiếu**. Soniox online trước đây nhận dạng được nhưng full native parser
dừng token 0 ms; không chuyển bằng chứng prefix cũ thành full success. Startup EXE và resume JSON
tổng hợp là gate riêng, không thay thế workflow media/API thật hoặc benchmark corpus S6.
