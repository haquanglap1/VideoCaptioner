# Hướng Dẫn Sử Dụng Module

Tài liệu này tóm tắt cách dùng các module chính của VideoCaptioner khi phát triển hoặc tích hợp vào script riêng.

## Module ASR

Module `videocaptioner.core.asr` dùng để chuyển âm thanh/video thành dữ liệu phụ đề.

```python
from pathlib import Path

from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum
from videocaptioner.core.asr.transcribe import transcribe

config = TranscribeConfig(
    transcribe_model=TranscribeModelEnum.BIJIAN,
    transcribe_language="",
    need_word_time_stamp=True,
)
asr_data = transcribe("video.mp4", config)
Path("output.srt").write_text(asr_data.to_srt(), encoding="utf-8")
```

Nên dùng engine miễn phí như `bijian` hoặc `jianying` cho tác vụ phổ thông. Với môi trường cục bộ mạnh, có thể dùng `faster-whisper`.

## Module Tách Câu

Module `videocaptioner.core.split` tách phụ đề thành các câu ngắn hơn để dễ đọc và dễ render.

```python
from videocaptioner.core.split.split import SubtitleSplitter

splitter = SubtitleSplitter(
    thread_num=4,
    model="gpt-4o-mini",
    max_word_count_cjk=28,
    max_word_count_english=20,
)
split_data = splitter.split_subtitle(asr_data)
```

Giảm `max_word_count_*` nếu phụ đề bị quá dài trên màn hình.

## Module Tối Ưu Phụ Đề

Module `videocaptioner.core.optimize` dùng LLM để chỉnh câu, dấu câu và cách ngắt ý.

```python
from videocaptioner.core.optimize.optimize import SubtitleOptimizer

optimizer = SubtitleOptimizer(
    thread_num=4,
    batch_num=10,
    model="gpt-4o-mini",
    custom_prompt="",
)
optimized_data = optimizer.optimize_subtitle(asr_data)
```

Module này cần API key LLM.

## Module Dịch Phụ Đề

Module `videocaptioner.core.translate` hỗ trợ nhiều dịch vụ dịch.

```python
from videocaptioner.core.translate.factory import TranslatorFactory
from videocaptioner.core.translate.types import TargetLanguage, TranslatorType

translator = TranslatorFactory.create_translator(
    translator_type=TranslatorType.BING,
    target_language=TargetLanguage.VIETNAMESE,
)
translated_data = translator.translate_subtitle(asr_data)
```

Dùng `bing` hoặc `google` khi muốn dịch nhanh. Dùng `llm` khi cần chất lượng cao và giữ ngữ cảnh tốt hơn.

## Module Phụ Đề Và Render

Module `videocaptioner.core.subtitle` tạo phụ đề ASS, render nền bo góc và xử lý kiểu hiển thị.

```python
from videocaptioner.core.subtitle.style_manager import load_style

style = load_style("rounded-default")
ass_text = style.to_ass_string()
```

Các style mặc định nằm trong `resource/subtitle_style/`.

## Module Ghép Video

Module `videocaptioner.core.utils.video_utils` dùng FFmpeg để ghép phụ đề vào video.

```python
from videocaptioner.core.utils.video_utils import add_subtitles

add_subtitles(
    input_file="video.mp4",
    subtitle_file="subtitle.srt",
    output="video_captioned.mp4",
    soft_subtitle=True,
)
```

Với phụ đề cứng và kiểu render:

```python
from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.entities import SubtitleRenderModeEnum, SubtitleLayoutEnum
from videocaptioner.core.utils.video_utils import add_subtitles_with_style

asr_data = ASRData.from_subtitle_file("subtitle.srt")

add_subtitles_with_style(
    video_path="video.mp4",
    asr_data=asr_data,
    output_path="video_captioned.mp4",
    render_mode=SubtitleRenderModeEnum.ROUNDED_BG,
    subtitle_layout=SubtitleLayoutEnum.ORIGINAL_ON_TOP,
    rounded_style=None,
    ass_style="",
    crf=28,
    preset="medium",
)
```

## Module GUI

Module `videocaptioner.ui` là giao diện desktop.

```bash
uv run videocaptioner
```

Các màn hình chính nằm trong `videocaptioner/ui/view/`, thread xử lý nền nằm trong `videocaptioner/ui/thread/`.

## Module CLI

Module `videocaptioner.cli` cung cấp các lệnh:

- `transcribe`: tạo phụ đề từ âm thanh/video.
- `subtitle`: tối ưu, tách câu hoặc dịch phụ đề.
- `synthesize`: ghép phụ đề vào video.
- `process`: chạy toàn bộ quy trình.
- `download`: tải video trực tuyến.
- `config`: xem và sửa cấu hình.

```bash
uv run videocaptioner config show
```

## Gợi Ý Tích Hợp

- Dùng CLI nếu cần tự động hóa đơn giản.
- Dùng module Python nếu cần nhúng vào pipeline riêng.
- Luôn kiểm tra FFmpeg trước khi ghép video.
- Với file dài, nên bật cache để tránh gọi lại API hoặc xử lý lại phụ đề.
