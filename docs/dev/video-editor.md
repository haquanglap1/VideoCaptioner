# Video Editor

`VideoEditorInterface` là page PyQt5/QFluentWidgets do VideoCaptioner sở hữu. Không import UI PySide6,
MPV hoặc module từ CapCap. CapCap chỉ là Apache-2.0 reference cho các khái niệm timeline/cache; code ở
đây được viết lại theo model và worker conventions của VideoCaptioner GPL-3.0.

## Canonical state

- Schema project là `editor-project-v1`; milliseconds là timing canonical và cue ID được giữ ổn định
  sau lần import đầu.
- `EditorCue` tách `source_text`, `display_text`, `tts_text`, speaker, voice settings, fit state và
  audio đã tạo. Project JSON chỉ persist voice identity không nhạy cảm; credential nằm trong runtime
  `DubbingConfig`, không đi vào project.
- Track mặc định là `V1 Video`, `A1 Original Audio`, `TS1 Subtitle + TTS`; `FX1 Visual Layers` xuất
  hiện khi có Blur/Logo/Mask/Text.
- `EditorProjectStore` ghi JSON và SRT bằng temp-file + `os.replace`. Mọi path được serialize relative.
  Normal save luôn tạo SRT cạnh project và không sửa source SRT đã mở. ASS chỉ qua explicit
  `save_as_ass`; render/export không persist ASS.

## Mutation và synchronization

`CommandStack` là write path cho text, timing, add/split/delete, move/resize, speaker, voice settings,
track state và visual layers. Inspector dùng composite command để một lần Apply không để lại mutation
một phần khi validation fail. Timing phải không âm, dài ít nhất 50 ms, không overlap và không vượt
duration video.

Playback position cập nhật playhead, active cue, subtitle overlay và inspector trên Qt main thread.
Timeline click cập nhật selection và seek preview. Worker chỉ emit data/error/progress; widget update
luôn nằm trong slot của UI thread. Mọi media request có signature và slot bỏ kết quả stale.

## Timeline và media cache

`TimelineIndex` giữ start-sorted cues cùng prefix maximum end. Viewport query là
`O(log n + visible cues)`; paint không duyệt toàn TS1. Waveform dùng FFmpeg PCM mono 800 Hz và envelope
bị chặn kích thước. Thumbnail tối đa 120 frame. Cả hai cache dưới
`AppData/cache/editor_media/v1/<media fingerprint>` với fingerprint từ resolved path, size và mtime.

QtMultimedia là backend preview hiện tại. FFmpeg vẫn là source of truth cho Fast Preview và export.
Không thêm MPV: H.264/AAC play + seek có deterministic machine test; nếu codec thực tế ngoài backend
Qt của máy user thất bại, UI giữ lỗi cụ thể thay vì báo thành công.

## Dubbing và export

`DubbingEngine.regenerate_groups` dùng planner Natural/Legacy hiện có, tìm group chứa selected cue,
invalidate đúng persistent cache key, synthesize/measure target và trả fit/warning state. Group khác
không bị synthesize hoặc xóa cache.

Fast Preview chọn selection range, nếu không có thì lấy 5 giây quanh playhead. Subtitle, visual layers
và WAV đã regenerate đều lấy từ live project. A1 mute làm im audio gốc nhưng vẫn giữ TTS; TS1 mute bỏ
TTS. Final export có thể chạy full Natural/Legacy Dubbing từ live TTS SRT rồi render subtitle/layers từ
cùng snapshot editor. Dubbing report vẫn in-memory trừ khi caller CLI yêu cầu `--report`.

Blur/Logo/Mask/Text dùng cùng filter-graph builder cho preview/export. Text dùng temporary `textfile`,
Logo là image input + overlay, Mask hỗ trợ solid/pixelate/blur và Blur dùng crop/effect/overlay theo
range. Temporary run directory được cleanup sau success hoặc failure.

## Acceptance boundary

Offline tests dùng video H.264/AAC và WAV deterministic để kiểm tra play/seek, preview range, duration,
SRT-only policy, visual filters, selected-cache isolation và 60 phút/1.000 cue. Đây là machine
acceptance; chưa chứng minh UX chủ quan, codec/video lạ, provider thật, rate limit hoặc chất lượng nghe
tiếng Việt.
