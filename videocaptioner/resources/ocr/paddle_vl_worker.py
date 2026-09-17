"""Pinned offline PaddleOCR-VL transport. Executed only by the separate GPU Python."""

from __future__ import annotations

# pyright: reportMissingImports=false
import argparse
import hashlib
import importlib.metadata
import inspect
import json
import os
import socket
import sys
import time
from pathlib import Path


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def emit(payload):
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--profile-sha256", required=True)
    args = parser.parse_args()
    manifest = json.loads((args.root / "paddle-vl-runtime.json").read_text(encoding="utf-8"))
    model_path = (args.root / manifest["model"]).resolve()
    sys.path.insert(0, str((args.root / manifest["dependencies"]).resolve()))
    recipe_path = Path(__file__).with_name("paddle-vl.json")
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    identity = {"id": recipe["id"], "recipe_sha256": file_hash(recipe_path), "worker_sha256": file_hash(__file__)}
    revision = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                        separators=(",", ":")).encode()).hexdigest()
    if revision != args.profile_sha256:
        raise ValueError("Recognizer identity changed")
    for name, expected in recipe["model_files"].items():
        if Path(name).name != name or file_hash(model_path / name) != expected:
            raise ValueError("Model or processor hash mismatch")
    for name, version in {**recipe["packages"], **recipe["overlay_packages"]}.items():
        if importlib.metadata.version(name) != version:
            raise ValueError("Runtime package mismatch")
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1")
    os.environ.pop("HF_TOKEN", None)
    os.environ.pop("HUGGING_FACE_HUB_TOKEN", None)
    calls = {"det": 0, "rec": 0, "cls": 0}
    network_attempts = 0

    def deny_network(*_args, **_kwargs):
        nonlocal network_attempts
        network_attempts += 1
        raise RuntimeError("OCR worker is offline")

    socket.socket.connect = deny_network
    socket.create_connection = deny_network
    import torch
    from PIL import Image
    from transformers import AutoModelForCausalLM, AutoProcessor
    from transformers.masking_utils import create_causal_mask

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable; no CPU fallback")
    torch.set_num_threads(recipe["threads"])
    torch.manual_seed(recipe["seed"])
    processor = AutoProcessor.from_pretrained(model_path, local_files_only=True, trust_remote_code=True, use_fast=False)
    model = AutoModelForCausalLM.from_pretrained(model_path, local_files_only=True, trust_remote_code=True,
                torch_dtype=torch.bfloat16, attn_implementation="sdpa").to("cuda").eval()
    if (list(model.get_output_embeddings().weight.shape) != [recipe["output_classes"], 1024]
            or len(processor.tokenizer) != recipe["tokenizer_size"]):
        raise ValueError("Output classes or tokenizer changed")
    if "input_embeds" not in inspect.signature(create_causal_mask).parameters:
        raise ValueError("Unsupported causal mask API")

    def compatible_causal_mask(*positional, **kwargs):
        if "inputs_embeds" in kwargs:
            if "input_embeds" in kwargs:
                raise TypeError("Both embedding keyword spellings were supplied")
            kwargs["input_embeds"] = kwargs.pop("inputs_embeds")
        return create_causal_mask(*positional, **kwargs)

    setattr(sys.modules[type(model).__module__], "create_causal_mask", compatible_causal_mask)
    torch.cuda.reset_peak_memory_stats()

    def metrics():
        return {"inference_calls": calls, "network_attempts": network_attempts,
                "peak_allocated_vram_bytes": torch.cuda.max_memory_allocated(),
                "device": torch.cuda.get_device_name(0)}

    emit({"status": "ready", "protocol": "ocr-stream-v1", "profile_sha256": revision,
          "bridge_sha256": identity["worker_sha256"], "provider": "CUDAExecutionProvider", "metrics": metrics()})
    expected = 1
    while True:
        line = sys.stdin.buffer.readline(8193)
        if not line:
            return 0
        if len(line) > 8192 or not line.endswith(b"\n"):
            raise ValueError("Invalid request size")
        request = json.loads(line)
        width, height = request.get("width"), request.get("height")
        if (request.get("op") != "recognize" or request.get("request_id") != expected
                or type(width) is not int or type(height) is not int or min(width, height) <= 0
                or width * height * 3 > 32 * 1024 * 1024):
            raise ValueError("Invalid OCR frame request")
        path = args.job_dir / "frame.rgb"
        if path.stat().st_size != width * height * 3:
            raise ValueError("Frame size mismatch")
        raw = path.read_bytes()
        crop_hash = hashlib.sha256(raw).hexdigest()
        if crop_hash != request.get("crop_sha256"):
            raise ValueError("Frame hash mismatch")
        image = Image.frombytes("RGB", (width, height), raw)
        messages = [{"role": "user", "content": [{"type": "image", "image": image},
                                                   {"type": "text", "text": recipe["prompt"]}]}]
        inputs = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=True,
                                               return_dict=True, return_tensors="pt")
        inputs = {name: tensor.to("cuda", dtype=torch.bfloat16) if tensor.is_floating_point()
                  else tensor.to("cuda") for name, tensor in inputs.items()}
        calls["rec"] += 1
        emit({"status": "inference", "request_id": expected, "inference_calls": calls})
        begun = time.monotonic()
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=recipe["max_new_tokens"],
                                    do_sample=recipe["do_sample"], use_cache=recipe["use_cache"])
        torch.cuda.synchronize()
        ids = output[0, inputs["input_ids"].shape[-1]:].cpu().tolist()
        eos_id = model.generation_config.eos_token_id
        result = {"token_ids": ids, "text": processor.tokenizer.decode(ids, skip_special_tokens=True),
                  "raw_decode": processor.tokenizer.decode(ids, skip_special_tokens=False),
                  "eos": bool(ids and ids[-1] == eos_id), "eos_token_id": eos_id,
                  "inference_s": time.monotonic() - begun}
        emit({"status": "result", "request_id": expected, "crop_sha256": crop_hash,
              "result": result, "metrics": metrics()})
        del raw, image, inputs, output
        expected += 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        emit({"status": "error", "error_type": type(error).__name__})
        raise SystemExit(2) from None
