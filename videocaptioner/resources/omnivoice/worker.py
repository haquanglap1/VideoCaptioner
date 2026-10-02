"""Isolated OmniVoice JSON-line worker. Never imported by the Qt application."""
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false

import argparse
import contextlib
import gc
import hashlib
import json
import logging
import math
import sys
import time
from pathlib import Path


def load_prompt(path, torch):
    from omnivoice.models.omnivoice import VoiceClonePrompt
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Prompt cache is oversized")
    value = json.loads(path.read_text(encoding="utf-8"))
    tokens = value["tokens"]
    if (value["schema"] != "omnivoice-tokens-v1" or not isinstance(value["text"], str)
        or not value["text"] or not math.isfinite(value["rms"]) or not 0 < value["rms"] <= 10
        or not isinstance(tokens, list) or len(tokens) != 8
        or not isinstance(tokens[0], list) or not 1 <= len(tokens[0]) <= 3000
        or any(not isinstance(row, list) or len(row) != len(tokens[0]) for row in tokens)
        or any(type(token) is not int or not 0 <= token < 1024 for row in tokens for token in row)):
        raise ValueError("Invalid cached reference prompt")
    return VoiceClonePrompt(ref_audio_tokens=torch.tensor(tokens, dtype=torch.long),
        ref_text=value["text"], ref_rms=value["rms"])


def save_prompt(path, prompt):
    path.write_text(json.dumps({"schema": "omnivoice-tokens-v1",
        "tokens": prompt.ref_audio_tokens.detach().cpu().tolist(),
        "text": prompt.ref_text, "rms": float(prompt.ref_rms)},
        ensure_ascii=False, allow_nan=False), encoding="utf-8")


def synchronize(torch):
    if hasattr(torch, "cuda"):
        torch.cuda.synchronize()


def inference_metrics(torch, started) -> dict:
    synchronize(torch)
    result = {"generation_seconds": time.monotonic() - started}
    if hasattr(torch, "cuda"):
        result.update(peak_allocated_bytes=torch.cuda.max_memory_allocated(),
            peak_reserved_bytes=torch.cuda.max_memory_reserved())
    return result


def generate_batch(model, prompt, request, scratch, send, torch, np, sf, max_batch=4):
    """A bounded split tree retries only unfinished items after a model failure."""
    items = request["items"]
    limit = max_batch
    if not isinstance(items, list) or not 1 <= len(items) <= 4:
        raise ValueError("Invalid batch size")
    ids = [item["id"] for item in items]
    if len(set(ids)) != len(ids) or any(not isinstance(item_id, str) for item_id in ids):
        raise ValueError("Invalid batch IDs")
    for item in items:
        destination = Path(item["output"]).resolve()
        if not destination.is_relative_to(scratch) or destination.suffix != ".wav":
            raise ValueError("Output must be an owned WAV file")
        if not isinstance(item["text"], str) or not item["text"].strip():
            raise ValueError("Empty batch text")
    if prompt is None and request.get("voice", "auto") != "auto":
        raise ValueError("A fixed voice requires its reference audio and transcript")

    def emit(value):
        send({**value, "request_id": request["request_id"]})

    def run(group):
        nonlocal limit
        if len(group) > limit:
            emit({"status": "fallback", "ids": [item["id"] for item in group],
                "batch_size": len(group), "reason": "ReducedAfterOutOfMemoryError"})
            chunk_size = limit
            for start in range(0, len(group), chunk_size):
                run(group[start:start + chunk_size])
            return
        texts = [item["text"] for item in group]
        context = hashlib.sha256(json.dumps(texts, ensure_ascii=False).encode("utf-8")).hexdigest()
        torch.manual_seed(request["seed"])
        synchronize(torch)
        if hasattr(torch, "cuda"):
            torch.cuda.reset_peak_memory_stats()
        started = time.monotonic()
        error = ""
        audios = None
        try:
            audios = model.generate(text=texts, language=request["language"], voice_clone_prompt=prompt,
                speed=request["speed"], num_step=request["steps"])
            if len(audios) != len(group):
                raise ValueError("Batch result count mismatch")
        except Exception as exc:
            error = type(exc).__name__
        metrics = inference_metrics(torch, started)
        metrics.update(batch_size=len(group), context_sha256=context, error_type=error)
        emit({"status": "metrics", "metrics": metrics})
        if error:
            # Leave the exception scope before retrying, so traceback tensors do not retain VRAM.
            audios = None
            gc.collect()
            if hasattr(torch, "cuda"):
                torch.cuda.empty_cache()
            if len(group) > 1:
                if error == "OutOfMemoryError":
                    limit = min(limit, max(1, len(group) // 2))
                emit({"status": "fallback", "ids": [item["id"] for item in group],
                    "batch_size": len(group), "reason": error})
                half = len(group) // 2
                run(group[:half])
                run(group[half:])
            else:
                emit({"status": "item", "id": group[0]["id"], "error_type": error})
            return
        assert audios is not None
        for item, audio in zip(group, audios):
            try:
                if not len(audio) or not np.isfinite(audio).all():
                    raise ValueError("Invalid audio")
                sf.write(item["output"], audio, model.sampling_rate, subtype="PCM_16")
                emit({"status": "item", "id": item["id"], "samples": len(audio), "actual_batch_size": len(group)})
            except Exception as exc:
                emit({"status": "item", "id": item["id"], "error_type": type(exc).__name__})

    run(items)
    emit({"status": "complete", "count": len(items)})
    return limit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()
    scratch = Path(args.scratch).resolve()
    output = sys.stdout

    def send(value):
        output.write("VC_OMNI " + json.dumps(value, ensure_ascii=False) + "\n")
        output.flush()

    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import soundfile as sf
        import torch
        from omnivoice import OmniVoice

        logging.disable(logging.INFO)
        started = time.monotonic()
        model = OmniVoice.from_pretrained(args.model, device_map="cuda:0", dtype=torch.float16,
                                          load_asr=False, local_files_only=True)
        synchronize(torch)
        send({"status": "ready", "sample_rate": model.sampling_rate,
              "metrics": {"model_load_seconds": time.monotonic() - started}})
        prompt = None
        batch_limit = 4
        for line in sys.stdin:
            request = {}
            try:
                request = json.loads(line)
                operation = request["operation"]
                if operation == "configure":
                    started = time.monotonic()
                    prompt = None
                    cache_hit = False
                    ref_audio, ref_text = request.get("reference_audio"), request.get("reference_text")
                    if bool(ref_audio) != bool(ref_text):
                        raise ValueError("Both reference audio and transcript are required")
                    if ref_audio:
                        if not Path(ref_audio).resolve().is_relative_to(scratch):
                            raise ValueError("Reference must be an owned snapshot")
                        prompt_file = Path(request["prompt_file"]).resolve() if request.get("prompt_file") else None
                        if prompt_file and not prompt_file.is_relative_to(scratch):
                            raise ValueError("Prompt must be an owned snapshot")
                        if prompt_file and prompt_file.is_file():
                            try:
                                prompt = load_prompt(prompt_file, torch)
                                cache_hit = True
                            except (OSError, ValueError, KeyError, TypeError, IndexError):
                                prompt = None
                        if prompt is None:
                            # Reset encoding RNG too, so a warm prompt does not shift synthesis RNG.
                            torch.manual_seed(0)
                            prompt = model.create_voice_clone_prompt(ref_audio=ref_audio, ref_text=ref_text,
                                preprocess_prompt=True)
                            if prompt_file:
                                save_prompt(prompt_file, prompt)
                    synchronize(torch)
                    send({"status": "configured", "metrics": {"prompt_cache_hit": cache_hit,
                        "prompt_seconds": time.monotonic() - started}})
                    continue
                if operation == "synthesize_batch":
                    batch_limit = generate_batch(model, prompt, request, scratch, send, torch, np, sf, batch_limit)
                    continue
                if operation != "synthesize":
                    raise ValueError("Unknown worker operation")
                destination = Path(request["output"]).resolve()
                if not destination.is_relative_to(scratch) or destination.suffix != ".wav":
                    raise ValueError("Output must be an owned WAV file")
                voice = request.get("voice", "auto")
                if prompt is None and voice != "auto":
                    raise ValueError("A fixed voice requires its reference audio and transcript")
                torch.manual_seed(request["seed"])
                synchronize(torch)
                if hasattr(torch, "cuda"):
                    torch.cuda.reset_peak_memory_stats()
                started = time.monotonic()
                audio = model.generate(text=request["text"], language=request["language"],
                    voice_clone_prompt=prompt,
                    speed=request["speed"], num_step=request["steps"])[0]
                metrics = inference_metrics(torch, started)
                if not len(audio) or not np.isfinite(audio).all():
                    raise ValueError("OmniVoice produced invalid audio")
                sf.write(str(destination), audio, model.sampling_rate, subtype="PCM_16")
                send({"status": "complete", "sample_rate": model.sampling_rate,
                      "samples": len(audio), "metrics": metrics})
            except Exception as exc:
                # Do not echo private text, reference paths, or a provider traceback.
                send({"status": "error", "error_type": type(exc).__name__, "request_id": request.get("request_id")})


if __name__ == "__main__":
    main()
