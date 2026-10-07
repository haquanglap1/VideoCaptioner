"""Layer 1 of speaker labeling: LLM naming of diarized clusters with a fake request; no network."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.local import speaker_naming as module
from videocaptioner.core.asr.local.profiles import LocalASRConfig
from videocaptioner.core.asr.local.speaker_naming import (
    AUTO_CONFIRM_CONFIDENCE,
    MAX_CLUSTERS,
    SpeakerNamingError,
    SpeakerNamingSettings,
    apply_decisions,
    apply_naming,
    name_speakers,
    naming_messages,
    parse_naming_reply,
    sample_lines,
    speaker_clusters,
    transcript_lines,
)
from videocaptioner.core.asr.metadata import (
    ASRMetadata,
    SpeakerAssociation,
    SpeakerNaming,
    SpeakerProfile,
    StageProvenance,
)
from videocaptioner.core.entities import TranscribeConfig, TranscribeModelEnum
from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.prompts import list_prompts
from videocaptioner.core.translate.conversation import (
    Character,
    ConversationContext,
    Evidence,
    SpeakerMapping,
)

DIARIZATION = StageProvenance("pyannote", "pyannote/speaker-diarization-community-1", "rev", "policy")
RECOGNITION = StageProvenance("qwen-local", "Qwen/Qwen3-ASR-1.7B", "rev", "qwen-text-v1")
CREDENTIALS = LLMCredentials("sk-fixture-only", "https://fixture.invalid/v1")
SETTINGS = SpeakerNamingSettings(CREDENTIALS, "fixture-model", 60, "")


def cue(text, start, end, label, cue_id, *, scope="scope1", override=None):
    if label is None:
        association = SpeakerAssociation(DIARIZATION, scope, "unknown", (), 0)
    else:
        association = SpeakerAssociation(DIARIZATION, scope, "assigned", (label,), 900_000)
    metadata = ASRMetadata("qwen-local", scope, label, recognition=RECOGNITION, diarization=association,
                           speaker_override=override)
    return ASRDataSeg(text, start, end, cue_id=cue_id, metadata=metadata)


def document():
    return ASRData([
        cue("师父，弟子知错了。", 0, 1000, "SPEAKER_00", "c1"),
        cue("清宵，起来吧。", 1000, 2000, "SPEAKER_01", "c2"),
        cue("是，师父。", 2000, 3000, "SPEAKER_00", "c3"),
        cue("（风声）", 3000, 4000, None, "c4"),
        cue("我是旁白。", 4000, 5000, "SPEAKER_02", "c5", override="Narrator"),
    ])


def speaker_id(label, scope="scope1"):
    return f"pyannote:{scope}:{label}"


def entry(label, name, confidence=0.9, evidence=(2,), **extra):
    value = {"label": label, "name": name, "role": "", "gender": "unknown", "age_group": "unknown",
             "confidence": confidence, "evidence_cue_ids": list(evidence)}
    value.update(extra)
    return value


def reply(*entries):
    return json.dumps({"speakers": list(entries)}, ensure_ascii=False)


def response(content, finish_reason="stop", reasoning=None):
    usage = SimpleNamespace(completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning)) if reasoning else None
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)],
                           usage=usage)


class FakeRequest:
    def __init__(self, *contents):
        self.contents = list(contents)
        self.calls = []

    def __call__(self, messages, model, **kwargs):
        self.calls.append({"messages": messages, "model": model, **kwargs})
        content = self.contents.pop(0)
        if isinstance(content, Exception):
            raise content
        return content if isinstance(content, SimpleNamespace) else response(content)


def test_clusters_skip_unknown_cues_and_user_overrides_and_keep_first_appearance():
    clusters = speaker_clusters(document())
    assert [(c.label, c.speaker_id, c.cue_ids) for c in clusters] == [
        ("SPEAKER_00", speaker_id("SPEAKER_00"), ("c1", "c3")), ("SPEAKER_01", speaker_id("SPEAKER_01"), ("c2",))]
    labels = [line.label for line in transcript_lines(document(), clusters)]
    assert labels == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00", "?", "Narrator"]


def test_duplicate_raw_labels_from_two_scopes_and_numeric_labels_get_distinct_tags():
    data = ASRData([cue("一", 0, 1000, "1", "a", scope="job-a"), cue("二", 1000, 2000, "1", "b", scope="job-b")])
    assert [c.label for c in speaker_clusters(data)] == ["SPEAKER_1", "SPEAKER_1#2"]


def test_messages_carry_text_labels_counts_and_background_only():
    assert "asr/speaker_naming" in list_prompts()
    data = document()
    messages, lines, sampled = naming_messages(data, speaker_clusters(data),
                                               "<series_notes>\n清宵 là đệ tử\n</series_notes>")
    assert not sampled and len(lines) == 5
    assert messages[0]["role"] == "system" and "evidence_cue_ids" in messages[0]["content"]
    user = messages[1]["content"]
    assert user.startswith("<series_notes>") and "CLUSTERS:\nSPEAKER_00: 2 lines\nSPEAKER_01: 1 lines" in user
    assert "1 | SPEAKER_00 | 师父，弟子知错了。" in user and "4 | ? | （风声）" in user and "5 | Narrator |" in user
    assert "scope1" not in user and "pyannote" not in user and "c1" not in user.split("TRANSCRIPT")[1]


def test_long_transcript_is_sampled_with_markers_and_keeps_every_cluster():
    segments = [cue("甲" * 50, i * 1000, i * 1000 + 900, "SPEAKER_00", f"k{i}") for i in range(300)]
    segments[150] = cue("乙" * 10, 150_000, 150_900, "SPEAKER_01", "k150")
    segments[290] = cue("丙" * 10, 290_000, 290_900, "SPEAKER_02", "k290")
    data = ASRData(segments)
    clusters = speaker_clusters(data)
    lines = transcript_lines(data, clusters)
    sample, sampled = sample_lines(lines, clusters, limit=6000)
    assert sampled and len(sample) < len(lines)
    numbers = [line.number for line in sample]
    assert numbers[0] == 1 and numbers[-1] == 300 and 151 in numbers
    assert sum(line.text.startswith("甲") for line in sample) * 60 <= 6000 + 3 * 60
    assert {line.label for line in sample} >= {"SPEAKER_00", "SPEAKER_01", "SPEAKER_02"}
    messages, _, flagged = naming_messages(data, clusters)
    assert flagged and "..." in messages[1]["content"] and "sampled" in messages[1]["content"]


@pytest.mark.parametrize("content", [
    "not json",
    "```json\n{\"speakers\": []}",
    json.dumps({"speakers": [entry("SPEAKER_00", "清宵")]}),
    json.dumps({"speakers": [entry("SPEAKER_00", "清宵"), entry("SPEAKER_01", "")], "note": "x"}),
    reply(entry("SPEAKER_01", "清宵"), entry("SPEAKER_00", "")),
    reply(entry("SPEAKER_00", "清宵", extra=1), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", "清宵", confidence=1.2), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", "清宵", confidence=True), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", "清宵", confidence="0.9"), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", "清宵", evidence=(9,)), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", "清宵", evidence=("c2",)), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", "清宵", gender="boy"), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", "清宵", age_group="old"), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", "x" * 61), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", "清\n宵"), entry("SPEAKER_01", "")),
    reply(entry("SPEAKER_00", 5), entry("SPEAKER_01", "")),
    '{"speakers": [], "speakers": []}',
    None,
])
def test_parse_rejects_invalid_replies(content):
    data = document()
    clusters = speaker_clusters(data)
    with pytest.raises(SpeakerNamingError):
        parse_naming_reply(content, clusters, transcript_lines(data, clusters))


def test_parse_accepts_fenced_json_and_maps_line_numbers_to_cue_ids():
    data = document()
    clusters = speaker_clusters(data)
    content = "```json\n" + reply(entry("SPEAKER_00", " 清宵 ", role="弟子", gender="male", age_group="teen",
                                           evidence=(2, 2, 3)), entry("SPEAKER_01", "", confidence=0, evidence=())) + "\n```"
    profiles = parse_naming_reply(content, clusters, transcript_lines(data, clusters))
    assert profiles[0].name == "清宵" and profiles[0].evidence_cue_ids == ("c2", "c3")
    assert (profiles[0].gender, profiles[0].age_group, profiles[0].confidence) == ("male", "teen", 0.9)
    assert profiles[1].name == "" and profiles[1].evidence_cue_ids == () and profiles[1].confidence == 0


def test_one_request_normally_and_one_retry_on_an_invalid_reply():
    request = FakeRequest("garbage", reply(entry("SPEAKER_00", "清宵"), entry("SPEAKER_01", "")))
    result = name_speakers(document(), SETTINGS, request=request)
    assert len(request.calls) == 2 and request.calls[0]["model"] == "fixture-model"
    assert request.calls[0]["max_completion_tokens"] == 2400
    assert result.speaker_naming is not None and result.speaker_naming.model == "fixture-model"
    assert [p.status for p in result.speaker_naming.profiles] == ["confirmed", "proposed"]
    assert not document().speaker_naming and not document().conversation_context.enabled


def test_two_invalid_replies_fail_without_a_third_request_and_leave_the_input_untouched():
    data = document()
    request = FakeRequest("garbage", response(None), reply(entry("SPEAKER_00", "清宵"), entry("SPEAKER_01", "")))
    with pytest.raises(SpeakerNamingError):
        name_speakers(data, SETTINGS, request=request)
    assert len(request.calls) == 2 and data.speaker_naming is None and not data.conversation_context.enabled


def test_reasoning_budget_exhaustion_is_reported_and_provider_errors_are_not_retried():
    request = FakeRequest(response("", finish_reason="length", reasoning=2400),
                          response("", finish_reason="length", reasoning=2400))
    with pytest.raises(SpeakerNamingError, match="reasoning"):
        name_speakers(document(), SETTINGS, request=request)
    request = FakeRequest(RuntimeError("Translation HTTP 500; review or retry explicitly."))
    with pytest.raises(RuntimeError):
        name_speakers(document(), SETTINGS, request=request)
    assert len(request.calls) == 1


def test_no_assigned_speakers_means_no_request_and_too_many_clusters_is_refused():
    plain = ASRData([ASRDataSeg("你好", 0, 1000, cue_id="p1")])
    request = FakeRequest()
    assert name_speakers(plain, SETTINGS, request=request) is plain and not request.calls
    crowd = ASRData([cue("嗯", i * 1000, i * 1000 + 500, f"SPEAKER_{i:02d}", f"m{i}") for i in range(MAX_CLUSTERS + 1)])
    with pytest.raises(SpeakerNamingError, match="Too many"):
        name_speakers(crowd, SETTINGS, request=request)
    assert not request.calls


def test_cancellation_check_runs_before_and_after_the_request():
    calls = []

    def check():
        calls.append(len(calls))
        if len(calls) == 2:
            raise RuntimeError("cancelled")

    request = FakeRequest(reply(entry("SPEAKER_00", "清宵"), entry("SPEAKER_01", "")))
    with pytest.raises(RuntimeError, match="cancelled"):
        name_speakers(document(), SETTINGS, request=request, check=check)
    assert len(request.calls) == 1


def naming(*profiles, model="fixture-model"):
    return SpeakerNaming(model, "sha", tuple(profiles), 5, False)


def profile(label, name, confidence=0.9, evidence=("c2",), **extra):
    return SpeakerProfile(speaker_id(label), label, name, confidence=confidence, evidence_cue_ids=tuple(evidence), **extra)


def mapping_for(data, label):
    return next(m for m in data.conversation_context.mappings if m.speaker_id == speaker_id(label))


def test_apply_confirms_confident_unique_evidenced_names_and_proposes_the_rest():
    result = apply_naming(document(), naming(profile("SPEAKER_00", "清宵", AUTO_CONFIRM_CONFIDENCE),
                                             profile("SPEAKER_01", "师父", 0.6)))
    context = result.conversation_context
    assert sorted(c.label for c in context.characters) == ["师父", "清宵"]
    confirmed, proposed = mapping_for(result, "SPEAKER_00"), mapping_for(result, "SPEAKER_01")
    assert confirmed.evidence == Evidence("text", "confirmed", ("c2",))
    assert proposed.evidence == Evidence("text", "proposed", ("c2",))
    assert [p.status for p in result.speaker_naming.profiles] == ["confirmed", "proposed"]
    # Only confirmed entries resolve a speaker for translation; proposals wait for the user.
    resolved = {cue.id: cue.speaker_id for cue in result.context_snapshot().resolved}
    assert resolved["c1"] and not resolved["c2"]


def test_apply_without_evidence_duplicate_names_or_empty_name_stays_a_proposal():
    result = apply_naming(document(), naming(profile("SPEAKER_00", "清宵", 0.95, evidence=()),
                                             profile("SPEAKER_01", "", 0.3, evidence=())))
    first, second = result.speaker_naming.profiles
    assert first.status == "proposed" and first.evidence_cue_ids == ("c1", "c3")  # the cluster's own cues
    assert second.status == "proposed" and not any(m.speaker_id == speaker_id("SPEAKER_01")
                                                  for m in result.conversation_context.mappings)
    twins = apply_naming(document(), naming(profile("SPEAKER_00", "清宵", 0.95), profile("SPEAKER_01", "清宵", 0.95)))
    assert [p.status for p in twins.speaker_naming.profiles] == ["proposed", "proposed"]
    assert [c.label for c in twins.conversation_context.characters] == ["清宵"]


def test_apply_reuses_an_existing_character_and_never_replaces_a_user_decision():
    data = document()
    data.conversation_context = ConversationContext(
        characters=(Character("user-a", "清宵", Evidence("user", "locked")), Character("user-b", "老道")),
        mappings=(SpeakerMapping("user-map", speaker_id("SPEAKER_01"), "user-b"),))
    result = apply_naming(data, naming(profile("SPEAKER_00", "清宵"), profile("SPEAKER_01", "师父", 0.99)))
    assert [c.id for c in result.conversation_context.characters] == ["user-a", "user-b"]
    assert mapping_for(result, "SPEAKER_00").character_id == "user-a"
    assert mapping_for(result, "SPEAKER_01") == SpeakerMapping("user-map", speaker_id("SPEAKER_01"), "user-b")
    assert [p.status for p in result.speaker_naming.profiles] == ["confirmed", "confirmed"]
    with pytest.raises(SpeakerNamingError):
        apply_naming(document(), naming(SpeakerProfile("pyannote:other:SPEAKER_00", "SPEAKER_00", "x")))


def test_rerun_replaces_earlier_machine_proposals_without_duplicates():
    first = apply_naming(document(), naming(profile("SPEAKER_00", "清宵"), profile("SPEAKER_01", "师父", 0.5)))
    second = apply_naming(first, naming(profile("SPEAKER_00", "清霄", 0.7), profile("SPEAKER_01", "老道", 0.95)))
    context = second.conversation_context
    assert sorted(c.label for c in context.characters) == ["清霄", "老道"]
    assert len(context.mappings) == 2 and mapping_for(second, "SPEAKER_01").evidence.status == "confirmed"
    assert ConversationContext.from_dict(context.to_dict()) == context


def test_document_round_trip_keeps_the_map_and_srt_prints_no_names(tmp_path):
    result = apply_naming(document(), naming(profile("SPEAKER_00", "清宵"), profile("SPEAKER_01", "师父", 0.5)))
    path = tmp_path / "named.json"
    result.save(str(path))
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["speaker_naming"]["policy"] == "speaker-naming-v1" and saved["speaker_naming"]["profiles"][0]["name"] == "清宵"
    reopened = ASRData.from_subtitle_file(str(path))
    assert reopened.to_document() == result.to_document() and reopened.speaker_naming == result.speaker_naming
    assert reopened.with_segments(list(reopened.segments)).speaker_naming == result.speaker_naming
    srt = result.to_srt()
    assert srt == document().to_srt() and "SPEAKER_00" not in srt and "师父，弟子知错了。" in srt
    broken = dict(saved)
    broken["speaker_naming"] = {"policy": "speaker-naming-v1"}
    with pytest.raises(ValueError):
        ASRData.from_json(broken)


@pytest.mark.parametrize("value", [
    {"policy": "other"}, {"confidence": 2}, {"gender": "x"}, {"status": "maybe"}, {"evidence_cue_ids": ["a", "a"]},
])
def test_profile_contract_is_strict(value):
    raw = profile("SPEAKER_00", "清宵").to_dict()
    raw.update(value)
    with pytest.raises(ValueError):
        if "policy" in value:
            SpeakerNaming.from_dict({**naming().to_dict(), **value})
        else:
            SpeakerProfile.from_dict(raw)


def test_user_decisions_confirm_with_user_evidence_or_reject_a_cluster():
    data = apply_naming(document(), naming(profile("SPEAKER_00", "清宵", 0.5), profile("SPEAKER_01", "", 0.2)))
    assert len(data.speaker_naming.pending) == 2
    decided = apply_decisions(data, {speaker_id("SPEAKER_00"): " 清宵 ", speaker_id("SPEAKER_01"): ""})
    assert mapping_for(decided, "SPEAKER_00").evidence.source == "user"
    assert mapping_for(decided, "SPEAKER_00").evidence.status == "confirmed"
    assert [p.status for p in decided.speaker_naming.profiles] == ["confirmed", "rejected"]
    assert not decided.speaker_naming.pending
    assert [c.label for c in decided.conversation_context.characters] == ["清宵"]
    renamed = apply_decisions(decided, {speaker_id("SPEAKER_00"): "老道"})
    assert [c.label for c in renamed.conversation_context.characters] == ["老道"]
    assert renamed.speaker_naming.profiles[0].name == "老道"
    with pytest.raises(SpeakerNamingError):
        apply_decisions(document(), {})


def test_transcribe_names_after_diarization_and_keeps_labels_when_naming_fails(monkeypatch, tmp_path):
    from importlib import import_module
    transcribe = import_module("videocaptioner.core.asr.transcribe")
    base = ASRData([ASRDataSeg("你好", 0, 1000)])

    class Recognizer:
        def run(self, callback):
            return base

    diarized = document()
    monkeypatch.setattr(transcribe, "_create_asr_instance", lambda *a: Recognizer())
    monkeypatch.setattr(transcribe, "add_local_speakers", lambda *a, **k: diarized)
    replies = [reply(entry("SPEAKER_00", "清宵"), entry("SPEAKER_01", ""))]
    seen = []

    def fake_call(self, messages, model, **kwargs):
        seen.append((self.credentials.api_key, self.timeout, messages))
        if not replies:
            raise RuntimeError("Translation HTTP 500; review or retry explicitly.")
        return response(replies.pop(0))

    monkeypatch.setattr("videocaptioner.core.llm.owned_request.OwnedLLMRequest.__call__", fake_call)
    source = tmp_path / "audio.wav"
    source.write_bytes(b"snapshot fixture")
    settings = replace(SETTINGS, context_notes="<series_notes>\n清宵 = đệ tử\n</series_notes>")
    config = TranscribeConfig(transcribe_model=TranscribeModelEnum.WHISPER_API,
                              local_asr=LocalASRConfig(diarize=True, name_speakers=True), speaker_naming=settings)
    messages = []
    result = transcribe.transcribe(str(source), config, callback=lambda p, m: messages.append(m))
    assert result.speaker_naming is not None and result.speaker_naming.profiles[0].name == "清宵"
    assert seen[0][0] == "sk-fixture-only" and seen[0][1] == 60
    assert "清宵 = đệ tử" in seen[0][2][1]["content"] and str(source) not in seen[0][2][1]["content"]
    assert any("Naming" in m for m in messages)
    # Second job: the provider fails; the diarized labels survive and the job still succeeds.
    messages.clear()
    again = transcribe.transcribe(str(source), config, callback=lambda p, m: messages.append(m))
    assert again.speaker_naming is None and again.segments[0].speaker == speaker_id("SPEAKER_00")
    assert any("remain anonymous" in m for m in messages)
    # Without an LLM snapshot the step is skipped explicitly rather than attempted.
    messages.clear()
    skipped = transcribe.transcribe(str(source), replace(config, speaker_naming=None),
                                    callback=lambda p, m: messages.append(m))
    assert skipped.speaker_naming is None and any("skipped" in m for m in messages)
    assert len(seen) == 2


def test_settings_require_complete_credentials_and_a_model():
    with pytest.raises(SpeakerNamingError):
        SpeakerNamingSettings(LLMCredentials("", "https://fixture.invalid/v1"), "model")
    with pytest.raises(SpeakerNamingError):
        SpeakerNamingSettings(CREDENTIALS, "  ")
    with pytest.raises(ValueError):
        SpeakerNamingSettings(CREDENTIALS, "model", 0)
    assert module.prompt_sha256() == module.prompt_sha256() and len(module.prompt_sha256()) == 64
