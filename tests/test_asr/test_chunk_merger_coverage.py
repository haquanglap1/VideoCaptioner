"""Synthetic timing evidence: repeated speech at distinct times must survive merging."""

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.chunk_merger import ChunkMerger
from videocaptioner.core.asr.chunked_asr import ChunkedASR


def _chunk(texts):
    return ASRData([
        ASRDataSeg(text, index * 1000, (index + 1) * 1000, f"translation {index}")
        for index, text in enumerate(texts)
    ])


def _values(data):
    return [(seg.text, seg.start_time, seg.end_time, seg.translated_text) for seg in data.segments]


@pytest.mark.parametrize("texts", [("go", "now"), ("Please wait here.", "We will return.")])
@pytest.mark.parametrize("gap_ms", [0, 1, 8000])
def test_repeated_speech_at_disjoint_times_is_preserved(texts, gap_ms):
    left, right = _chunk(texts), _chunk(texts)
    before = [_values(left), _values(right)]
    offset = 2000 + gap_ms
    merged = ChunkMerger().merge_chunks([left, right], [0, offset], overlap_duration=10000)

    expected = before[0] + [(text, start + offset, end + offset, translated)
                            for text, start, end, translated in before[1]]
    assert _values(merged) == expected
    assert [_values(left), _values(right)] == before


@pytest.mark.parametrize("texts", [("go", "now"), ("Please wait here.", "We will return.")])
@pytest.mark.parametrize("offsets", [[0, 1000], None])
def test_same_speech_in_actual_overlap_still_merges(texts, offsets):
    left = _chunk(("opening", *texts))
    right = _chunk((*texts, "closing"))
    merged = ChunkMerger().merge_chunks([left, right], offsets, overlap_duration=2000)
    assert [(s.text, s.start_time, s.end_time) for s in merged.segments] == [
        (text, i * 1000, (i + 1) * 1000) for i, text in enumerate(("opening", *texts, "closing"))
    ]


@pytest.mark.parametrize("empty_middle", [True, False])
def test_chunked_provider_repetitions_survive_empty_chunk_and_srt(tmp_path, monkeypatch, empty_middle):
    source = tmp_path / "synthetic.input"
    source.write_bytes(b"unused: splitter is replaced by synthetic chunks")
    responses = {b"first": _chunk(("go", "now")), b"middle": ASRData([]) if empty_middle else _chunk(("go", "now")),
                 b"last": _chunk(("go", "now"))}

    class SavedProvider:
        def __init__(self, audio_input, **kwargs):
            self.data = responses[audio_input]

        def run(self, callback=None):
            return self.data

    engine = ChunkedASR(SavedProvider, str(source), chunk_length=20, chunk_overlap=10)
    monkeypatch.setattr(engine, "_split_audio", lambda: [(b"first", 0), (b"middle", 10000), (b"last", 20000)])
    result = engine.run()
    expected = [("go", 0, 1000), ("now", 1000, 2000), ("go", 20000, 21000), ("now", 21000, 22000)]
    if not empty_middle:
        expected[2:2] = [("go", 10000, 11000), ("now", 11000, 12000)]
    assert [(s.text, s.start_time, s.end_time) for s in result.segments] == expected
    path = tmp_path / "repeated.srt"
    result.to_srt(save_path=str(path))
    reopened = ASRData.from_subtitle_file(str(path))
    assert [(s.text, s.start_time, s.end_time) for s in reopened.segments] == expected
