"""Real subprocess fault injection: exercise pipes, termination and reader joins."""

import subprocess
import sys
import time
from fractions import Fraction

import pytest

from videocaptioner.core.ocr.decoder import RoiDecoder
from videocaptioner.core.ocr.geometry import Roi, VideoGeometry
from videocaptioner.core.ocr.models import OcrError, VideoInfo


@pytest.mark.parametrize("behavior,error", [
    ("truncated", "Truncated"), ("missing", "no source PTS"),
    ("extra", "without an ROI frame"), ("malformed", "malformed"),
    ("reordered", "Non-increasing"), ("stall", "timed out"), ("exit", "decode failed"),
    ("oversized", "Oversized"),
])
def test_fault_closes_exact_process_and_joins_readers(tmp_path, monkeypatch, behavior, error):
    source = tmp_path / "synthetic.bin"
    source.write_bytes(b"fixture")
    real_popen = subprocess.Popen
    code = """
import sys,time
kind = sys.argv[1]
def meta(index, pts):
    sys.stderr.write(f'[showinfo] n: {index} pts: {pts} pts_time:0 fmt:rgb24 s:2x2\\n')
    sys.stderr.flush()
sys.stderr.write('[showinfo] config in time_base: 1/1000\\n')
sys.stderr.flush()
if kind == 'stall':
    time.sleep(20)
elif kind == 'exit':
    sys.exit(7)
elif kind == 'oversized':
    sys.stderr.write('x'*17000+'\\n'); sys.stderr.flush()
elif kind == 'extra':
    meta(0, 0)
elif kind == 'malformed':
    meta(0, 'NOPTS'); sys.stdout.buffer.write(b'x'*12)
elif kind == 'missing':
    sys.stdout.buffer.write(b'x'*12)
elif kind == 'truncated':
    meta(0, 0); sys.stdout.buffer.write(b'x'*5)
elif kind == 'reordered':
    meta(0, 10); meta(1, 5); sys.stdout.buffer.write(b'x'*24)
sys.stdout.flush()
"""

    def launch(_command, **kwargs):
        return real_popen([sys.executable, "-I", "-c", code, behavior], **kwargs)

    monkeypatch.setattr("videocaptioner.core.ocr.decoder.subprocess.Popen", launch)
    # Windows taskkill uses subprocess.run/Popen; restore Popen only for the tree killer.
    from videocaptioner.core.ocr import decoder as module
    real_stop = module.stop_owned_process

    def stop(process):
        monkeypatch.setattr(subprocess, "Popen", real_popen)
        real_stop(process)

    monkeypatch.setattr(module, "stop_owned_process", stop)
    info = VideoInfo(0, VideoGeometry(2, 2), Fraction(1, 1000), Fraction(0))
    decoder = RoiDecoder(source, info, Roi(0, 0, 1, 1), timeout=0.4)
    started = time.monotonic()
    with pytest.raises(OcrError, match=error), decoder:
        list(decoder)
    assert time.monotonic() - started < 5
    assert decoder.process.poll() is not None
    assert all(not thread.is_alive() for thread in decoder.readers)


def test_no_heavy_imports_in_clean_host_and_context_propagation(tmp_path, ffmpeg_tools, make_video, text_image):
    from videocaptioner.core.llm.context import (
        clear_task_context,
        get_task_context,
        set_task_context,
    )
    from videocaptioner.core.ocr.decoder import probe_video
    from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

    code = """
import sys
from videocaptioner.core.ocr import decoder, pipeline, tracking, consensus, runtime
assert not any(name in sys.modules for name in ('numpy','cv2','onnxruntime','torch','paddle','PyQt5'))
"""
    subprocess.run([sys.executable, "-c", code], check=True, timeout=15,
                   env=child_environment(), creationflags=_NO_WINDOW, capture_output=True)
    ffmpeg, ffprobe = ffmpeg_tools
    source = make_video([text_image()] * 2)
    decoder = RoiDecoder(source, probe_video(source, ffprobe), Roi(0, 0, 1, 1), ffmpeg=ffmpeg)
    seen = []
    original = decoder._stderr

    def record():
        seen.append(get_task_context().task_id)
        original()

    decoder._stderr = record
    set_task_context("ocr-fixture", "synthetic", "ocr")
    try:
        with decoder:
            list(decoder)
    finally:
        clear_task_context()
    assert seen == ["ocr-fixture"]
