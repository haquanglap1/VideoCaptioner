"""Completed translations survive reruns but not source/language changes or damage."""

import json
import os
from dataclasses import replace
from threading import Lock

import pytest
from PyQt5.QtCore import QEventLoop, QThread, QTimer

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.entities import SubtitleConfig, SubtitleLayoutEnum, SubtitleTask
from videocaptioner.core.subtitle import reuse
from videocaptioner.core.subtitle.publication import SubtitleOutput, publish_subtitles
from videocaptioner.core.translate.dialogue import DialogueCue, DialogueDocument, SpeechBlock
from videocaptioner.core.translate.types import TargetLanguage
from videocaptioner.ui.thread.subtitle_thread import SubtitleThread


@pytest.fixture
def saved(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"synthetic-video")
    source = ASRData([ASRDataSeg("Original sentence.", 0, 2000, cue_id="one")])
    segment = source.segments[0].clone()
    segment.translated_text = "Câu đã dịch."
    translated = source.with_segments([segment])
    config = SubtitleConfig(need_translate=True, need_optimize=True, target_language=TargetLanguage.VIETNAMESE)
    original = tmp_path / "raw.srt"
    source.save(str(original))
    output = tmp_path / "translated.srt"
    translated.save(str(output), layout=config.subtitle_layout)
    identity = reuse.source_identity(source, str(video), config)
    reuse.save_completed(str(output), identity, reuse.CompletedSubtitles(translated))
    return source, translated, config, video, original, output, identity


def test_checkpoint_preserves_exact_translation_when_model_prompt_or_threads_change(saved):
    source, translated, config, video, _, output, identity = saved
    changed = replace(config, llm_model="new-model", custom_prompt_text="new prompt", thread_num=60,
                      batch_size=4, llm_request_timeout=300, subtitle_layout=SubtitleLayoutEnum.ONLY_TRANSLATE)
    assert reuse.source_identity(source, str(video), changed) == identity
    result = reuse.load_completed(str(output), identity)
    assert result and result.data.to_document() == translated.to_document()


@pytest.mark.parametrize("change", ["text", "timing", "video", "language", "dialogue"])
def test_source_or_target_changes_invalidate_result(saved, change):
    source, _, config, video, _, output, identity = saved
    if change == "text":
        source.segments[0].text += " Added."
    elif change == "timing":
        source.segments[0].end_time += 1
    elif change == "video":
        video.write_bytes(b"changed-video")
    elif change == "language":
        config.target_language = TargetLanguage.ENGLISH
    else:
        config.dialogue_translation = True
    updated = reuse.source_identity(source, str(video), config)
    assert updated != identity and reuse.load_completed(str(output), updated) is None


@pytest.mark.parametrize("damage", ["json", "body", "display", "missing", "foreign-path"])
def test_damaged_or_incomplete_result_is_not_reused(saved, damage):
    _, _, _, _, _, output, identity = saved
    checkpoint = reuse.checkpoint_path(str(output))
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    if damage == "json":
        checkpoint.write_text("incomplete", encoding="utf-8")
    elif damage == "body":
        payload["result"]["data"]["1"]["translated_subtitle"] = ""
        checkpoint.write_text(json.dumps(payload), encoding="utf-8")
    elif damage == "display":
        output.write_text("edited", encoding="utf-8")
    elif damage == "missing":
        output.unlink()
    else:
        payload["files"]["../outside.srt"] = "foreign"
        checkpoint.write_text(json.dumps(payload), encoding="utf-8")
    assert reuse.load_completed(str(output), identity) is None


def test_cancel_during_checkpoint_staging_keeps_previous_checkpoint(saved, monkeypatch):
    _, data, _, _, _, output, identity = saved
    path = reuse.checkpoint_path(str(output))
    before = path.read_bytes()
    def cancel(*_, **__):
        raise RuntimeError("cancelled")
    monkeypatch.setattr(reuse.json, "dump", cancel)
    with pytest.raises(RuntimeError, match="cancelled"):
        reuse.save_completed(str(output), identity, reuse.CompletedSubtitles(data))
    assert path.read_bytes() == before
    assert sorted(p.name for p in output.parent.glob('*.json')) == [path.name]


def run_worker(task, qapp):
    worker = SubtitleThread(task)
    errors, finished, messages = [], [], []
    worker.error.connect(errors.append)
    worker.finished.connect(lambda *args: finished.append(args))
    worker.progress.connect(lambda _, message: messages.append(message))
    loop = QEventLoop()
    QThread.finished.__get__(worker).connect(loop.quit)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(worker.stop)
    timer.start(5000)
    worker.start()
    loop.exec_()
    worker.wait()
    timer.stop()
    return errors, finished, messages


def test_worker_reuses_before_llm_validation_and_republishes_layout(saved, qapp, monkeypatch):
    source, _, config, video, original, output, _ = saved
    config.subtitle_layout = SubtitleLayoutEnum.ONLY_TRANSLATE
    config.api_key = None
    monkeypatch.setattr(SubtitleThread, "_process_subtitles", lambda *args: pytest.fail("Existing result must skip all LLM stages"))
    task = SubtitleTask(subtitle_path=str(original), output_path=str(output), video_path=str(video),
                        subtitle_config=config, asr_data=source, need_next_task=False)
    errors, finished, messages = run_worker(task, qapp)
    assert not errors and finished and any("Dùng lại" in message for message in messages)
    assert task.asr_data.segments[0].translated_text == "Câu đã dịch."
    assert "Original sentence" not in output.read_text(encoding="utf-8")


def test_forced_retranslation_bypasses_completed_result(saved, qapp, monkeypatch):
    source, data, config, _, original, output, _ = saved
    config.reuse_translation = False
    calls = []
    def process(*_):
        calls.append(True)
        segment = data.segments[0].clone()
        segment.translated_text = "Bản dịch mới."
        return data.with_segments([segment])
    monkeypatch.setattr(SubtitleThread, "_process_subtitles", process)
    task = SubtitleTask(subtitle_path=str(original), output_path=str(output), subtitle_config=config,
                        asr_data=source, need_next_task=False)
    errors, finished, _ = run_worker(task, qapp)
    assert calls == [True] and not errors and finished
    assert "Bản dịch mới" in output.read_text(encoding="utf-8")


def test_reprocessing_the_completed_table_retains_the_original_source_binding(saved, qapp, monkeypatch):
    source, data, config, video, original, output, identity = saved
    processed = reuse.source_identity(data, str(video), config)
    reuse.save_completed(str(output), identity, reuse.CompletedSubtitles(data), processed_identity=processed)
    monkeypatch.setattr(SubtitleThread, "_process_subtitles", lambda *args: pytest.fail("Completed table must not be translated again"))
    task = SubtitleTask(subtitle_path=str(original), output_path=str(output), video_path=str(video),
                        subtitle_config=config, asr_data=data, need_next_task=False)
    errors, finished, _ = run_worker(task, qapp)
    assert not errors and finished
    assert reuse.load_completed(str(output), reuse.source_identity(source, str(video), config)) is not None


def test_legacy_dialogue_pair_reused_without_creating_duplicate_dialogue(tmp_path, qapp, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"synthetic")
    original = tmp_path / "raw.srt"
    source = ASRData([ASRDataSeg("Original.", 0, 2000, cue_id="one")])
    source.save(str(original))
    output = tmp_path / "translated [video-id].srt"
    document = DialogueDocument((DialogueCue("one", "Original.", "Bản dịch cũ.", 0, 2000),),
                                (SpeechBlock(("one",), "Lời đọc cũ."),), TargetLanguage.VIETNAMESE.value)
    dialogue_path = output.with_name(output.stem + ".dialogue-2.json")
    data = document.subtitle_data()
    config = SubtitleConfig(need_translate=True, dialogue_translation=True, target_language=TargetLanguage.VIETNAMESE)
    assert publish_subtitles(data, [SubtitleOutput(str(output), config.subtitle_layout)], lambda: False,
                             Lock(), dialogue=(document, dialogue_path))
    monkeypatch.setattr(SubtitleThread, "_process_subtitles", lambda *args: pytest.fail("Legacy pair should be reused"))
    task = SubtitleTask(subtitle_path=str(original), output_path=str(output), video_path=str(video),
                        subtitle_config=config, asr_data=source, need_next_task=False)
    before = dialogue_path.read_bytes()
    errors, finished, _ = run_worker(task, qapp)
    assert not errors and finished and task.dubbing_subtitle_path == str(dialogue_path)
    assert dialogue_path.read_bytes() == before
    assert len(list(tmp_path.glob('*.dialogue*.json'))) == 1
    assert reuse.checkpoint_path(str(output)).exists()


def test_legacy_pair_rejects_replaced_video_or_wrong_language(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"synthetic")
    data = ASRData([ASRDataSeg("Original.", 0, 1000, translated_text="Đã dịch.", cue_id="one")])
    output = tmp_path / "out.srt"
    doc = DialogueDocument((DialogueCue("one", "Original.", "Đã dịch.", 0, 1000),),
                           (SpeechBlock(("one",), "Đã dịch."),), TargetLanguage.VIETNAMESE.value)
    doc.save(output.with_suffix('.dialogue.json'))
    data.save(str(output))
    config = SubtitleConfig(need_translate=True, dialogue_translation=True, target_language=TargetLanguage.ENGLISH)
    assert reuse.load_existing_dialogue(str(output), str(video), data, config) is None
    config.target_language = TargetLanguage.VIETNAMESE
    os.utime(video, (video.stat().st_atime, output.stat().st_mtime + 60))
    assert reuse.load_existing_dialogue(str(output), str(video), data, config) is None


def test_explicit_selected_row_retranslation_disables_chunk_reuse():
    from videocaptioner.core.entities import TranslatorServiceEnum
    from videocaptioner.ui.thread.subtitle_thread import (
        RetranslateThread,
        create_translator_from_config,
    )
    config = SubtitleConfig(need_translate=True, reuse_translation=True,
                            translator_service=TranslatorServiceEnum.OPENAI, target_language=TargetLanguage.VIETNAMESE)
    worker = RetranslateThread({}, config)
    assert not worker.subtitle_config.reuse_translation and config.reuse_translation
    translator = create_translator_from_config(worker.subtitle_config)
    try:
        assert not translator.reuse_cached_chunks
    finally:
        translator.close()
