"""Explicit, bounded vision comparison on the existing hash-verified pilot crops.

No retry, reference text, translation, shared prompt logger or automatic service fallback.
Credentials remain in memory; result files belong only in private pilot scratch.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import time
from pathlib import Path

import openai

from videocaptioner.core.llm.client import LLMCredentials, configure_llm_client, normalize_base_url
from videocaptioner.core.llm.request_logger import OwnedRequestLog


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_answer(content: str) -> dict:
    payload = json.loads(content)
    if (not isinstance(payload, dict) or type(payload.get("unreadable")) is not bool
            or not isinstance(payload.get("lines"), list) or len(payload["lines"]) > 32):
        raise ValueError("Malformed vision response")
    for line in payload["lines"]:
        if (not isinstance(line, dict) or not isinstance(line.get("text"), str)
                or not isinstance(line.get("uncertain_spans"), list)):
            raise ValueError("Malformed vision line")
    return payload


def previous_attempts(args, manifest: dict, plan: dict) -> list[str]:
    """Count failed/timed-out requests too; continuation never resends an attempted crop."""
    ids = [crop["id"] for crop in manifest["crops"]]
    attempted = []
    for directory in getattr(args, "previous_run", []):
        prior = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        if (prior.get("status") not in ("completed", "stopped_on_error")
                or prior.get("endpoint") != normalize_base_url(args.endpoint)
                or prior.get("model") != args.model
                or prior.get("input_manifest_sha256") != plan["input_manifest_sha256"]
                or prior.get("prompt_sha256") != plan["prompt_sha256"]
                or type(prior.get("actual_calls")) is not int or not 0 <= prior["actual_calls"] <= 13):
            raise ValueError("Previous vision receipt mismatch or still running")
        # The first pilot predates the explicit ID ledger and always started at crop 01.
        current = prior.get("attempted_crop_ids", ids[:prior["actual_calls"]])
        if (not isinstance(current, list) or len(current) != prior["actual_calls"]
                or any(value not in ids or value in attempted for value in current)
                or len(set(current)) != len(current)):
            raise ValueError("Duplicate or invalid vision attempts")
        attempted.extend(current)
    return attempted


def execute(args) -> int:
    if args.output.exists():
        raise ValueError("Preserve previous runs: choose a new output directory")
    manifest = json.loads(args.inputs.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    prompt = args.prompt.read_text(encoding="utf-8")
    if (digest(args.inputs) != plan["input_manifest_sha256"]
            or digest(args.prompt) != plan["prompt_sha256"] or len(manifest["crops"]) != 13
            or args.max_calls != 13 + bool(getattr(args, "retry_crop", None))
            or not 1 <= args.max_output_tokens <= 1000):
        raise ValueError("Pilot input/prompt/budget mismatch")
    for crop in manifest["crops"]:
        path = args.inputs.parent / crop["file"]
        if path.parent.resolve() != args.inputs.parent.resolve() or digest(path) != crop["sha256"]:
            raise ValueError("Pilot crop SHA mismatch")
    attempted = previous_attempts(args, manifest, plan)
    remaining = [crop for crop in manifest["crops"] if crop["id"] not in attempted]
    retry_crop = getattr(args, "retry_crop", None)
    if retry_crop:
        failed, successful = set(), set()
        for directory in getattr(args, "previous_run", []):
            prior = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
            failed.update(item["id"] for item in prior.get("errors", []))
            successful.update(json.loads(line)["id"] for line in
                              (directory / "raw.jsonl").read_text(encoding="utf-8").splitlines())
        if retry_crop not in attempted or retry_crop not in failed or retry_crop in successful:
            raise ValueError("Explicit retry must identify a failed crop without a successful result")
        remaining += [crop for crop in manifest["crops"] if crop["id"] == retry_crop]
    if not remaining or len(attempted) + len(remaining) > args.max_calls:
        raise ValueError("No unattempted crops within the total vision budget")
    # This reader deliberately accepts a single bare key, never guesses among service keys.
    key = args.key_file.read_text(encoding="utf-8-sig").strip()
    if not re.fullmatch(r"sk-[A-Za-z0-9_-]+", key):
        raise ValueError("Expected one bare, endpoint-scoped gateway key")
    credentials = LLMCredentials(key, args.endpoint)
    configure_llm_client(credentials)
    args.output.mkdir(parents=True, exist_ok=False)
    metrics = {"schema": "ocr-vision-pilot-v1", "endpoint": credentials.base_url, "model": args.model,
               "input_manifest_sha256": digest(args.inputs), "prompt_sha256": digest(args.prompt),
               "max_calls": args.max_calls, "max_output_tokens_per_call": args.max_output_tokens,
               "actual_calls": 0, "successful_calls": 0, "cache_hits": 0, "retries": 0,
               "fresh_crops": 0, "provider_usage": [], "provider_cost": None, "errors": [],
               "prior_attempted_crop_ids": attempted, "attempted_crop_ids": [],
               "explicit_retry_crop": retry_crop,
               "status": "running", "request_loop_wall_s": None, "process_wall_s": None}
    begun = time.perf_counter()

    def save():
        (args.output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    try:
        with openai.OpenAI(api_key=credentials.api_key, base_url=credentials.base_url,
                           timeout=300, max_retries=0,
                           http_client=openai.DefaultHttpxClient(follow_redirects=False, trust_env=False, timeout=300)) as client, \
                (args.output / "provider-raw.jsonl").open("x", encoding="utf-8") as provider, \
                (args.output / "raw.jsonl").open("x", encoding="utf-8") as normalized:
            for crop in remaining:
                path = args.inputs.parent / crop["file"]
                blob = path.read_bytes()
                if hashlib.sha256(blob).hexdigest() != crop["sha256"]:
                    raise ValueError("Crop changed before request")
                metrics["actual_calls"] += 1
                metrics["retries"] += crop["id"] in attempted
                metrics["attempted_crop_ids"].append(crop["id"])
                metrics["fresh_crops"] += 1
                save()
                started = time.perf_counter()
                messages = [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": "data:image/png;base64," + base64.b64encode(blob).decode("ascii"), "detail": "high"}},
                ]}]
                journal = OwnedRequestLog(credentials.base_url, args.model, messages,
                                          {"max_completion_tokens": args.max_output_tokens},
                                          log_content=False, secret=credentials.api_key)
                try:
                    response = client.chat.completions.create(
                        model=args.model, max_completion_tokens=args.max_output_tokens,
                        messages=messages,  # pyright: ignore[reportArgumentType]
                    )
                    journal.finish(response, status=200)
                    wall = time.perf_counter() - started
                    usage = response.usage.model_dump(mode="json") if response.usage else None
                    provider.write(json.dumps({"id": crop["id"], "wall_s": wall,
                                               "response": response.model_dump(mode="json")},
                                              ensure_ascii=False) + "\n")
                    provider.flush()
                    metrics["provider_usage"].append(usage)
                    if len(response.choices) != 1 or response.choices[0].finish_reason != "stop":
                        raise ValueError("Incomplete vision response")
                    answer = parse_answer(response.choices[0].message.content or "")
                    normalized.write(json.dumps({"id": crop["id"], "crop_sha256": crop["sha256"],
                                                  "cache": "fresh", "texts": [r["text"] for r in answer["lines"]],
                                                  "scores": [], "boxes": [], "error": None,
                                                  "answer": answer, "usage": usage, "wall_s": wall},
                                                 ensure_ascii=False) + "\n")
                    normalized.flush()
                    metrics["successful_calls"] += 1
                    save()
                    print(json.dumps({"crop": crop["id"], "status": "received", "wall_s": wall}), flush=True)
                except Exception as exc:
                    journal.finish(status=getattr(exc, "status_code", None),
                                   outcome="timeout" if isinstance(exc, openai.APITimeoutError)
                                   else "http_error" if isinstance(exc, openai.APIStatusError) else "error",
                                   error_type=type(exc).__name__)
                    metrics["errors"].append({"id": crop["id"], "type": type(exc).__name__,
                                               "http_status": getattr(exc, "status_code", None),
                                               "wall_s": time.perf_counter() - started})
                    metrics["status"] = "stopped_on_error"
                    # HTTP bodies and exception strings can contain request data or credentials.
                    print(json.dumps({"crop": crop["id"], "status": "stopped_on_error",
                                      "error_type": type(exc).__name__,
                                      "http_status": getattr(exc, "status_code", None)}), flush=True)
                    return 2
        metrics["status"] = "completed"
        return 0
    finally:
        metrics["request_loop_wall_s"] = time.perf_counter() - begun
        save()
        configure_llm_client(None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "plan", "prompt", "key-file", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-calls", type=int, required=True)
    parser.add_argument("--max-output-tokens", type=int, required=True)
    parser.add_argument("--previous-run", type=Path, action="append", default=[])
    parser.add_argument("--retry-crop", help="Only after explicit approval for one additional failed-crop request")
    return execute(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
