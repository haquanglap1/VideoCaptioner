# VideoCaptioner

VideoCaptioner là công cụ xử lý phụ đề video bằng AI, hỗ trợ nhận dạng giọng nói, tối ưu phụ đề, dịch phụ đề và ghép phụ đề vào video.

## Tính năng chính

- Chuyển âm thanh/video thành phụ đề SRT, ASS, VTT hoặc TXT.
- Tối ưu câu phụ đề bằng LLM để dễ đọc hơn. Tích hợp tính năng Tìm kiếm và Thay thế hàng loạt từ bị dịch sai.
- Dịch phụ đề bằng LLM, Bing, Google hoặc DeepLX.
- Ghép phụ đề mềm hoặc ghi phụ đề cứng vào video.
- Xử lý trọn quy trình từ video đầu vào đến video có phụ đề.
- Lồng tiếng Natural theo timeline đo từ audio thật: ưu tiên bản dịch, mượn khoảng lặng an toàn,
  cache WAV bền vững, viết lại câu vượt khung khi có LLM và không âm thầm cắt lời.
- Giữ report review trong RAM để GUI giải thích lỗi; chỉ xuất JSON khi CLI được truyền `--report`.
  Vẫn có chế độ Legacy cho workflow cần giới hạn tốc độ/cắt âm thanh như bản cũ.
- Có tab `Video Editor` native PyQt5 để chỉnh subtitle/TTS trên timeline V1/A1/TS1, xem trước,
  tạo lại đúng group giọng đã chọn và export từ editor state hiện tại.
- Có provider `VieNeu Local` tích hợp: tự quản lý GPU sidecar ẩn, voice/model revision, update có kiểm
  định và rollback; không cần chạy server, nhập API Base hay API key giả.
- Có CLI cho tự động hóa và GUI cho người dùng Windows.

## Cài đặt để chạy từ mã nguồn

Yêu cầu:

- Python 3.10 đến 3.12.
- FFmpeg có trong `PATH`.
- `uv` để đồng bộ môi trường.

```bash
uv sync
uv run videocaptioner --help
uv run videocaptioner
```

Khi chạy `uv run videocaptioner` không kèm tham số, ứng dụng sẽ mở giao diện desktop nếu đã có các gói GUI.

## Dùng CLI

```bash
# Nhận dạng giọng nói sang phụ đề
uv run videocaptioner transcribe video.mp4 --asr bijian

# Dịch phụ đề
uv run videocaptioner subtitle input.srt --translator bing --target-language en

# Ghép phụ đề vào video
uv run videocaptioner synthesize video.mp4 -s subtitle.srt

# Lồng tiếng Natural từ phụ đề đã dịch
uv run videocaptioner dub video.mp4 --subtitle translated.srt \
  --tts-api-key <your-key> --tts-model tts-1 --voice alloy

# Lồng tiếng bằng VieNeu Local được quản lý, không cần API key/server riêng
uv run videocaptioner dub video.mp4 --subtitle translated.srt \
  --tts-provider vieneu-local --voice "Minh Đức"

# Kiểm tra/update/rollback model VieNeu theo commit SHA
uv run videocaptioner vieneu status
uv run videocaptioner vieneu update
uv run videocaptioner vieneu rollback

# Xử lý toàn bộ: nhận dạng -> tối ưu/dịch -> ghép video
uv run videocaptioner process video.mp4 --target-language vi

# Toàn bộ pipeline với target-only artifact riêng cho TTS
uv run videocaptioner process video.mp4 --target-language vi --dub \
  --tts-api-key <your-key>

# Tải video trực tuyến
uv run videocaptioner download "https://youtube.com/watch?v=xxx"
```

Xem chi tiết tham số:

```bash
uv run videocaptioner <lenh> --help
```

## Cấu hình LLM

Các tính năng nhận dạng/dịch miễn phí có thể dùng ngay. Nếu dùng tối ưu phụ đề hoặc dịch bằng LLM, cấu hình API:

```bash
uv run videocaptioner config set llm.api_key <your-key>
uv run videocaptioner config set llm.api_base https://api.openai.com/v1
uv run videocaptioner config set llm.model gpt-4o-mini
```

Thứ tự ưu tiên cấu hình: tham số CLI, biến môi trường `VIDEOCAPTIONER_*`, file cấu hình, giá trị mặc định.

## Lồng tiếng Natural

Trong tab Lồng tiếng, chọn nguồn text `Auto / Translation / Original` và timing `Natural / Legacy`.
Natural là mặc định mới: engine group các cue liên tiếp, tính sức chứa đến cue kế tiếp với silence guard,
tổng hợp ở tốc độ provider đã chọn, đo WAV thật rồi chỉ rewrite/re-synthesize group vượt ngưỡng. Nếu vẫn
không vừa, `Review` dừng trước bước mix và mở report; `Allow overlap` giữ nguyên lời nói đầy đủ và ghi cảnh
báo. Natural không dùng đường truncate của Legacy.

Cache dùng `AppData/cache/dubbing_tts/v1/` với key SHA-256 không chứa API key hay transcript trong tên
file. GUI/full pipeline không ghi report JSON; dùng `--report PATH` ở CLI khi thực sự cần lưu report.

### VieNeu Local

Chọn `VieNeu Local` trong tab Lồng tiếng để ứng dụng tự khởi động sidecar ẩn khi tải voice hoặc synthesize.
Model active được giữ offline sau lần download thành công; check/update chạy nền, candidate chỉ được
activate sau health + voices + WAV 48 kHz smoke và không đổi revision giữa một dubbing job. `Local AI`
vẫn giữ nguyên cho server bên ngoài. Chi tiết runtime, updater, build và acceptance nằm tại
[`docs/dev/vieneu-one-app.md`](docs/dev/vieneu-one-app.md).

## Video Editor

Tab `Video Editor` nằm ngay dưới `Kiểu phụ đề`. Chọn `Open` để mở video cùng SRT, hoặc dùng
`Open in Video Editor` từ màn Tối ưu/Dịch phụ đề hay Lồng tiếng. Workspace gồm preview QtMultimedia,
context inspector và timeline `V1 Video / A1 Original Audio / TS1 Subtitle + TTS`.

Editor dùng dark workspace riêng cho cả widget Qt chuẩn và QFluent: empty preview không còn native white
surface, loaded preview dùng thumbnail đầu làm poster trước khi Play, inspector/scrollbar/timeline cùng
palette và command bar tự thu action phụ vào `More` khi chiều rộng hạn chế.

Editor giữ riêng `source_text`, `display_text` và `tts_text`. Các thao tác text/timing, add, split,
delete, drag, resize, voice settings, mute/lock và visual layer đều đi qua undo/redo. Waveform và
thumbnail được tạo ở background và cache theo fingerprint media; timeline chỉ paint cue nằm trong
viewport.

`Save project` ghi atomically `editor-project-v1` cùng một file SRT cạnh project; đường dẫn trong JSON
là relative và không chứa API key. Normal save không persist ASS. Chỉ `Save as ASS` tạo file ASS lâu
dài; Fast Preview/export dùng SRT tạm từ live editor state và tự cleanup.

Nếu Dubbing đang bật, final export dùng Natural/Legacy config hiện có. `Regenerate voice` force-refresh
đúng cache key của cue/group được chọn; Fast Preview dùng ngay WAV đã regenerate và giữ riêng semantics
mute của A1 (audio gốc) với TS1 (subtitle/TTS). Blur, Logo, Mask và Text có model, timeline clip,
preview, export và project round-trip; không cần PySide6 hoặc MPV.

## Các module chính

- `videocaptioner.core.asr`: nhận dạng giọng nói và xuất dữ liệu phụ đề.
- `videocaptioner.core.split`: tách câu phụ đề theo thời gian và độ dài.
- `videocaptioner.core.optimize`: tối ưu nội dung phụ đề bằng LLM.
- `videocaptioner.core.translate`: dịch phụ đề qua LLM/Bing/Google/DeepLX.
- `videocaptioner.core.subtitle`: render phụ đề ASS hoặc nền bo góc.
- `videocaptioner.core.utils.video_utils`: tách âm thanh, đọc thông tin video và ghép phụ đề.
- `videocaptioner.ui`: giao diện desktop.
- `videocaptioner.cli`: giao diện dòng lệnh.

Hướng dẫn dùng module chi tiết nằm ở [docs/MODULE_USAGE.md](docs/MODULE_USAGE.md).

## Build EXE trên Windows

Project đã có file cấu hình PyInstaller:

```bash
uv run pyinstaller VideoCaptioner.spec --clean --noconfirm
```

File EXE được tạo trong thư mục `dist/`. Có thể chép file EXE đó sang máy Windows khác; nếu ứng dụng cần gọi FFmpeg bên ngoài, máy đích cũng cần có FFmpeg trong `PATH` hoặc đi kèm thư mục công cụ tương ứng.

Đặt tên build riêng mà không tạo thêm file spec:

```powershell
$env:VC_BUILD_NAME = 'VideoCaptioner-<label>'
uv run pyinstaller VideoCaptioner.spec --clean --noconfirm
Remove-Item Env:VC_BUILD_NAME
```

`VideoCaptioner.spec` đã bundle các prompt Natural Dubbing và module report dialog. EXE windowed vẫn định
tuyến tham số sang CLI, nên cùng EXE hỗ trợ `dub` và `vieneu` mà không mở GUI.

Gói VieNeu one-app cần runtime/model mutable cạnh EXE. Offline bundle dùng
`scripts/build_vieneu_runtime.py`, `scripts/build_vieneu_one_app.py` và
`installer/VideoCaptioner-VieNeu-OneApp.wxs`. Xem lệnh và layout tại
[`docs/dev/vieneu-one-app.md`](docs/dev/vieneu-one-app.md).

Để giảm file cài ban đầu, web installer dùng ba source trong `installer/`: base MSI được nhúng vào setup,
còn VieNeu runtime/model MSI + CAB được tải qua WiX Burn `DownloadUrl` và verify trước khi cài. Build test
loopback không phải artifact để phát hành cho máy khác; release phải rebuild với một `PayloadBaseUrl`
HTTPS bất biến. Chi tiết nằm trong tài liệu VieNeu one-app ở trên.

## Kiểm thử

```bash
uv run pytest tests/test_cli/ -q
uv run pytest tests/test_thread/test_video_synthesis_thread.py -q
```

## Giấy phép

VideoCaptioner sử dụng giấy phép [GPL-3.0](LICENSE).
