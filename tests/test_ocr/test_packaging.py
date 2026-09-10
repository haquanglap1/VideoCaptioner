import hashlib
import json

import pytest

from scripts.package_test_models import SCHEMA, append_ocr_payload


def collection(path, component, name, content):
    path.mkdir()
    (path / ".portable-models-staging.json").write_text(json.dumps({"schema": SCHEMA}))
    target = path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    manifest = {"schema": SCHEMA, "components": [component], "files": {
        name: {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}}, "total_bytes": len(content)}
    (path / "portable-models.json").write_text(json.dumps(manifest))
    return manifest


def test_append_ocr_preserves_existing_inventory_and_sources(tmp_path):
    target, incoming = tmp_path / "destination", tmp_path / "ocr-source"
    old = collection(target, "qwen", "qwen/model.bin", b"existing ASR fixture")
    ocr = collection(incoming, "ocr", "ocr/weights/model.bin", b"OCR fixture")
    original = (incoming / "portable-models.json").read_bytes()
    append_ocr_payload(target, incoming)
    merged = json.loads((target / "portable-models.json").read_text())
    assert merged["components"] == ["qwen", "ocr"]
    assert merged["files"] == old["files"] | ocr["files"]
    assert (target / "qwen/model.bin").read_bytes() == b"existing ASR fixture"
    assert (incoming / "portable-models.json").read_bytes() == original
    with pytest.raises(ValueError):
        append_ocr_payload(target, incoming)


@pytest.mark.parametrize("fault", ["no-owner", "changed-hash", "escape", "collision"])
def test_append_ocr_rejects_invalid_payload_before_inventory_change(tmp_path, fault):
    target, incoming = tmp_path / "destination", tmp_path / "ocr-source"
    collection(target, "qwen", "qwen/model.bin", b"existing")
    ocr = collection(incoming, "ocr", "ocr/model.bin", b"fixture")
    before = (target / "portable-models.json").read_bytes()
    if fault == "no-owner":
        (target / ".portable-models-staging.json").unlink()
    elif fault == "changed-hash":
        (incoming / "ocr/model.bin").write_bytes(b"changed")
    elif fault == "escape":
        ocr["files"]["ocr/../secret"] = next(iter(ocr["files"].values()))
        (incoming / "portable-models.json").write_text(json.dumps(ocr))
    else:
        (target / "ocr").mkdir()
    with pytest.raises(ValueError):
        append_ocr_payload(target, incoming)
    assert (target / "portable-models.json").read_bytes() == before
