"""Measured cache/rewrite/fit orchestration behind :class:`DubbingEngine`."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.dubbing.audio_mixer import (
    adjust_audio_speed,
    build_voice_track,
    mix_audio_tracks,
)
from videocaptioner.core.dubbing.cache import (
    PersistentTTSCache,
    measure_audio_duration,
)
from videocaptioner.core.dubbing.models import (
    DubbingFitStatus,
    DubbingPlan,
    DubbingProviderError,
    DubbingReport,
    DubbingReviewRequired,
    DubbingTimingMode,
    calculate_report_summary,
)
from videocaptioner.core.dubbing.planner import plan_dubbing_groups
from videocaptioner.core.dubbing.review import DubbingReview, bind_sources, synthesis_cache_key
from videocaptioner.core.dubbing.rewrite_service import (
    TimingRewriteService,
    request_for_group,
)
from videocaptioner.core.dubbing.scheduling import sequential_slots
from videocaptioner.core.tts import TTSData, TTSDataSeg
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.video_utils import get_video_info

if TYPE_CHECKING:
    from videocaptioner.core.dubbing.config import DubbingConfig
    from videocaptioner.core.dubbing.engine import DubbingEngine
    from videocaptioner.core.dubbing.models import DubbingGroup
    from videocaptioner.core.tts import BaseTTS

from videocaptioner.core.dubbing.config import tts_provider_key
from videocaptioner.core.utils.subprocess_helper import child_environment

logger = setup_logger("dubbing.orchestrator")
_CREATE_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class DubbingOrchestrator:
    def __init__(self, engine: "DubbingEngine"):
        self.engine = engine

    def run(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        config: "DubbingConfig",
        callback: Callable[[int, str], None],
        *,
        review: DubbingReview | None = None,
        display_subtitle_path: str | None = None,
        allow_config_change: bool = False,
    ) -> str:
        self._validate(video_path, subtitle_path, config)
        if Path(output_path).resolve() in {Path(video_path).resolve(), Path(subtitle_path).resolve()}:
            raise ValueError("Dubbing output must not overwrite a source file")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        report_path = self._report_path(config)
        self.engine.last_report_path = ""
        self.engine.last_subtitle_path = ""
        if review is None:
            self.engine.last_report = {}
            self.engine.last_review = None
        cache = PersistentTTSCache(self.engine.cache_root, enabled=config.cache_enabled)
        review_root = None
        if (config.timing_mode == DubbingTimingMode.NATURAL
            and config.unresolved_policy.value == "sequential" and not config.cache_enabled):
            # A failed no-cache job still needs durable audio for inspection.
            # Resume keeps honoring cache=False and never executes report paths.
            review_root = cache.root / "review-audio"
            review_root.mkdir(parents=True, exist_ok=True)
        work_dir = Path(tempfile.mkdtemp(prefix="vc_dub_", dir=review_root))
        keep_audio = False
        plan = None
        try:
            callback(5, "Đang đọc phụ đề...")
            prepared = self._prepare_plan(
                video_path, subtitle_path, display_subtitle_path, config, callback
            )
            if review is not None:
                review.restore_into(prepared, config, allow_config_change=allow_config_change)
            # Do not replace the retained review until every binding has passed.
            plan = prepared
            assert plan.resume_metadata is not None
            total_duration = plan.resume_metadata.video_duration / config.video_speed
            if not plan.groups:
                raise ValueError("Phụ đề trống, không có gì để lồng tiếng")
            self._write_report(plan, "", output_created=False)

            if plan.schema_version == "dubbing-plan-dialogue-v1" and review is None:
                for group in plan.groups:
                    group.needs_review = True
                    group.action_taken = "dialogue_wording_preview"
                self._write_report(plan, report_path, output_created=False)
                raise DubbingReviewRequired(report_path=report_path,
                    reason="Duyệt lời thoại trước TTS, rồi tiếp tục lời đã duyệt với tempo/video đã chọn.")

            callback(12, "Đang kiểm tra TTS cache...")
            provider = self.engine._create_tts_provider(config)
            if config.tts_config:
                config.tts_config.use_cache = config.cache_enabled
            self._resolve_cache_hits(plan.groups, config, cache)
            callback(18, "Đang tổng hợp giọng nói...")
            self._synthesize_missing_groups(
                plan.groups, config, provider, cache, work_dir / "tts", callback
            )
            self._measure_groups(plan.groups)

            if any(group.fit_status == DubbingFitStatus.FAILED for group in plan.groups):
                self._write_report(plan, report_path, output_created=False)
                raise DubbingProviderError(
                    report_path=report_path,
                    reason=self._provider_failure_reason(plan.groups),
                )

            if config.timing_mode == DubbingTimingMode.NATURAL and review is None:
                rewrite_service = self.engine._create_rewrite_service(config, callback)
                callback(55, "Đang xử lý các câu vượt khung...")
                self._rewrite_outliers(
                    plan.groups,
                    config,
                    rewrite_service,
                    provider,
                    cache,
                    work_dir / "rewrite",
                    callback,
                )

            callback(67, "Đang áp dụng chính sách timing...")
            from .playback import (
                apply_voice_tempo,
                playback_captions,
                publish_captions,
                render_captions,
                retime_video,
            )
            apply_voice_tempo(plan.groups, config, cache, work_dir / "tempo", callback)
            segment_infos = self._apply_fit_policy(
                plan.groups, config, work_dir / "adjusted", video_duration=total_duration
            )
            self._write_report(plan, report_path, output_created=False)
            if any(group.fit_status == DubbingFitStatus.FAILED for group in plan.groups):
                raise DubbingProviderError(
                    report_path=report_path,
                    reason=self._provider_failure_reason(plan.groups),
                )
            if any(group.needs_review for group in plan.groups):
                raise DubbingReviewRequired(
                    report_path=report_path,
                    reason=self._review_failure_reason(plan.groups),
                )

            render_video = retime_video(video_path, work_dir / "retimed.mp4", config.video_speed, callback)
            if config.video_speed != 1:
                actual_duration = self._video_duration(render_video, ASRData([]), True)
                if any((g.playback_end_time or 0) > actual_duration + .000001 for g in plan.groups):
                    for group in plan.groups:
                        if (group.playback_end_time or 0) > actual_duration + .000001:
                            group.needs_review = True
                            group.warnings.append("Measured retimed video is shorter than the complete speech")
                    raise DubbingReviewRequired(report_path=report_path, reason="Video sau đổi tốc độ không đủ chứa toàn bộ lời đọc.")
                total_duration = actual_duration

            callback(76, "Đang ghép voice track...")
            voice_track_path = str(work_dir / "voice_track.wav")
            sample_rate = config.tts_config.sample_rate if config.tts_config else 24000
            if not build_voice_track(
                segment_infos,
                total_duration,
                voice_track_path,
                sample_rate=sample_rate or 24000,
                normalize=True,
            ):
                raise RuntimeError("Ghép voice track thất bại")

            callback(87, "Đang mix audio vào video...")
            mixed_output = work_dir / ("mixed" + (Path(output_path).suffix or ".mp4"))
            if not mix_audio_tracks(
                render_video,
                voice_track_path,
                str(mixed_output),
                mix_mode=config.mix_mode,
                original_volume=config.original_volume,
                voice_volume=config.voice_volume,
                normalize_voice=False,
            ):
                raise RuntimeError("Mix audio thất bại")
            final_output = mixed_output
            captions = None
            if config.subtitle_mode != "none" or config.voice_tempo != 1 or config.video_speed != 1:
                captions = work_dir / "playback.srt"
                playback_captions(plan).save(str(captions))
                if config.subtitle_mode != "none":
                    final_output = work_dir / ("captioned" + (Path(output_path).suffix or ".mp4"))
                    render_captions(str(mixed_output), final_output, captions, config, callback)
            if not final_output.is_file():
                raise RuntimeError("Dubbing không tạo artifact đầu ra")
            callback(99, "Đang lưu video hoàn chỉnh...")
            # Staging can live on another volume; publish from the destination volume.
            with tempfile.NamedTemporaryFile(dir=Path(output_path).parent, suffix=Path(output_path).suffix,
                                             delete=False) as staged:
                staged_path = Path(staged.name)
            try:
                shutil.copyfile(final_output, staged_path)
                callback(99, "Đang lưu video hoàn chỉnh...")
                os.replace(staged_path, output_path)
            finally:
                staged_path.unlink(missing_ok=True)
            if captions is not None:
                self.engine.last_subtitle_path = publish_captions(captions, output_path)
            self._write_report(plan, report_path, output_created=True)
            callback(100, "Lồng tiếng hoàn tất!")
            return output_path
        except Exception:
            if plan is not None:
                keep_audio = review_root is not None and any(
                    group.audio_path and Path(group.audio_path).is_file() for group in plan.groups
                )
                if keep_audio:
                    logger.warning("Sequential review audio retained: %s", work_dir)
                    for group in plan.groups:
                        if group.audio_path:
                            group.warnings.append(f"Audio retained in review-audio/{work_dir.name}")
                for group in plan.groups:
                    if group.fit_status in {DubbingFitStatus.PENDING, DubbingFitStatus.FAILED}:
                        group.needs_review = True
                # Callback cancellation and provider exceptions must keep wording,
                # including when an explicit JSON report cannot be written.
                self._write_report(plan, "", output_created=False)
                if report_path:
                    try:
                        self._write_report(plan, report_path, output_created=False)
                    except OSError:
                        logger.warning("Could not save dubbing review; retained in memory")
            raise
        finally:
            if not keep_audio:
                shutil.rmtree(work_dir, ignore_errors=True)

    def _prepare_plan(
        self, video_path: str, subtitle_path: str, display_subtitle_path: str | None,
        config: "DubbingConfig", callback: Callable[[int, str], None],
    ) -> DubbingPlan:
        asr_data = self._load_dubbing_source(subtitle_path)
        duration = self._video_duration(
            video_path, asr_data,
            config.timing_mode == DubbingTimingMode.NATURAL and config.unresolved_policy.value == "sequential",
        )
        plan = self._build_dubbing_plan(asr_data, subtitle_path, duration, config)
        from videocaptioner.core.dubbing.dialogue import PLAN_SCHEMA, dialogue_groups, load_dialogue
        dialogue = load_dialogue(subtitle_path)
        if dialogue is not None:
            plan.groups = dialogue_groups(dialogue, duration)
            plan.schema_version = PLAN_SCHEMA
        plan.resume_metadata = bind_sources(
            video_path, subtitle_path, display_subtitle_path, duration, config, callback
        )
        plan.voice_tempo, plan.video_speed = config.voice_tempo, config.video_speed
        plan.max_start_delay_ms = config.max_start_delay_ms
        return plan

    @staticmethod
    def _validate(video_path: str, subtitle_path: str, config: "DubbingConfig") -> None:
        if not Path(video_path).is_file():
            raise ValueError(f"Video không tồn tại: {video_path}")
        if not Path(subtitle_path).is_file():
            raise ValueError(f"Subtitle không tồn tại: {subtitle_path}")
        if not config.tts_config:
            raise ValueError("TTS config chưa được cấu hình")
        missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
        if missing:
            raise RuntimeError(
                "Không tìm thấy: %s. Vui lòng cài FFmpeg và thêm vào PATH."
                % ", ".join(missing)
            )

    @staticmethod
    def _load_dubbing_source(subtitle_path: str) -> ASRData:
        from videocaptioner.core.dubbing.dialogue import load_dialogue
        document = load_dialogue(subtitle_path)
        if document is not None:
            return document.subtitle_data()
        return ASRData.from_subtitle_file(subtitle_path)

    @staticmethod
    def _video_duration(video_path: str, asr_data: ASRData, require_video: bool = False) -> float:
        if require_video:
            # Container duration can belong to a longer original audio stream;
            # using it would let -shortest silently cut approved speech.
            try:
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                     "stream=duration:stream_tags=DURATION", "-of", "json", video_path],
                    env=child_environment(), capture_output=True, text=True, encoding="utf-8",
                    errors="replace", creationflags=_CREATE_FLAGS, timeout=30,
                )
                if result.returncode == 0:
                    stream = json.loads(result.stdout)["streams"][0]
                    raw = stream.get("duration")
                    if raw in (None, "N/A"):
                        # Matroska commonly records per-stream duration as a tag.
                        hours, minutes, seconds = stream.get("tags", {})["DURATION"].split(":")
                        duration = float(hours) * 3600 + float(minutes) * 60 + float(seconds)
                    else:
                        duration = float(raw)
                    if math.isfinite(duration) and duration > 0:
                        return duration
            except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, TypeError):
                pass
            raise ValueError("Cannot determine video stream duration; sequential dubbing stopped before TTS")
        video_info = get_video_info(video_path)
        duration = video_info.duration_seconds if video_info else 0.0
        if duration <= 0 and asr_data.segments:
            duration = max(segment.end_time / 1000.0 for segment in asr_data.segments) + 1.0
        return duration

    def _build_dubbing_plan(
        self,
        asr_data: ASRData,
        subtitle_path: str,
        total_duration: float,
        config: "DubbingConfig",
    ) -> DubbingPlan:
        cues = self.engine._create_dubbing_cues(
            asr_data.segments,
            strip_cjk=config.strip_cjk,
            source_mode=config.text_source,
        )
        natural = config.timing_mode == DubbingTimingMode.NATURAL
        groups = plan_dubbing_groups(
            cues,
            video_duration=total_duration,
            borrow_gap_ms=config.borrow_gap_ms if natural else -1,
            silence_guard_ms=config.silence_guard_ms if natural else 0,
            max_group_duration=config.max_group_duration,
            target_language=config.target_language,
            preserve_tts_text=natural and config.unresolved_policy.value == "sequential",
        )
        tts = config.tts_config
        return DubbingPlan(
            source_path=subtitle_path,
            target_language=config.target_language,
            provider=tts_provider_key(config.tts_provider),
            model=tts.model if tts else "",
            voice=(tts.voice or "") if tts else "",
            timing_mode=config.timing_mode,
            created_at=datetime.now(timezone.utc).isoformat(),
            groups=groups,
            provider_identity=dict(config.managed_tts_identity),
        )

    @staticmethod
    def _report_path(config: "DubbingConfig") -> str:
        return config.report_path

    @staticmethod
    def _cache_key(group: "DubbingGroup", config: "DubbingConfig") -> str:
        return synthesis_cache_key(group.tts_text, config)

    def _resolve_cache_hits(
        self,
        groups: list["DubbingGroup"],
        config: "DubbingConfig",
        cache: PersistentTTSCache,
    ) -> None:
        for group in groups:
            group.cache_key = self._cache_key(group, config)
            hit = cache.get(group.cache_key)
            if hit:
                group.audio_path = hit.audio_path
                group.measured_duration = hit.duration
                group.fit_status = DubbingFitStatus.CACHED
                group.action_taken = "cache_hit"

    def _synthesize_missing_groups(
        self,
        groups: list["DubbingGroup"],
        config: "DubbingConfig",
        provider: "BaseTTS",
        cache: PersistentTTSCache,
        output_dir: Path,
        callback: Callable[[int, str], None],
    ) -> None:
        missing = [group for group in groups if not group.audio_path]
        leaders: dict[str, "DubbingGroup"] = {}
        duplicates: dict[str, list["DubbingGroup"]] = {}
        for group in missing:
            group.cache_key = self._cache_key(group, config)
            if group.cache_key in leaders:
                duplicates.setdefault(group.cache_key, []).append(group)
            else:
                leaders[group.cache_key] = group
        unique = list(leaders.values())
        if not unique:
            return
        tts_data = TTSData(
            [
                TTSDataSeg(
                    text=group.tts_text,
                    start_time=group.start_time,
                    end_time=group.subtitle_end_time,
                )
                for group in unique
            ]
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        assert config.tts_config is not None
        previous_use_cache = config.tts_config.use_cache
        # The provider's older binary cache omits endpoint/runtime/format fields.
        # Missing authoritative WAV entries must reach synthesis with this config.
        config.tts_config.use_cache = False
        try:
            provider.synthesize(
                tts_data,
                str(output_dir),
                lambda progress, message: callback(18 + int(progress * 0.32), message),
                max_workers=config.tts_concurrency,
            )
        finally:
            config.tts_config.use_cache = previous_use_cache
            # Providers can finish some segments before a callback cancels the
            # batch. Persist those WAVs before the temporary directory is removed.
            self._collect_synthesis_results(unique, duplicates, tts_data, config, cache, output_dir)

    def _collect_synthesis_results(
        self, unique: list["DubbingGroup"], duplicates: dict[str, list["DubbingGroup"]],
        tts_data: TTSData, config: "DubbingConfig", cache: PersistentTTSCache, output_dir: Path,
    ) -> None:
        assert config.tts_config is not None
        for group, segment in zip(unique, tts_data.segments):
            group.attempt_count += 1
            group.warnings.extend(segment.warnings)
            audio_path = self._ensure_wav(
                segment.audio_path, output_dir / f"{group.group_id}.wav", config
            )
            if not audio_path:
                group.fit_status = DubbingFitStatus.FAILED
                group.warnings.append(
                    segment.error or "Nhà cung cấp TTS không tạo file audio hợp lệ"
                )
                continue
            group.audio_path = audio_path
            group.measured_duration = measure_audio_duration(audio_path)
            entry = cache.put(
                group.cache_key,
                audio_path,
                provider=tts_provider_key(config.tts_provider),
                model=config.tts_config.model,
                voice=config.tts_config.voice or "",
                sample_rate=config.tts_config.sample_rate,
                runtime_identity=config.managed_tts_identity,
            )
            if entry is not None:
                group.audio_path = entry.audio_path
            for duplicate in duplicates.get(group.cache_key, []):
                duplicate.audio_path = group.audio_path
                duplicate.measured_duration = group.measured_duration
                duplicate.action_taken = "in_job_cache_hit"
                duplicate.fit_status = DubbingFitStatus.CACHED
        for failed in unique:
            if failed.fit_status == DubbingFitStatus.FAILED:
                for duplicate in duplicates.get(failed.cache_key, []):
                    duplicate.fit_status = DubbingFitStatus.FAILED
                    duplicate.warnings.append("TTS provider failed for duplicate text")

    @staticmethod
    def _ensure_wav(
        source_path: str, destination: Path, config: "DubbingConfig"
    ) -> str:
        if not source_path or not Path(source_path).is_file():
            return ""
        if Path(source_path).suffix.lower() == ".wav" and measure_audio_duration(source_path) > 0:
            return source_path
        sample_rate = config.tts_config.sample_rate if config.tts_config else 24000
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-i", source_path,
                "-ac", "1", "-ar", str(sample_rate or 24000), "-y", str(destination),
            ], env=child_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_CREATE_FLAGS,
        )
        if result.returncode == 0 and measure_audio_duration(destination) > 0:
            return str(destination)
        return ""

    @staticmethod
    def _measure_groups(groups: list["DubbingGroup"]) -> None:
        for group in groups:
            if group.fit_status == DubbingFitStatus.FAILED:
                continue
            group.measured_duration = measure_audio_duration(group.audio_path)
            if group.measured_duration <= 0:
                group.fit_status = DubbingFitStatus.FAILED
                group.warnings.append("Synthesized audio duration is invalid")
                continue
            group.fit_ratio = (
                group.measured_duration / group.available_duration
                if group.available_duration > 0
                else float("inf")
            )

    def _rewrite_outliers(
        self,
        groups: list["DubbingGroup"],
        config: "DubbingConfig",
        service: TimingRewriteService,
        provider: "BaseTTS",
        cache: PersistentTTSCache,
        output_dir: Path,
        callback: Callable[[int, str], None],
    ) -> None:
        if not config.rewrite_enabled or not service.configured:
            return
        outliers = [group for group in groups if group.fit_ratio > config.fit_ratio_limit]
        for position, group in enumerate(outliers):
            group_index = groups.index(group)
            for attempt in range(1, config.max_rewrite_attempts + 1):
                snapshot = (
                    group.tts_text,
                    group.audio_path,
                    group.measured_duration,
                    group.fit_ratio,
                    group.fit_status,
                    group.action_taken,
                    group.cache_key,
                )
                request = request_for_group(
                    group,
                    source_language="",
                    target_language=config.target_language,
                    attempt_number=attempt,
                    custom_style_prompt=config.rewrite_style_prompt,
                    previous_text=groups[group_index - 1].subtitle_text if group_index else "",
                    next_text=groups[group_index + 1].subtitle_text if group_index + 1 < len(groups) else "",
                )
                try:
                    candidate = service.rewrite(request, rescue=True)
                except Exception as exc:
                    callback(55, "Đang kiểm tra trạng thái lồng tiếng...")
                    group.warnings.append(f"Rewrite attempt {attempt} rejected: {exc}")
                    continue
                if not candidate:
                    break
                group.tts_text = candidate
                group.audio_path = ""
                group.measured_duration = 0.0
                group.fit_ratio = 0.0
                group.cache_key = self._cache_key(group, config)
                hit = cache.get(group.cache_key)
                if hit:
                    group.audio_path = hit.audio_path
                    group.measured_duration = hit.duration
                else:
                    self._synthesize_missing_groups(
                        [group], config, provider, cache, output_dir, callback
                    )
                self._measure_groups([group])
                old_ratio = snapshot[3]
                candidate_ratio = group.fit_ratio
                acceptable = 0.85 <= candidate_ratio <= config.fit_ratio_limit
                improved = candidate_ratio >= 0.75 and abs(candidate_ratio - 1.0) < abs(old_ratio - 1.0)
                if group.fit_status == DubbingFitStatus.FAILED or not (acceptable or improved):
                    attempts = group.attempt_count
                    (
                        group.tts_text,
                        group.audio_path,
                        group.measured_duration,
                        group.fit_ratio,
                        group.fit_status,
                        group.action_taken,
                        group.cache_key,
                    ) = snapshot
                    group.attempt_count = attempts
                    group.warnings.append(f"Rewrite attempt {attempt} was not a better fit")
                    continue
                group.action_taken = "rewrite"
                group.fit_status = DubbingFitStatus.REWRITTEN
                if group.fit_ratio <= config.fit_ratio_limit:
                    break
            callback(
                55 + int((position + 1) / max(len(outliers), 1) * 10),
                "Đang xử lý các câu vượt khung...",
            )

    def _apply_fit_policy(
        self,
        groups: list["DubbingGroup"],
        config: "DubbingConfig",
        adjusted_dir: Path,
        *,
        video_duration: float | None = None,
    ) -> list[dict]:
        adjusted_dir.mkdir(parents=True, exist_ok=True)
        result: list[dict] = []
        natural = config.timing_mode == DubbingTimingMode.NATURAL
        if natural and config.unresolved_policy.value == "sequential":
            if video_duration is None:
                raise ValueError("Sequential dubbing requires video duration")
            return self._apply_sequential_policy(groups, config, adjusted_dir, video_duration)
        for group in groups:
            if group.fit_status == DubbingFitStatus.FAILED:
                continue
            if natural and config.tts_config and config.tts_config.speed > config.natural_max_speed:
                group.warnings.append(
                    f"User-requested provider speed {config.tts_config.speed:.2f}x exceeds natural ceiling"
                )
            if group.fit_ratio <= config.fit_ratio_limit:
                if group.fit_status not in {
                    DubbingFitStatus.CACHED,
                    DubbingFitStatus.REWRITTEN,
                }:
                    group.fit_status = DubbingFitStatus.FIT
                result.append(self._segment_info(group))
                continue

            speed_ceiling = config.natural_max_speed if natural else config.max_speed
            needed_speed = group.measured_duration / max(group.available_duration, 0.001)
            speed = max(1.0, min(speed_ceiling, needed_speed))
            if speed > 1.02:
                adjusted = adjusted_dir / f"{group.group_id}-speed.wav"
                if adjust_audio_speed(group.audio_path, str(adjusted), speed):
                    group.audio_path = str(adjusted)
                    group.measured_duration = measure_audio_duration(adjusted)
                    group.fit_ratio = group.measured_duration / max(group.available_duration, 0.001)
                    prefix = f"{group.action_taken}+" if group.action_taken else ""
                    group.action_taken = f"{prefix}speed_adjust_{speed:.3f}x"
                    group.fit_status = DubbingFitStatus.SPEED_ADJUSTED

            if group.fit_ratio > config.fit_ratio_limit:
                if natural:
                    group.fit_status = DubbingFitStatus.NEEDS_REVIEW
                    if config.unresolved_policy.value == "review":
                        group.needs_review = True
                        prefix = f"{group.action_taken}+" if group.action_taken else ""
                        group.action_taken = f"{prefix}review_required"
                    else:
                        prefix = f"{group.action_taken}+" if group.action_taken else ""
                        group.action_taken = f"{prefix}allow_overlap"
                        group.warnings.append(
                            f"Full speech overlaps planned capacity by {group.measured_duration - group.available_duration:.3f}s"
                        )
                else:
                    truncated = adjusted_dir / f"{group.group_id}-truncated.wav"
                    if self.engine._truncate_audio(
                        group.audio_path, str(truncated), group.available_duration
                    ):
                        group.audio_path = str(truncated)
                        group.measured_duration = measure_audio_duration(truncated)
                        group.fit_ratio = group.measured_duration / max(group.available_duration, 0.001)
                        prefix = f"{group.action_taken}+" if group.action_taken else ""
                        group.action_taken = f"{prefix}legacy_truncate"
                        group.fit_status = DubbingFitStatus.FIT
            result.append(self._segment_info(group))
        return result

    def _apply_sequential_policy(self, groups, config, adjusted_dir, video_duration):
        provider_speed = config.tts_config.speed if config.tts_config else 1.0
        ceiling = max(1.0, min(config.natural_max_speed, config.natural_max_speed / max(provider_speed, 0.01)))
        gap = max(0.02, config.silence_guard_ms / 1000.0)
        delay_limit = config.max_start_delay_ms / 1000.0
        timeline_groups = [replace(g, start_time=g.start_time / config.video_speed) for g in groups]
        slots = sequential_slots(timeline_groups, video_duration=video_duration, max_speed=ceiling,
                                 max_delay=delay_limit, gap=gap)
        result, previous_end = [], -gap
        for group, slot in zip(groups, slots):
            group.needs_review = False
            group.applied_speed = slot.speed * config.voice_tempo
            if slot.speed > 1.001:
                output = adjusted_dir / f"{group.group_id}-sequential.wav"
                if not adjust_audio_speed(group.audio_path, str(output), slot.speed):
                    group.fit_status = DubbingFitStatus.FAILED
                    group.warnings.append("Cannot render sequential speech speed adjustment")
                    continue
                group.audio_path = str(output)
                group.measured_duration = measure_audio_duration(output)
                if group.measured_duration <= 0:
                    group.fit_status = DubbingFitStatus.FAILED
                    group.warnings.append("Adjusted sequential audio has invalid duration")
                    continue
                group.action_taken = "+".join(filter(None, (group.action_taken, f"speed_adjust_{slot.speed:.3f}x")))
                group.fit_status = DubbingFitStatus.SPEED_ADJUSTED
            # Recompute from the actual WAV, never from the ideal duration/speed ratio.
            group.fit_ratio = group.measured_duration / max(group.available_duration / config.video_speed, 0.001)
            source_start = group.start_time / config.video_speed
            start = math.ceil(max(source_start, previous_end + gap) * 1000) / 1000
            end = start + group.measured_duration
            group.playback_start_time, group.playback_end_time = start, end
            group.start_delay = max(0.0, start - source_start)
            hard_end = min(video_duration, group.hard_end_time / config.video_speed) if group.hard_end_time is not None else video_duration
            if group.start_delay > delay_limit + 0.000001 or end > hard_end + 0.000001:
                group.needs_review = True
                group.fit_status = DubbingFitStatus.NEEDS_REVIEW
                if group.start_delay > delay_limit + 0.000001:
                    group.warnings.append(
                        f"Sequential start delay {group.start_delay * 1000:.3f} ms exceeds "
                        f"limit {config.max_start_delay_ms} ms"
                    )
                if end > video_duration + 0.000001:
                    group.warnings.append(
                        f"Sequential speech ends at {end:.3f}s, beyond video end "
                        f"{video_duration:.3f}s by {end - video_duration:.3f}s"
                    )
                elif end > hard_end + 0.000001:
                    group.warnings.append(f"Dialogue crosses a turn/scene/silence boundary at {hard_end:.3f}s")
            elif group.fit_status not in (DubbingFitStatus.SPEED_ADJUSTED, DubbingFitStatus.REWRITTEN, DubbingFitStatus.CACHED):
                group.fit_status = DubbingFitStatus.FIT
            group.action_taken = "+".join(filter(None, (group.action_taken, f"sequential_delay_{round(group.start_delay * 1000)}ms")))
            previous_end = end
            result.append(self._segment_info(group))
        return result

    @staticmethod
    def _segment_info(group: "DubbingGroup") -> dict:
        return {
            "audio_path": group.audio_path,
            "start_time": group.playback_start_time if group.playback_start_time is not None else group.start_time,
            "end_time": group.playback_end_time if group.playback_end_time is not None else group.subtitle_end_time,
        }

    @staticmethod
    def _provider_failure_reason(groups: list["DubbingGroup"]) -> str:
        failed = [group for group in groups if group.fit_status == DubbingFitStatus.FAILED]
        details = "; ".join(
            f"{group.group_id}: {group.warnings[-1] if group.warnings else 'không có audio'}"
            for group in failed[:3]
        )
        extra = f"; và {len(failed) - 3} nhóm khác" if len(failed) > 3 else ""
        return f"TTS thất bại ở {len(failed)} nhóm. {details}{extra}"

    @staticmethod
    def _review_failure_reason(groups: list["DubbingGroup"]) -> str:
        review = [group for group in groups if group.needs_review]
        if any(group.playback_start_time is not None for group in review):
            details = "; ".join(
                f"{group.group_id}: {warning}" for group in review[:3]
                for warning in group.warnings if warning.startswith("Sequential ")
            )
            return (
                f"Có {len(review)} nhóm không thể đọc đủ trong giới hạn hiện tại. {details}. "
                "Đã giữ lời đọc và audio để xem lại; chưa xuất video."
            )
        worst = max(review, key=lambda group: group.fit_ratio)
        return (
            f"Có {len(review)} nhóm chưa khớp thời gian. Tệ nhất {worst.group_id}: "
            f"audio {worst.measured_duration:.2f}s, khung khả dụng "
            f"{worst.available_duration:.2f}s, tỷ lệ {worst.fit_ratio:.2f}x. "
            "Hãy rút gọn lời đọc bằng LLM hoặc điều chỉnh giới hạn tốc độ/độ trễ."
        )

    def _write_report(
        self,
        plan: DubbingPlan,
        report_path: str,
        *,
        output_created: bool,
    ) -> None:
        plan.summary = calculate_report_summary(plan.groups, output_created, plan.video_speed)
        report = DubbingReport(plan=plan, report_path=report_path)
        report_data = report.to_dict()
        self.engine.last_report = report_data
        self.engine.last_review = DubbingReview.from_report(report_data) if plan.groups else None
        self.engine.last_report_path = ""
        if not report_path:
            return
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temp_path.write_text(
            json.dumps(report_data, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        os.replace(temp_path, path)
        self.engine.last_report_path = str(path)
