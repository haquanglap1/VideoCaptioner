"""Spoken translation must preserve source ownership through cache and export."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.translate.dialogue import DialogueCue, DialogueDocument, SpeechBlock
from videocaptioner.core.translate.dialogue_translator import DialogueTranslator
from videocaptioner.core.translate.types import TargetLanguage


def source():
    return ASRData([
        ASRDataSeg("Nếu ngày mai trời mưa,", 0, 1500, cue_id="synthetic-1"),
        ASRDataSeg("chúng ta sẽ ở nhà.", 1500, 3200, cue_id="synthetic-2"),
        ASRDataSeg("Không, không được đi.", 3500, 5000, cue_id="synthetic-3"),
    ])


def payload():
    return {"subtitle_translations": {"synthetic-1": "Nếu mai trời mưa,", "synthetic-2": "mình sẽ ở nhà.",
                                      "synthetic-3": "Không, không được đi."},
            "speech_blocks": [{"cue_ids": ["synthetic-1", "synthetic-2"], "text": "Nếu mai trời mưa, mình sẽ ở nhà."},
                              {"cue_ids": ["synthetic-3"], "text": "Không, không được đi."}]}


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value, expire=None):
        self.values[key] = value


@pytest.fixture
def translator(monkeypatch):
    cache = MemoryCache()
    monkeypatch.setattr("videocaptioner.core.translate.base.get_translate_cache", lambda: cache)
    engine = DialogueTranslator(1, 10, TargetLanguage.VIETNAMESE, "synthetic", "", False, None,
                               credentials=LLMCredentials("synthetic-key", "https://synthetic.invalid/v1"))
    try:
        yield engine
    finally:
        engine.close()


def respond(engine, monkeypatch, value):
    calls = []
    def request(messages):
        calls.append(messages)
        wire = json.loads(json.dumps(value))
        translations = wire.get("subtitle_translations", {})
        wire["subtitle_translations"] = {engine._wire_ids.get(cid, cid): text for cid, text in translations.items()}
        if isinstance(wire.get("speech_blocks"), list):
            for block in wire["speech_blocks"]:
                block["cue_ids"] = [engine._wire_ids.get(cid, cid) for cid in block["cue_ids"]]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(wire)))])
    monkeypatch.setattr(engine, "_request", request)
    return calls


def test_empty_source_never_requests_llm_or_publishes_dialogue(translator, monkeypatch):
    calls = respond(translator, monkeypatch, payload())
    with pytest.raises(RuntimeError, match="phụ đề nguồn rỗng"):
        translator.translate_subtitle(ASRData([]))
    assert calls == [] and translator.dialogue_document is None
    assert translator._cache.values == {}


def test_spoken_groups_roundtrip_preserve_source_and_display_timing(translator, monkeypatch, tmp_path):
    data = source()
    original = data.to_document()
    calls = respond(translator, monkeypatch, payload())
    result = translator.translate_subtitle(data)
    document = translator.dialogue_document
    assert document is not None
    assert data.to_document() == original
    assert [(s.cue_id, s.start_time, s.end_time) for s in result] == [(s.cue_id, s.start_time, s.end_time) for s in data]
    assert document.blocks[0].cue_ids == ("synthetic-1", "synthetic-2")
    assert document.blocks[1].text == "Không, không được đi."
    path = tmp_path / "spoken.json"
    document.save(path)
    assert DialogueDocument.load(path) == document
    with pytest.raises(FileExistsError):
        document.save(path)
    translator.translate_subtitle(data)
    assert len(calls) == 1
    assert translator.dialogue_document == document
    owned = json.loads(calls[0][1]["content"])["owned_cues"]
    assert [c["id"] for c in owned] == ["c1", "c2", "c3"]
    assert [c["text"] for c in owned] == [s.text for s in data]


@pytest.mark.parametrize("failure", ["missing", "duplicate", "reverse", "extra", "blank", "foreign", "shape"])
def test_invalid_llm_response_is_not_cached_or_published(translator, monkeypatch, failure):
    value = payload()
    if failure == "missing":
        value["speech_blocks"].pop()
    elif failure == "duplicate":
        value["speech_blocks"][1]["cue_ids"] = ["synthetic-2", "synthetic-3"]
    elif failure == "reverse":
        value["speech_blocks"].reverse()
    elif failure == "extra":
        value["subtitle_translations"]["context-99"] = "Extra."
    elif failure == "blank":
        value["speech_blocks"][0]["text"] = " "
    elif failure == "foreign":
        value["speech_blocks"][0]["cue_ids"] = ["context-99", "synthetic-2"]
    else:
        value["speech_blocks"] = "bad"
    calls = respond(translator, monkeypatch, value)
    with pytest.raises(RuntimeError, match="Malformed dialogue"):
        translator.translate_subtitle(source())
    assert len(calls) == 3
    assert not translator._cache.values
    assert translator.dialogue_document is None


@pytest.mark.parametrize("change", ["speaker", "scene", "silence", "overlap", "span"])
def test_document_rejects_groups_across_hard_boundaries(change):
    first = DialogueCue("a", "A", "A", 0, 1000)
    second = DialogueCue("b", "B", "B", 1000, 2000)
    if change == "speaker":
        second = replace(second, speaker="another")
    elif change == "scene":
        second = replace(second, scene="next")
    elif change == "silence":
        second = replace(second, start_ms=2200, end_ms=3000)
    elif change == "overlap":
        second = replace(second, start_ms=900)
    else:
        second = replace(second, end_ms=13000)
    with pytest.raises(ValueError):
        DialogueDocument((first, second), (SpeechBlock(("a", "b"), "A B"),), "vi").validate()


def test_editing_source_invalidates_saved_dialogue(translator, monkeypatch):
    respond(translator, monkeypatch, payload())
    translator.translate_subtitle(source())
    data = translator.dialogue_document.to_dict()
    data["cues"][0]["source_text"] = "Changed source"
    with pytest.raises(ValueError, match="fingerprint"):
        DialogueDocument.from_dict(data)


def test_long_source_subject_and_predicate_can_stay_together_without_unbounded_groups():
    first = DialogueCue("a", "Tổng số cây trong khu vườn", "Tổng số cây trong khu vườn", 0, 5320)
    second = DialogueCue("b", "là ba mươi cây.", "là ba mươi cây.", 5320, 9664)
    block = SpeechBlock(("a", "b"), "Tổng số cây trong khu vườn là ba mươi cây.")
    DialogueDocument((first, second), (block,), "vi").validate()
    with pytest.raises(ValueError, match="8 seconds"):
        DialogueDocument((replace(first, source_text="Một câu đã hoàn chỉnh."), second), (block,), "vi").validate()


def test_context_is_read_only_and_cache_tracks_prompt(translator, monkeypatch):
    data = source()
    selected = data.with_segments([data.segments[1].clone()])
    value = {"subtitle_translations": {"synthetic-2": "mình sẽ ở nhà."},
             "speech_blocks": [{"cue_ids": ["synthetic-2"], "text": "mình sẽ ở nhà."}]}
    calls = respond(translator, monkeypatch, value)
    translator.translate_subtitle(selected, context_data=data)
    assert translator.dialogue_document.blocks[0].cue_ids == ("synthetic-2",)
    request = json.loads(calls[0][1]["content"])
    assert len(request["owned_cues"]) == 1
    assert request["owned_cues"][0]["id"] == "c2"
    assert request["context_read_only"]["source_window"][0]["id"] == "c1"
    translator.custom_prompt = "Giữ nguyên các thuật ngữ."
    translator.translate_subtitle(selected, context_data=data)
    assert len(calls) == 2


def test_oversized_blocks_use_complete_display_cues_without_extra_network_repairs(translator, monkeypatch):
    data = source()
    data.segments[1].end_time = 13000
    data.segments[2].start_time, data.segments[2].end_time = 13200, 15000
    before = data.to_document()
    value = payload()
    calls = respond(translator, monkeypatch, value)
    translator.translate_subtitle(data)
    blocks = translator.dialogue_document.blocks
    assert len(calls) == 1
    assert blocks == (SpeechBlock(("synthetic-1",), value["subtitle_translations"]["synthetic-1"]),
                      SpeechBlock(("synthetic-2",), value["subtitle_translations"]["synthetic-2"]),
                      SpeechBlock(("synthetic-3",), value["speech_blocks"][1]["text"]))
    assert data.to_document() == before
    translator.translate_subtitle(data)
    assert len(calls) == 1


def test_timing_repair_cannot_hide_a_second_invalid_block(translator, monkeypatch):
    data = source()
    data.segments[1].end_time = 13000
    data.segments[2].start_time, data.segments[2].end_time = 13200, 15000
    value = payload()
    value["speech_blocks"][1]["text"] = ""
    respond(translator, monkeypatch, value)
    with pytest.raises(RuntimeError, match="Malformed dialogue"):
        translator.translate_subtitle(data)
    assert not translator._cache.values


def test_cancel_keeps_source_and_does_not_cache(translator, monkeypatch):
    def request(messages):
        translator.stop()
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload())))])
    monkeypatch.setattr(translator, "_request", request)
    data = source()
    before = data.to_document()
    with pytest.raises(RuntimeError, match="cancelled"):
        translator.translate_subtitle(data)
    assert data.to_document() == before and not translator._cache.values


def test_explicit_retranslation_bypasses_chunk_cache(translator, monkeypatch):
    calls = respond(translator, monkeypatch, payload())
    translator.translate_subtitle(source())
    translator.translate_subtitle(source())
    assert len(calls) == 1
    translator.reuse_cached_chunks = False
    translator.translate_subtitle(source())
    assert len(calls) == 2


def test_dialogue_uses_the_apps_llm_configuration():
    from videocaptioner.core.entities import SubtitleConfig, TranslatorServiceEnum
    from videocaptioner.ui.thread.subtitle_thread import create_translator_from_config
    config = SubtitleConfig(translator_service=TranslatorServiceEnum.OPENAI, dialogue_translation=True,
        api_key="synthetic-app-key", base_url="https://configured.invalid/v1", llm_model="configured-model",
        llm_request_timeout=240, target_language=TargetLanguage.VIETNAMESE)
    engine = create_translator_from_config(config)
    try:
        assert isinstance(engine, DialogueTranslator)
        assert engine.model == "configured-model" and engine.request_timeout == 240
        assert engine._credentials == LLMCredentials("synthetic-app-key", "https://configured.invalid/v1")
    finally:
        engine.close()


def test_unpunctuated_dialogue_does_not_double_large_requests(translator, monkeypatch):
    translator.batch_num = 30
    data = ASRData([ASRDataSeg("Unpunctuated source", i * 4000, (i + 1) * 4000,
                              cue_id=f"stable-source-{i:020d}") for i in range(48)])
    before = data.to_document()
    calls = []
    def request(messages):
        owned = json.loads(messages[1]["content"])["owned_cues"]
        calls.append(owned)
        value = {"subtitle_translations": {c["id"]: "Bản dịch đầy đủ." for c in owned},
                 "speech_blocks": [{"cue_ids": [c["id"]], "text": "Bản dịch đầy đủ."} for c in owned]}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)))])
    monkeypatch.setattr(translator, "_request", request)
    result = translator.translate_subtitle(data)
    assert [len(c) for c in calls] == [32, 16]
    assert [c["id"] for call in calls for c in call] == [f"c{i + 1}" for i in range(48)]
    assert [s.cue_id for s in result] == [s.cue_id for s in data]
    assert tuple(cid for block in translator.dialogue_document.blocks for cid in block.cue_ids) == tuple(s.cue_id for s in data)
    assert data.to_document() == before
    translator.translate_subtitle(data)
    assert len(calls) == 2


@pytest.mark.parametrize("field", ["subtitle_translations", "speech_blocks"])
def test_wire_response_cannot_claim_neighbor_or_guess_mistyped_id(translator, monkeypatch, field):
    calls = []
    def request(messages):
        calls.append(messages)
        value = {"subtitle_translations": {"c2": "Translated"}, "speech_blocks": [{"cue_ids": ["c2"], "text": "Translated"}]}
        if field == "subtitle_translations":
            value[field] = {"c1": "Neighbor"}
        else:
            value[field][0]["cue_ids"] = ["c1"]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)))])
    monkeypatch.setattr(translator, "_request", request)
    data = source()
    with pytest.raises(RuntimeError, match="Malformed dialogue"):
        translator.translate_subtitle(data.with_segments([data.segments[1].clone()]), context_data=data)
    assert len(calls) == 3 and not translator._cache.values


def test_wire_context_preserves_text_and_non_cue_identifiers(translator):
    from copy import deepcopy
    translator._wire_ids = {"source-a": "c1", "source-b": "c2"}
    context = {"selected": [{"id": "source-a", "speaker_id": "source-b"}],
               "source_window": [{"id": "source-a", "text": "source-b"}],
               "characters": [{"id": "source-b", "label": "source-a", "evidence": {"cue_ids": ["source-a"]}}],
               "evidence": [{"entry_id": "source-a", "cue_ids": ["source-b"]}],
               "review": {"cues_by_issue": {"conflict": ["source-a"]}}}
    before = deepcopy(context)
    wire = translator._wire_context(context)
    assert context == before
    assert wire["selected"] == [{"id": "c1", "speaker_id": "source-b"}]
    assert wire["source_window"] == [{"id": "c1", "text": "source-b"}]
    assert wire["characters"] == [{"id": "source-b", "label": "source-a", "evidence": {"cue_ids": ["c1"]}}]
    assert wire["evidence"] == [{"entry_id": "source-a", "cue_ids": ["c2"]}]
    assert wire["review"]["cues_by_issue"] == {"conflict": ["c1"]}
