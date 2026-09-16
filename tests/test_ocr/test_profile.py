import copy
import hashlib
import json
from dataclasses import replace

import pytest

from videocaptioner.core.ocr.codec import decode, encode
from videocaptioner.core.ocr.document import OcrConfig, OcrDocument, document_id
from videocaptioner.core.ocr.installation import default_runtime, inspect_installation, resources
from videocaptioner.core.ocr.models import OcrError
from videocaptioner.core.ocr.profile import OcrProfileSnapshot
from videocaptioner.resources.ocr.ocr_stream_worker import stage_parameters

from .test_document import make_document


def recipe(name="profile-v6-medium.json"):
    return json.loads((resources() / name).read_bytes())


def snapshot(value):
    raw = json.dumps(value).encode()
    return OcrProfileSnapshot.from_bytes(raw, hashlib.sha256(raw).hexdigest())


def test_medium_stage_pins_round_trip_in_existing_document_schema():
    profile = snapshot(recipe())
    det, rec, cls = profile.stages
    assert (det.ocr_version, rec.ocr_version, cls.ocr_version) == ("PP-OCRv6", "PP-OCRv6", "PP-OCRv4")
    assert (rec.model_type, rec.lang_type, rec.dictionary_count) == ("medium", "multi", 18708)
    assert det.dictionary_sha256 is None and cls.dictionary_count is None
    assert profile.stage_parameters == stage_parameters(recipe())
    assert decode(OcrProfileSnapshot, encode(profile)) == profile
    config = replace(make_document().config, profile_snapshot=profile)
    assert decode(OcrConfig, encode(config)).profile_snapshot.stages == profile.stages


def test_legacy_document_serialization_and_ids_do_not_gain_stage_fields():
    legacy = snapshot(recipe("profile.json"))
    assert not any(key.endswith("ocr_version") for key, _ in legacy.parameters)
    assert legacy.stages[1].dictionary_count == 18383
    doc = make_document()
    original = encode(doc)
    restored = decode(OcrDocument, copy.deepcopy(original))
    assert encode(restored) == original
    assert document_id(restored.visual_source, restored.config) == doc.id
    assert [c.id for c in restored.cues] == [c.id for c in doc.cues]


@pytest.mark.parametrize("mutate", [
    lambda v: v["models"]["rec"].update(ocr_version="PP-OCRv5"),
    lambda v: v["models"]["det"].update(lang_type="ch"),
    lambda v: v["models"]["rec"].update(engine_type="paddle"),
    lambda v: v["models"]["rec"].pop("model_type"),
    lambda v: v["models"].pop("cls"),
    lambda v: v["models"]["rec"]["dictionary"].update(count=18383),
    lambda v: v["models"]["cls"].update(dictionary={}),
    lambda v: v["params"].update({"Rec.ocr_version": "PP-OCRv5"}),
    lambda v: v.update(schema="ocr-profile-v99"),
    lambda v: v.update(schema="ocr-pilot-profile-v1"),
])
def test_invalid_stage_contract_rejected_before_runtime(mutate):
    value = recipe()
    mutate(value)
    with pytest.raises(OcrError):
        snapshot(value)


@pytest.mark.parametrize("name", ["profile.json", "profile-v6-medium.json"])
def test_installation_accepts_each_bundled_recipe_and_verifies_weights(tmp_path, monkeypatch, name):
    root, bundle = tmp_path / "runtime", tmp_path / "resources"
    (root / "env").mkdir(parents=True)
    (root / "env/python.exe").write_bytes(b"fixture")
    (root / "weights").mkdir()
    bundle.mkdir()
    value = recipe(name)
    for stage, model in value["models"].items():
        data = stage.encode()
        (root / "weights" / model["file"]).write_bytes(data)
        model["sha256"] = hashlib.sha256(data).hexdigest()
    raw = json.dumps(value).encode()
    (root / "profile.json").write_bytes(raw)
    (bundle / name).write_bytes(raw)
    (bundle / "ocr_stream_worker.py").write_text("# fixture")
    monkeypatch.setattr("videocaptioner.core.ocr.installation.resources", lambda: bundle)
    installed = inspect_installation(root)
    assert installed.profile.id == value["id"]
    (root / "weights" / value["models"]["rec"]["file"]).write_bytes(b"changed")
    with pytest.raises(OcrError, match="SHA"):
        inspect_installation(root)


def test_candidate_discovery_is_local_and_does_not_fallback_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr("videocaptioner.config.portable_models_path", lambda: tmp_path)
    assert default_runtime() == tmp_path / "ocr"
    (tmp_path / "ocr-v6-medium").mkdir()
    assert default_runtime() == tmp_path / "ocr-v6-medium"
    with pytest.raises(OcrError):
        inspect_installation()
