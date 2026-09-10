"""Sentence punctuation must survive the subtitle pipeline's TTS handoff."""
from pathlib import Path

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import (
    SubtitleConfig,
    SubtitleLayoutEnum,
    SubtitleTask,
    TranslatorServiceEnum,
)
from videocaptioner.core.translate.types import TargetLanguage
from videocaptioner.ui.thread.subtitle_thread import SubtitleThread


def test_explicit_sentence_segmentation_requires_llm_configuration():
    source = ASRData([ASRDataSeg("Nếu trời mưa, chúng ta sẽ ở nhà.", 0, 4000)])
    config = SubtitleConfig(need_split=True, need_optimize=False, need_translate=False)
    worker = SubtitleThread(SubtitleTask(subtitle_config=config))
    assert worker.need_llm(config, source)
    worker.wait()


def test_gui_translation_preserves_sentence_marks_in_tts_artifact(tmp_path, qapp, monkeypatch):
    source = ASRData([ASRDataSeg("请等一下。", 0, 1600), ASRDataSeg("然后继续。", 1800, 3300)])
    path = tmp_path / "source.srt"
    source.save(str(path))

    class Translator:
        def translate_subtitle(self, data):
            result = data.with_segments([s.clone() for s in data])
            for seg, text in zip(result, ["请稍候，别着急。", "现在可以继续了。"]):
                seg.translated_text = text
            return result

        def close(self):
            pass

        stop = close

    monkeypatch.setattr("videocaptioner.ui.thread.subtitle_thread.create_translator_from_config",
                        lambda *args: Translator())
    task = SubtitleTask(subtitle_path=str(path), output_path=str(tmp_path / "out.srt"),
                        video_path=str(tmp_path / "clip.mp4"), need_next_task=True, asr_data=source,
                        subtitle_config=SubtitleConfig(need_split=False, need_optimize=False, need_translate=True,
                            api_key="synthetic", base_url="https://translation.invalid/v1", llm_model="offline-test",
                            translator_service=TranslatorServiceEnum.OPENAI, target_language=TargetLanguage.SIMPLIFIED_CHINESE,
                            subtitle_layout=SubtitleLayoutEnum.ONLY_TRANSLATE))
    errors = []
    worker = SubtitleThread(task)
    worker.error.connect(errors.append)
    worker.run()
    worker.wait()
    assert not errors
    spoken = Path(task.dubbing_subtitle_path or "").read_text(encoding="utf-8")
    assert "请稍候，别着急。" in spoken and "现在可以继续了。" in spoken
    assert task.asr_data is not None
    assert [s.text for s in task.asr_data] == ["请等一下。", "然后继续。"]
