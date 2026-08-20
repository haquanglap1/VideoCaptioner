import json
from types import SimpleNamespace

import pytest

from videocaptioner.core.dubbing.models import DubbingGroup
from videocaptioner.core.dubbing.rewrite_service import (
    RewriteRequest,
    TimingRewriteService,
    generate_rewrite_cache_key,
    validate_rewrite_response,
)


def request(**overrides):
    values = {
        "group_id": "g-0001",
        "source_language": "en",
        "target_language": "vi",
        "source_text": "Model X200 is not 50% faster and costs $20",
        "subtitle_text": "Model X200 không nhanh hơn 50% và giá $20",
        "available_duration": 2.0,
        "measured_duration": 3.0,
        "measured_fit_ratio": 1.5,
        "target_spoken_unit_budget": 6,
        "attempt_number": 1,
    }
    values.update(overrides)
    return RewriteRequest(**values)


def response(text, group_id="g-0001"):
    return json.dumps({"group_id": group_id, "tts_text": text, "preserved_terms": ["X200", "50%", "$20"]})


def test_valid_response_and_protected_content():
    result = validate_rewrite_response(
        response("Model X200 không hơn 50%, giá $20"), request(), rescue=True
    )
    assert result.startswith("Model X200")


@pytest.mark.parametrize(
    "raw,match",
    [
        (response("Model X200 không hơn 50%, giá $20", "bad"), "group_id"),
        ("```json\n{}\n```", "strict JSON"),
        (response(""), "empty"),
        (response("Model không nhanh hơn"), "removed"),
        (response("Model X200 nhanh hơn 50%, giá $20"), "negation"),
        (response("Model X200 không nhanh hơn 50% và giá $20"), "did not shorten"),
    ],
)
def test_invalid_responses(raw, match):
    with pytest.raises(ValueError, match=match):
        validate_rewrite_response(raw, request(), rescue=True)


def test_cache_key_is_stable_and_budget_sensitive():
    first = generate_rewrite_cache_key(request(), "model", True)
    assert first == generate_rewrite_cache_key(request(), "model", True)
    assert first != generate_rewrite_cache_key(request(target_spoken_unit_budget=4), "model", True)


class MemoryCache:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, expire=None):
        self.data[key] = value


def test_service_cache_avoids_duplicate_calls():
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content=response("Model X200 không hơn 50%, giá $20"))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    service = TimingRewriteService("model", caller=fake_call, cache=MemoryCache())
    assert service.rewrite(request(), rescue=True)
    assert service.rewrite(request(), rescue=True)
    assert len(calls) == 1


def test_no_llm_fallback():
    assert TimingRewriteService("", cache=MemoryCache()).rewrite(request(), rescue=True) is None


def test_rewrite_call_keeps_task_context():
    from videocaptioner.core.llm.context import (
        clear_task_context,
        get_task_context,
        set_task_context,
    )

    seen = []

    def fake_call(**kwargs):
        seen.append(get_task_context())
        message = SimpleNamespace(content=response("Model X200 không hơn 50%, giá $20"))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    set_task_context("task-1", "input.mp4", "dubbing")
    try:
        TimingRewriteService("model", caller=fake_call, cache=MemoryCache()).rewrite(
            request(), rescue=True
        )
    finally:
        clear_task_context()
    assert seen[0] is not None and seen[0].task_id == "task-1"


def test_group_type_remains_available_for_orchestrator_contract():
    group = DubbingGroup("g", [1], 0, 1, 1, 1, "s", "t", "t")
    assert group.group_id == "g"
