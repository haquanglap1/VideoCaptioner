"""Dubbing Engine — orchestrator chính cho pipeline lồng tiếng.

Pipeline:
1. Parse subtitle → ASRData
2. Tạo TTSData từ ASRData segments
3. Gọi TTS provider batch synthesize
4. Căn chỉnh timeline (speed up/slow down từng segment)
5. Ghép voice track (silence padding + concat)
6. Mix voice track vào video gốc
"""

import os
import re
import tempfile
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from typing import Callable, Optional

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.dubbing.audio_mixer import (
    adjust_audio_speed,
    build_voice_track,
    get_audio_duration,
    mix_audio_tracks,
)
from videocaptioner.core.dubbing.config import DubbingConfig, TTSProviderEnum
from videocaptioner.core.dubbing.models import (
    DubbingCue,
    DubbingFitStatus,
    DubbingProviderError,
    DubbingTextSource,
    resolve_dubbing_text,
)
from videocaptioner.core.tts import (
    BaseTTS,
    MiniMaxTTS,
    OpenAITTS,
    TTSData,
    TTSDataSeg,
)
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.video_utils import get_video_info

logger = setup_logger("dubbing.engine")

# Ký tự Hán/CJK còn sót trong phụ đề đích (vd tiếng Trung chưa dịch hết) khiến
# TTS đọc nhầm. Lọc bỏ trước khi tổng hợp giọng.
_CJK_PATTERN = re.compile(
    "["
    "\u3000-\u303f"      # CJK symbols & punctuation (、。「」…)
    "\u3400-\u4dbf"      # CJK Unified Ext A
    "\u4e00-\u9fff"      # CJK Unified Ideographs
    "\uf900-\ufaff"      # CJK Compatibility Ideographs
    "\uff00-\uffef"      # Halfwidth/Fullwidth forms
    "\U00020000-\U0002a6df"  # CJK Unified Ext B
    "]+"
)
# Sau khi bỏ CJK, gộp khoảng trắng thừa.
_WS_PATTERN = re.compile(r"\s{2,}")


def _noop_progress(progress: int, message: str) -> None:
    """Callback tiến độ rỗng, dùng khi caller không truyền callback."""


def _strip_cjk(text: str) -> str:
    """Loại bỏ ký tự Hán/CJK và gộp khoảng trắng thừa."""
    cleaned = _CJK_PATTERN.sub(" ", text)
    cleaned = _WS_PATTERN.sub(" ", cleaned)
    return cleaned.strip()


class DubbingEngine:
    """Engine lồng tiếng video.

    Nhận video + subtitle, tạo voice track bằng TTS, căn chỉnh timeline,
    và mix vào video gốc.
    """

    def __init__(
        self,
        *,
        tts_provider_factory=None,
        rewrite_service_factory=None,
        cache_root: str | Path | None = None,
    ):
        self._tts_provider_factory = tts_provider_factory
        self._rewrite_service_factory = rewrite_service_factory
        self.cache_root = cache_root
        self.last_report_path = ""
        self.last_report: dict = {}

    def dub(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        config: DubbingConfig,
        callback: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """Thực hiện toàn bộ pipeline dubbing.

        Args:
            video_path: Đường dẫn video gốc.
            subtitle_path: Đường dẫn file phụ đề (SRT/ASS/VTT).
            output_path: Đường dẫn video đầu ra.
            config: Cấu hình dubbing.
            callback: Hàm callback tiến độ (progress: int, message: str).

        Returns:
            Đường dẫn video đầu ra.

        Raises:
            ValueError: Nếu thiếu config hoặc file không tồn tại.
            RuntimeError: Nếu bất kỳ bước nào thất bại.
        """
        if callback is None:
            callback = _noop_progress

        from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator

        with self._managed_runtime_context(config):
            return DubbingOrchestrator(self).run(
                video_path, subtitle_path, output_path, config, callback
            )

    def regenerate_groups(
        self,
        cues: list[DubbingCue],
        selected_cue_ids: set[int | str],
        *,
        video_duration: float,
        config: DubbingConfig,
        output_dir: str | Path,
        callback: Optional[Callable[[int, str], None]] = None,
    ):
        """Force-refresh only groups intersecting ``selected_cue_ids``.

        This is the editor-facing regeneration path. It plans with the same
        Natural/Legacy grouping rules, invalidates only each selected group's
        cache key, performs one provider request per unique selected key and
        returns measured groups without mixing or touching unrelated audio.
        """
        if (
            config.tts_provider == TTSProviderEnum.VIENEU_LOCAL
            and not config.managed_tts_identity
        ):
            with self._managed_runtime_context(config):
                return self.regenerate_groups(
                    cues,
                    selected_cue_ids,
                    video_duration=video_duration,
                    config=config,
                    output_dir=output_dir,
                    callback=callback,
                )
        if not config.tts_config:
            raise ValueError("TTS config chưa được cấu hình")
        if callback is None:
            callback = _noop_progress
        selected = {str(cue_id) for cue_id in selected_cue_ids}
        if not selected:
            raise ValueError("Chưa chọn cue/group để tạo lại giọng")

        from videocaptioner.core.dubbing.cache import PersistentTTSCache
        from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
        from videocaptioner.core.dubbing.planner import plan_dubbing_groups

        natural = config.timing_mode.value == "natural"
        groups = plan_dubbing_groups(
            cues,
            video_duration=max(0.0, float(video_duration)),
            borrow_gap_ms=config.borrow_gap_ms if natural else -1,
            silence_guard_ms=config.silence_guard_ms if natural else 0,
            max_group_duration=config.max_group_duration,
            target_language=config.target_language,
        )
        targets = [
            group for group in groups if selected.intersection(str(item) for item in group.cue_ids)
        ]
        if not targets:
            raise ValueError("Không tìm thấy group chứa cue đã chọn")

        cue_map = {str(cue.cue_id): cue for cue in cues}
        orchestrator = DubbingOrchestrator(self)
        cache = PersistentTTSCache(self.cache_root, enabled=config.cache_enabled)
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        for index, group in enumerate(targets):
            group_config = deepcopy(config)
            first_cue = next((cue_map.get(str(cue_id)) for cue_id in group.cue_ids), None)
            if first_cue and group_config.tts_config:
                if first_cue.voice:
                    group_config.tts_config.voice = first_cue.voice
                requested_speed = first_cue.metadata.get("voice_speed")
                if requested_speed is not None:
                    group_config.tts_config.speed = float(requested_speed)
            group.cache_key = orchestrator._cache_key(group, group_config)
            cache.invalidate(group.cache_key)
            group.audio_path = ""
            group.fit_status = DubbingFitStatus.PENDING
            provider = self._create_tts_provider(group_config)
            callback(10 + int(index * 70 / max(1, len(targets))), "Đang tạo lại giọng đã chọn...")
            orchestrator._synthesize_missing_groups(
                [group],
                group_config,
                provider,
                cache,
                root / group.group_id,
                callback,
            )
            orchestrator._measure_groups([group])
            if group.fit_status == DubbingFitStatus.FAILED:
                raise DubbingProviderError(reason=orchestrator._provider_failure_reason([group]))
            fit_limit = max(0.01, float(group_config.fit_ratio_limit))
            if group.fit_ratio <= fit_limit:
                group.fit_status = DubbingFitStatus.FIT
                group.action_taken = "editor_force_refresh"
            else:
                group.fit_status = DubbingFitStatus.NEEDS_REVIEW
                group.needs_review = True
                group.action_taken = "editor_force_refresh_needs_review"
                group.warnings.append(
                    f"Regenerated audio exceeds available duration ({group.fit_ratio:.2f}x)"
                )
        callback(100, "Đã tạo lại giọng cho group được chọn")
        return targets

    @staticmethod
    def _managed_runtime_context(config: DubbingConfig):
        if config.tts_provider != TTSProviderEnum.VIENEU_LOCAL:
            return nullcontext()
        from videocaptioner.core.tts.vieneu.service import get_vieneu_service

        return get_vieneu_service().acquire_for_dubbing(config)

    def _dub_legacy_compat(
        self,
        video_path: str,
        subtitle_path: str,
        output_path: str,
        config: DubbingConfig,
        callback: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """Previous orchestration retained temporarily for compatibility reference."""
        if callback is None:
            callback = _noop_progress

        # Validate inputs
        if not Path(video_path).is_file():
            raise ValueError(f"Video không tồn tại: {video_path}")
        if not Path(subtitle_path).is_file():
            raise ValueError(f"Subtitle không tồn tại: {subtitle_path}")
        if not config.tts_config:
            raise ValueError("TTS config chưa được cấu hình")

        # Kiểm tra ffmpeg/ffprobe có sẵn trong PATH
        import shutil as _shutil
        missing_tools = [t for t in ("ffmpeg", "ffprobe") if _shutil.which(t) is None]
        if missing_tools:
            raise RuntimeError(
                "Không tìm thấy: %s. Vui lòng cài FFmpeg và thêm vào PATH."
                % ", ".join(missing_tools)
            )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Tạo thư mục tạm cho intermediate files
        work_dir = Path(tempfile.mkdtemp(prefix="vc_dub_"))
        logger.info("Dubbing work dir: %s", work_dir)

        try:
            # --- Step 1: Parse subtitle ---
            callback(5, "Đang đọc phụ đề...")
            asr_data = ASRData.from_subtitle_file(subtitle_path)
            segments = asr_data.segments
            if not segments:
                raise ValueError("Phụ đề trống, không có gì để lồng tiếng")
            logger.info("Parsed %d subtitle segments", len(segments))

            # Lấy tổng thời lượng video
            video_info = get_video_info(video_path)
            total_duration = video_info.duration_seconds if video_info else 0.0
            if total_duration <= 0:
                # Fallback: dùng end time của segment cuối
                total_duration = max(seg.end_time / 1000.0 for seg in segments) + 1.0

            # --- Step 2: Tạo TTSData ---
            callback(10, "Đang chuẩn bị văn bản...")
            tts_data = self._create_tts_data(
                segments,
                strip_cjk=config.strip_cjk,
                source_mode=config.text_source,
            )
            logger.info("Created TTSData with %d segments", len(tts_data))

            # --- Step 3: TTS Synthesize ---
            callback(15, "Đang tổng hợp giọng nói...")
            tts_output_dir = str(work_dir / "tts_audio")
            tts_provider = self._create_tts_provider(config)

            def tts_callback(progress: int, message: str):
                # TTS chiếm 15-60% tổng tiến độ
                mapped = 15 + int(progress * 0.45)
                callback(mapped, f"Đang tổng hợp giọng nói... {progress}%")

            tts_data = tts_provider.synthesize(
                tts_data,
                tts_output_dir,
                tts_callback,
                max_workers=config.tts_concurrency,
            )

            # Kiểm tra kết quả TTS
            total_segs = len(tts_data.segments)
            success_count = sum(1 for seg in tts_data.segments if seg.audio_path)
            if success_count == 0:
                raise RuntimeError("TTS thất bại cho tất cả segments")
            logger.info("TTS success: %d/%d segments", success_count, total_segs)
            failed_count = total_segs - success_count
            if failed_count > 0:
                # Các câu lỗi sẽ thành khoảng lặng trên voice track — báo cho user biết
                logger.warning(
                    "TTS lỗi %d/%d câu, các câu này sẽ bị lặng tiếng",
                    failed_count, total_segs,
                )
                callback(60, f"TTS lỗi {failed_count}/{total_segs} câu (sẽ bị lặng tiếng)")

            # --- Step 4: Timeline Alignment ---
            callback(60, "Đang căn chỉnh timeline...")
            adjusted_dir = str(work_dir / "adjusted")
            Path(adjusted_dir).mkdir(parents=True, exist_ok=True)
            segment_infos = self._align_timeline(
                tts_data, adjusted_dir, config, total_duration
            )
            logger.info("Timeline aligned: %d segments", len(segment_infos))

            # --- Step 5: Build Voice Track ---
            callback(75, "Đang ghép voice track...")
            voice_track_path = str(work_dir / "voice_track.wav")
            voice_sample_rate = config.tts_config.sample_rate or 24000
            if not build_voice_track(
                segment_infos,
                total_duration,
                voice_track_path,
                sample_rate=voice_sample_rate,
                normalize=True,
            ):
                raise RuntimeError("Ghép voice track thất bại")

            # --- Step 6: Mix vào video ---
            # Voice track đã chuẩn hóa độ to ở bước trên → bỏ loudnorm (và pass
            # đo) ở bước ghép để tăng tốc, giữ nguyên chất lượng.
            callback(85, "Đang mix audio vào video...")
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

            callback(100, "Lồng tiếng hoàn tất!")
            logger.info("Dubbing complete: %s", output_path)
            return output_path

        finally:
            # Cleanup work dir
            import shutil
            shutil.rmtree(str(work_dir), ignore_errors=True)

    def _create_dubbing_cues(
        self,
        segments,
        strip_cjk: bool = True,
        source_mode: DubbingTextSource = DubbingTextSource.AUTO,
    ) -> list[DubbingCue]:
        """Create rich cues while keeping display and spoken text separate."""
        cues: list[DubbingCue] = []
        skipped_cjk = 0
        for index, seg in enumerate(segments):
            source_text = str(getattr(seg, "text", "") or "").strip()
            translated_text = str(getattr(seg, "translated_text", "") or "").strip()
            if not source_text and not translated_text:
                continue
            text = resolve_dubbing_text(seg, source_mode)
            if strip_cjk:
                cleaned = _strip_cjk(text)
                if not cleaned:
                    logger.debug("Bỏ qua câu chỉ chứa ký tự CJK: %.40s", text)
                    skipped_cjk += 1
                    continue
                text = cleaned
            cues.append(
                DubbingCue(
                    cue_id=index + 1,
                    start_time=seg.start_time / 1000.0,
                    end_time=seg.end_time / 1000.0,
                    source_text=source_text,
                    subtitle_text=translated_text or source_text,
                    tts_text=text,
                    original_index=index,
                )
            )

        if strip_cjk and not cues and skipped_cjk:
            raise ValueError(
                f"Toàn bộ {skipped_cjk} câu bị lọc sạch vì chỉ chứa ký tự CJK. "
                "Nếu ngôn ngữ đích là Trung/Nhật/Quảng, hãy tắt strip_cjk "
                "trong cấu hình lồng tiếng."
            )
        return cues

    def _create_tts_data(
        self,
        segments,
        strip_cjk: bool = True,
        source_mode: DubbingTextSource = DubbingTextSource.AUTO,
    ) -> TTSData:
        """Chuyển ASRData segments thành TTSData.

        Args:
            segments: Danh sách ASRDataSeg (có text, start_time, end_time in ms).
            strip_cjk: Lọc ký tự CJK khỏi text (chỉ đúng khi ngôn ngữ đích là hệ
                Latin). Đặt False khi lồng tiếng sang Trung/Nhật/Quảng, nếu không
                mọi câu sẽ bị xóa trắng và TTS thất bại toàn bộ.

        Returns:
            TTSData instance.
        """
        cues = self._create_dubbing_cues(segments, strip_cjk, source_mode)
        return TTSData(
            [
                TTSDataSeg(
                    text=cue.tts_text,
                    start_time=cue.start_time,
                    end_time=cue.end_time,
                    voice=cue.voice or None,
                )
                for cue in cues
            ]
        )

    def _create_tts_provider(self, config: DubbingConfig) -> BaseTTS:
        """Tạo TTS provider instance từ config.

        Args:
            config: Dubbing config chứa tts_provider và tts_config.

        Returns:
            BaseTTS instance.
        """
        tts_config = config.tts_config
        if tts_config is None:
            raise ValueError("tts_config is required")

        if self._tts_provider_factory is not None:
            return self._tts_provider_factory(config)

        if config.tts_provider == TTSProviderEnum.MINIMAX:
            return MiniMaxTTS(tts_config)
        elif config.tts_provider == TTSProviderEnum.LOCAL_AI:
            # Local AI uses the standard OpenAI-compatible adapter
            return OpenAITTS(tts_config)
        elif config.tts_provider == TTSProviderEnum.VIENEU_LOCAL:
            if not config.managed_tts_identity:
                raise RuntimeError("VieNeu Local runtime identity was not resolved for this job")
            return OpenAITTS(tts_config)
        else:
            # Default: OpenAI
            return OpenAITTS(tts_config)

    def _create_rewrite_service(self, config: DubbingConfig):
        if self._rewrite_service_factory is not None:
            return self._rewrite_service_factory(config)
        from videocaptioner.core.dubbing.rewrite_service import TimingRewriteService

        return TimingRewriteService(config.rewrite_model)

    @staticmethod
    def _truncate_audio(input_path: str, output_path: str, max_duration: float) -> bool:
        return _truncate_audio(input_path, output_path, max_duration)

    def _align_timeline(
        self,
        tts_data: TTSData,
        output_dir: str,
        config: DubbingConfig,
        total_duration: float,
    ) -> list:
        """Căn chỉnh timeline: tăng tốc TTS audio vừa đủ để không đè câu kế tiếp.

        Mỗi câu được phép tràn vào khoảng lặng phía sau (tới khi câu kế tiếp bắt
        đầu, hoặc tới hết video với câu cuối). Chỉ tăng tốc (không kéo giãn chậm)
        và chỉ cắt cụt khi sau khi đã tăng tới trần tốc độ mà vẫn đè lên câu kế.

        Args:
            tts_data: TTSData đã synthesize (có audio_path, thời gian tính bằng giây).
            output_dir: Thư mục lưu audio đã điều chỉnh.
            config: DubbingConfig.
            total_duration: Tổng thời lượng video (giây).

        Returns:
            List[dict] — mỗi item: {"audio_path", "start_time", "end_time"} (seconds).
        """
        max_speed = config.max_speed
        segs = tts_data.segments
        result = []

        for idx, tts_seg in enumerate(segs):
            if not tts_seg.audio_path or not Path(tts_seg.audio_path).is_file():
                logger.warning(
                    "Segment %d không có audio (TTS lỗi), bỏ qua: %.40s",
                    idx, tts_seg.text,
                )
                continue

            # Timeline target (seconds)
            target_start = tts_seg.start_time
            target_end = tts_seg.end_time
            target_duration = target_end - target_start

            if target_duration <= 0:
                continue

            # Actual TTS audio duration
            actual_duration = get_audio_duration(tts_seg.audio_path)
            if actual_duration <= 0:
                continue

            # Khung khả dụng: cho phép tràn vào khoảng lặng tới khi câu kế tiếp
            # bắt đầu (câu cuối: tới hết video). Không bao giờ nhỏ hơn khung gốc.
            next_start = segs[idx + 1].start_time if idx + 1 < len(segs) else None
            if next_start is not None:
                available_end = next_start
            elif total_duration > 0:
                available_end = total_duration
            else:
                available_end = target_end
            available_duration = max(target_duration, available_end - target_start)

            # Chỉ tăng tốc (>=1.0), không kéo giãn chậm; chặn ở trần tốc độ.
            needed_speed = actual_duration / available_duration
            clamped_speed = max(1.0, min(max_speed, needed_speed))

            # Áp dụng speed adjustment
            if abs(clamped_speed - 1.0) > 0.02:
                adjusted_path = str(Path(output_dir) / f"seg_{idx:04d}_adj.wav")
                if adjust_audio_speed(tts_seg.audio_path, adjusted_path, clamped_speed):
                    audio_path = adjusted_path
                else:
                    audio_path = tts_seg.audio_path  # Fallback: giữ nguyên
            else:
                audio_path = tts_seg.audio_path

            # Chỉ cắt khi vẫn vượt khung khả dụng (sẽ đè lên câu kế tiếp)
            final_duration = get_audio_duration(audio_path)
            if final_duration > available_duration + 0.05:
                truncated_path = str(Path(output_dir) / f"seg_{idx:04d}_trunc.wav")
                if _truncate_audio(audio_path, truncated_path, available_duration):
                    audio_path = truncated_path
                logger.debug(
                    "Segment %d cắt cụt: %.2fs > khung %.2fs",
                    idx, final_duration, available_duration,
                )

            result.append({
                "audio_path": audio_path,
                "start_time": target_start,
                "end_time": target_end,
            })

        return result


def _truncate_audio(input_path: str, output_path: str, max_duration: float) -> bool:
    """Cắt audio tới max_duration giây.

    Args:
        input_path: File đầu vào.
        output_path: File đầu ra.
        max_duration: Thời lượng tối đa (giây).

    Returns:
        True nếu thành công.
    """
    import subprocess as sp

    _flags = getattr(sp, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-t", f"{max_duration:.3f}",
        "-y",
        output_path,
    ]
    try:
        result = sp.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_flags,
        )
        return result.returncode == 0 and Path(output_path).is_file()
    except Exception:
        return False
