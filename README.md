# VideoCaptioner

VideoCaptioner là công cụ xử lý phụ đề video bằng AI, hỗ trợ nhận dạng giọng nói, tối ưu phụ đề, dịch phụ đề và ghép phụ đề vào video.

## Tính năng chính

- Chuyển âm thanh/video thành phụ đề SRT, ASS, VTT hoặc TXT.
- Tối ưu câu phụ đề bằng LLM để dễ đọc hơn.
- Dịch phụ đề bằng LLM, Bing, Google hoặc DeepLX.
- Ghép phụ đề mềm hoặc ghi phụ đề cứng vào video.
- Xử lý trọn quy trình từ video đầu vào đến video có phụ đề.
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

# Xử lý toàn bộ: nhận dạng -> tối ưu/dịch -> ghép video
uv run videocaptioner process video.mp4 --target-language vi

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
uv run pyinstaller VideoCaptioner-PhaseC-20260429.spec --clean --noconfirm
```

File EXE được tạo trong thư mục `dist/`. Có thể chép file EXE đó sang máy Windows khác; nếu ứng dụng cần gọi FFmpeg bên ngoài, máy đích cũng cần có FFmpeg trong `PATH` hoặc đi kèm thư mục công cụ tương ứng.

## Kiểm thử

```bash
uv run pytest tests/test_cli/ -q
uv run pytest tests/test_thread/test_video_synthesis_thread.py -q
```

## Giấy phép

VideoCaptioner sử dụng giấy phép [GPL-3.0](LICENSE).
