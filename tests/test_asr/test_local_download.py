"""Small file fixtures exercise the pinned helper's hash and resume decisions."""

import hashlib
import io
import json
import runpy
import sys
from types import SimpleNamespace

import huggingface_hub
import pytest

from videocaptioner.core.asr.local.runtime import recipe_directory


@pytest.mark.parametrize("initial", ["absent", "partial", "valid", "corrupt"])
def test_download_verifies_content_reuses_complete_and_preserves_resume(tmp_path, monkeypatch, initial):
    data = b"small model fixture"
    destination = tmp_path / "model"
    destination.mkdir()
    target = destination / "weight.bin"
    if initial in ("valid", "corrupt"):
        target.write_bytes(data if initial == "valid" else b"bad" )
    if initial == "partial":
        (destination / "partial.incomplete").write_bytes(data[:5])
    item = SimpleNamespace(rfilename="weight.bin", size=len(data),
                           lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()), blob_id=None)
    info = SimpleNamespace(sha="pin", id="model", siblings=[item])
    monkeypatch.setattr(huggingface_hub, "HfApi", lambda: SimpleNamespace(model_info=lambda *a, **k: info))
    calls = []

    def download(*args, **kwargs):
        calls.append(kwargs)
        if initial == "partial":
            assert (destination / "partial.incomplete").read_bytes() == data[:5]
        target.write_bytes(data)
        return str(target)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"repository": "model", "revision": "pin", "destination": str(destination)})))
    runpy.run_path(str(recipe_directory() / "download.py"))["main"]()
    inventory = json.loads((destination / "inventory.json").read_text())
    assert inventory["files"]["weight.bin"] == {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if initial == "valid":
        assert not calls
    else:
        assert calls[0]["force_download"] is (initial == "corrupt")
        assert calls[0]["token"] is False and calls[0]["revision"] == "pin"


def test_bad_hub_content_cannot_produce_inventory(tmp_path, monkeypatch):
    target = tmp_path / "config.json"
    target.write_bytes(b"bad")
    item = SimpleNamespace(rfilename=target.name, size=3, lfs=None, blob_id="0" * 40)
    info = SimpleNamespace(sha="pin", id="model", siblings=[item])
    monkeypatch.setattr(huggingface_hub, "HfApi", lambda: SimpleNamespace(model_info=lambda *a, **k: info))
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", lambda *a, **k: str(target))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"repository": "model", "revision": "pin", "destination": str(tmp_path)})))
    with pytest.raises(ValueError, match="hash mismatch"):
        runpy.run_path(str(recipe_directory() / "download.py"))["main"]()
    assert not (tmp_path / "inventory.json").exists()
