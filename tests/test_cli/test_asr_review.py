"""Local review CLI must not fall through to recognition or accept partial output."""

from videocaptioner.cli.main import main
from videocaptioner.core.asr.review import NativeReview


def test_cli_report_edit_and_resume_without_provider(tmp_path, monkeypatch):
    review = NativeReview.capture({"text": "合成", "tokens": [
        {"text": "合成", "start_ms": 100, "end_ms": 100, "speaker": "1"}]},
        "soniox", "synthetic-model", "request", 1000, True, True)
    source = review.save(tmp_path / "review.json")
    out, saved = tmp_path / "full.srt", tmp_path / "edited.json"
    monkeypatch.setattr("videocaptioner.core.asr.native_api.NativeASR.run",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Must not upload")))
    assert main(["asr-review", str(source), "-o", str(out)]) == 5
    assert not out.exists()
    assert main(["asr-review", str(source), "--set-timing", "token-000001:100:900",
                 "--save-review", str(saved), "-o", str(out)]) == 0
    assert out.exists() and NativeReview.load(saved).overrides
    assert NativeReview.load(source).issues()
    assert main(["asr-review", str(saved), "-o", str(saved)]) == 2
    assert main(["asr-review", str(source), "--set-timing", "token-000001:100:100"]) == 2


def test_cli_300_second_timeout_reaches_translator_and_closes_it(tmp_path, monkeypatch):
    from types import SimpleNamespace
    source = tmp_path / "source.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nSynthetic sentence\n", encoding="utf-8")
    seen, closed = [], []
    def factory(**kwargs):
        seen.append(kwargs)
        return SimpleNamespace(translate_subtitle=lambda data: data, close=lambda: closed.append(True))
    monkeypatch.setattr("videocaptioner.core.translate.factory.TranslatorFactory.create_translator", factory)
    assert main(["subtitle", str(source), "-o", str(tmp_path / "out.json"), "--no-split", "--no-optimize",
                 "--target-language", "vi", "--llm-timeout", "300", "--model", "gpt-5.6-terra",
                 "--api-key", "test-only", "--api-base", "https://test.invalid/v1", "-q"]) == 0
    assert seen[0]["request_timeout"] == 300 and seen[0]["model"] == "gpt-5.6-terra"
    assert seen[0]["credentials"].api_key == "test-only" and closed == [True]
