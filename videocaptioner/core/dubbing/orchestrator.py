"""Measured cache/rewrite/fit orchestration behind :class:`DubbingEngine`."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
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
    build_tts_cache_key,
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
from videocaptioner.core.dubbing.planner import plan_dubbing_groups, predict_spoken_duration
from videocaptioner.core.dubbing.rewrite_service import (
    TimingRewriteService,
    request_for_group,
)
from videocaptioner.core.tts import TTSData, TTSDataSeg
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.video_utils import get_video_info

if TYPE_CHECKING:
    from videocaptioner.core.dubbing.config import DubbingConfig
    from videocaptioner.core.dubbing.engine import DubbingEngine
    from videocaptioner.core.dubbing.models import DubbingGroup
    from videocaptioner.core.tts import BaseTTS

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
    ) -> str:
        self._validate(video_path, subtitle_path, config)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        report_path = self._report_path(config)
        self.engine.last_report_path = report_path
        self.engine.last_report = {}
        work_dir = Path(tempfile.mkdtemp(prefix="vc_dub_"))
        try:
            callback(5, "Đang đọc phụ đề...")
            asr_data = self._load_dubbing_source(subtitle_path)
            total_duration = self._video_duration(video_path, asr_data)
            plan = self._build_dubbing_plan(
                asr_data, subtitle_path, total_duration, config
            )
            if not plan.groups:
                raise ValueError("Phụ đề trống, không có gì để lồng tiếng")

            if config.rewrite_model and config.rewrite_api_key and config.rewrite_api_base:
                os.environ["OPENAI_API_KEY"] = config.rewrite_api_key
                os.environ["OPENAI_BASE_URL"] = config.rewrite_api_base
            rewrite_service = self.engine._create_rewrite_service(config)
            if config.timing_mode == DubbingTimingMode.NATURAL:
                self._pre_rewrite_hard_outliers(plan.groups, config, rewrite_service)

            callback(12, "Đang kiểm tra TTS cache...")
            cache = PersistentTTSCache(
                self.engine.cache_root, enabled=config.cache_enabled
            )
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

            if config.timing_mode == DubbingTimingMode.NATURAL:
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
            segment_infos = self._apply_fit_policy(
                plan.groups, config, work_dir / "adjusted"
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
            if not mix_audio_tracks(
                video_path,
                voice_track_path,
                output_path,
                mix_mode=config.mix_mode,
                original_volume=config.original_volume,
                voice_volume=config.voice_volume,
                normalize_voice=False,
            ):
                raise RuntimeError("Mix audio thất bại")
            if not Path(output_path).is_file():
                raise RuntimeError("Dubbing không tạo artifact đầu ra")
            self._write_report(plan, report_path, output_created=True)
            callback(100, "Lồng tiếng hoàn tất!")
            return output_path
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

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
        return ASRData.from_subtitle_file(subtitle_path)

    @staticmethod
    def _video_duration(video_path: str, asr_data: ASRData) -> float:
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
        )
        tts = config.tts_config
        return DubbingPlan(
            source_path=subtitle_path,
            target_language=config.target_language,
            provider=config.tts_provider.name.lower(),
            model=tts.model if tts else "",
            voice=(tts.voice or "") if tts else "",
            timing_mode=config.timing_mode,
            created_at=datetime.now(timezone.utc).isoformat(),
            groups=groups,
        )

    @staticmethod
    def _report_path(config: "DubbingConfig") -> str:
        return config.report_path

    @staticmethod
    def _cache_key(group: "DubbingGroup", config: "DubbingConfig") -> str:
        assert config.tts_config is not None
        return build_tts_cache_key(
            text=group.tts_text,
            provider=config.tts_provider.name.lower(),
            api_base=config.tts_config.base_url,
            model=config.tts_config.model,
            voice=config.tts_config.voice or "",
            speed=config.tts_config.speed,
            sample_rate=config.tts_config.sample_rate,
        )

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
        provider.synthesize(
            tts_data,
            str(output_dir),
            lambda progress, message: callback(18 + int(progress * 0.32), message),
            max_workers=config.tts_concurrency,
        )
        assert config.tts_config is not None
        for group, segment in zip(unique, tts_data.segments):
            group.attempt_count += 1
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
            cache.put(
                group.cache_key,
                audio_path,
                provider=config.tts_provider.name.lower(),
                model=config.tts_config.model,
                voice=config.tts_config.voice or "",
                sample_rate=config.tts_config.sample_rate,
            )
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
            ],
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

    @staticmethod
    def _pre_rewrite_hard_outliers(
        groups: list["DubbingGroup"],
        config: "DubbingConfig",
        service: TimingRewriteService,
    ) -> None:
        if not config.rewrite_enabled or not service.configured:
            return
        for group in groups:
            predicted_ratio = (
                group.predicted_duration / group.available_duration
                if group.available_duration > 0
                else float("inf")
            )
            if predicted_ratio <= 1.15:
                continue
            group.fit_ratio = predicted_ratio
            request = request_for_group(
                group,
                source_language="",
                target_language=config.target_language,
                attempt_number=0,
                custom_style_prompt=config.rewrite_style_prompt,
            )
            try:
                rewritten = service.rewrite(request, rescue=False)
            except Exception as exc:
                group.warnings.append(f"Pre-rewrite skipped: {exc}")
                continue
            if rewritten and rewritten != group.tts_text:
                group.tts_text = rewritten
                group.predicted_duration = predict_spoken_duration(
                    rewritten, config.target_language
                )
                group.action_taken = "pre_rewrite"

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
                )
                try:
                    candidate = service.rewrite(request, rescue=True)
                except Exception as exc:
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
    ) -> list[dict]:
        adjusted_dir.mkdir(parents=True, exist_ok=True)
        result: list[dict] = []
        natural = config.timing_mode == DubbingTimingMode.NATURAL
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

    @staticmethod
    def _segment_info(group: "DubbingGroup") -> dict:
        return {
            "audio_path": group.audio_path,
            "start_time": group.start_time,
            "end_time": group.subtitle_end_time,
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
        worst = max(review, key=lambda group: group.fit_ratio)
        return (
            f"Có {len(review)} nhóm chưa khớp thời gian. Tệ nhất {worst.group_id}: "
            f"audio {worst.measured_duration:.2f}s, khung khả dụng "
            f"{worst.available_duration:.2f}s, tỷ lệ {worst.fit_ratio:.2f}x. "
            "Hãy rút gọn TTS text hoặc chọn Cho phép chồng lấn."
        )

    def _write_report(
        self,
        plan: DubbingPlan,
        report_path: str,
        *,
        output_created: bool,
    ) -> None:
        plan.summary = calculate_report_summary(plan.groups, output_created)
        report = DubbingReport(plan=plan, report_path=report_path)
        report_data = report.to_dict()
        self.engine.last_report = report_data
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
