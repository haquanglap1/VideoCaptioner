"""Dialogue mode is explicit and exports a separate source-bound speech document."""

import json
from types import SimpleNamespace

from videocaptioner.cli.main import main
from videocaptioner.core.translate.dialogue import DialogueDocument


def test_cli_dialogue_translates_and_exports_without_changing_input(tmp_path, monkeypatch):
    cache = {}
    monkeypatch.setattr("videocaptioner.core.translate.base.get_translate_cache", lambda: SimpleNamespace(
        get=lambda key, default=None: cache.get(key, default),
        set=lambda key, value, expire=None: cache.__setitem__(key, value)))
    source = tmp_path / "source.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nNếu ngày mai\n\n"
                      "2\n00:00:01,000 --> 00:00:02,000\ntrời mưa.\n", encoding="utf-8")
    before = source.read_bytes()
    target = tmp_path / "translated.srt"
    calls = []
    def request(self, messages):
        data = json.loads(messages[1]["content"])
        ids = [c["id"] for c in data["owned_cues"]]
        calls.append(ids)
        payload = {"subtitle_translations": dict(zip(ids, ["Nếu mai", "trời mưa."])),
                   "speech_blocks": [{"cue_ids": ids, "text": "Nếu mai trời mưa."}]}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    monkeypatch.setattr("videocaptioner.core.translate.dialogue_translator.DialogueTranslator._request", request)
    result = main(["subtitle", str(source), "-o", str(target), "--dialogue", "--no-split", "--no-optimize",
                   "--target-language", "vi", "--api-key", "synthetic-key", "--api-base", "https://synthetic.invalid/v1"])
    assert result == 0
    assert source.read_bytes() == before
    document = DialogueDocument.load(target.with_suffix(".dialogue.json"))
    assert len(document.cues) == 2 and len(document.blocks) == 1
    assert document.blocks[0].text == "Nếu mai trời mưa."
    assert len(calls) == 1


def test_cli_dub_accepts_dialogue_json_for_wording_preview(tmp_path, monkeypatch):
    from contextlib import nullcontext

    from videocaptioner.core.dubbing.engine import DubbingEngine
    from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
    from videocaptioner.core.translate.dialogue import DialogueCue, SpeechBlock
    source = tmp_path / "speech.dialogue.json"
    DialogueDocument((DialogueCue("a", "Xin chào.", "Xin chào.", 0, 1000),),
                     (SpeechBlock(("a",), "Xin chào."),), "vi").save(source)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"synthetic-video")
    monkeypatch.setattr(DubbingEngine, "_managed_runtime_context", staticmethod(lambda *args: nullcontext()))
    monkeypatch.setattr(DubbingOrchestrator, "_video_duration", staticmethod(lambda *args: 5.0))
    target = tmp_path / "review.json"
    assert main(["dub", str(video), "--subtitle", str(source), "--tts-provider", "omnivoice-local",
                 "--prepare-review", str(target)]) == 0
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["plan_schema_version"] == "dubbing-plan-dialogue-v1"
    assert data["groups"][0]["tts_text"] == "Xin chào."
    assert not data["groups"][0]["audio_path"]
