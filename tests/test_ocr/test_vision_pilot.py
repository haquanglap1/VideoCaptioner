import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import ocr_vision_pilot


def arguments(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    crops = []
    for index in range(13):
        crop = inputs / f"crop-{index + 1:02d}.png"
        crop.write_bytes(b"synthetic image bytes")
        crops.append({"id": crop.stem, "file": crop.name, "sha256": ocr_vision_pilot.digest(crop)})
    manifest = inputs / "manifest.json"
    manifest.write_text(json.dumps({"crops": crops}), encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Read only the image", encoding="utf-8")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"input_manifest_sha256": ocr_vision_pilot.digest(manifest),
                                "prompt_sha256": ocr_vision_pilot.digest(prompt)}), encoding="utf-8")
    key = tmp_path / "key.txt"
    key.write_text("sk-fixture-only", encoding="utf-8")
    return SimpleNamespace(inputs=manifest, plan=plan, prompt=prompt, key_file=key,
                           output=tmp_path / "output", endpoint="https://fixture.invalid/v1",
                           model="fixture-vision", max_calls=13, max_output_tokens=1000)


def test_bounded_requests_omit_reference_credentials_and_unknown_cost(tmp_path, monkeypatch):
    args = arguments(tmp_path)
    requests = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0 and kwargs["api_key"] == "sk-fixture-only"
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def create(self, **kwargs):
            requests.append(kwargs)
            answer = '{"lines":[{"text":"学生","uncertain_spans":[]}],"unreadable":false}'
            return SimpleNamespace(usage=None, choices=[SimpleNamespace(finish_reason="stop",
                                   message=SimpleNamespace(content=answer))],
                                   model_dump=lambda **_: {"content": answer})

    monkeypatch.setattr(ocr_vision_pilot.openai, "OpenAI", Client)
    assert ocr_vision_pilot.execute(args) == 0
    assert len(requests) == 13
    for request in requests:
        assert request["max_completion_tokens"] == 1000
        content = request["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "Read only the image"}
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
        assert "fixture-only" not in json.dumps(request) and str(tmp_path) not in json.dumps(request)
    metrics = json.loads((args.output / "metrics.json").read_text())
    assert metrics["provider_cost"] is None and metrics["provider_usage"] == [None] * 13
    assert metrics["successful_calls"] == 13 and metrics["retries"] == 0
    assert all("sk-fixture-only" not in p.read_text(encoding="utf-8") for p in args.output.iterdir())


def test_hash_gate_runs_before_key_or_network(tmp_path):
    args = arguments(tmp_path)
    args.prompt.write_text("changed", encoding="utf-8")
    args.key_file.unlink()
    with pytest.raises(ValueError, match="mismatch"):
        ocr_vision_pilot.execute(args)
    assert not args.output.exists()
    assert hashlib.sha256(b"changed").hexdigest() == ocr_vision_pilot.digest(args.prompt)


def test_error_stops_at_first_request_without_sensitive_exception(tmp_path, monkeypatch):
    args = arguments(tmp_path)

    class Client:
        def __init__(self, **_):
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def create(self, **_):
            raise RuntimeError("sk-fixture-only private HTTP body")

    monkeypatch.setattr(ocr_vision_pilot.openai, "OpenAI", Client)
    assert ocr_vision_pilot.execute(args) == 2
    metrics = json.loads((args.output / "metrics.json").read_text())
    assert metrics["actual_calls"] == 1 and metrics["successful_calls"] == 0
    assert "sk-fixture-only" not in json.dumps(metrics)


@pytest.mark.parametrize("payload", ['{}', '{"lines":[],"unreadable":1}', '```json\n{}\n```'])
def test_malformed_vision_output_not_accepted(payload):
    with pytest.raises(ValueError):
        ocr_vision_pilot.parse_answer(payload)


def test_continuation_counts_timeout_and_rejects_duplicate_receipts(tmp_path):
    args = arguments(tmp_path)
    receipt = tmp_path / "previous"
    receipt.mkdir()
    plan = json.loads(args.plan.read_text())
    prior = dict(plan, status="stopped_on_error", endpoint=args.endpoint, model=args.model, actual_calls=5)
    (receipt / "metrics.json").write_text(json.dumps(prior))
    args.previous_run = [receipt]
    manifest = json.loads(args.inputs.read_text())
    assert ocr_vision_pilot.previous_attempts(args, manifest, plan) == [f"crop-{i:02d}" for i in range(1, 6)]
    args.previous_run = [receipt, receipt]
    with pytest.raises(ValueError, match="Duplicate"):
        ocr_vision_pilot.previous_attempts(args, manifest, plan)


def test_explicit_retry_cannot_resend_a_successful_crop(tmp_path):
    args = arguments(tmp_path)
    receipt = tmp_path / "previous"
    receipt.mkdir()
    plan = json.loads(args.plan.read_text())
    (receipt / "metrics.json").write_text(json.dumps(dict(plan, status="stopped_on_error",
        endpoint=args.endpoint, model=args.model, actual_calls=5, errors=[{"id": "crop-05"}])))
    (receipt / "raw.jsonl").write_text('{"id":"crop-01"}\n')
    args.previous_run, args.retry_crop, args.max_calls = [receipt], "crop-01", 14
    with pytest.raises(ValueError, match="failed crop"):
        ocr_vision_pilot.execute(args)
    assert not args.output.exists()
