"""CLI speech preparation must preserve pause marks and honor requested splitting."""
from videocaptioner.cli.main import main
from videocaptioner.core.split.split import SubtitleSplitter


def test_requested_segmentation_runs_for_legacy_sentence_timing(tmp_path, monkeypatch):
    source = tmp_path / "source.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:04,000\nNếu trời mưa, chúng ta sẽ ở nhà.\n", encoding="utf-8")
    target = tmp_path / "out.srt"
    seen = []

    def split(self, data):
        seen.append(data.segments[0].text)
        return data

    monkeypatch.setattr(SubtitleSplitter, "split_subtitle", split)
    code = main(["subtitle", str(source), "-o", str(target), "--no-optimize", "--no-translate",
                 "--api-key", "synthetic", "--api-base", "https://translation.invalid/v1",
                 "--model", "offline-test", "-q"])
    assert code == 0 and seen == ["Nếu trời mưa, chúng ta sẽ ở nhà."]


def test_cli_keeps_punctuation_in_both_languages(tmp_path, monkeypatch):
    source = tmp_path / "source.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:04,000\n请等一下。\n", encoding="utf-8")
    target = tmp_path / "out.srt"

    class Translator:
        def translate_subtitle(self, data):
            result = data.with_segments([s.clone() for s in data])
            result.segments[0].translated_text = "请稍候，别着急。"
            return result

        def close(self):
            pass

        stop = close

    monkeypatch.setattr("videocaptioner.core.translate.factory.TranslatorFactory.create_translator",
                        lambda **kwargs: Translator())
    code = main(["subtitle", str(source), "-o", str(target), "--no-optimize", "--no-split",
                 "--translator", "llm", "--target-language", "zh-Hans", "--layout", "target-above",
                 "--api-key", "synthetic", "--api-base", "https://translation.invalid/v1",
                 "--model", "offline-test", "-q"])
    assert code == 0
    assert "请稍候，别着急。\n请等一下。" in target.read_text(encoding="utf-8")
