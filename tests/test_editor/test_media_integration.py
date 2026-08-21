import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from videocaptioner.core.editor.media import (
    build_visual_filter_graph,
    export_editor_video,
    probe_media,
    render_fast_preview,
)
from videocaptioner.core.editor.models import EditorLayer, EditorLayerKind
from videocaptioner.core.editor.project_store import EditorProjectStore


@pytest.fixture
def editor_media(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/ffprobe are required")
    video = tmp_path / "input.mp4"
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error",
            "-f", "lavfi", "-i", "color=c=navy:s=320x180:r=24:d=3",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000:duration=3",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", "-y", str(video),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    subtitle = tmp_path / "input.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:01,400\nFirst display\n\n"
        "2\n00:00:01,500 --> 00:00:02,800\nSecond display\n",
        encoding="utf-8",
    )
    project = EditorProjectStore().create_from_media(
        str(video), str(subtitle), duration_ms=probe_media(video).duration_ms
    )
    return video, subtitle, project


def test_real_ffmpeg_fast_preview_and_export_use_live_state_and_preserve_duration(
    editor_media, tmp_path
):
    video, _subtitle, project = editor_media
    project.cues[0].display_text = "LIVE EDITOR DISPLAY"
    project.cues[0].tts_text = "LIVE EDITOR TTS"
    project.selection_start_ms = 500
    project.selection_end_ms = 2000
    project.layers.append(
        EditorLayer(
            "mask-1",
            EditorLayerKind.MASK,
            300,
            2300,
            name="Mask",
            x=0.05,
            y=0.05,
            width=0.15,
            height=0.15,
            properties={"mode": "solid", "color": "black"},
        )
    )

    preview = Path(render_fast_preview(project, tmp_path / "preview.mp4"))
    preview_info = probe_media(preview)
    assert preview.is_file() and preview.stat().st_size > 0
    assert preview_info.duration_ms == pytest.approx(1500, abs=120)

    output = Path(export_editor_video(project, tmp_path / "export.mp4"))
    output_info = probe_media(output)
    input_info = probe_media(video)
    assert output.is_file() and output.stat().st_size > 0
    assert output_info.duration_ms == pytest.approx(input_info.duration_ms, abs=120)
    assert list(tmp_path.glob("*.ass")) == []


def test_blur_logo_mask_text_share_one_preview_export_filter_builder(editor_media, tmp_path):
    _video, _subtitle, project = editor_media
    logo = tmp_path / "logo.png"
    from PIL import Image

    Image.new("RGBA", (32, 16), (255, 0, 0, 180)).save(logo)
    project.layers = [
        EditorLayer("blur", EditorLayerKind.BLUR, 0, 1000, properties={"strength": 6}),
        EditorLayer("logo", EditorLayerKind.LOGO, 0, 1000, properties={"path": str(logo)}),
        EditorLayer(
            "mask", EditorLayerKind.MASK, 0, 1000, properties={"mode": "pixelate"}
        ),
        EditorLayer(
            "text", EditorLayerKind.TEXT, 0, 1000, properties={"text": "Title", "font_size": 24}
        ),
    ]
    run_dir = tmp_path / "filters"
    run_dir.mkdir()
    (run_dir / "display.srt").write_text("", encoding="utf-8")
    extra_inputs, graph, output_label = build_visual_filter_graph(project, run_dir)
    assert extra_inputs == ["-loop", "1", "-i", str(logo)]
    assert "boxblur=6:1" in graph
    assert "colorchannelmixer" in graph
    assert "flags=neighbor" in graph
    assert "drawtext=textfile=" in graph
    assert output_label.startswith("v")
    rendered = export_editor_video(project, tmp_path / "all-layers.mp4")
    assert Path(rendered).is_file() and Path(rendered).stat().st_size > 0


def test_export_routes_live_tts_state_through_existing_dubbing_engine(editor_media, tmp_path):
    _video, _subtitle, project = editor_media
    project.cues[0].tts_text = "EDITOR SPOKEN VALUE"
    captured = {}

    class FakeEngine:
        def dub(self, video_path, subtitle_path, output_path, config, callback):
            captured["tts_srt"] = Path(subtitle_path).read_text(encoding="utf-8")
            shutil.copyfile(video_path, output_path)
            callback(100, "fake dubbed")
            return output_path

    from videocaptioner.core.dubbing.config import DubbingConfig
    from videocaptioner.core.tts import TTSConfig

    config = DubbingConfig(
        enabled=True,
        tts_config=TTSConfig(
            model="fake",
            api_key="runtime-only",
            base_url="https://fake.invalid/v1",
            voice="fake",
            response_format="wav",
        ),
    )
    output = export_editor_video(
        project,
        tmp_path / "dubbed-export.mp4",
        dubbing_config=config,
        engine=FakeEngine(),
    )
    assert Path(output).is_file()
    assert "EDITOR SPOKEN VALUE" in captured["tts_srt"]
    assert list(tmp_path.glob("*-dubbing-report.json")) == []


def test_fast_preview_uses_regenerated_voice_and_a1_mute_does_not_remove_tts(
    editor_media, tmp_path
):
    _video, _subtitle, project = editor_media
    voice = tmp_path / "voice.wav"
    with wave.open(str(voice), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\0\0" * 12000)
    project.cues[0].audio_path = str(voice)
    project.selection_start_ms = 0
    project.selection_end_ms = 1500
    project.track_by_id("track-a1").muted = True
    output = render_fast_preview(project, tmp_path / "voice-preview.mp4")
    info = probe_media(output)
    assert info.has_audio is True
    assert info.duration_ms == pytest.approx(1500, abs=120)
