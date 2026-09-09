"""External S5 worker. Never imported by the host; stdout is a bounded control protocol."""
# pyright: reportMissingImports=false
# GPU imports below are validated in the separately locked runtime, not the Qt environment.

import contextlib
import importlib.metadata
import json
import os
import socket
import sys
import time
import wave
from pathlib import Path


def emit(value):
    print(json.dumps(value), flush=True)


def deny_network(*args, **kwargs):
    raise RuntimeError("Network disabled during local inference")


def raw_timestamp(value):
    return value.tolist()


class IncompleteGeneration(RuntimeError):
    """A generation budget is exhausted; partial text must not leave the worker."""


def recognition_token_limit(frames):
    # A generous speech budget bounds degenerate decoding, not accepted text length.
    # Exhaustion requests a smaller audio window; only EOS-complete text is returned.
    return min(8192, 256 + (frames * 32 + 15999) // 16000)


def require_completed_generation(result, eos):
    eos = [eos] if isinstance(eos, int) else eos
    if not eos or any(int(row[-1]) not in eos for row in result.sequences):
        raise IncompleteGeneration("Recognition generation did not finish; review required")


def main():
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    root, model_id = Path(sys.argv[1]), sys.argv[2]
    manifest = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))
    recipe = manifest["recipe"]
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Python mismatch")
    for package, version in recipe["versions"].items():
        if importlib.metadata.version(package) != version:
            raise RuntimeError("Runtime version mismatch")
    model_path = root / "models" / model_id
    started = time.monotonic()
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        import numpy as np
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable")
        torch.zeros(1, device="cuda").sum().item()
        if model_id == "community-1":
            from pyannote.audio import Pipeline
            model = Pipeline.from_pretrained(str(model_path))
            model.to(torch.device("cuda"))
        elif model_id == "aligner":
            from qwen_asr import Qwen3ForcedAligner
            model = Qwen3ForcedAligner.from_pretrained(str(model_path), dtype=torch.bfloat16,
                    device_map="cuda:0", attn_implementation="sdpa", local_files_only=True)
            model.aligner_processor.fix_timestamp = raw_timestamp
        else:
            from qwen_asr import Qwen3ASRModel
            model = Qwen3ASRModel.from_pretrained(str(model_path), dtype=torch.bfloat16,
                    device_map="cuda:0", attn_implementation="sdpa", local_files_only=True,
                    max_inference_batch_size=1, max_new_tokens=8192)
            generate = model.model.generate
            generation_metrics = {}

            def checked_generate(*args, **kwargs):
                result = generate(*args, **kwargs)
                generation_metrics["generated_tokens"] = int(result.sequences.shape[1] - kwargs["input_ids"].shape[1])
                eos = model.model.generation_config.eos_token_id
                require_completed_generation(result, eos)
                return result

            model.model.generate = checked_generate
    identity = {"status": "ready", "protocol": "local-asr-v1", "model": model_id,
                "revision": manifest["models"][model_id]["revision"]}
    emit({**identity, "load_seconds": time.monotonic() - started,
          "peak_vram_bytes": torch.cuda.max_memory_allocated()})
    for line in sys.stdin:
        request_root = Path(json.loads(line)["directory"])
        request = json.loads((request_root / "request.json").read_text(encoding="utf-8"))
        with wave.open(str(request_root / "audio.wav"), "rb") as handle:
            if handle.getframerate() != 16000 or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                raise ValueError("Invalid PCM input")
            frames = handle.getnframes()
            if frames <= 0 or (model_id != "community-1" and frames > 240_000 * 16):
                raise ValueError("Invalid audio duration")
            waveform = np.frombuffer(handle.readframes(frames), dtype=np.int16).astype(np.float32) / 32768.0
        started = time.monotonic()
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            if model_id == "community-1":
                output = model({"waveform": torch.from_numpy(waveform).unsqueeze(0), "sample_rate": 16000})
                result = [{"start_ms": round(turn.start * 1000), "end_ms": round(turn.end * 1000),
                           "speaker": speaker} for turn, speaker in output.speaker_diarization]
            elif model_id == "aligner":
                output = model.align(audio=(waveform, 16000), text=request["text"], language="Chinese")[0]
                result = [{"text": item.text, "start_ms": round(item.start_time * 1000),
                           "end_ms": round(item.end_time * 1000)} for item in output]
            else:
                model.max_new_tokens = recognition_token_limit(frames)
                generation_metrics.clear()
                generation_metrics["token_limit"] = model.max_new_tokens
                try:
                    output = model.transcribe(audio=(waveform, 16000), language="Chinese", return_time_stamps=False)
                except IncompleteGeneration:
                    # Keep the loaded model for a smaller retry; no partial result file.
                    with contextlib.redirect_stdout(sys.__stdout__):
                        emit({**identity, "status": "incomplete", "reason": "generation-limit",
                              **generation_metrics, "inference_seconds": time.monotonic() - started})
                    continue
                if len(output) != 1:
                    raise ValueError("Recognition batch mismatch")
                result = {"text": output[0].text, "language": output[0].language}
        (request_root / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        emit({**identity, **(generation_metrics if model_id.startswith("qwen-") else {}),
              "inference_seconds": time.monotonic() - started,
              "peak_vram_bytes": torch.cuda.max_memory_allocated()})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit({"status": "error", "reason": "oom" if "out of memory" in str(exc).lower() else "inference"})
        sys.exit(1)
