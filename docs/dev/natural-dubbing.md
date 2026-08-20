# Natural Dubbing

Natural Dubbing giữ ba lớp dữ liệu tách biệt: `source_text` để đối chiếu, `subtitle_text` để hiển thị và
`tts_text` để đọc. Full pipeline ghi một SRT target-only riêng cho TTS; file subtitle display vẫn giữ layout
song ngữ/đơn ngữ mà user đã chọn.

## Luồng xử lý

1. `DubbingTextSource` chọn text rõ ràng. `AUTO` ưu tiên `translated_text`; `TRANSLATED` fail nếu thiếu.
2. Planner thuần sắp cue theo timeline, group câu liền nhau và mượn silence có `silence_guard_ms`.
   Khi các cue được merge có overlap 1-4 token ở biên, planner bỏ phần overlap khỏi `tts_text`, giữ nguyên
   từng display cue và ghi warning vào report. Cue lặp hoàn toàn được giữ vì có thể là lời thoại có chủ ý.
3. Persistent cache tra SHA-256 theo normalized text, provider host, model, voice, speed và sample rate.
4. TTS chạy ở provider-native speed. Duration từ WAV thật quyết định fit; prediction chỉ dùng routing.
5. Group vượt `fit_ratio_limit` mới được rewrite và synthesize lại, tối đa `max_rewrite_attempts`.
6. Natural chỉ speed-adjust tới `natural_max_speed`, không truncate. Outlier còn lại đi `review` hoặc
   `allow-overlap`. Legacy giữ `max_speed` và truncate, với action `legacy_truncate` trong report.
7. Engine dựng voice track đúng vị trí group, giữ duration video và mix theo keep/reduce/mute.

Report version `dubbing-report-v1` luôn tồn tại trong RAM để GUI hiển thị chi tiết. Không có file JSON mặc
định; CLI chỉ ghi atomically khi user truyền `--report PATH`. Dữ liệu report không serialize API key,
credential URL hay raw provider response.

## CLI

```powershell
uv run --frozen videocaptioner dub video.mp4 --subtitle translated.srt `
  --tts-provider openai --tts-api-key <key> --tts-model tts-1 --voice alloy `
  --text-source auto --timing-mode natural --unresolved review

uv run --frozen videocaptioner process video.mp4 --translator google `
  --target-language vi --dub --tts-api-key <key>
```

Exit code `6` nghĩa là Natural timing cần review; exit code `7` là provider không tạo audio hợp lệ. Cả hai
in nguyên nhân trực tiếp ra stderr; report path chỉ xuất hiện khi `--report` được yêu cầu. `-q` của lệnh
`dub` chỉ in output path khi thành công.

Full GUI pipeline persist SRT only. ASS chỉ được tạo khi user chọn Save as ASS hoặc tạm thời trong renderer;
render mode ASS không yêu cầu pipeline giữ một file `.ass` cạnh video.

## Acceptance boundary

Unit và FFmpeg integration dùng `FakeTTS` WAV deterministic, gồm cache miss/hit, measured rewrite, review,
allow-overlap, Legacy truncate, silent-source mix và provider failure. Đây là machine acceptance, không phải
bằng chứng chất lượng nghe, rate-limit hay chất lượng của OpenAI/MiniMax/local provider thật.
