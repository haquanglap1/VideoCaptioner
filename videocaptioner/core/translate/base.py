"""Translator base class."""

import atexit
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional, cast

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.llm.context import submit_with_context
from videocaptioner.core.translate.types import TargetLanguage
from videocaptioner.core.utils.cache import generate_cache_key, get_translate_cache
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("subtitle_translator")


class BaseTranslator(ABC):
    """Translator base class."""

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        target_language: TargetLanguage,
        update_callback: Optional[Callable],
    ):
        self.thread_num = thread_num
        self.batch_num = batch_num
        self.target_language = target_language
        self.is_running = True
        self.update_callback = update_callback
        self.executor = None
        self._cache = get_translate_cache()

        self._init_thread_pool()

    def _init_thread_pool(self):
        """Create the worker pool."""
        self.executor = ThreadPoolExecutor(max_workers=self.thread_num)
        atexit.register(self.stop)

    def translate_subtitle(self, subtitle_data: ASRData) -> ASRData:
        """Translate a subtitle file."""
        try:
            asr_data = subtitle_data

            # Convert ASRData into a SubtitleProcessData list
            translate_data_list = [
                SubtitleProcessData(index=i, original_text=seg.text)
                for i, seg in enumerate(asr_data.segments, 1)
            ]

            # Pre-chunk hook (e.g. build global context); no-op by default
            self._prepare(translate_data_list)

            # Split into chunks
            chunks = self._split_chunks(translate_data_list)

            # Translate chunks in parallel
            translated_list = self._parallel_translate(chunks)

            # Write the translations back into the segments
            new_segments = self._set_segments_translated_text(
                asr_data.segments, translated_list
            )

            return ASRData(new_segments)
        except Exception as e:
            logger.error(f"Translation failed: {str(e)}")
            raise RuntimeError(f"Translation failed: {str(e)}")

    def _prepare(self, translate_data_list: List[SubtitleProcessData]) -> None:
        """Hook run before chunking.

        Subclasses may build state shared across chunks (global context,
        glossary). The base class does nothing.
        """
        pass

    def _split_chunks(
        self, translate_data_list: List[SubtitleProcessData]
    ) -> List[List[SubtitleProcessData]]:
        """Split the subtitles into chunks."""
        return [
            translate_data_list[i : i + self.batch_num]
            for i in range(0, len(translate_data_list), self.batch_num)
        ]

    def _parallel_translate(
        self, chunks: List[List[SubtitleProcessData]]
    ) -> List[SubtitleProcessData]:
        """Translate all chunks in parallel."""
        future_to_chunk = {}
        translated_list = []
        failed_count = 0
        first_error: Optional[BaseException] = None
        total_segments = sum(len(c) for c in chunks)

        executor = self.executor
        if executor is None:
            raise RuntimeError("Translator executor has already been shut down")
        for chunk in chunks:
            future = submit_with_context(executor, self._safe_translate_chunk, chunk)
            future_to_chunk[future] = chunk

        for future in as_completed(future_to_chunk):
            if not self.is_running:
                break
            try:
                result = future.result()
                translated_list.extend(result)
            except Exception as e:
                logger.error(f"Translation chunk failed: {e}")
                if first_error is None:
                    first_error = e
                failed_count += len(future_to_chunk[future])
                translated_list.extend(future_to_chunk[future])

        # Raise if all or most translations failed
        if failed_count > 0 and total_segments > 0:
            fail_rate = failed_count / total_segments
            if fail_rate >= 0.5:
                cause = type(first_error).__name__ if first_error else "unknown"
                detail = str(first_error) if first_error else ""
                raise RuntimeError(
                    f"Translation failed: {failed_count}/{total_segments} segments failed "
                    f"({fail_rate:.0%}). First error [{cause}]: {detail}"
                ) from first_error
            elif failed_count > 0:
                logger.warning(f"Translation partially failed: {failed_count}/{total_segments} segments")

        return translated_list

    def _get_cache_key(self, chunk: List[SubtitleProcessData]) -> str:
        """Build the cache key."""
        class_name = self.__class__.__name__
        chunk_key = generate_cache_key(chunk)
        lang = self.target_language.value
        return f"{class_name}:{chunk_key}:{lang}"

    def _safe_translate_chunk(
        self, chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        """Translate one chunk with caching and error isolation."""
        try:
            cache_key = self._get_cache_key(chunk)
            try:
                # diskcache's overloads widen the return type; the cache only ever
                # stores the list this method produced.
                cached_result = cast(
                    Optional[List[SubtitleProcessData]],
                    self._cache.get(cache_key, default=None),
                )
            except Exception:
                # Graceful degradation: corrupted cache (e.g. old pickle from app→videocaptioner rename)
                cached_result = None
                self._cache.delete(cache_key)
            if cached_result is not None:
                # Cache hit vẫn phải báo tiến độ, nếu không progress bar sẽ đứng
                # và bảng phụ đề không hiển thị phần lấy từ cache.
                if self.update_callback:
                    self.update_callback(cached_result)
                return cached_result

            result = self._translate_chunk(chunk)

            if self.update_callback:
                self.update_callback(result)

            self._cache.set(cache_key, result, expire=86400 * 7)
            return result

        except Exception as e:
            logger.exception(f"Translation failed: {str(e)}")
            raise

    @staticmethod
    def _set_segments_translated_text(
        original_segments: List[ASRDataSeg], translated_list: List[SubtitleProcessData]
    ) -> List[ASRDataSeg]:
        """Write translated text back into the segments."""
        # Map index -> translated text
        translation_map = {data.index: data.translated_text for data in translated_list}

        for i, seg in enumerate(original_segments, 1):
            if i not in translation_map:
                logger.error(f"Subtitle segment {i} has no translation")
                continue
            seg.translated_text = translation_map[i]

        return original_segments

    @abstractmethod
    def _translate_chunk(
        self, subtitle_chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        """Translate one chunk."""
        pass

    def stop(self):
        """Stop the translator."""
        if not self.is_running:
            return

        self.is_running = False
        if hasattr(self, "executor") and self.executor is not None:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                logger.error(f"Error closing thread pool: {str(e)}")
            finally:
                self.executor = None
