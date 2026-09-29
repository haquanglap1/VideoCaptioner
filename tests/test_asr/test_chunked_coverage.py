"""Verify PCM coverage before encoding, independently of recognition quality."""

import io
import shutil
from array import array

import pytest
from pydub import AudioSegment

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.chunked_asr import ChunkedASR


@pytest.mark.parametrize("overlap_ms", [0, 2000])
@pytest.mark.parametrize("tail_ms", [0, 1, 30, 500, 999, 1000])
def test_short_tail_is_included_before_encoding(tmp_path, monkeypatch, overlap_ms, tail_ms):
    # The final signal is nonzero: a short remainder is not proof of padding.
    covered_ms = 20000 - overlap_ms
    samples = array("h", [0]) * (covered_ms * 16)
    samples.extend(array("h", [9000, -9000]) * (tail_ms * 8))
    audio = AudioSegment(samples.tobytes(), sample_width=2, frame_rate=16000, channels=1)
    source = tmp_path / "source.wav"
    audio.export(source, format="wav")
    exported = []

    def capture_export(part, output, format):
        assert format == "mp3"
        exported.append(part)
        output.write(b"encoded-placeholder")

    monkeypatch.setattr(AudioSegment, "export", capture_export)
    engine = ChunkedASR(object, str(source), chunk_length=10, chunk_overlap=overlap_ms // 1000)
    chunks = engine._split_audio()

    expected_offsets = [0, 10000 - overlap_ms]
    if tail_ms >= 1000:
        expected_offsets.append(20000 - 2 * overlap_ms)
    assert [offset for _, offset in chunks] == expected_offsets
    covered_samples = 0
    reconstructed = bytearray()
    for part, (_, offset) in zip(exported, chunks):
        start_sample = offset * 16
        assert start_sample <= covered_samples
        skip_samples = covered_samples - start_sample
        reconstructed.extend(part.raw_data[skip_samples * part.frame_width:])
        covered_samples = start_sample + int(part.frame_count())
    assert covered_samples == int(audio.frame_count())
    assert reconstructed == audio.raw_data


def test_final_chunk_keeps_samples_beyond_rounded_millisecond(tmp_path, monkeypatch):
    audio = AudioSegment(
        b"\x00\x00" * (20500 * 16) + b"\x23\x45" * 7,
        sample_width=2, frame_rate=16000, channels=1,
    )
    source = tmp_path / "fractional-tail.wav"
    audio.export(source, format="wav")
    exported = []

    def capture_export(part, output, format):
        exported.append(part.raw_data)
        output.write(b"encoded-placeholder")

    monkeypatch.setattr(AudioSegment, "export", capture_export)
    chunks = ChunkedASR(object, str(source), chunk_length=10, chunk_overlap=0)._split_audio()
    assert [offset for _, offset in chunks] == [0, 10000]
    joined = b"".join(exported)
    assert len(joined) == len(audio.raw_data)
    assert joined == audio.raw_data


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
                    reason="FFmpeg and ffprobe are required for the real MP3 roundtrip")
def test_short_tail_reaches_provider_and_merged_subtitle(tmp_path):
    # Only the final 500 ms has a signal; the provider is deliberately a fake.
    from pydub.generators import Sine

    audio = AudioSegment.silent(20000, frame_rate=16000) + Sine(440, sample_rate=16000).to_audio_segment(500)
    source = tmp_path / "tail-marker.wav"
    audio.export(source, format="wav")
    received = []

    class SignalProvider:
        def __init__(self, binary):
            self.binary = binary

        def run(self, callback=None):
            decoded = AudioSegment.from_file(io.BytesIO(self.binary), format="mp3")
            received.append(len(decoded))
            if decoded[-300:].rms > 500:
                return ASRData([ASRDataSeg("Tail marker.", len(decoded) - 500, len(decoded))])
            return ASRData([])

    result = ChunkedASR(SignalProvider, str(source), chunk_length=10, chunk_overlap=0,
                        chunk_concurrency=1).run()
    assert len(received) == 2
    assert abs(received[-1] - 10500) < 100
    assert len(result.segments) == 1
    assert result.segments[0].text == "Tail marker."
    assert abs(result.segments[0].start_time - 20000) < 100
    assert abs(result.segments[0].end_time - 20500) < 100
