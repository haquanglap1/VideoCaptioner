"""dub command -- measured Natural/Legacy dubbing through the core engine."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.cli.config import get
from videocaptioner.core.dubbing.config import (
    AudioMixMode,
    DubbingConfig,
    TTSProviderEnum,
)
from videocaptioner.core.dubbing.models import (
    DubbingProviderError,
    DubbingReviewRequired,
    DubbingTextSource,
    DubbingTimingMode,
    UnresolvedFitPolicy,
)
from videocaptioner.core.tts import TTSConfig


def build_dubbing_config(config: dict, report_path: str = "") -> DubbingConfig:
    provider = get(config, "dubbing.tts_provider", "openai")
    provider_map = {
        "openai": TTSProviderEnum.OPENAI,
        "minimax": TTSProviderEnum.MINIMAX,
        "local-ai": TTSProviderEnum.LOCAL_AI,
        "local_ai": TTSProviderEnum.LOCAL_AI,
        "vieneu-local": TTSProviderEnum.VIENEU_LOCAL,
        "vieneu_local": TTSProviderEnum.VIENEU_LOCAL,
    }
    mix_map = {
        "keep": AudioMixMode.KEEP_ORIGINAL,
        "reduce": AudioMixMode.REDUCE_ORIGINAL,
        "mute": AudioMixMode.MUTE_ORIGINAL,
    }
    target_language = str(get(config, "translate.target_language", ""))
    strip_cjk = not target_language.lower().startswith(("zh", "ja", "yue"))
    rewrite_key = str(get(config, "llm.api_key", ""))
    rewrite_base = str(get(config, "llm.api_base", ""))
    rewrite_model = str(get(config, "llm.model", ""))
    if not (rewrite_key and rewrite_base and rewrite_model):
        rewrite_model = ""
    return DubbingConfig(
        enabled=True,
        tts_provider=provider_map.get(provider, TTSProviderEnum.OPENAI),
        tts_config=TTSConfig(
            model=str(get(config, "dubbing.tts_model", "tts-1")),
            api_key=str(get(config, "dubbing.tts_api_key", "")),
            base_url=str(get(config, "dubbing.tts_api_base", "https://api.openai.com/v1")),
            voice=str(get(config, "dubbing.voice", "alloy")),
            speed=float(get(config, "dubbing.tts_speed", 1.0)),
            sample_rate=int(get(config, "dubbing.sample_rate", 32000)),
            response_format="wav",
        ),
        tts_concurrency=int(get(config, "dubbing.tts_concurrency", 4)),
        text_source=DubbingTextSource(get(config, "dubbing.text_source", "auto")),
        timing_mode=DubbingTimingMode(get(config, "dubbing.timing_mode", "natural")),
        natural_max_speed=float(get(config, "dubbing.natural_max_speed", 1.08)),
        max_speed=float(get(config, "dubbing.legacy_max_speed", 1.5)),
        fit_ratio_limit=float(get(config, "dubbing.fit_ratio_limit", 1.05)),
        borrow_gap_ms=int(get(config, "dubbing.borrow_gap_ms", 350)),
        max_rewrite_attempts=int(get(config, "dubbing.max_rewrite_attempts", 2)),
        rewrite_enabled=bool(get(config, "dubbing.timing_rewrite", True)),
        cache_enabled=bool(get(config, "dubbing.tts_cache", True)),
        unresolved_policy=UnresolvedFitPolicy(
            get(config, "dubbing.unresolved_policy", "review")
        ),
        mix_mode=mix_map.get(
            get(config, "dubbing.mix_mode", "reduce"), AudioMixMode.REDUCE_ORIGINAL
        ),
        original_volume=float(get(config, "dubbing.original_volume", 0.4)),
        voice_volume=float(get(config, "dubbing.voice_volume", 1.0)),
        target_language=target_language,
        rewrite_model=rewrite_model,
        rewrite_api_key=rewrite_key,
        rewrite_api_base=rewrite_base,
        report_path=report_path,
        strip_cjk=strip_cjk,
    )


def _validate_ranges(config: DubbingConfig) -> str | None:
    assert config.tts_config is not None
    checks = [
        (0.25 <= config.tts_config.speed <= 4.0, "--tts-speed must be between 0.25 and 4.0"),
        (config.tts_concurrency >= 1, "--tts-concurrency must be at least 1"),
        (1.0 <= config.natural_max_speed <= 1.5, "--natural-max-speed must be between 1.0 and 1.5"),
        (1.0 <= config.max_speed <= 3.0, "--legacy-max-speed must be between 1.0 and 3.0"),
        (1.0 <= config.fit_ratio_limit <= 2.0, "--fit-ratio-limit must be between 1.0 and 2.0"),
        (0 <= config.borrow_gap_ms <= 5000, "--borrow-gap-ms must be between 0 and 5000"),
        (0 <= config.max_rewrite_attempts <= 10, "--max-rewrite-attempts must be between 0 and 10"),
        (0.0 <= config.original_volume <= 1.0, "--original-volume must be between 0 and 1"),
        (0.1 <= config.voice_volume <= 3.0, "--voice-volume must be between 0.1 and 3"),
    ]
    return next((message for valid, message in checks if not valid), None)


def run(args: Namespace, config: dict) -> int:
    video_path = Path(args.video)
    subtitle_path = Path(args.subtitle)
    if not video_path.is_file() or not subtitle_path.is_file():
        missing = video_path if not video_path.is_file() else subtitle_path
        output.error(f"Input file not found: {missing}")
        return EXIT.FILE_NOT_FOUND
    from videocaptioner.cli.validators import (
        validate_ffmpeg,
        validate_subtitle_input,
        validate_video_input,
    )
    validation = validate_video_input(video_path) or validate_subtitle_input(subtitle_path)
    if validation is not None:
        return validation
    if not validate_ffmpeg():
        return EXIT.DEPENDENCY_MISSING

    output_path = Path(args.output) if args.output else video_path.with_stem(video_path.stem + "_dubbed")
    if output_path.resolve() == video_path.resolve():
        output.error("Output path is the same as input video")
        return EXIT.USAGE_ERROR
    report_path = str(getattr(args, "report", None) or "")
    dubbing_config = build_dubbing_config(config, report_path)
    assert dubbing_config.tts_config is not None
    if (
        dubbing_config.tts_provider != TTSProviderEnum.VIENEU_LOCAL
        and not dubbing_config.tts_config.api_key
    ):
        output.config_missing_error(
            "TTS API key", "dubbing.tts_api_key", "VIDEOCAPTIONER_TTS_API_KEY", "--tts-api-key"
        )
        return EXIT.USAGE_ERROR
    range_error = _validate_ranges(dubbing_config)
    if range_error:
        output.error(range_error)
        return EXIT.USAGE_ERROR

    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)
    progress = None if quiet else output.ProgressLine("Dubbing video").start()
    try:
        from videocaptioner.core.dubbing.engine import DubbingEngine
        engine = DubbingEngine()
        engine.dub(
            str(video_path),
            str(subtitle_path),
            str(output_path),
            dubbing_config,
            callback=(
                (lambda value, message: progress.update(value, message))
                if progress
                else None
            ),
        )
        if progress:
            progress.finish(f"Done -> {output_path}")
        if quiet and not getattr(args, "suppress_result", False):
            print(output_path)
        elif verbose and engine.last_report_path:
            output.info(f"Dubbing report: {engine.last_report_path}")
        return EXIT.SUCCESS
    except DubbingReviewRequired as exc:
        if progress:
            progress.fail(str(exc))
        else:
            output.error(str(exc))
        if exc.report_path:
            output.hint(f"Report: {exc.report_path}")
        return EXIT.REVIEW_REQUIRED
    except DubbingProviderError as exc:
        if progress:
            progress.fail(str(exc))
        else:
            output.error(str(exc))
        if exc.report_path:
            output.hint(f"Report: {exc.report_path}")
        return EXIT.PROVIDER_ERROR
    except Exception as exc:
        message = output.clean_error(str(exc))
        if progress:
            progress.fail(message)
        else:
            output.error(message)
        if verbose:
            import traceback
            traceback.print_exc()
        return EXIT.RUNTIME_ERROR
    finally:
        if dubbing_config.tts_provider == TTSProviderEnum.VIENEU_LOCAL:
            from videocaptioner.core.tts.vieneu.service import get_vieneu_service

            get_vieneu_service().shutdown()
