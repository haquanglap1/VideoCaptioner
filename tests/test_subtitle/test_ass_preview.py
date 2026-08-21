import shutil
from pathlib import Path

import pytest
from PIL import Image

import videocaptioner.core.subtitle.ass_renderer as ass_renderer
from videocaptioner.core.subtitle.style_manager import load_style


def test_filter_path_is_quoted_and_windows_safe():
    escaped = ass_renderer._escape_filter_path(
        r"E:\Game\Translate video\AppData\cache\preview's.ass"
    )
    assert escaped == r"E\:/Game/Translate video/AppData/cache/preview\'s.ass"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is required")
def test_real_ass_preview_handles_windows_drive_path(tmp_path, monkeypatch):
    cache_path = tmp_path / "preview cache"
    monkeypatch.setattr(ass_renderer, "CACHE_PATH", cache_path)

    background = tmp_path / "background image.png"
    Image.new("RGB", (640, 360), (20, 30, 40)).save(background)
    style = load_style("default")
    assert style is not None

    output = Path(
        ass_renderer.render_ass_preview(
            style.to_ass_string(),
            ("Hello world", "Xin chào"),
            str(background),
            640,
            360,
        )
    )

    assert output.is_file()
    assert output.stat().st_size > 0
    assert not list(cache_path.glob("*.ass"))
