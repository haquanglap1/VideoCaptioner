from copy import deepcopy
from pathlib import Path
from threading import Event, Lock
from typing import List

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.entities import (
    SubtitleConfig,
    SubtitleLayoutEnum,
    SubtitleProcessData,
    SubtitleTask,
    TranslatorServiceEnum,
)
from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.llm.context import (
    clear_task_context,
    generate_task_id,
    set_task_context,
    update_stage,
)
from videocaptioner.core.llm.owned_request import OwnedLLMRequest
from videocaptioner.core.optimize.optimize import SubtitleOptimizer
from videocaptioner.core.split.split import SubtitleSplitter
from videocaptioner.core.subtitle.publication import SubtitleOutput, publish_subtitles
from videocaptioner.core.translate.factory import TranslatorFactory
from videocaptioner.core.translate.types import TranslatorType
from videocaptioner.core.utils.logger import setup_logger

SERVICE_TO_TYPE = {
    TranslatorServiceEnum.OPENAI: TranslatorType.OPENAI,
    TranslatorServiceEnum.GOOGLE: TranslatorType.GOOGLE,
    TranslatorServiceEnum.BING: TranslatorType.BING,
    TranslatorServiceEnum.DEEPLX: TranslatorType.DEEPLX,
}

logger = setup_logger("subtitle_optimization_thread")


def create_translator_from_config(
    config: SubtitleConfig,
    custom_prompt: str = "",
    callback=None,
):
    """Build a translator from a SubtitleConfig."""
    translator_service = config.translator_service
    if translator_service not in SERVICE_TO_TYPE:
        raise ValueError(f"不支持的翻译服务: {translator_service}")

    return TranslatorFactory.create_translator(
        translator_type=SERVICE_TO_TYPE[translator_service],
        thread_num=config.thread_num,
        batch_num=config.batch_size,
        target_language=config.target_language,
        model=config.llm_model or "",
        custom_prompt=custom_prompt,
        is_reflect=config.need_reflect,
        update_callback=callback,
        deeplx_endpoint=config.deeplx_endpoint or "",
        request_timeout=config.llm_request_timeout,
        credentials=LLMCredentials(config.api_key or "", config.base_url or ""),
    )


class SubtitleThread(QThread):
    finished = pyqtSignal(str, str)
    progress = pyqtSignal(int, str)
    update = pyqtSignal(dict)
    update_all = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, task: SubtitleTask):
        super().__init__()
        self.source_task = task
        self.task: SubtitleTask = deepcopy(task)
        self._cancel = Event()
        self._publication_lock = Lock()
        self._active_thread = None
        self.subtitle_length = 0
        self.finished_subtitle_length = 0
        self.custom_prompt_text = ""
        self.optimizer = None
        self.translator = None
        self.splitter = None

    def set_custom_prompt_text(self, text: str):
        self.custom_prompt_text = text

    def _setup_llm_config(self) -> SubtitleConfig:
        """Validate the captured settings; the actual job request checks the service."""
        config = self.task.subtitle_config
        if not config:
            raise Exception(self.tr("LLM API 未配置, 请检查LLM配置"))
        if config.base_url and config.api_key and config.llm_model:
            return config
        else:
            raise Exception(self.tr("LLM API 未配置, 请检查LLM配置"))

    def run(self):
        self._active_thread = QThread.currentThread()
        # Task context for logs
        task_file = (
            Path(self.task.video_path) if self.task.video_path else Path(self.task.subtitle_path)
        )
        set_task_context(
            task_id=self.task.task_id,
            file_name=task_file.name,
            stage="subtitle",
        )

        try:
            if self.cancelled():
                return
            outputs = []
            logger.info(f"\n{self.task.subtitle_config.print_config()}")

            # The subtitle path is required from here on
            subtitle_path = self.task.subtitle_path
            assert subtitle_path is not None, self.tr("字幕文件路径为空")

            subtitle_config = self.task.subtitle_config
            assert subtitle_config is not None, self.tr("字幕配置为空")
            request = OwnedLLMRequest(LLMCredentials(subtitle_config.api_key or "", subtitle_config.base_url or ""),
                                      subtitle_config.llm_request_timeout, self.cancelled)

            asr_data = self.task.asr_data if self.task.asr_data is not None else ASRData.from_subtitle_file(subtitle_path)

            # Verify the LLM configuration
            if self.need_llm(subtitle_config, asr_data):
                self.progress.emit(2, self.tr("开始验证 LLM 配置..."))
                subtitle_config = self._setup_llm_config()

            # 2. Re-segment word-level subtitles into sentences
            if asr_data.is_word_timestamp() or subtitle_config.need_split:
                update_stage("split")
                self.progress.emit(5, self.tr("字幕断句..."))
                logger.info("正在字幕断句...")
                splitter = SubtitleSplitter(
                    thread_num=subtitle_config.thread_num,
                    model=subtitle_config.llm_model,
                    max_word_count_cjk=subtitle_config.max_word_count_cjk,
                    max_word_count_english=subtitle_config.max_word_count_english,
                    request=request,
                )
                self.splitter = splitter
                asr_data = splitter.split_subtitle(asr_data)
                if self.cancelled():
                    return

            # 3. Optimize subtitles
            # Only minimal filename context, never an absolute local path.
            context_info = f'The subtitles below are from a file named "{task_file.name}". Use this context to improve accuracy if needed.\n'
            custom_prompt = context_info + (subtitle_config.custom_prompt_text or "") + "\n"
            self.task.asr_data = asr_data
            self.subtitle_length = len(asr_data.segments)

            if subtitle_config.need_optimize:
                update_stage("optimize")
                self.progress.emit(0, self.tr("优化字幕..."))
                logger.info("正在优化字幕...")
                self.finished_subtitle_length = 0
                if not subtitle_config.llm_model:
                    raise Exception(self.tr("LLM 模型未配置"))
                optimizer = SubtitleOptimizer(
                    thread_num=subtitle_config.thread_num,
                    batch_num=subtitle_config.batch_size,
                    model=subtitle_config.llm_model,
                    custom_prompt=custom_prompt or "",
                    update_callback=self.callback,
                    request=request,
                )
                self.optimizer = optimizer
                asr_data = optimizer.optimize_subtitle(asr_data)

            # 4. Translate subtitles
            if self.cancelled():
                return
            if subtitle_config.need_translate:
                update_stage("translate")
                if (
                    subtitle_config.translator_service == TranslatorServiceEnum.OPENAI
                    and subtitle_config.need_reflect
                ):
                    self.progress.emit(
                        0, self.tr("翻译字幕（反思模式，质量更高但更慢）...")
                    )
                else:
                    self.progress.emit(0, self.tr("翻译字幕..."))
                logger.info("正在翻译字幕...")
                self.finished_subtitle_length = 0

                if not subtitle_config.target_language:
                    raise Exception(self.tr("目标语言未配置"))

                translator = create_translator_from_config(
                    subtitle_config, custom_prompt, self.callback
                )

                self.translator = translator
                if self.cancelled():
                    return
                asr_data = translator.translate_subtitle(asr_data)
                if self.cancelled():
                    return

                # Save the translation (monolingual and bilingual layouts)
                if self.task.need_next_task and self.task.video_path:
                    for layout in SubtitleLayoutEnum:
                        save_path = str(
                            Path(self.task.subtitle_path).parent
                            / f"{Path(self.task.video_path).stem}-{layout.value}.srt"
                        )
                        outputs.append(SubtitleOutput(save_path, layout, subtitle_config.subtitle_style or ""))

            # 5. Save subtitles
            if self.cancelled():
                return
            if self.task.need_next_task and self.task.video_path:
                dubbing_path = (
                    Path(self.task.output_path or self.task.subtitle_path).parent
                    / f"{Path(self.task.video_path).stem}-dubbing-target.srt"
                )
                outputs.append(SubtitleOutput(str(dubbing_path), SubtitleLayoutEnum.ONLY_TRANSLATE))
                self.task.dubbing_subtitle_path = str(dubbing_path)
                logger.info("Dubbing target subtitle saved to: %s", dubbing_path)

            self.task.asr_data = asr_data
            outputs.append(SubtitleOutput(self.task.output_path or "",
                                           subtitle_config.subtitle_layout or SubtitleLayoutEnum.ONLY_TRANSLATE,
                                           subtitle_config.subtitle_style or ""))

            # 6. Move files and clean up
            if self.task.need_next_task and self.task.video_path:
                # Full pipeline persists SRT only. ASS remains an explicit
                # export choice in SubtitleInterface's Save menu.
                save_srt_path = (
                    Path(self.task.video_path).parent / f"{Path(self.task.video_path).stem}.srt"
                )
                outputs.append(SubtitleOutput(str(save_srt_path), subtitle_config.subtitle_layout))

            if not publish_subtitles(asr_data, outputs, self.cancelled, self._publication_lock):
                return

            self.progress.emit(100, self.tr("优化完成"))
            logger.info("优化完成")
            self.source_task.asr_data = asr_data
            self.source_task.dubbing_subtitle_path = self.task.dubbing_subtitle_path
            self.update_all.emit(asr_data.to_json())
            self.finished.emit(self.task.video_path, self.task.output_path)

        except Exception as e:
            if self.cancelled():
                return
            logger.exception(f"字幕处理失败: {str(e)}")
            self.error.emit(str(e))
            self.progress.emit(100, self.tr("字幕处理失败"))
        finally:
            for component in (self.translator, self.optimizer, self.splitter):
                if component is not None:
                    getattr(component, "close", component.stop)()
            clear_task_context()

    def need_llm(self, subtitle_config: SubtitleConfig, asr_data: ASRData):
        return (
            subtitle_config.need_optimize
            or ((subtitle_config.need_split or asr_data.is_word_timestamp()) and not asr_data.has_metadata)
            or (
                subtitle_config.need_translate
                and subtitle_config.translator_service
                not in [
                    TranslatorServiceEnum.DEEPLX,
                    TranslatorServiceEnum.BING,
                    TranslatorServiceEnum.GOOGLE,
                ]
            )
        )

    def callback(self, result: List[SubtitleProcessData]):
        if self.cancelled():
            raise RuntimeError("Subtitle processing cancelled.")
        self.finished_subtitle_length += len(result)
        # Rough progress estimate (0-100%)
        progress = min(int((self.finished_subtitle_length / max(self.subtitle_length, 1)) * 100), 100)
        self.progress.emit(progress, self.tr("{0}% 处理字幕").format(progress))
        # Publish table text only after the whole job succeeds.

    def stop(self):
        """Request cancellation; the worker joins its pools in finally."""
        with self._publication_lock:
            self._cancel.set()
        self.requestInterruption()
        for component in (self.translator, self.optimizer, self.splitter):
            if component is not None:
                component.stop()

    def cancelled(self):
        return self._cancel.is_set() or self.isInterruptionRequested() or bool(
            self._active_thread and self._active_thread.isInterruptionRequested())


class RetranslateThread(QThread):
    """Lightweight worker that re-translates the selected rows."""

    finished = pyqtSignal(dict)  # {key: translated_text}
    progress = pyqtSignal(int, str)  # (percent, status text)
    error = pyqtSignal(str)

    def __init__(self, selected_data: dict, subtitle_config: SubtitleConfig, file_name: str = "",
                 *, context_data: ASRData | None = None):
        """
        selected_data: selected entries from model._data, keyed by row number string
        subtitle_config: current task configuration
        file_name: file name for the log context
        """
        super().__init__()
        self.selected_data = deepcopy(selected_data)
        self.context_data = deepcopy(context_data)
        self.subtitle_config = deepcopy(subtitle_config)
        self.translator = None
        self.file_name = file_name
        self.total = len(selected_data)
        self.done = 0
        self._cancel = Event()

    def _callback(self, result: List[SubtitleProcessData]):
        if self._cancel.is_set():
            raise RuntimeError("Translation cancelled.")
        self.done += len(result)
        pct = min(int(self.done / self.total * 100), 100)
        self.progress.emit(pct, self.tr("{0}% 翻译中").format(pct))

    def run(self):
        set_task_context(
            task_id=generate_task_id(),
            file_name=self.file_name,
            stage="translate",
        )
        try:
            if self._cancel.is_set():
                return
            config = self.subtitle_config
            if not config.target_language:
                raise Exception("目标语言未配置")

            # The translator receives credentials directly from this job snapshot.
            if config.translator_service == TranslatorServiceEnum.OPENAI:
                if not (config.base_url and config.api_key and config.llm_model):
                    raise Exception("LLM API 未配置，请检查 LLM 配置")

            # ASRData containing only the selected rows
            asr_data = ASRData.from_json(self.selected_data)

            # Build the translator and translate
            translator = create_translator_from_config(config, callback=self._callback)
            self.translator = translator
            if self._cancel.is_set() or self.isInterruptionRequested():
                return
            if self.context_data is not None:
                asr_data.conversation_context = self.context_data.conversation_context
                asr_data = translator.translate_subtitle(asr_data, context_data=self.context_data)
            else:
                asr_data = translator.translate_subtitle(asr_data)

            # Map {original row number: translated_text}
            by_id = {seg.cue_id: seg.translated_text for seg in asr_data}
            selected = ASRData.from_json(self.selected_data).to_json()
            # Original row numbers may be nonconsecutive or ordered differently from time.
            ids = {key: value.get("cue_id") for key, value in self.selected_data.items()}
            if not all(ids.values()):
                ids = {key: value["cue_id"] for key, value in zip(sorted(ids, key=int), selected.values())}
            result = {key: by_id[cue_id] for key, cue_id in ids.items()}
            if not self._cancel.is_set() and not self.isInterruptionRequested():
                self.finished.emit(result)

        except Exception as e:
            if self._cancel.is_set():
                return
            logger.exception(f"重新翻译失败: {e}")
            self.error.emit(str(e))
        finally:
            if self.translator is not None:
                getattr(self.translator, "close", self.translator.stop)()
            clear_task_context()

    def stop(self):
        self._cancel.set()
        self.requestInterruption()
        if self.translator is not None:
            self.translator.stop()
