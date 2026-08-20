from argparse import Namespace
from pathlib import Path

import pytest

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli.commands.dub import build_dubbing_config, run
from videocaptioner.cli.config import build_config
from videocaptioner.cli.main import _build_cli_overrides, build_parser, main
from videocaptioner.core.dubbing.models import (
    DubbingProviderError,
    DubbingReviewRequired,
    DubbingTextSource,
    DubbingTimingMode,
)


def test_dub_help_and_required_subtitle(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["dub", "--help"])
    assert exc.value.code == 0
    assert "--natural-max-speed" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        main(["dub", "video.mp4"])
    assert exc.value.code == 2


def test_dub_invalid_enum():
    with pytest.raises(SystemExit) as exc:
        main(["dub", "video.mp4", "--subtitle", "sub.srt", "--timing-mode", "fast"])
    assert exc.value.code == 2


def test_cli_overrides_config_priority():
    parser = build_parser()
    args = parser.parse_args(
        [
            "dub", "video.mp4", "--subtitle", "sub.srt",
            "--tts-provider", "minimax", "--timing-mode", "legacy",
        ]
    )
    config = build_config(cli_overrides=_build_cli_overrides(args))
    assert config["dubbing"]["tts_provider"] == "minimax"
    assert config["dubbing"]["timing_mode"] == "legacy"


def test_builds_core_config():
    config = build_config(
        cli_overrides={
            "dubbing": {
                "tts_api_key": "secret",
                "text_source": "translated",
                "timing_mode": "natural",
                "natural_max_speed": 1.07,
                "tts_cache": False,
            }
        }
    )
    result = build_dubbing_config(config, "report.json")
    assert result.text_source == DubbingTextSource.TRANSLATED
    assert result.timing_mode == DubbingTimingMode.NATURAL
    assert result.natural_max_speed == 1.07
    assert result.cache_enabled is False
    assert result.report_path == "report.json"


def command_args(video, subtitle, **overrides):
    values = {
        "video": str(video),
        "subtitle": str(subtitle),
        "output": None,
        "report": None,
        "quiet": True,
        "verbose": False,
        "suppress_result": False,
    }
    values.update(overrides)
    return Namespace(**values)


def test_invalid_range_returns_usage(tmp_path):
    video = tmp_path / "video.mp4"
    subtitle = tmp_path / "sub.srt"
    video.write_bytes(b"x")
    subtitle.write_text("x", encoding="utf-8")
    config = build_config(
        cli_overrides={
            "dubbing": {"tts_api_key": "fake", "natural_max_speed": 2.0}
        }
    )
    assert run(command_args(video, subtitle), config) == EXIT.USAGE_ERROR


def test_quiet_prints_only_output_path(tmp_path, monkeypatch, capsys):
    video = tmp_path / "video.mp4"
    subtitle = tmp_path / "sub.srt"
    video.write_bytes(b"x")
    subtitle.write_text("x", encoding="utf-8")

    def fake_dub(self, video_path, subtitle_path, output_path, config, callback=None):
        Path(output_path).write_bytes(b"output")
        self.last_report_path = str(tmp_path / "report.json")
        return output_path

    monkeypatch.setattr("videocaptioner.core.dubbing.engine.DubbingEngine.dub", fake_dub)
    config = build_config(cli_overrides={"dubbing": {"tts_api_key": "fake"}})
    assert run(command_args(video, subtitle), config) == EXIT.SUCCESS
    captured = capsys.readouterr()
    assert captured.out.strip() == str(video.with_stem("video_dubbed"))
    assert "fake" not in captured.out + captured.err


def test_review_required_exit_prints_report_to_stderr(tmp_path, monkeypatch, capsys):
    video = tmp_path / "video.mp4"
    subtitle = tmp_path / "sub.srt"
    report = tmp_path / "review.json"
    video.write_bytes(b"x")
    subtitle.write_text("x", encoding="utf-8")

    def fake_dub(self, *args, **kwargs):
        raise DubbingReviewRequired(str(report))

    monkeypatch.setattr("videocaptioner.core.dubbing.engine.DubbingEngine.dub", fake_dub)
    config = build_config(cli_overrides={"dubbing": {"tts_api_key": "fake"}})
    assert run(command_args(video, subtitle), config) == EXIT.REVIEW_REQUIRED
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(report) in captured.err


def test_provider_failure_without_report_prints_reason_only(tmp_path, monkeypatch, capsys):
    video = tmp_path / "video.mp4"
    subtitle = tmp_path / "sub.srt"
    video.write_bytes(b"x")
    subtitle.write_text("x", encoding="utf-8")

    def fake_dub(self, *args, **kwargs):
        raise DubbingProviderError(reason="TTS thất bại ở g-0001: HTTP 429 rate limited")

    monkeypatch.setattr("videocaptioner.core.dubbing.engine.DubbingEngine.dub", fake_dub)
    config = build_config(cli_overrides={"dubbing": {"tts_api_key": "fake"}})
    assert run(command_args(video, subtitle), config) == EXIT.PROVIDER_ERROR
    captured = capsys.readouterr()
    assert "HTTP 429 rate limited" in captured.err
    assert "Report:" not in captured.err


def test_process_dub_uses_target_artifact_and_display_for_synthesis(tmp_path, monkeypatch):
    video = tmp_path / "movie.mp4"
    video.write_bytes(b"video")
    seen = {}

    def fake_transcribe(args, config):
        Path(args.output).write_text("source", encoding="utf-8")
        return EXIT.SUCCESS

    def fake_subtitle(args, config):
        Path(args.output).write_text("display bilingual", encoding="utf-8")
        Path(args.dubbing_output).write_text("target only", encoding="utf-8")
        return EXIT.SUCCESS

    def fake_dub(args, config):
        seen["dub_subtitle"] = Path(args.subtitle).read_text(encoding="utf-8")
        Path(args.output).write_bytes(b"dubbed")
        return EXIT.SUCCESS

    def fake_synthesize(args, config):
        seen["display_subtitle"] = Path(args.subtitle).read_text(encoding="utf-8")
        seen["video"] = Path(args.video).read_bytes()
        return EXIT.SUCCESS

    monkeypatch.setattr("videocaptioner.cli.validators.validate_process", lambda *a, **k: True)
    monkeypatch.setattr("videocaptioner.cli.commands.transcribe.run", fake_transcribe)
    monkeypatch.setattr("videocaptioner.cli.commands.subtitle.run", fake_subtitle)
    monkeypatch.setattr("videocaptioner.cli.commands.dub.run", fake_dub)
    monkeypatch.setattr("videocaptioner.cli.commands.synthesize.run", fake_synthesize)
    args = Namespace(
        input=str(video), output=None, verbose=False, quiet=True, config=None,
        no_synthesize=False, dub=True, no_optimize=False, no_translate=False,
        no_split=True, translator="google", target_language="vi", asr="bijian",
        language="en", whisper_api_key=None, whisper_api_base=None,
        api_key=None, api_base=None, model=None, reflect=False, prompt=None,
        prompt_file=None, thread_num=None, batch_size=None, layout="target-above",
        subtitle_mode="soft", quality="medium", report=None,
    )
    from videocaptioner.cli.commands.process import run as process_run
    assert process_run(args, build_config()) == EXIT.SUCCESS
    assert seen == {
        "dub_subtitle": "target only",
        "display_subtitle": "display bilingual",
        "video": b"dubbed",
    }
