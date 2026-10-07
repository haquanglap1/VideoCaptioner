"""Series/video background for translation: sidecar, notes block and prompt wiring; no network."""

import json
from types import SimpleNamespace

import pytest

from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.translate import SubtitleProcessData, TargetLanguage
from videocaptioner.core.translate.dialogue_translator import DialogueTranslator
from videocaptioner.core.translate.factory import TranslatorFactory
from videocaptioner.core.translate.llm_translator import LLMTranslator
from videocaptioner.core.translate.series_context import (
    VideoContext,
    bilibili_description,
    bilibili_page_context,
    compose_context_notes,
    context_from_info,
    fetch_video_context,
    load_video_context,
    save_video_context,
    sidecar_path,
)
from videocaptioner.core.translate.types import TranslatorType

CREDENTIALS = LLMCredentials("sk-fixture-only", "https://fixture.invalid/v1")


def test_video_context_round_trip_and_bounds(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    context = VideoContext.make(title=" 《鸣潮》PV | 修行 ", url="https://b.example/v#t=1", uploader="鸣潮",
                                description="“徒儿，看剑。”\r\n第二行\x07", parts=["【中】P1", "", 3, "【日】P2"])
    assert context.parts == ("【中】P1", "【日】P2") and context.url == "https://b.example/v"
    assert context.description == "“徒儿，看剑。”\n第二行"
    path = save_video_context(video, context)
    assert path == sidecar_path(video) == tmp_path / "clip.mp4.context.json"
    assert load_video_context(video) == context and load_video_context(str(video)) == context
    assert load_video_context(None) is None and load_video_context(tmp_path / "missing.mp4") is None
    path.write_text("{not json", encoding="utf-8")
    assert load_video_context(video) is None
    path.write_text(json.dumps({"schema": "video-context-v1", "title": ""}), encoding="utf-8")
    assert load_video_context(video) is None  # empty context is no context
    assert len(VideoContext.make(description="x" * 2500).description) == 2000
    with pytest.raises(ValueError):
        VideoContext(title="x" * 301)


def test_context_from_info_handles_parts_and_odd_shapes():
    info = {"title": "Series", "uploader": "Channel", "description": "About",
            "entries": iter([{"title": "P1"}, {"part": "P2"}, None, {"id": "p3"}]), "webpage_url": "https://x/1"}
    context = context_from_info(info, "https://fallback")
    assert (context.title, context.uploader, context.description, context.url) == ("Series", "Channel", "About", "https://x/1")
    assert context.parts == ("P1", "P2", "p3")
    assert context_from_info(None, "https://u").url == "https://u" and context_from_info({"entries": 5}).parts == ()


def test_bilibili_description_prefers_initial_state_then_meta():
    page = ('<meta name="description" content="meta &amp; desc"><script>window.__INITIAL_STATE__={"ad":{"desc":"buy"},'
            '"videoData":{"desc":"\\u201c玄方地界\\u201d\\n第二行","owner":{"mid":1,"name":"鸣潮"},'
            '"pages":[{"cid":1,"part":"【中】P1"},{"cid":2,"part":"【日】P2"}]}}</script>')
    assert bilibili_description(page) == "“玄方地界”\n第二行"
    found = bilibili_page_context(page)
    assert found["uploader"] == "鸣潮" and found["parts"] == ["【中】P1", "【日】P2"]
    assert bilibili_description('<meta name="description" content="meta &amp; desc">') == "meta & desc"
    assert bilibili_description("nothing") == ""


def test_fetch_video_context_uses_extractor_then_bilibili_page():
    calls = []

    def extract(url, cookies):
        calls.append(("extract", url, cookies))
        return {"title": "PV", "entries": [{"title": "【中】"}, {"title": "【日】"}]}

    def page(url):
        calls.append(("page", url))
        return '<script>__INITIAL_STATE__={"videoData":{"desc":"师徒","owner":{"name":"鸣潮"},"pages":[{"part":"ignored"}]}}</script>'

    context = fetch_video_context("https://www.bilibili.com/video/BV1/", extract=extract, page=page)
    assert context.description == "师徒" and context.uploader == "鸣潮" and len(calls) == 2
    assert context.parts == ("【中】", "【日】")  # extractor parts win over the page
    bare = fetch_video_context("https://www.bilibili.com/video/BV2/", extract=lambda *_: {"title": "T"}, page=page)
    assert bare.parts == ("ignored",) and bare.uploader == "鸣潮"
    youtube = fetch_video_context("https://www.youtube.com/watch?v=a", extract=lambda *_: {"title": "T", "description": "D"},
                                  page=lambda _: pytest.fail("no page fetch for a filled description"))
    assert (youtube.title, youtube.description) == ("T", "D")
    with pytest.raises(ValueError):
        fetch_video_context("ftp://x", extract=extract, page=page)
    with pytest.raises(ValueError, match="tiêu đề"):
        fetch_video_context("https://www.youtube.com/watch?v=b", extract=lambda *_: {}, page=lambda _: "")


def test_compose_context_notes_blocks():
    assert compose_context_notes(None, "") == "" and compose_context_notes(VideoContext(), "  ") == ""
    notes = compose_context_notes(VideoContext.make(title="T", parts=["a", "b"]), "清宵 = sư phụ")
    assert notes.startswith("Background supplied by the user")
    assert "<video_context>\nTitle: T\nParts: a | b\n</video_context>" in notes
    assert "<series_notes>\n清宵 = sư phụ\n</series_notes>" in notes
    assert len(compose_context_notes(None, "x" * 5000)) < 4200


def items(count=12):
    return [SubtitleProcessData(index=i, original_text=f"第{i}句", cue_id=f"c{i}", start_ms=i * 1000, end_ms=i * 1000 + 900)
            for i in range(1, count + 1)]


def test_llm_translator_sends_background_in_brief_chunks_and_cache_key(monkeypatch):
    requests = []

    def fake_request(self, messages):
        requests.append(messages)
        content = messages[0]["content"]
        if "localization analyst" in content:
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="TOPIC & GENRE: PV"))])
        payload = json.loads(messages[-1]["content"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({k: f"[vi] {v}" for k, v in payload.items()}, ensure_ascii=False)))])

    monkeypatch.setattr(LLMTranslator, "_request", fake_request)
    notes = compose_context_notes(VideoContext.make(title="PV"), "清宵 = sư phụ")
    translator = TranslatorFactory.create_translator(TranslatorType.OPENAI, thread_num=1, batch_num=6,
                                                     target_language=TargetLanguage.SIMPLIFIED_CHINESE, model="m",
                                                     credentials=CREDENTIALS, context_notes=notes)
    translator.reuse_cached_chunks = False
    data = items()
    translator._prepare(data)
    assert requests[0][1]["content"].startswith(notes) and "TRANSCRIPT:\n第1句" in requests[0][1]["content"]
    assert "background block" in requests[0][0]["content"]
    translator._translate_chunk(data[:6])
    assert "<series_notes>" in requests[1][0]["content"] and "TOPIC & GENRE: PV" in requests[1][0]["content"]
    plain = TranslatorFactory.create_translator(TranslatorType.OPENAI, thread_num=1, batch_num=6,
                                                target_language=TargetLanguage.SIMPLIFIED_CHINESE, model="m",
                                                credentials=CREDENTIALS)
    plain._prepare(data)
    assert translator._get_cache_key(data[:6]) != plain._get_cache_key(data[:6])
    assert "sk-fixture-only" not in json.dumps(requests, ensure_ascii=False)


def test_dialogue_translator_appends_background_to_prompt():
    notes = compose_context_notes(None, "卜灵 = đồ đệ")
    translator = DialogueTranslator(thread_num=1, batch_num=4, target_language=TargetLanguage.SIMPLIFIED_CHINESE, model="m",
                                    custom_prompt="", is_reflect=False, update_callback=None, credentials=CREDENTIALS,
                                    context_notes=notes)
    translator._prepare(items(4))
    assert translator._prompt.endswith(notes)
    plain = DialogueTranslator(thread_num=1, batch_num=4, target_language=TargetLanguage.SIMPLIFIED_CHINESE, model="m",
                               custom_prompt="", is_reflect=False, update_callback=None, credentials=CREDENTIALS)
    plain._prepare(items(4))
    assert "<series_notes>" not in plain._prompt
