"""External Qwen worker. stdout is protocol only; all model output is discarded."""

import contextlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path


def emit(payload):
    print(json.dumps(payload), flush=True)


def raw_timestamp(timestamp):
    # Upstream fix_timestamp uses interpolation. Retain raw model output for host validation.
    return timestamp.tolist()


def main():
    model_path = Path(sys.argv[1])
    manifest = json.loads((model_path.parent / "runtime-manifest.json").read_text(encoding="utf-8"))
    if (sys.version_info[:2] != (3, 12) or importlib.metadata.version("qwen-asr") != "0.0.6"
            or importlib.metadata.version("torch") != "2.8.0+cu128"):
        raise RuntimeError("Runtime dependency mismatch")
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        import torch
        from qwen_asr import Qwen3ForcedAligner

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")
        torch.zeros(1, device="cuda").sum().item()
        aligner = Qwen3ForcedAligner.from_pretrained(
            str(model_path), dtype=torch.bfloat16, device_map="cuda:0",
            attn_implementation="sdpa", local_files_only=True,
        )
        aligner.aligner_processor.fix_timestamp = raw_timestamp
    emit({"status": "ready", "revision": manifest["model_revision"],
          "policy": manifest["policy"], "language": "Chinese"})
    for line in sys.stdin:
        root = Path(json.loads(line)["directory"])
        request = json.loads((root / "request.json").read_text(encoding="utf-8"))
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            result = aligner.align(audio=str(root / "audio.wav"), text=request["text"], language="Chinese")[0]
        items = [{"text": item.text, "start_ms": round(item.start_time * 1000),
                  "end_ms": round(item.end_time * 1000)} for item in result]
        (root / "result.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        emit({"status": "ready", "peak_vram_bytes": torch.cuda.max_memory_allocated()})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        emit({"status": "error"})
        sys.exit(1)
