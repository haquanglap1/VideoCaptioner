"""Metadata survives real offline transforms and editor persistence."""

from copy import deepcopy

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.metadata import ASRAudioEvent, ASRMetadata
from videocaptioner.core.editor.adapters import cues_from_asr, project_to_asr
from videocaptioner.core.editor.commands import (
    CommandStack,
    EditCueSpeakerCommand,
    EditCueTextCommand,
    EditCueTimingCommand,
    SplitCueCommand,
)
from videocaptioner.core.editor.models import EditorProject
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.optimize.optimize import SubtitleOptimizer
from videocaptioner.core.split.split import SubtitleSplitter
from videocaptioner.core.subtitle import editing
from videocaptioner.core.translate.base import BaseTranslator
from videocaptioner.core.translate.types import TargetLanguage


def sample():
    a, b = ASRMetadata("soniox", "job-a", "1"), ASRMetadata("soniox", "job-a", "2")
    return ASRData([
        ASRDataSeg("王小明", 100, 500, metadata=a),
        ASRDataSeg("来了。", 500, 900, metadata=a),
        ASRDataSeg("你好！", 800, 1300, metadata=b),
        ASRDataSeg("好。", 1400, 1800, metadata=a),
    ], [ASRAudioEvent("(music)", 1900, 2000, ASRMetadata("soniox", "job-a"))])


def test_splitter_uses_only_measured_spans_and_keeps_all_text(monkeypatch):
    splitter = SubtitleSplitter(1, "unused")
    monkeypatch.setattr(splitter, "_process_segments", lambda *a: pytest.fail("fuzzy matching must not run"))
    try:
        result = splitter.split_subtitle(sample())
    finally:
        splitter.stop()
    assert [s.text for s in result] == ["王小明来了。", "你好！", "好。"]
    assert [(s.start_time, s.end_time) for s in result] == [(100, 900), (800, 1300), (1400, 1800)]
    assert result.events == sample().events
    with pytest.raises(ValueError, match="estimate"):
        result.split_to_word_segments()


@pytest.mark.parametrize("operation", ["range", "next", "table"])
def test_merge_does_not_cross_speaker_or_missing_metadata(operation):
    for metadata in (ASRMetadata("soniox", "job-a", "2"), ASRMetadata("soniox", "job-b", "1"), None):
        data = sample().with_segments([sample().segments[0], ASRDataSeg("好", 600, 800, metadata=metadata)])
        before = data.to_json()
        with pytest.raises(ValueError, match="Cannot merge"):
            if operation == "range":
                data.merge_segments(0, 1)
            elif operation == "next":
                data.merge_with_next_segment(0)
            else:
                editing.merge_rows(data.to_json(), [0, 1])
        assert data.to_json() == before


def test_same_speaker_merge_preserves_metadata_and_events():
    data = sample()
    data.merge_segments(0, 1)
    assert data.segments[0].text == "王小明来了。"
    assert data.segments[0].metadata == sample().segments[0].metadata
    data = ASRData.from_json(editing.merge_rows(sample().to_json(), [0, 1]))
    assert data.segments[0].speaker == sample().segments[0].speaker


def test_optimizer_single_source_requests_and_translation_input_metadata(monkeypatch):
    optimizer = SubtitleOptimizer(2, 10, "test-model", "")
    received = []
    def optimize(chunks):
        received.extend(chunks)
        return {k: v.replace("来了", "來了") for chunk in chunks for k, v in chunk.items()}
    monkeypatch.setattr(optimizer, "_parallel_optimize", optimize)
    data = sample()
    try:
        optimized = optimizer.optimize_subtitle(data)
    finally:
        optimizer.stop()
    assert all(len(chunk) == 1 for chunk in received)
    assert [s.metadata for s in optimized] == [s.metadata for s in data]
    assert optimized.events == data.events

    class Translator(BaseTranslator):
        def _prepare(self, items):
            assert [item.asr_metadata for item in items] == [s.metadata for s in data]

        def _translate_chunk(self, items):
            return [SubtitleProcessData(item.index, item.original_text, "Xin chào") for item in items]
    translator = Translator(2, 2, TargetLanguage.VIETNAMESE, None)
    try:
        translated = translator.translate_subtitle(optimized)
    finally:
        translator.stop()
    assert [s.metadata for s in translated] == [s.metadata for s in data]
    assert translated.events == data.events
    assert all(s.translated_text == "Xin chào" for s in translated)


def test_optimizer_refuses_unrecoverable_association(monkeypatch):
    optimizer = SubtitleOptimizer(1, 10, "test", "")
    monkeypatch.setattr(optimizer, "_parallel_optimize", lambda chunks: {"999": "other"})
    try:
        with pytest.raises(RuntimeError, match="association"):
            optimizer.optimize_subtitle(sample())
    finally:
        optimizer.stop()


def test_editor_import_overlap_save_load_speaker_override_undo(tmp_path):
    data = sample()
    handoff = editing.write_editor_handoff(data.to_json(), tmp_path, "handoff", "clip.mp4", events=data.events)
    assert handoff.suffix == ".json"
    store = EditorProjectStore()
    project = store.create_from_media(str(tmp_path / "clip.mp4"), str(handoff), duration_ms=3000)
    assert [c.speaker for c in project.cues] == [s.speaker for s in data]
    assert [c.id for c in project.cues] == [c.id for c in cues_from_asr(data)]
    assert project.audio_events == data.events
    stack = CommandStack()
    cue = project.cues[0]
    original = deepcopy(cue)
    stack.execute(EditCueSpeakerCommand(project, cue.id, "User label"))
    stack.execute(EditCueTextCommand(project, cue.id, "display_text", "王小明！"))
    stack.execute(EditCueTimingCommand(project, cue.id, 120, 520))
    assert project_to_asr(project).segments[0].metadata.speaker == "User label"
    project_file, subtitle = store.save(project, tmp_path / "review.vceditor.json")
    loaded = store.load(project_file)
    assert loaded.schema_version == "editor-project-v1"
    assert loaded.cues[0].speaker == "User label"
    assert loaded.cues[0].asr_metadata == cue.asr_metadata
    assert loaded.audio_events == data.events
    assert not list(tmp_path.glob("*.ass"))
    assert "User label" not in open(subtitle, encoding="utf-8").read()
    for _ in range(3):
        assert stack.undo()
    assert project.cues[0] == original
    for _ in range(3):
        assert stack.redo()
    assert project.cues[0].speaker == "User label"


def test_editor_refuses_native_split_without_explicit_text_boundary():
    project = EditorProject.empty(duration_ms=3000)
    project.cues = cues_from_asr(sample())
    before = project.to_dict()
    stack = CommandStack()
    with pytest.raises(ValueError, match="review"):
        stack.execute(SplitCueCommand(project, project.cues[0].id, 300))
    assert project.to_dict() == before and not stack.can_undo


def test_silence_event_json_roundtrip_without_fake_cue(tmp_path):
    data = ASRData([], sample().events)
    path = tmp_path / "events.json"
    data.save(str(path))
    loaded = ASRData.from_subtitle_file(str(path))
    assert not loaded.segments and loaded.events == data.events
    assert loaded.to_srt() == ""


def test_srt_explicitly_loses_metadata_json_preserves_it(tmp_path):
    data = sample()
    assert ASRData.from_json(data.to_json()).segments[0].speaker == data.segments[0].speaker
    assert ASRData.from_srt(data.to_srt()).segments[0].metadata is None


def test_unknown_speaker_roundtrip_keeps_provider_and_request_scope():
    metadata = ASRMetadata("scribe", "request", None)
    data = ASRData([ASRDataSeg("你好", 0, 100, metadata=metadata)])
    project = EditorProject.empty(duration_ms=1000)
    project.cues = cues_from_asr(data)
    result = project_to_asr(project)
    assert result.segments[0].metadata == metadata
    assert result.segments[0].speaker is None


def test_legacy_fuzzy_chunk_merge_cannot_drop_scoped_speakers():
    from videocaptioner.core.asr.chunk_merger import ChunkMerger
    with pytest.raises(ValueError, match="request-scoped"):
        ChunkMerger().merge_chunks([sample(), sample()], [0, 1000])
