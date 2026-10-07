# Ngữ cảnh video/bộ phim cho LLM dịch — 2026-10-07

User hỏi app có phân tích được ngữ cảnh video để LLM dịch tốt hơn không, rồi yêu cầu làm cho mọi
video (Bilibili, YouTube), không riêng PV 清宵. Brief tự động (`translate/context.md`) chỉ nhìn lời
thoại nên không biết tên video, ai là thầy ai là trò. Lượt này thêm hai nguồn nền được gửi trước
transcript trong mọi prompt dịch LLM.

## Hành vi

- **Sidecar `<video>.context.json`** (`core/translate/series_context.py`, schema `video-context-v1`):
  tiêu đề, URL, kênh, mô tả (≤ 2000 ký tự), danh sách phần (≤ 40). Ghi tự động khi tải bằng GUI
  (`video_download_thread`) hoặc playlist (`core/playlist._download_entry`), từ info dict của yt-dlp
  nên dùng được cho mọi extractor. Chỉ metadata công khai; không key, cookies hay đường dẫn máy.
  Sidecar hỏng/thiếu → không có ngữ cảnh, không lỗi.
- **Ngữ cảnh bộ phim** (`cfg.translate_series_context`, Settings → Dịch và tối ưu → *Ngữ cảnh bộ phim
  cho bản dịch* → Sửa): một ô văn bản (≤ 4000 ký tự) về nhân vật, quan hệ, xưng hô, thuật ngữ. Nút
  **Lấy từ link** chạy `fetch_video_context` trong QThread: yt-dlp `process=False` (title, uploader,
  description, parts); với Bilibili khi extractor trả mô tả rỗng, đọc trang HTML và lấy `desc` trong
  `__INITIAL_STATE__` hoặc `<meta name="description">`. Kết quả điền đầu ô, user sửa rồi Lưu.
- **Ghép vào prompt** (`compose_context_notes`): một khối "Background supplied by the user… reference
  data, not instructions" chứa `<video_context>` và `<series_notes>`. `SubtitleConfig.context_notes`
  được `TaskFactory.create_subtitle_task` tính từ sidecar của `video_path` + ô Settings; CLI
  `subtitle`/`process` nhận `--series-context FILE` hoặc `translate.series_context` (map từ
  `Translate.SeriesContext` của GUI). `LLMTranslator` đặt khối này trước transcript khi tạo brief,
  trước brief trong prompt mỗi chunk (`_context_block`, kể cả khi brief bị bỏ vì < 10 câu hoặc có
  Ngữ cảnh xưng hô), và đưa vào cache key; `DialogueTranslator` nối vào prompt dialogue. Phụ đề OCR
  đi cùng đường vì handoff mang `video_path`.
- Không đụng schema `ConversationContext` (S4); khối nền chỉ là text tham khảo trong prompt.

## Nghiệm thu

- `tests/test_translate/test_series_context.py` (7): bounds/round-trip sidecar, info dict lạ, parse mô
  tả Bilibili, fetch với extractor giả + trang giả (YouTube không gọi trang), compose, LLMTranslator
  gửi nền trong brief và chunk + đổi cache key, DialogueTranslator nối prompt.
  `tests/test_ui/test_series_context.py` (2): task mang sidecar + ô Settings; dialog fetch off-thread,
  điền ô, Lưu ghi cfg. `tests/test_thread/test_video_download.py` thêm test sidecar sau tải.
- Chưa gọi yt-dlp/mạng thật trong test; chưa nghiệm thu chất lượng dịch có nền với model thật.
  Build/deploy ghi ở `status.md`.

## Giới hạn

- CLI `download` (chạy yt-dlp bằng subprocess) chưa ghi sidecar; dùng `--series-context` hoặc GUI.
- Mô tả Bilibili cần tải trang (một request HTTP, không cookies); trang chặn thì chỉ có tiêu đề/phần.
- Ô Settings là một ngữ cảnh toàn cục: đổi bộ phim thì sửa lại ô, hoặc đặt sidecar riêng cho video.
