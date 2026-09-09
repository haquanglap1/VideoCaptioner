"""Offline installation ownership, interrupted download and verified activation."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from videocaptioner.core.asr.local import prepare, runtime
from videocaptioner.core.asr.local.profiles import MODELS
from videocaptioner.core.asr.local.runtime import LocalRuntimeError

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows runtime recipe")


def test_progress_counts_hub_partial_files_beyond_windows_max_path(tmp_path):
    directory = tmp_path / ("runtime-" + "a" * 65) / ("model-" + "b" * 65)
    partial = directory / ("c" * 90 + ".incomplete")
    assert len(str(partial)) > 260
    extended = Path("\\\\?\\" + str(partial.resolve()))
    extended.parent.mkdir(parents=True)
    extended.write_bytes(b"retained download")
    (extended.parent / "completed.bin").write_bytes(b"not a partial")
    assert prepare._partial_download_bytes(directory) == len(b"retained download")


@pytest.fixture
def installation(tmp_path, monkeypatch):
    recipe = tmp_path / "recipe"
    recipe.mkdir()
    (recipe / "qwen.lock").write_text("locked-test-recipe")
    (recipe / "qwen.json").write_text('{"python": "3.12"}')
    (recipe / "bridge.py").write_text("# synthetic worker")
    monkeypatch.setattr(prepare, "recipe_directory", lambda: recipe)
    monkeypatch.setattr(runtime, "recipe_directory", lambda: recipe)
    monkeypatch.setattr(prepare.shutil, "which", lambda program: "uv" if program == "uv" else None)
    root = tmp_path / "original"
    root.mkdir()
    (root / "keep.txt").write_text("existing runtime remains untouched")
    calls = []

    def run(args, env, check, payload=None):
        check()
        calls.append((args, env, payload))
        if args[:2] == ["uv", "venv"]:
            python = Path(args[-1]) / "Scripts/python.exe"
            python.parent.mkdir()
            python.write_bytes(b"synthetic python")
        if payload:
            destination = Path(payload["destination"])
            destination.mkdir(parents=True, exist_ok=True)
            files = {}
            for name in ("config.json", "preprocessor_config.json", "tokenizer_config.json",
                         "vocab.json", "merges.txt", "model.safetensors"):
                data = (name + " fixture").encode()
                (destination / name).write_bytes(data)
                files[name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            (destination / "inventory.json").write_text(json.dumps({
                "repository": payload["repository"], "revision": payload["revision"], "files": files}))

    monkeypatch.setattr(prepare, "_run", run)
    return root, calls, run


def test_first_job_prepares_only_selected_model_and_second_reuses_without_network(installation):
    root, calls, _ = installation
    layout = prepare.ensure_model("qwen-0.6b", root)
    assert layout.model == MODELS["qwen-0.6b"]
    assert list(root.iterdir()) == [root / "keep.txt"]
    downloads = [payload for _, _, payload in calls if payload]
    assert len(downloads) == 1 and downloads[0]["repository"] == MODELS["qwen-0.6b"].repository
    assert not (layout.root / ".installing").exists()
    count = len(calls)
    assert prepare.ensure_model("qwen-0.6b", root) == layout
    assert len(calls) == count
    assert runtime.locate("qwen-0.6b", root, verify=True) == layout


def test_cancelled_download_keeps_owned_staging_and_resumes_at_same_destination(installation, monkeypatch):
    root, calls, run = installation
    partials = []

    def cancel(args, env, check, payload=None):
        if payload:
            partial = Path(payload["destination"]) / ".cache/huggingface/download/weight.incomplete"
            partial.parent.mkdir(parents=True)
            partial.write_bytes(b"retained partial")
            partials.append(partial)
            raise LocalRuntimeError("cancelled")
        return run(args, env, check, payload)

    monkeypatch.setattr(prepare, "_run", cancel)
    with pytest.raises(LocalRuntimeError, match="cancelled"):
        prepare.ensure_model("qwen-0.6b", root)
    with pytest.raises(LocalRuntimeError, match="incomplete"):
        runtime.locate("qwen-0.6b", root)
    monkeypatch.setattr(prepare, "_run", run)
    layout = prepare.ensure_model("qwen-0.6b", root)
    assert partials[0].read_bytes() == b"retained partial"
    assert partials[0].is_relative_to(layout.root)
    assert len([args for args, _, _ in calls if args[:2] == ["uv", "venv"]]) == 1


def test_corrupt_download_never_activates(installation, monkeypatch):
    root, _, run = installation

    def corrupt(args, env, check, payload=None):
        run(args, env, check, payload)
        if payload:
            (Path(payload["destination"]) / "model.safetensors").write_bytes(b"bad")

    monkeypatch.setattr(prepare, "_run", corrupt)
    with pytest.raises(LocalRuntimeError):
        prepare.ensure_model("qwen-0.6b", root)
    assert (runtime.managed_root("qwen-0.6b", root) / ".installing").exists()
    with pytest.raises(LocalRuntimeError):
        runtime.locate("qwen-0.6b", root)


def test_unowned_destination_and_insufficient_disk_never_install(installation, monkeypatch):
    root, calls, _ = installation
    destination = runtime.managed_root("qwen-0.6b", root)
    destination.mkdir(parents=True)
    (destination / "user.txt").write_text("keep")
    with pytest.raises(LocalRuntimeError, match="not owned"):
        prepare.ensure_model("qwen-0.6b", root)
    assert not calls and (destination / "user.txt").read_text() == "keep"
    from types import SimpleNamespace
    monkeypatch.setattr(prepare.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(LocalRuntimeError, match="disk space"):
        prepare.ensure_model("aligner", root)
    assert not calls


def test_installation_lock_wait_can_cancel_and_then_reacquire(tmp_path):
    path = tmp_path / "prepare.lock"
    messages = []

    def cancel_after_wait():
        if messages:
            raise LocalRuntimeError("cancelled")

    with prepare.installation_lock(path, lambda: None, lambda _: None):
        with pytest.raises(LocalRuntimeError, match="cancelled"):
            with prepare.installation_lock(path, cancel_after_wait, messages.append):
                pytest.fail("concurrent installation entered")
    with prepare.installation_lock(path, lambda: None, lambda _: None):
        pass


def test_gated_model_requires_secure_token_before_any_install(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare, "locate", lambda *a, **k: (_ for _ in ()).throw(LocalRuntimeError("missing")))
    monkeypatch.setattr(prepare, "_run", lambda *a, **k: pytest.fail("gated download"))
    with pytest.raises(LocalRuntimeError, match="read token"):
        prepare.ensure_model("community-1", tmp_path)


def test_previous_managed_runtime_remains_discoverable_after_bridge_update(installation, monkeypatch):
    root, calls, _ = installation
    recipe = runtime.recipe_directory()
    old_bridge = (recipe / "bridge.py").read_bytes()
    monkeypatch.setattr(runtime, "LEGACY_BRIDGE_SHA256", hashlib.sha256(old_bridge).hexdigest())
    old = prepare.ensure_model("qwen-0.6b", root)
    count = len(calls)
    (recipe / "bridge.py").write_bytes(b"# next compatible bundled worker")
    loaded = prepare.ensure_model("qwen-0.6b", root)
    assert loaded.root == old.root and loaded.bridge == recipe / "bridge.py"
    assert (old.root / "bridge.py").read_bytes() == old_bridge
    assert len(calls) == count
    (old.root / "bridge.py").write_bytes(b"# unrecognized modification")
    with pytest.raises(LocalRuntimeError):
        runtime.locate("qwen-0.6b", root, verify=True)
