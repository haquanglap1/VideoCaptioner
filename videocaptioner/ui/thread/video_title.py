"""Optional output naming runs in media workers, never on the Qt main thread."""

from videocaptioner.core.entities import DubbingTask, SynthesisTask
from videocaptioner.core.llm.rate_limit import LLMRateLimitError
from videocaptioner.core.translate.video_title import translated_output_path
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("video_title")


def prepare_video_title(task: DubbingTask | SynthesisTask, check, progress, reservations=None):
    settings = task.title_translation
    if settings is None or not task.output_path:
        return
    check()
    # A review/resume reuses this task's selected path instead of translating again.
    task.title_translation = None
    progress(1, "Đang dịch tiêu đề video...")

    def cancelled():
        try:
            check()
            return False
        except Exception:
            return True

    try:
        if reservations is None:
            task.output_path = translated_output_path(task.output_path, settings, cancelled)
        else:
            task.output_path = translated_output_path(task.output_path, settings, cancelled, reservations)
    except LLMRateLimitError:
        raise
    except Exception as exc:
        check()
        logger.warning("Title translation unavailable (%s); keeping the original output name", type(exc).__name__)
        progress(1, "Không dịch được tiêu đề; tiếp tục với tên gốc.")
