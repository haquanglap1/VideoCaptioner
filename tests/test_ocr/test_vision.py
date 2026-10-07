"""Vision-LLM OCR contracts with synthetic frames and fake replies; no provider, key or model."""

import io
import json
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import pytest
from PIL import Image

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli.main import main
from videocaptioner.core.llm.client import LLMCredentials
from videocaptioner.core.ocr import vision
from videocaptioner.core.ocr.consensus import CacheScope, ReadCache
from videocaptioner.core.ocr.decoder import RoiDecoder, probe_video
from videocaptioner.core.ocr.document import OcrDocument
from videocaptioner.core.ocr.geometry import Roi
from videocaptioner.core.ocr.models import EngineRead, OcrError, RoiFrame, Selection
from videocaptioner.core.ocr.pipeline import OcrPipeline
from videocaptioner.core.ocr.tracking import TrackedRegion
from videocaptioner.core.ocr.vision import (
    GUTTER,
    SEPARATOR,
    VisionRecognizer,
    VisionSettings,
    parse_rows,
    render_sheet,
    run_vision_ocr,
    vision_config,
    vision_profile,
)
from videocaptioner.core.ocr.vision_profile import VisionProfile

from .test_document import make_document

CREDENTIALS = LLMCredentials("sk-fixture-only", "https://fixture.invalid/v1")


def frame(index, width=320, height=40, pts=None, color=(255, 255, 0)):
    image = Image.new("RGB", (width, height), "black")
    image.putpixel((index % width, index % height), color)
    return RoiFrame(index, pts if pts is not None else index * 100, Fraction(1, 1000),
                    Fraction((pts if pts is not None else index * 100)), width, height, image.tobytes())


def reply(texts, *, fence=False, finish="stop", usage=(120, 30)):
    content = json.dumps({"rows": [{"index": i, "text": t} for i, t in enumerate(texts, 1)]}, ensure_ascii=False)
    if fence:
        content = "```json\n" + content + "\n```"
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))],
                           usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]))


class FakeRequest:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, messages, model, **kwargs):
        self.calls.append({"messages": messages, "model": model, **kwargs})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def settings(model="vision-fixture", rows=4, width=512, crops=1, **extra):
    return VisionSettings(CREDENTIALS, vision_profile(model, rows, width, crops), **extra)


def test_profile_config_identity_and_legacy_documents_unchanged():
    profile = vision_profile(" gpt-vision ", 8, 640)
    assert profile == VisionProfile("vision-sheet-v1", "gpt-vision", 8, 640, 1, vision.PROMPT_SHA256)
    config = vision_config(Roi(0, .8, 1, .2), Selection(0, 1000), profile)
    assert config.profile_snapshot is None and config.vision == profile
    assert config.read_revision != config.profile_sha256
    assert vision_config(Roi(0, .8, 1, .2), Selection(0, 1000), vision_profile("other", 8, 640)).read_revision != config.read_revision
    assert "vision" not in make_document().to_dict()["config"]
    for bad in (dict(rows=0), dict(rows=41), dict(width=100), dict(crops=3), dict(model=" ")):
        with pytest.raises(OcrError):
            replace(profile, **bad)
    with pytest.raises(OcrError):
        replace(config, profile_snapshot=make_document().config.profile_snapshot)
    with pytest.raises(OcrError):
        replace(config, tracking_policy="character-features-v1")
    with pytest.raises(OcrError):
        VisionSettings(LLMCredentials("", ""), profile)


def test_render_sheet_numbers_rows_and_bounds_scale():
    frames = [frame(0, 320, 40), frame(1, 1600, 60), frame(2, 100, 20)]
    png, bounds = render_sheet(frames, 512)
    image = Image.open(io.BytesIO(png))
    assert image.size[0] == GUTTER + 512 + SEPARATOR
    assert [b[2] - b[0] for b in bounds] == [512, 512, 300] and [b[3] - b[1] for b in bounds] == [64, 19, 60]
    assert image.size[1] == sum(b[3] - b[1] for b in bounds) + SEPARATOR * 4
    for left, top, _right, bottom in bounds:
        gutter = image.crop((0, top, left, bottom)).convert("L")
        assert gutter.getextrema() == (0, 255)  # black digit on the white gutter
    assert image.getpixel((GUTTER + 1, bounds[2][1] + 1)) == (0, 0, 0)
    with pytest.raises(OcrError):
        render_sheet([], 512)


@pytest.mark.parametrize("content, count", [
    ('{"rows":[{"index":1,"text":"a"}]}', 2),
    ('{"rows":[{"index":2,"text":"a"}]}', 1),
    ('{"rows":[{"index":1,"text":1}]}', 1),
    ('{"rows":[{"index":1,"text":"a","extra":1}]}', 1),
    ('{"rows":[{"index":1,"text":"a"}],"note":""}', 1),
    ('{"rows":[{"index":1,"text":"a"},{"index":1,"text":"b"}]}', 2),
    ('{"rows":[{"index":1,"text":"a\\u0007"}]}', 1),
    ('```json\n{"rows":[]}', 0),
    ("not json", 1),
    (None, 1),
])
def test_parse_rows_rejects_malformed_replies(content, count):
    with pytest.raises(OcrError):
        parse_rows(content, count)


def test_parse_rows_keeps_text_exactly_and_normalizes_line_breaks():
    content = '{"rows":[{"index":1,"text":" 學生三人， 2026年。\\r\\n第二行 "},{"index":2,"text":""}]}'
    assert parse_rows(content, 2) == ("學生三人， 2026年。\n第二行", "")
    assert parse_rows("```json\n" + content + "\n```", 2)[0].startswith("學生三人")


def test_recognizer_sends_one_sheet_per_group_and_keeps_only_metadata():
    request = FakeRequest([reply(["学生三人", "", "第一行\n第二行"], fence=True), reply(["尾句"])])
    recognizer = VisionRecognizer(settings(rows=3), "r" * 64, request=request)
    frames = [frame(i) for i in range(4)]
    reads = recognizer.recognize_many(frames, lambda: None)
    assert len(request.calls) == 2 and request.calls[0]["model"] == "vision-fixture"
    first = request.calls[0]["messages"]
    assert first[0] == {"role": "system", "content": vision.PROMPT}
    assert first[1]["content"][0] == {"type": "text", "text": "Rows: 3. Subtitle language: zh."}
    assert first[1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert request.calls[0]["max_completion_tokens"] == 440
    assert "sk-fixture-only" not in json.dumps(request.calls, default=str)
    assert [r.text for r in reads] == ["学生三人", "", "第一行\n第二行", "尾句"]
    assert all(r.revision == "r" * 64 for r in reads) and len(reads[2].lines) == 2
    assert reads[0].lines[0].box == ((0., 0.), (320., 0.), (320., 40.), (0., 40.))
    metrics = recognizer.metrics
    assert (metrics.requests, metrics.completed, metrics.rows, metrics.retries) == (2, 2, 4, 0)
    assert (metrics.prompt_tokens, metrics.completion_tokens, metrics.empty_reads) == (240, 60, 1)


def test_recognizer_retries_once_then_fails_without_private_details(tmp_path):
    sheets = tmp_path / "sheets"
    request = FakeRequest([reply(["a"], finish="length"), reply(["b"]),
                           RuntimeError("sk-fixture-only private body"), reply(["x"])])
    recognizer = VisionRecognizer(settings(rows=2, sheets_dir=sheets), "r" * 64, request=request)
    assert [r.text for r in recognizer.recognize_many([frame(0)], lambda: None)] == ["b"]
    assert recognizer.metrics.retries == 1 and recognizer.metrics.requests == 2
    with pytest.raises(OcrError) as failure:
        recognizer.recognize_many([frame(1), frame(2)], lambda: None)
    assert "sk-fixture-only" not in str(failure.value) and "private" not in str(failure.value)
    assert recognizer.metrics.requests == 4 and recognizer.metrics.retries == 2
    files = sorted(p.name for p in sheets.iterdir())
    assert files == ["sheet-0001.json", "sheet-0001.png", "sheet-0002.json", "sheet-0002.png"]
    record = json.loads((sheets / "sheet-0002.json").read_text(encoding="utf-8"))
    assert record["rows"] == 2 and record["error"].startswith("Vision OCR reply row count") and "sk-" not in json.dumps(record)


def test_recognizer_budget_and_cancellation():
    request = FakeRequest([reply(["a"]), reply(["b"])])
    recognizer = VisionRecognizer(settings(rows=1, max_requests=1), "r" * 64, request=request)
    assert recognizer.recognize_many([frame(0)], lambda: None)[0].text == "a"
    with pytest.raises(OcrError, match="budget"):
        recognizer.recognize_many([frame(1)], lambda: None)

    def cancelled():
        raise OcrError("cancelled")

    with pytest.raises(OcrError, match="cancelled"):
        VisionRecognizer(settings(rows=1), "r" * 64, request=request).recognize_many([frame(2)], cancelled)


class BatchStub:
    def __init__(self, rows, texts):
        self.rows_per_request, self.texts, self.calls = rows, texts, []

    def recognize_many(self, frames, check):
        check()
        self.calls.append([f.pts for f in frames])
        return [EngineRead(tuple(), "b" * 64) if self.texts(f) == "" else
                EngineRead((vision.ReadLine(self.texts(f), 0., ((0., 0.), (1., 0.), (1., 1.), (0., 1.))),), "b" * 64)
                for f in frames]


def region(start, end, frames, best):
    return TrackedRegion(Fraction(start), Fraction(end), frames[0].pts, frames[-1].pts, tuple(frames), (),
                         (Fraction(start), Fraction(start)), (Fraction(end), Fraction(end)), best)


def test_pipeline_batches_regions_prefers_sharpest_crop_dedups_and_drops_empty():
    frames = [frame(i) for i in range(6)]
    regions = [region(0, 300, frames[0:3], frames[1].pts), region(300, 500, frames[3:5], frames[4].pts),
               region(500, 600, [frames[5]], frames[5].pts), region(600, 700, [frames[1]], frames[1].pts)]
    stub = BatchStub(2, lambda f: "" if f.pts == 500 else f"t{f.pts}")
    pipeline = OcrPipeline(stub, ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64)), candidate_limit=1, drop_empty=True)
    results = pipeline._recognize_batch(regions)
    assert stub.calls == [[100, 400], [500]]  # the repeated crop of region 4 reused region 1's row
    assert [r.consensus.text for r in results] == ["t100", "t400", "", "t100"]
    assert [len(r.reads) for r in results] == [1, 1, 1, 1] and results[3].reads[0].cache_hit is False
    assert pipeline.metrics.candidate_crops == 4 and pipeline.metrics.fresh_calls == 3
    emitted = [r for result in results for r in pipeline._emit(result)]
    assert [r.consensus.text for r in emitted] == ["t100", "t400", "t100"] and pipeline.metrics.empty_regions == 1
    with pytest.raises(OcrError):
        OcrPipeline(BatchStub(0, lambda f: ""), ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64)))


def test_pipeline_streams_batches_from_video_and_reuses_cache(make_video, text_image, ffmpeg_tools):
    ffmpeg, ffprobe = ffmpeg_tools
    images = [text_image(""), text_image(), text_image(), text_image("学生五人"), text_image("学生五人"),
              text_image(""), text_image("第三句"), text_image("第三句"), text_image("")]
    source = make_video(images, vfr=True, offset=3)
    info = probe_video(source, ffprobe)
    cache = ReadCache(CacheScope("a" * 64, "b" * 64, "c" * 64))
    stub = BatchStub(2, lambda f: "read")
    pipeline = OcrPipeline(stub, cache, candidate_limit=1)
    decoder = RoiDecoder(source, info, Roi(0, 0, 1, 1), ffmpeg=ffmpeg)
    output = list(pipeline.run(decoder, Selection(0, 1200)))
    assert [(r.start_ms, r.end_ms) for r in output] == [(100, 400), (400, 700), (900, 1200)]
    assert len(stub.calls) == 2 and [len(c) for c in stub.calls] == [2, 1]
    assert all(len(r.reads) == 1 for r in output)
    again = OcrPipeline(BatchStub(2, lambda f: "unused"), cache, candidate_limit=1)
    cached = list(again.run(RoiDecoder(source, info, Roi(0, 0, 1, 1), ffmpeg=ffmpeg), Selection(0, 1200)))
    assert again.metrics.fresh_calls == 0 and again.metrics.cache_hits == 3 and len(cached) == 3


def _install_fake_request(monkeypatch, answers):
    request = FakeRequest(answers)
    monkeypatch.setattr(vision, "OwnedLLMRequest", lambda *_, **__: request)
    return request


def test_run_vision_ocr_document_round_trip_resume_and_export(make_video, text_image, ffmpeg_tools, tmp_path, monkeypatch):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(""), text_image(), text_image(), text_image(""), text_image("学生五人"), text_image("")])
    config = vision_config(Roi(0, 0, 1, 1), Selection(0, 600), vision_profile("vision-fixture", 2, 512))
    saved = tmp_path / "scan.ocr.json"
    request = _install_fake_request(monkeypatch, [reply(["学生三人，2026年。", "学生五人"])])
    document = run_vision_ocr(source, config, settings(rows=2, width=512), ffmpeg=ffmpeg, ffprobe=ffprobe,
                              checkpoint=lambda d: d.save(saved))
    assert len(request.calls) == 1
    loaded = OcrDocument.load(saved)
    assert loaded == document and document.complete and not document.export_issues
    assert [c.text for c in document.cues] == ["学生三人，2026年。", "学生五人"]
    assert all(len(c.candidates) == 1 and c.candidates[0].raw.revision == config.read_revision for c in document.cues)
    assert document.metrics.vision_requests == 1 and document.metrics.vision_rows == 2
    assert document.metrics.dropped_empty_cues == 0 and document.metrics.vision_prompt_tokens == 120
    data = document.resume(document.visual_source)
    assert [seg.text for seg in data.segments] == ["学生三人，2026年。", "学生五人"]
    with pytest.raises(OcrError):
        run_vision_ocr(source, config, settings(model="other", rows=2, width=512), ffmpeg=ffmpeg, ffprobe=ffprobe)
    partial = replace(document, cues=document.cues[:1], complete=False)
    request = _install_fake_request(monkeypatch, [reply(["学生五人"])])
    resumed = run_vision_ocr(source, config, settings(rows=2, width=512), ffmpeg=ffmpeg, ffprobe=ffprobe,
                             resume_document=partial, cache_mib=0)
    assert resumed.complete and [c.text for c in resumed.cues] == ["学生三人，2026年。", "学生五人"]
    assert len(request.calls) == 1 and len(request.calls[0]["messages"][1]["content"]) == 2


def test_run_vision_ocr_drops_rows_without_text_and_keeps_checkpoint_on_failure(make_video, text_image, ffmpeg_tools, tmp_path, monkeypatch):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image(), text_image(""), text_image("学生五人"), text_image("")])
    config = vision_config(Roi(0, 0, 1, 1), Selection(0, 500), vision_profile("vision-fixture", 1, 512))
    saved = tmp_path / "partial.ocr.json"
    _install_fake_request(monkeypatch, [reply([""]), RuntimeError("boom"), RuntimeError("boom")])
    with pytest.raises(OcrError):
        run_vision_ocr(source, config, settings(rows=1, width=512), ffmpeg=ffmpeg, ffprobe=ffprobe,
                       checkpoint=lambda d: d.save(saved), cache_mib=0)
    partial = OcrDocument.load(saved)
    assert not partial.complete and partial.cues == () and partial.metrics.dropped_empty_cues == 1
    assert partial.metrics.vision_retries == 1 and partial.metrics.vision_requests == 3


@pytest.mark.parametrize("checkpoint", [True, False])
def test_cli_vision_scan_and_resume_use_config_credentials(make_video, text_image, ffmpeg_tools, tmp_path, monkeypatch, checkpoint):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(""), text_image(), text_image(""), text_image("学生五人")])
    monkeypatch.setenv("VIDEOCAPTIONER_LLM_API_KEY", "sk-fixture-only")
    monkeypatch.setenv("VIDEOCAPTIONER_LLM_API_BASE", "https://fixture.invalid/v1")
    monkeypatch.setenv("VIDEOCAPTIONER_LLM_MODEL", "config-vision")
    request = _install_fake_request(monkeypatch, [reply(["学生三人，2026年。", "学生五人"])])
    sheets = tmp_path / "sheets"
    saved, srt = tmp_path / "scan.ocr.json", tmp_path / "captions.srt"
    command = ["ocr", str(source), "--vision-llm", "--start-ms", "0", "--end-ms", "400", "--roi", "0,0,1,1",
               "--vision-rows", "2", "--vision-width", "512", "--vision-sheets-dir", str(sheets),
               "--ffmpeg", ffmpeg, "--ffprobe", ffprobe, "--cache-mib", "0", "-o", str(srt)]
    if checkpoint:
        command += ["--checkpoint", str(saved)]
    assert main(command) == EXIT.SUCCESS
    assert request.calls[0]["model"] == "config-vision" and len(request.calls) == 1
    assert "学生五人" in srt.read_text(encoding="utf-8") and (sheets / "sheet-0001.png").is_file()
    if not checkpoint:
        return
    document = OcrDocument.load(saved)
    assert document.config.vision.model == "config-vision" and document.complete
    assert main(["ocr", str(source), "--vision-llm", "--start-ms", "0", "--end-ms", "400", "--roi", "0,0,1,1",
                 "--line-anchors", "0.5", "-o", str(tmp_path / "x.srt")]) == EXIT.USAGE_ERROR
    partial = replace(document, cues=document.cues[:1], complete=False)
    partial.save(saved)
    _install_fake_request(monkeypatch, [reply(["学生五人"])])
    assert main(["ocr-resume", str(saved), "--source", str(source), "--vision-model", "wrong", "--ffmpeg", ffmpeg,
                 "--ffprobe", ffprobe, "-o", str(tmp_path / "resumed.srt")]) == EXIT.USAGE_ERROR
    assert main(["ocr-resume", str(saved), "--source", str(source), "--ffmpeg", ffmpeg, "--ffprobe", ffprobe,
                 "--cache-mib", "0", "-o", str(tmp_path / "resumed.srt")]) == EXIT.SUCCESS
    assert "学生五人" in (tmp_path / "resumed.srt").read_text(encoding="utf-8")


def test_cli_vision_requires_model_and_credentials(make_video, text_image, ffmpeg_tools, tmp_path, monkeypatch):
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image(), text_image("")])
    for name in ("VIDEOCAPTIONER_LLM_API_KEY", "VIDEOCAPTIONER_LLM_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("videocaptioner.cli.config.load_gui_settings", lambda *_: {})
    monkeypatch.setattr("videocaptioner.cli.config.load_config_file", lambda *_: {})
    command = ["ocr", str(source), "--vision-llm", "--start-ms", "0", "--end-ms", "200", "--roi", "0,0,1,1",
               "--ffmpeg", ffmpeg, "--ffprobe", ffprobe, "-o", str(tmp_path / "out.srt")]
    assert main(command) == EXIT.USAGE_ERROR
    assert main(command + ["--vision-model", "x"]) == EXIT.USAGE_ERROR  # key still missing
    assert not (tmp_path / "out.srt").exists()


def moving_scene(text_image, text, shift):
    """Subtitle over a bright diagonal gradient that pans each frame, like camera motion."""
    from PIL import Image as PILImage
    from PIL import ImageFilter
    image = text_image(text, level=255, size=(640, 120))
    background = PILImage.new("RGB", (640, 120))
    pixels = background.load()
    for y in range(120):
        for x in range(640):
            value = ((x + shift * 7) // 4 + y) % 160 + 40
            pixels[x, y] = (value, value // 2 + 20, value // 3)
    mask = image.convert("L").point(lambda v: 255 if v >= 128 else 0)
    outline = mask.filter(ImageFilter.MaxFilter(5))
    background.paste((0, 0, 0), mask=outline)
    background.paste(image, mask=mask)
    return background


def test_stroke_tracking_survives_moving_background_and_edges_do_not(text_image):
    from videocaptioner.core.ocr.models import FrameSpan
    from videocaptioner.core.ocr.tracking import RegionTracker, edge_signature, stroke_signature

    def run(signature):
        tracker, output = RegionTracker(signature=signature), []
        images = [moving_scene(text_image, "", i) for i in range(2)]
        images += [moving_scene(text_image, "学生三人，2026年。", i) for i in range(2, 10)]
        images += [moving_scene(text_image, "第二句话", i) for i in range(10, 14)]
        images += [moving_scene(text_image, "", i) for i in range(14, 16)]
        for index, image in enumerate(images):
            roi = RoiFrame(index, index * 100, Fraction(1, 1000), Fraction(index * 100), 640, 120, image.tobytes())
            result = tracker.feed(FrameSpan(roi, Fraction(index * 100), Fraction((index + 1) * 100)))
            if result:
                output.append(result)
        result = tracker.finish()
        if result:
            output.append(result)
        return output

    strokes = run(stroke_signature)
    assert [(r.start_ms, r.end_ms) for r in strokes] == [(200, 1000), (1000, 1400)]
    assert all(r.best_pts is not None for r in strokes)
    assert len(run(edge_signature)) > 2  # panning scenery splits the same subtitle under edge tiles


def test_text_bounds_and_focus_crop_follow_the_glyphs(text_image):
    from videocaptioner.core.ocr.tracking import text_bounds
    from videocaptioner.core.ocr.vision import focus_crop

    image = moving_scene(text_image, "学生三人", 3)
    roi = RoiFrame(0, 0, Fraction(1, 1000), Fraction(0), 640, 120, image.tobytes())
    bounds = text_bounds(roi)
    assert bounds is not None
    left, top, right, bottom = bounds
    assert 0 <= left < 40 and right < 400 and 0 <= top < 40 and bottom <= 120
    crop, crop_bounds = focus_crop(roi)
    assert crop_bounds == bounds and (crop.width, crop.height) == (right - left, bottom - top)
    blank = RoiFrame(1, 100, Fraction(1, 1000), Fraction(100), 640, 120, moving_scene(text_image, "", 5).tobytes())
    assert text_bounds(blank) is None and focus_crop(blank)[1] == (0, 0, 640, 120)
