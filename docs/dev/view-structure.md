# Cấu trúc view (videocaptioner/ui/view)

Sơ đồ các page và widget chính của GUI để tìm nhanh file cần sửa. Logic không phụ thuộc Qt nằm ở
`core/` (xem [Kiến trúc](architecture.md)); view chỉ điều phối và trình bày. Worker QThread nằm ở
`ui/thread/`, `ui/task_factory.py` dịch `cfg` thành các entity task, `ui/components/` chứa widget dùng
lại (setting card, dialog cài đặt Whisper, report lồng tiếng, panel của Video Editor).

```text
main_window.py ---------------- FluentWindow; page nạp lười qua LazyInterface; khởi động launch check
│                               VieNeu; khi đóng: dừng job dubbing, sidecar và child process
├── home_interface.py --------- 5 bước pipeline (SegmentedWidget + QStackedWidget, nạp lười)
│   ├── task_creation_interface.py --- Tạo task: chọn file/URL, cấu hình nhanh
│   ├── transcription_interface.py --- Nhận dạng giọng nói (TranscriptThread)
│   ├── subtitle_interface.py -------- Tách/tối ưu/dịch phụ đề, bảng chỉnh sửa (core/subtitle/editing)
│   ├── dubbing_interface.py --------- Lồng tiếng: provider TTS, VieNeu Local (hàng đợi action, đề nghị
│   │                                   cập nhật model), lồng tiếng thủ công, ghép audio thủ công
│   └── video_synthesis_interface.py - Ghép phụ đề vào video
├── batch_process_interface.py ------ Xử lý hàng loạt (BatchProcessThread)
├── subtitle_style_interface.py ----- Kiểu phụ đề; logic ở core/subtitle/style_presenter
├── video_editor_interface.py ------- Video Editor; domain ở core/editor, logic view ở core/editor/presenter
├── llm_logs_interface.py ----------- Xem log request LLM
├── setting_interface.py ------------ Cài đặt; card provider LLM dựng từ core/llm/services
└── log_window.py ------------------- Cửa sổ log (mở từ trang chủ)
```
