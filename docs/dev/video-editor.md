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
  hiện khi có Blur/Logo/Mask/Text. Track header có V/M/L; V chỉ bật cho TS1 (burn phụ đề) và FX1
  (render visual layer) vì V1/A1 không đổi output khi ẩn.
- `EditorProjectStore` ghi JSON và SRT bằng temp-file + `os.replace`. Video/subtitle path phải relative
  so với project. Asset vệ tinh (ảnh logo, WAV TTS trong cache) giữ absolute khi không tính được
  relative — thường là khác ổ đĩa — thay vì làm hỏng cả thao tác save. Normal save luôn tạo SRT cạnh
  project và không sửa source SRT đã mở. ASS chỉ qua explicit `save_as_ass`; render/export không
  persist ASS.

## Mutation và synchronization

`CommandStack` là write path cho text, timing, add/split/delete, move/resize, speaker, voice settings,
track state và visual layers. Inspector dùng composite command để một lần Apply không để lại mutation
một phần khi validation fail. Timing phải không âm, dài ít nhất 50 ms, không overlap và không vượt
duration video. Visual layer được phép overlap nhau nên chỉ bị chặn bởi biên media; `LayerInspector`
gom geometry, timing, opacity, visible/lock và property theo kind vào một `EditLayerCommand`. Tab
`Layers` chứa cả nút add, danh sách và inspector nên context panel chỉ có hai tab ở width hẹp.

Playback position cập nhật playhead, active cue, subtitle overlay và inspector trên Qt main thread.
Timeline click cập nhật selection và seek preview. Worker chỉ emit data/error/progress; widget update
luôn nằm trong slot của UI thread. Mọi media request có signature và slot bỏ kết quả stale.

## Timeline và media cache

`TimelineIndex` giữ start-sorted cues cùng prefix maximum end. Viewport query là
`O(log n + visible cues)`; paint không duyệt toàn TS1. Waveform dùng FFmpeg PCM mono 800 Hz và envelope
bị chặn kích thước. Thumbnail tối đa 120 frame. Cả hai cache dưới
`AppData/cache/editor_media/v1/<media fingerprint>` với fingerprint từ resolved path, size và mtime.

Fast Preview phát clip đã render trong preview mode riêng: vị trí local của clip được cộng offset về
timeline project nên playhead, cue active và inspector không bị ghi đè, và `Exit preview` trả player về
video gốc đúng vị trí. Poster thumbnail đến muộn không ẩn surface đã bắt đầu phát. Render có `Cancel`:
worker poll cancel flag và kill FFmpeg child, đồng thời page tự dừng worker khi app quit vì navigation
page không nhận `closeEvent`.

QtMultimedia là backend preview hiện tại. FFmpeg vẫn là source of truth cho Fast Preview và export.
Không thêm MPV: H.264/AAC play + seek có deterministic machine test; nếu codec thực tế ngoài backend
Qt của máy user thất bại, UI giữ lỗi cụ thể thay vì báo thành công.

Native `QVideoWidget` được ẩn ở empty/loading state để không fallback về Windows white palette. Thumbnail
đầu từ media worker làm poster pause; `QVideoWidget` chỉ hiện khi playback bắt đầu. Editor áp local dark
palette/QSS cho native Qt controls, context tabs, scrollbar, timeline shell và command bar. Action chính
luôn nằm trên bar; Save as ASS và visual layers nằm trong `More`, để width 700 px không chồng chữ.

## Dubbing và export

`DubbingEngine.regenerate_groups` dùng planner Natural/Legacy hiện có, tìm group chứa selected cue,
invalidate đúng persistent cache key, synthesize/measure target và trả fit/warning state. Group khác
không bị synthesize hoặc xóa cache.

Fast Preview chọn selection range, nếu không có thì lấy 5 giây quanh playhead. Subtitle, visual layers
và WAV đã regenerate đều lấy từ live project. A1 mute làm im audio gốc nhưng vẫn giữ TTS; TS1 mute bỏ
TTS. Final export có thể chạy full Natural/Legacy Dubbing từ live TTS SRT rồi render subtitle/layers từ
cùng snapshot editor. Dubbing report vẫn in-memory trừ khi caller CLI yêu cầu `--report`.

Blur/Logo/Mask/Text dùng cùng filter-graph builder cho preview/export. Text dùng temporary `textfile`
với `fontfile` ghim từ `resource/fonts/` (fontconfig mặc định khác nhau theo máy) và được canh giữa
trong box của layer đúng như overlay preview. Logo là image input + overlay, scale theo frame width
thật lấy từ probe chứ không đoán 1920. Mask hỗ trợ solid/pixelate/blur và Blur dùng crop/effect/overlay
theo range, với bán kính boxblur clamp theo kích thước vùng và opacity áp qua `colorchannelmixer`. Box
của layer bị clamp trong khung để `crop`/`drawbox` không vượt biên. Overlay preview dùng đúng rect video
đã letterbox và scale font theo tỉ lệ video/widget. Temporary run directory được cleanup sau success
hoặc failure; file Fast Preview cũ trong cache bị dọn trước mỗi lần render mới.

## Acceptance boundary

Offline tests dùng video H.264/AAC và WAV deterministic để kiểm tra play/seek, preview range, duration,
SRT-only policy, visual filters, selected-cache isolation và 60 phút/1.000 cue. Đây là machine
acceptance; chưa chứng minh UX chủ quan, codec/video lạ, provider thật, rate limit hoặc chất lượng nghe
tiếng Việt.
