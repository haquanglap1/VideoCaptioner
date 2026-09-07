import atexit
import difflib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Union

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.llm.context import submit_with_context
from videocaptioner.core.split.split_by_llm import split_by_llm
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.text_utils import (
    count_words,
    is_mainly_cjk,
    is_pure_punctuation,
    is_space_separated_language,
)

logger = setup_logger("subtitle_splitter")

# ==================== Configuration constants ====================

# Word limits
MAX_WORD_COUNT_CJK = 25  # Max characters per line for CJK text
MAX_WORD_COUNT_ENGLISH = 18  # Max words per line for English text

# Segment thresholds
SEGMENT_WORD_THRESHOLD = 500  # Word count above which text is cut into segments

# Time gaps
MAX_GAP = 1500  # Largest allowed gap (ms)
MERGE_SHORT_GAP = 200  # Gap under which short segments merge (ms)
MERGE_VERY_SHORT_GAP = 500  # Gap under which very short segments merge (ms)

# Short segment merge thresholds
MERGE_MIN_WORDS = 5  # Word count below which a segment is short
MERGE_VERY_SHORT_WORDS = 3  # Word count below which a segment is very short

# Splitting
SPLIT_SEARCH_RANGE = 30  # Search range around a split point
TIME_GAP_WINDOW_SIZE = 5  # Window size for gap analysis
TIME_GAP_MULTIPLIER = 3  # Multiplier that marks a gap as large
MIN_GROUP_SIZE = 5  # Minimum group size

# Rule-based splitting
RULE_SPLIT_GAP = 500  # Gap threshold for rule-based splitting (ms)
RULE_MIN_SEGMENT_SIZE = 4  # Minimum segment size for rule-based splitting

# Common-word splitting
PREFIX_WORD_RATIO = 0.6  # Split ratio at prefix words
SUFFIX_WORD_RATIO = 0.4  # Split ratio at suffix words

# Matching
MATCH_SIMILARITY_THRESHOLD = 0.5  # Similarity threshold for text matching
MATCH_MAX_SHIFT = 30  # Largest sliding-window offset while matching
MATCH_MAX_UNMATCHED = 5  # Largest allowed number of unmatched sentences
MATCH_LARGE_SHIFT = 100  # Large offset used when nothing matches


def preprocess_segments(
    segments: List[ASRDataSeg], need_lower: bool = True
) -> List[ASRDataSeg]:
    """Preprocess ASR segments.

    1. Drop segments that are only punctuation
    2. Add spaces for space-separated languages (English, Russian, Arabic, ...; not CJK)

    Args:
        segments: ASR segment list
        need_lower: lowercase the text (Latin and Cyrillic scripts only)

    Returns:
        Processed segment list
    """
    new_segments = []
    for seg in segments:
        if not is_pure_punctuation(seg.text):
            text = seg.text.strip()
            # Space-separated language (not CJK)?
            if is_space_separated_language(text):
                if need_lower:
                    text = text.lower()
                seg.text = text + " "
            new_segments.append(seg)
    return new_segments


class SubtitleSplitter:
    """Smart subtitle splitter.

    Splits into semantic segments with an LLM, with caching, concurrency and
    a rule-based fallback.
    """

    def __init__(
        self,
        thread_num,
        model,
        max_word_count_cjk: int = MAX_WORD_COUNT_CJK,
        max_word_count_english: int = MAX_WORD_COUNT_ENGLISH,
    ):
        """Create the splitter.

        Args:
            thread_num: number of concurrent threads
            model: LLM model name
            max_word_count_cjk: max characters for CJK text
            max_word_count_english: max words for English text
        """
        self.thread_num = thread_num
        self.model = model
        self.max_word_count_cjk = max_word_count_cjk
        self.max_word_count_english = max_word_count_english
        self.is_running = True
        self._init_thread_pool()

    def _init_thread_pool(self):
        """Create the thread pool and register its cleanup."""
        self.executor = ThreadPoolExecutor(max_workers=self.thread_num)
        atexit.register(self.stop)

    def split_subtitle(self, subtitle_data: Union[str, ASRData]) -> ASRData:
        """Split subtitles (main entry point).

        Steps:
        1. Read and preprocess the subtitles
        2. Cut into segments by word count
        3. Process the segments concurrently with the LLM
        4. Merge the results and optimize

        Args:
            subtitle_data: subtitle file path or ASRData object

        Returns:
            Split ASRData object

        Raises:
            RuntimeError: Raised on split failure
        """
        try:
            # 1. Read the subtitles
            if isinstance(subtitle_data, str):
                asr_data = ASRData.from_subtitle_file(subtitle_data)
            else:
                asr_data = subtitle_data

            if asr_data.has_metadata:
                from videocaptioner.core.asr.native_result import native_cues

                return native_cues(asr_data, self.max_word_count_cjk)

            if not asr_data.is_word_timestamp():
                asr_data = asr_data.split_to_word_segments()

            # 2. Preprocess
            asr_data.segments = preprocess_segments(asr_data.segments, need_lower=False)
            txt = asr_data.to_txt().replace("\n", "")

            # 3. Decide the segment count and split
            total_word_count = count_words(txt)
            num_segments = self._determine_num_segments(total_word_count)
            logger.debug(f"Based on word count {total_word_count},determined segment count: {num_segments}")

            asr_data_list = self._split_asr_data(asr_data, num_segments)

            # 4. Process concurrently
            processed_segments = self._process_segments(asr_data_list)

            # 5. Merge and optimize
            final_segments = self._merge_processed_segments(processed_segments)

            return ASRData(final_segments)

        except Exception as e:
            logger.error(f"Split failed:{str(e)}")
            raise RuntimeError(f"Split failed:{str(e)}")

    def _determine_num_segments(
        self, word_count: int, threshold: int = SEGMENT_WORD_THRESHOLD
    ) -> int:
        """Decide the segment count from the word count.

        Args:
            word_count: total word count
            threshold: target words per segment

        Returns:
            Segment count (at least 1)
        """
        num_segments = word_count // threshold
        if word_count % threshold > 0:
            num_segments += 1
        return max(1, num_segments)

    def _split_asr_data(self, asr_data: ASRData, num_segments: int) -> List[ASRData]:
        """Split long text into segments at time gaps.

        Strategy:
        1. Compute evenly spaced split points
        2. Look for the largest time gap near each split point
        3. Cut at that gap so sentences stay intact

        Args:
            asr_data: ASR data object
            num_segments: target segment count

        Returns:
            List of ASRData segments
        """
        total_segs = len(asr_data.segments)
        total_word_count = count_words(asr_data.to_txt())
        words_per_segment = total_word_count // num_segments

        if num_segments <= 1 or total_segs <= num_segments:
            return [asr_data]

        # Initial split points
        split_indices = [i * words_per_segment for i in range(1, num_segments)]

        # Adjust each split point to the largest nearby time gap
        adjusted_split_indices = []
        for split_point in split_indices:
            start = max(0, split_point - SPLIT_SEARCH_RANGE)
            end = min(total_segs - 1, split_point + SPLIT_SEARCH_RANGE)

            # Find the largest gap
            max_gap = -1
            best_index = split_point

            for j in range(start, end):
                gap = (
                    asr_data.segments[j + 1].start_time - asr_data.segments[j].end_time
                )
                if gap > max_gap:
                    max_gap = gap
                    best_index = j

            adjusted_split_indices.append(best_index)

        # Deduplicate and sort
        adjusted_split_indices = sorted(list(set(adjusted_split_indices)))

        # Split
        segments = []
        prev_index = 0
        for index in adjusted_split_indices:
            part = ASRData(asr_data.segments[prev_index : index + 1])
            segments.append(part)
            prev_index = index + 1

        if prev_index < total_segs:
            part = ASRData(asr_data.segments[prev_index:])
            segments.append(part)

        return segments

    def _process_segments(self, asr_data_list: List[ASRData]) -> List[List[ASRDataSeg]]:
        """Process all segments concurrently."""
        futures = []
        for asr_data in asr_data_list:
            if not self.executor:
                raise ValueError("Thread pool not initialized")
            future = submit_with_context(
                self.executor, self._process_single_segment, asr_data
            )
            futures.append(future)

        processed_segments = []
        for future in as_completed(futures):
            if not self.is_running:
                break
            try:
                result = future.result()
                processed_segments.append(result)
            except Exception as e:
                logger.error(f"Segment processing failed:{str(e)}")

        return processed_segments

    def _process_single_segment(self, asr_data_part: ASRData) -> List[ASRDataSeg]:
        """Process one segment with retry and fallback."""
        if not asr_data_part.segments:
            return []
        try:
            return self._process_by_llm(asr_data_part.segments)
        except Exception as e:
            logger.warning(f"LLM processing failed, falling back to rules: {str(e)}")
            return self._process_by_rules(asr_data_part.segments)

    def _process_by_llm(self, segments: List[ASRDataSeg]) -> List[ASRDataSeg]:
        """Split into sentences with the LLM.

        Args:
            segments: ASR segment list

        Returns:
            Processed segment list
        """
        txt = "".join([seg.text for seg in segments])
        logger.debug(f"Calling API for segmentation,text length: {count_words(txt)}")

        sentences = split_by_llm(
            text=txt,
            model=self.model,
            max_word_count_cjk=self.max_word_count_cjk,
            max_word_count_english=self.max_word_count_english,
        )

        return self._merge_segments_based_on_sentences(segments, sentences)

    def _process_by_rules(self, segments: List[ASRDataSeg]) -> List[ASRDataSeg]:
        """Basic rule-based splitting (fallback when the LLM fails).

        Rules:
        1. Group by time gaps
        2. Split long sentences at common words
        3. Split over-long segments

        Args:
            segments: ASR segment list

        Returns:
            Processed segment list
        """
        logger.debug(f"Segments: {len(segments)}")

        # 1. Grouped by time gaps
        segment_groups = self._group_by_time_gaps(
            segments, max_gap=RULE_SPLIT_GAP, check_large_gaps=True
        )
        logger.debug(f"Grouped by time gaps: {len(segment_groups)}")

        # 2. Split long sentences at common words
        common_result_groups = []
        for group in segment_groups:
            max_word_count = (
                self.max_word_count_cjk
                if is_mainly_cjk("".join(seg.text for seg in group))
                else self.max_word_count_english
            )
            if count_words("".join(seg.text for seg in group)) > max_word_count:
                split_groups = self._split_by_common_words(group)
                common_result_groups.extend(split_groups)
            else:
                common_result_groups.append(group)

        # 3. Split over-long segments
        result_segments = []
        for group in common_result_groups:
            result_segments.extend(self._split_long_segment(group))

        return result_segments

    def _group_by_time_gaps(
        self,
        segments: List[ASRDataSeg],
        max_gap: int = MAX_GAP,
        check_large_gaps: bool = False,
    ) -> List[List[ASRDataSeg]]:
        """Group segments by time gaps.

        Args:
            segments: segment list
            max_gap: largest allowed gap (ms)
            check_large_gaps: also cut at unusually large gaps

        Returns:
            List of groups
        """
        if not segments:
            return []

        result = []
        current_group = [segments[0]]
        recent_gaps = []

        for i in range(1, len(segments)):
            time_gap = segments[i].start_time - segments[i - 1].end_time

            # Unusually large gap?
            if check_large_gaps:
                recent_gaps.append(time_gap)
                if len(recent_gaps) > TIME_GAP_WINDOW_SIZE:
                    recent_gaps.pop(0)
                if len(recent_gaps) == TIME_GAP_WINDOW_SIZE:
                    avg_gap = sum(recent_gaps) / len(recent_gaps)
                    if (
                        time_gap > avg_gap * TIME_GAP_MULTIPLIER
                        and len(current_group) > MIN_GROUP_SIZE
                    ):
                        result.append(current_group)
                        current_group = []
                        recent_gaps = []

            # Start a new group past the largest gap
            if time_gap > max_gap:
                result.append(current_group)
                current_group = []
                recent_gaps = []

            current_group.append(segments[i])

        if current_group:
            result.append(current_group)

        return result

    def _split_by_common_words(
        self, segments: List[ASRDataSeg]
    ) -> List[List[ASRDataSeg]]:
        """Split at common connective words.

        Args:
            segments: ASR segment list

        Returns:
            List of groups
        """
        # Prefix words: split before them
        prefix_split_words = {
            # English
            "and",
            "or",
            "but",
            "if",
            "then",
            "because",
            "as",
            "until",
            "while",
            "what",
            "when",
            "where",
            "nor",
            "yet",
            "so",
            "for",
            "however",
            "moreover",
            # Chinese
            "和",
            "及",
            "与",
            "但",
            "而",
            "或",
            "因",
            "我",
            "你",
            "他",
            "她",
            "它",
            "咱",
            "您",
            "这",
            "那",
            "哪",
        }

        # Suffix words: split after them
        suffix_split_words = {
            # Punctuation
            ".",
            ",",
            "!",
            "?",
            "。",
            "，",
            "！",
            "？",
            # Chinese modal particles
            "的",
            "了",
            "着",
            "过",
            "吗",
            "呢",
            "吧",
            "啊",
            "呀",
            "嘛",
            "啦",
            # English pronouns
            "mine",
            "yours",
            "hers",
            "its",
            "ours",
            "theirs",
            "either",
            "neither",
        }

        result = []
        current_group = []

        for i, seg in enumerate(segments):
            max_word_count = (
                self.max_word_count_cjk
                if is_mainly_cjk(seg.text)
                else self.max_word_count_english
            )

            # Split at prefix words
            if any(
                seg.text.lower().startswith(word) for word in prefix_split_words
            ) and len(current_group) >= int(max_word_count * PREFIX_WORD_RATIO):
                result.append(current_group)
                logger.debug(f"Split before prefix word {seg.text} ")
                current_group = []

            # Split at suffix words
            if (
                i > 0
                and any(
                    segments[i - 1].text.lower().endswith(word)
                    for word in suffix_split_words
                )
                and len(current_group) >= int(max_word_count * SUFFIX_WORD_RATIO)
            ):
                result.append(current_group)
                logger.debug(f"Split after suffix word {segments[i - 1].text} ")
                current_group = []

            current_group.append(seg)

        if current_group:
            result.append(current_group)

        return result

    def _split_long_segment(self, segments: List[ASRDataSeg]) -> List[ASRDataSeg]:
        """Split over-long segments.

        Strategy: cut at the largest time gap.

        Args:
            segments: segment list

        Returns:
            Split segment list
        """
        result_segs = []
        segments_to_process = [segments]

        while segments_to_process:
            current_segments = segments_to_process.pop(0)

            if not current_segments:
                continue

            merged_text = "".join(seg.text for seg in current_segments)
            max_word_count = (
                self.max_word_count_cjk
                if is_mainly_cjk(merged_text)
                else self.max_word_count_english
            )
            n = len(current_segments)

            # Short enough, or nothing left to split
            if count_words(merged_text) <= max_word_count or n < RULE_MIN_SEGMENT_SIZE:
                merged_seg = ASRDataSeg(
                    merged_text.strip(),
                    current_segments[0].start_time,
                    current_segments[-1].end_time,
                )
                result_segs.append(merged_seg)
                continue

            # Look at the time gaps
            gaps = [
                current_segments[i + 1].start_time - current_segments[i].end_time
                for i in range(n - 1)
            ]
            all_equal = all(abs(gap - gaps[0]) < 1e-6 for gap in gaps)

            if all_equal:
                # Equal gaps: cut in the middle
                split_index = n // 2
            else:
                # Unequal gaps: cut at the largest one
                start_idx = max(n // 6, 1)
                end_idx = min((5 * n) // 6, n - 2)
                split_index = max(
                    range(start_idx, end_idx),
                    key=lambda i: current_segments[i + 1].start_time
                    - current_segments[i].end_time,
                    default=n // 2,
                )
                if split_index == 0 or split_index == n - 1:
                    split_index = n // 2

            # Cut and queue both halves
            first_segs = current_segments[: split_index + 1]
            second_segs = current_segments[split_index + 1 :]
            segments_to_process.extend([first_segs, second_segs])

        # Sort by time
        result_segs.sort(key=lambda seg: seg.start_time)
        return result_segs

    def _merge_processed_segments(
        self, processed_segments: List[List[ASRDataSeg]]
    ) -> List[ASRDataSeg]:
        """Merge all processed segments and sort them."""
        final_segments = []
        for segments in processed_segments:
            final_segments.extend(segments)

        final_segments.sort(key=lambda seg: seg.start_time)
        return final_segments

    def merge_short_segment(self, segments: List[ASRDataSeg]) -> None:
        """Deprecated: merge short segments.

        Merge conditions:
        1. Small time gap and few words
        2. The merged text stays under the word limit

        Args:
            segments: segment list (modified in place)
        """
        if not segments:
            return

        i = 0
        while i < len(segments) - 1:
            current_seg = segments[i]
            next_seg = segments[i + 1]

            time_gap = abs(next_seg.start_time - current_seg.end_time)
            current_words = count_words(current_seg.text)
            next_words = count_words(next_seg.text)
            total_words = current_words + next_words
            max_word_count = (
                self.max_word_count_cjk
                if is_mainly_cjk(current_seg.text)
                else self.max_word_count_english
            )

            # Merge?
            should_merge = (
                time_gap < MERGE_SHORT_GAP
                and (current_words < MERGE_MIN_WORDS or next_words < MERGE_MIN_WORDS)
                and total_words <= max_word_count
            ) or (
                time_gap < MERGE_VERY_SHORT_GAP
                and (
                    current_words < MERGE_VERY_SHORT_WORDS
                    or next_words < MERGE_VERY_SHORT_WORDS
                )
                and total_words <= max_word_count
            )

            if should_merge:
                logger.debug(
                    f"合并短Segments: {current_seg.text} + {next_seg.text} (间隔:{time_gap}ms)"
                )

                # Merge the text
                if is_mainly_cjk(current_seg.text):
                    current_seg.text += next_seg.text
                else:
                    current_seg.text += " " + next_seg.text
                current_seg.end_time = next_seg.end_time

                segments.pop(i + 1)
            else:
                i += 1

    def _merge_segments_based_on_sentences(
        self,
        segments: List[ASRDataSeg],
        sentences: List[str],
        max_unmatched: int = MATCH_MAX_UNMATCHED,
    ) -> List[ASRDataSeg]:
        """Merge ASR segments according to the sentences returned by the LLM.

        Sliding-window matching:
        1. For each LLM sentence, find the best matching run of ASR segments
        2. Match by text similarity
        3. Merge the matched segments

        Args:
            segments: ASR segment list
            sentences: sentences returned by the LLM
            max_unmatched: largest allowed number of unmatched sentences

        Returns:
            Merged segment list

        Raises:
            ValueError: when unmatched sentences exceed the threshold
        """

        def preprocess_text(s: str) -> str:
            """Normalize text: lowercase and collapse whitespace."""
            return " ".join(s.lower().split())

        asr_texts = [seg.text for seg in segments]
        asr_len = len(asr_texts)
        asr_index = 0
        threshold = MATCH_SIMILARITY_THRESHOLD
        max_shift = MATCH_MAX_SHIFT
        unmatched_count = 0

        new_segments = []

        for sentence in sentences:
            logger.debug("==========")
            logger.debug(f"Processing sentence: {sentence}")
            logger.debug("Next sentences: :" + "".join(asr_texts[asr_index : asr_index + 10]))

            sentence_proc = preprocess_text(sentence)
            word_count = count_words(sentence_proc)
            best_ratio = 0.0
            best_pos = None
            best_window_size = 0

            # Sliding window size
            max_window_size = min(word_count * 2, asr_len - asr_index)
            min_window_size = max(1, word_count // 2)
            window_sizes = sorted(
                range(min_window_size, max_window_size + 1),
                key=lambda x: abs(x - word_count),
            )

            # Sliding-window match
            for window_size in window_sizes:
                max_start = min(asr_index + max_shift + 1, asr_len - window_size + 1)
                for start in range(asr_index, max_start):
                    substr = "".join(asr_texts[start : start + window_size])
                    substr_proc = preprocess_text(substr)
                    ratio = difflib.SequenceMatcher(
                        None, sentence_proc, substr_proc
                    ).ratio()

                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_pos = start
                        best_window_size = window_size
                    if ratio == 1.0:
                        break
                if best_ratio == 1.0:
                    break

            # Apply the match
            if best_ratio >= threshold and best_pos is not None:
                start_seg_index = best_pos
                end_seg_index = best_pos + best_window_size - 1

                segs_to_merge = segments[start_seg_index : end_seg_index + 1]

                # Cut by time so no segment spans too long
                seg_groups = self._group_by_time_gaps(segs_to_merge, max_gap=MAX_GAP)

                for group in seg_groups:
                    merged_text = "".join(seg.text for seg in group)
                    merged_start_time = group[0].start_time
                    merged_end_time = group[-1].end_time
                    merged_seg = ASRDataSeg(
                        merged_text, merged_start_time, merged_end_time
                    )

                    logger.debug(f"Merged segments: {merged_seg.text}")

                    # Split over-long segments
                    split_segs = self._split_long_segment(group)
                    new_segments.extend(split_segs)

                max_shift = MATCH_MAX_SHIFT
                asr_index = end_seg_index + 1
            else:
                logger.warning(f"Cannot match sentence: {sentence}")
                unmatched_count += 1
                if unmatched_count > max_unmatched:
                    raise ValueError(f"Unmatched sentences exceeded threshold {max_unmatched},processing aborted")
                max_shift = MATCH_LARGE_SHIFT
                asr_index = min(asr_index + 1, asr_len - 1)

        return new_segments

    def stop(self):
        """Stop the splitter and release resources."""
        if not self.is_running:
            return
        self.is_running = False
        if hasattr(self, "executor") and self.executor is not None:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception as e:
                logger.error(f"Error closing thread pool:{str(e)}")
            finally:
                self.executor = None
