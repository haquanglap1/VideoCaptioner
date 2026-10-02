# Tempo giọng, tốc độ video và phụ đề theo lời đọc

## Tùy chỉnh trong app

Trong tab **Lồng tiếng**, dùng **Tempo giọng sau TTS** (1,00–1,20×) và
**Tốc độ video** (0,50–1,00×). Nút **Cân bằng 1,20× / 0,77×** điền hai tốc độ,
trễ bắt đầu 2000 ms và phụ đề ghi vào hình. Đây là lựa chọn tường minh; mở app
không tự thay cấu hình đã lưu. Có thể chọn không gắn phụ đề, gắn mềm hoặc ghi vào
hình; kiểu chữ lấy từ tab Kiểu phụ đề.

Tempo là xử lý WAV bằng FFmpeg sau khi đã sinh giọng. Khi chọn tốc độ khác 1×,
job dùng giọng nguồn 1×, Natural/sequential và tắt rewrite/tăng tốc tự động.
Một tốc độ giọng chung được áp dụng cho mọi nhóm; trần của control này là 1,20×.
Control tốc độ sinh TTS cũ vẫn phục vụ các job không dùng chế độ cân bằng.
Dialogue luôn dùng giọng nguồn 1×; tempo/video mới không bị preset dialogue xóa.

Chọn kịch bản, bấm **Chuẩn bị lời đọc trước TTS**, duyệt lời, rồi **Xem trước
lời đã duyệt**. Preview tạo một video riêng trong thư mục làm việc của app,
có thể sinh những WAV còn thiếu; WAV gốc được giữ để xuất tiếp. Bấm **Tiếp tục
lời đã duyệt** để xuất theo tempo/video/trễ đang chọn. Giọng, provider và lời đã
duyệt vẫn được giữ từ job. Nguồn hoặc cấu hình sinh giọng không khớp phải được
chuẩn bị/duyệt lại; không lấy đường dẫn WAV từ JSON làm quyền đọc audio.

## Bảo toàn và timing

- Cache TTS vẫn bind lời, reference/model/voice/native speed như trước.
  Đổi tempo/video không làm sinh lại WAV gốc hợp lệ. WAV đã đổi tempo có cache
  dẫn xuất riêng theo SHA nội dung và tốc độ; resume không tăng tốc hai lần.
- Timing nguồn, cue ID, membership và source fingerprint giữ nguyên. Lịch phát
  dùng mốc nguồn chia cho tốc độ video, duration WAV sau đổi tempo và gap 80 ms.
  Trễ được đo so với mốc nguồn đã đổi tốc độ, không so với giây của video cũ.
- Video và audio nền đổi tốc độ cùng nhau. Đường retime chép video packets,
  không nội suy frame. Ghi phụ đề vào hình cần encode video. Audio mix có đệm
  để AAC rounding không làm `-shortest` bỏ frame video cuối.
- Phải vừa giới hạn trễ, biên thoại/cảnh/khoảng lặng đã biết và duration video
  thực sau retime. Vượt giới hạn giữ review/audio; không cắt lời hoặc tự đổi tốc độ.
- Phụ đề mới có một event cho mỗi nhóm lời đọc, dùng playback timing thực.
  Không suy timestamp nội bộ từng từ bằng tỷ lệ ký tự. File SRT nằm trong thư
  mục `<output>-subtitles/playback.srt`; không ghi đè subtitle nguồn.
- Pipeline synthesis nhận phụ đề playback để tránh dùng mốc video cũ.
  Editor export dùng bản sao chỉ để render: đổi mốc layer/clip và dùng caption
  playback, giữ nguyên project/CommandStack và style người dùng. Fast Preview
  nguồn trong Editor vẫn là preview của timeline nguồn; dùng preview của tab
  Lồng tiếng để xem đầy đủ thay đổi tốc độ và timing.

## CLI

```powershell
videocaptioner dub video.mp4 --subtitle display.dialogue.json --prepare-review wording.json --voice-tempo 1.20 --video-speed 0.77 --dubbing-subtitles hard
videocaptioner dub video.mp4 --subtitle display.dialogue.json --review wording.json --voice-tempo 1.20 --video-speed 0.77 --dubbing-subtitles hard -o balanced.mp4
```

Các flag cũng có trong `process`. Cấu hình TOML tương ứng:

```toml
[dubbing]
voice_tempo = 1.20
video_speed = 0.77
subtitle_mode = "hard"
```

Mặc định vẫn là 1×/1× và `none`; không migrate settings/API key của bản cài.
Các report cũ đọc được. Thay tempo/video/giới hạn trễ trong review chỉ được nhận
nếu toàn bộ binding sinh giọng và nguồn còn khớp; mix/style là lựa chọn xuất.

## Evidence

Audit triển khai: `.tools/dialogue-speed-integration-20261002/`.
Mẫu người dùng đã duyệt trước khi tích hợp nằm ở
`.tools/mp4-asr-llm-omni-20261002-01/balanced-120-077/subtitled/`.
Đó là evidence của job riêng; validation source/EXE sau tích hợp được ghi riêng,
không suy chất lượng ASR/TTS từ unit tests hoặc từ việc render video thành công.

Kết quả cuối: full offline2293 pass/5 skip/58 deselected;27 UI tests sau chỉnh
layout và11 playback tests sau sửa fallback caption pass. Ruff/Pyright/sync pass.
Source và EXE đều xuất video thật với60 cache hit/0 TTS mới,max delay1591ms,
giữ8782 frame và đủ lời đến cuối. Native GUI smoke20s/exit0; các thao tác review,
preset/preview và cache có test Qt riêng. Không gọi ASR/LLM/provider inference
mới để nghiệm thu thay đổi playback.

Bản cài chính đã nhận payload cuối, EXE vẫn giữ tên cũ
cho shortcut.602 file app khớp SHA artifact;1.329 file dữ liệu/settings/voices/
manifest giữ nguyên. Model và credential không bị thay. Có backup delta trong
audit. Người dùng chọn preset/control mới khi muốn áp dụng cho job tiếp theo.
