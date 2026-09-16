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
`Layers` chứa cả nút add, danh sách và inspector. Context panel gồm `Cue`, `Layers` và `Style`;
form Style cuộn dọc và các tab vẫn dùng được ở page width 700 px.

Playback position cập nhật playhead, active cue, subtitle overlay và inspector trên Qt main thread.
Timeline click cập nhật selection và seek preview. Worker chỉ emit data/error/progress; widget update
luôn nằm trong slot của UI thread. Mọi media request có signature và slot bỏ kết quả stale.

## Subtitle Style

`EditorSubtitleStyle` là immutable model riêng của project, không đọc/ghi cấu hình style toàn ứng dụng.
Project v1 cũ thiếu `subtitle_style` nhận defaults; project mới persist các trường font, màu `#RRGGBB`,
cỡ chữ, bold, letter spacing, alignment 1–9 và lề. Validation từ chối màu, số hoặc tên font không hợp lệ
trước mutation. `SubtitleStylePanel` phát snapshot qua `EditSubtitleStyleCommand`; Apply không đổi giá trị
không thêm undo step, Reset cũng undo được. Đổi style khi đang render preview sẽ hủy/bỏ kết quả stale.

Mặc định dùng `Noto Sans SC` có sẵn trong bundle, chữ trắng, không background/outline/shadow. Qt đăng ký
font bundle một lần; FFmpeg nhận cùng `fontsdir`. Font, spacing và lề dùng hệ quy chiếu cao 720, chiều rộng
theo aspect ratio thực (probe nếu model chưa có dimensions). Overlay Qt áp style trong rect video letterbox;
đây là xem trước tương tác, font metrics/wrapping có thể khác libass. Clip Fast Preview đã burn sẽ ẩn overlay
để không vẽ phụ đề/layer hai lần; thoát preview hoặc sửa project trả về overlay của source.

Render chữ đơn giản vẫn dùng SRT tạm và `subtitles:force_style`, không tạo ASS lâu dài. Save as ASS dùng cùng model và
reference resolution. Lưu ý libass `force_style` dùng ScaleX/Y dạng tỷ lệ (`1`), Alignment theo enum nội bộ;
dòng `Style:` trong ASS dùng phần trăm (`100`) và numpad alignment. Hai đường được kiểm tra bằng ảnh render
thật; xem [libass override parser](https://github.com/libass/libass/blob/master/libass/ass.c).

Panel có thêm preset và hộp nền tùy chọn: màu, độ đục, bo góc, đệm ngang/dọc. Nạp preset chỉ điền form;
Apply mới thay project qua undo/redo. Reset đưa về chữ đơn giản. Khi bật nền, `layout_subtitle()` tính
cùng hình học cho overlay Qt và ASS tạm của preview/export, bao gồm letter spacing; `build_editor_ass()`
vẽ nền bằng ASS vector và ghim text theo vị trí. Save as ASS giữ cùng nền bo góc và hình học này. Normal
save vẫn chỉ tạo JSON + SRT; temp ASS được dọn cùng run directory. Không đổi encoder hoặc tùy chọn hủy render.

Project từ bản style cũ có `align_h`/`align_v` hoặc `margin_l`/`margin_r`/`margin_v` được chuyển sang các
trường hiện tại, giữ số đo pixel bằng `reference_height=0`, `layout_mode=shared`. Project hiện tại và preset
mới giữ mốc 720; thiếu `subtitle_style` vẫn nhận default chữ đơn giản. Metadata được persist trong schema
v1 để save/reopen không scale lần hai. Unknown field khi load vẫn được bỏ qua để tương thích phía trước;
mutation từ command luôn validate. Font bundle được đo theo em và quy đổi theo OS/2 trước khi ghi Fontsize
ASS để hộp nền không lệch glyph; font thiếu trong chế độ shared dùng fallback bundle ở cả Qt và FFmpeg.

Burn chữ đơn giản đi thẳng qua libass, không dùng pipeline PIL nền bo góc. Encoder hiện vẫn là
`libx264 -preset veryfast -crf 20`; không mặc định chuyển NVENC chỉ dựa vào tên GPU. Cần benchmark trên
video thật trước khi chọn encoder: chi phí decode, filter, encode và kích thước output đều ảnh hưởng.

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
