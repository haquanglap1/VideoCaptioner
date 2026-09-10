"""Prepare shared native-resolution OCR crops, run an isolated worker, and score raw text.

Pilot evidence only: this does not implement video tracking or export accepted subtitles.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import unicodedata
from fractions import Fraction
from pathlib import Path

from scripts.package_test_models import digest
from videocaptioner.core.utils.subprocess_helper import child_environment


def run(command, **kwargs):
    return subprocess.run([str(value) for value in command], env=child_environment(),
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                          check=kwargs.pop("check", True), timeout=300, **kwargs)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def nearest_frame(frames, requested_ms, time_base):
    """Select a real presentation timestamp; break an exact tie toward the earlier frame."""
    target = Fraction(requested_ms, 1000)
    return min(frames, key=lambda frame: (abs(int(frame["pts"]) * time_base - target), int(frame["pts"])))


def prepare(args):
    begun = time.perf_counter()
    target = args.output.resolve()
    target.mkdir(parents=True, exist_ok=False)
    source = args.evidence / "inputs/sample-zh.mp4"
    mapping = args.evidence / "reports/source-caption-visibility-refined.json"
    candidates = json.loads(mapping.read_text(encoding="utf-8"))["candidates"]
    # This pilot intentionally supports only the inspected sample geometry.
    probe = json.loads(run([args.ffprobe, "-v", "error", "-select_streams", "v:0", "-show_streams",
                            "-show_frames", "-show_entries",
                            "stream=index,width,height,time_base,start_pts,sample_aspect_ratio,duration:"
                            "stream_tags=rotate:stream_side_data=rotation:frame=pts,pts_time,duration",
                            "-of", "json", source], capture_output=True).stdout)
    stream = probe["streams"][0]
    if ((stream["width"], stream["height"]) != (1920, 1080)
            or stream.get("sample_aspect_ratio") != "1:1"
            or stream.get("start_pts") != 0 or stream.get("side_data_list")
            or stream.get("tags", {}).get("rotate", "0") != "0"):
        raise ValueError("This pilot needs the original 1920x1080 square-pixel, zero-start, unrotated sample")
    frames = probe["frames"]
    time_base = Fraction(stream["time_base"])
    if any("pts" not in frame for frame in frames):
        raise ValueError("Missing source PTS")
    selected = [nearest_frame(frames, row["representative_ms"], time_base) for row in candidates]
    pts = [frame["pts"] for frame in selected]
    if pts != sorted(set(pts)):
        raise ValueError("Representative source frames must be unique and ordered")
    selection = "+".join(f"eq(pts,{value})" for value in pts)
    filter_graph = f"select='{selection}',crop=1920:80:0:960,showinfo"
    decoding = time.perf_counter()
    result = run([args.ffmpeg, "-hide_banner", "-nostdin", "-n", "-i", source, "-map", "0:v:0",
                  "-vf", filter_graph, "-frames:v", len(selected), "-fps_mode", "passthrough",
                  "-c:v", "png", "-pix_fmt", "rgb24", target / "crop-%02d.png"], capture_output=True)
    decode_s = time.perf_counter() - decoding
    observed = [int(value) for value in re.findall(rb"\bn:\s*\d+\s+pts:\s*(\d+)", result.stderr)]
    if observed != pts:
        raise ValueError("FFmpeg crop/PTS alignment mismatch")
    (target / "decode.log").write_bytes(result.stderr)
    crops = []
    for index, (candidate, frame) in enumerate(zip(candidates, selected), 1):
        path = target / f"crop-{index:02d}.png"
        actual_ms = int(frame["pts"]) * time_base * 1000
        crops.append({"id": f"crop-{index:02d}", "file": path.name, "sha256": digest(path),
                      "size": path.stat().st_size, "width": 1920, "height": 80,
                      "representative_ms": candidate["representative_ms"], "pts": frame["pts"],
                      "time_base": str(time_base), "pts_ms_exact": str(actual_ms),
                      "pts_ms": float(actual_ms),
                      "representative_delta_ms": float(actual_ms - candidate["representative_ms"]),
                      "prototype_start_ms": candidate["start_ms"], "prototype_end_ms": candidate["end_ms"]})
    manifest = {"schema": "ocr-pilot-inputs-v1", "source_sha256": digest(source),
                "mapping_sha256": digest(mapping), "source_stream": stream,
                "roi_pixels": [0, 960, 1920, 80], "roi_normalized": [0, 960/1080, 1, 80/1080],
                "selection": "Nearest original PTS, ties choose earlier; no fps filter",
                "boundary_accuracy_ms": None, "actual_source_frames_probed": len(frames),
                "decode_s": decode_s, "preparation_wall_s": time.perf_counter() - begun,
                "crops": crops}
    save(target / "manifest.json", manifest)
    print(json.dumps({"crops": len(crops), "decode_s": decode_s,
                      "max_pts_delta_ms": max(abs(row["representative_delta_ms"]) for row in crops)}))


def execute(args):
    if args.output.exists():
        raise ValueError("Use a new output directory; earlier measurements are preserved")
    root = args.root.resolve()
    python = root / "env/python.exe"
    if not python.exists():
        python = root / "env/Scripts/python.exe"
    begun = time.perf_counter()
    result = run([python, "-I", root / "bridge/ocr_pilot_worker.py", "--root", root,
                  "--inputs", args.inputs.resolve(), "--output", args.output.resolve()],
                 capture_output=True, check=False)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "worker.stderr.log").write_bytes(result.stderr)
    (args.output / "worker.stdout.log").write_bytes(result.stdout)
    save(args.output / "process.json", {"exit_code": result.returncode,
                                         "process_wall_s": time.perf_counter() - begun})
    print(result.stdout.decode("utf-8", errors="replace"))
    if result.returncode:
        print(result.stderr.decode("utf-8", errors="replace"))
        raise SystemExit(result.returncode)


def fixtures(args):
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    args.output.mkdir(parents=True, exist_ok=False)
    font = ImageFont.truetype(str(args.font), 32)
    texts = ["学生三人，2026年。", "學生三人，2026年。", "学生五人，2026年。",
             "玄青带来12件礼物\n玄清带来13件礼物", "", "学生三人，2026年。"]
    crops, reference = [], []
    for index, text in enumerate(texts, 1):
        image = Image.new("RGB", (800, 120), "black")
        ImageDraw.Draw(image).multiline_text((30, 10), text, font=font, fill="white", spacing=8)
        if index == 6:
            image = image.filter(ImageFilter.GaussianBlur(1.2))
        path = args.output / f"crop-{index:02d}.png"
        image.save(path)
        crops.append({"id": f"crop-{index:02d}", "file": path.name, "sha256": digest(path)})
        reference.append({"source_text": text})
    save(args.output / "manifest.json", {"schema": "ocr-pilot-inputs-v1", "synthetic": True,
                                         "font_sha256": digest(args.font), "crops": crops})
    save(args.output / "reference.json", {"synthetic": True, "cues": reference})


def edit_distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for index, char in enumerate(reference, 1):
        current = [index]
        for other, actual in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[other] + 1,
                               previous[other - 1] + (char != actual)))
        previous = current
    return previous[-1]


def letters_numbers(value):
    return "".join(char for char in value if unicodedata.category(char)[0] in "LN")


def score(args):
    reference = json.loads(args.reference.read_text(encoding="utf-8"))["cues"]
    raw = [json.loads(line) for line in args.raw.read_text(encoding="utf-8").splitlines()]
    if len(reference) != len(raw) or [row["id"] for row in raw] != [f"crop-{i:02d}" for i in range(1, len(raw)+1)]:
        raise ValueError("Reference/raw crop mapping mismatch")
    rows = []
    for expected, actual in zip(reference, raw):
        text = "\n".join(actual["texts"])
        target = expected["source_text"]
        rows.append({"id": actual["id"], "reference": target, "hypothesis": text,
                     "exact": text == target, "edit_distance": edit_distance(target, text),
                     "letters_numbers_distance": edit_distance(letters_numbers(target), letters_numbers(text)),
                     "reference_chars": len(target), "reference_letters_numbers": len(letters_numbers(target)),
                     "error": actual["error"], "scores": actual["scores"]})
    report = {"reference_status": "See reference provenance; metric does not establish ground truth",
              "raw_sha256": digest(args.raw), "reference_sha256": digest(args.reference), "crops": rows,
              "exact_crops": sum(row["exact"] for row in rows),
              "character_errors": sum(row["edit_distance"] for row in rows),
              "reference_chars": sum(row["reference_chars"] for row in rows),
              "letters_numbers_errors": sum(row["letters_numbers_distance"] for row in rows),
              "reference_letters_numbers": sum(row["reference_letters_numbers"] for row in rows)}
    save(args.output, report)
    print(json.dumps({key: value for key, value in report.items() if key != "crops"}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    for name in ("evidence", "ffmpeg", "ffprobe", "output"):
        prep.add_argument("--" + name, type=Path, required=True)
    worker = commands.add_parser("run")
    for name in ("root", "inputs", "output"):
        worker.add_argument("--" + name, type=Path, required=True)
    scoring = commands.add_parser("score")
    for name in ("reference", "raw", "output"):
        scoring.add_argument("--" + name, type=Path, required=True)
    synthetic = commands.add_parser("fixtures")
    for name in ("font", "output"):
        synthetic.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    {"prepare": prepare, "run": execute, "score": score, "fixtures": fixtures}[args.command](args)


if __name__ == "__main__":
    main()
