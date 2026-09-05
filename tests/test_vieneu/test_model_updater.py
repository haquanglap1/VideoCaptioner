from pathlib import Path

import pytest

from videocaptioner.core.tts.vieneu.model_updater import (
    VieNeuModelPaths,
    VieNeuModelUpdateError,
    VieNeuModelUpdater,
    VieNeuStateStore,
)
from videocaptioner.core.tts.vieneu.models import VieNeuModelState
from videocaptioner.core.tts.vieneu.runtime_manager import VieNeuRuntimeManager


class FakeHub:
    def __init__(self, revision="b" * 40, *, fail_once=False, offline=False):
        self.revision = revision
        self.fail_once = fail_once
        self.offline = offline
        self.download_calls = 0

    def remote_revision(self, repository_id):
        if self.offline:
            raise OSError("offline")
        return self.revision

    def snapshot_download(
        self,
        repository_id,
        revision,
        cache_dir,
        *,
        progress_callback=None,
        cancel_event=None,
    ):
        self.download_calls += 1
        snapshot = Path(cache_dir) / "snapshots" / revision
        snapshot.mkdir(parents=True, exist_ok=True)
        partial = snapshot / "partial.bin"
        partial.write_bytes(b"partial")
        if self.fail_once and self.download_calls == 1:
            raise ConnectionError("download interrupted")
        (snapshot / "model.safetensors").write_bytes(b"complete")
        if progress_callback:
            progress_callback(1, 1, repository_id)
        return snapshot


def make_store(tmp_path, *, active=True):
    store = VieNeuStateStore(VieNeuModelPaths.under(tmp_path / "models"))
    state = VieNeuModelState()
    if active:
        active_snapshot = store.paths.hf_cache / "snapshots" / ("a" * 40)
        active_snapshot.mkdir(parents=True)
        (active_snapshot / "model.safetensors").write_bytes(b"active")
        state.active_revision = "a" * 40
        state.active_snapshot = store.relative_snapshot(active_snapshot)
        state.runtime_version = "fake-runtime-1"
    store.save(state)
    return store


def test_remote_check_offline_keeps_active_model(tmp_path):
    store = make_store(tmp_path)
    updater = VieNeuModelUpdater(store=store, hub=FakeHub(offline=True))
    result = updater.check_for_update()
    assert result.status == "offline"
    assert result.active_revision == "a" * 40
    assert store.load().active_revision == "a" * 40


def test_stage_download_resumes_after_interruption_without_deleting_partial(tmp_path):
    store = make_store(tmp_path)
    hub = FakeHub(fail_once=True)
    updater = VieNeuModelUpdater(store=store, hub=hub)
    with pytest.raises(VieNeuModelUpdateError, match="download failed"):
        updater.stage_revision("b" * 40)
    state = store.load()
    assert state.candidate_revision == "b" * 40
    partial = store.paths.hf_cache / "snapshots" / ("b" * 40) / "partial.bin"
    assert partial.is_file()
    snapshot = updater.stage_revision("b" * 40)
    assert snapshot == partial.parent
    assert partial.is_file()
    assert hub.download_calls == 2


def test_candidate_validates_health_voices_wav_then_activates(runtime_config, tmp_path):
    store = make_store(tmp_path)
    hub = FakeHub()
    updater = VieNeuModelUpdater(store=store, hub=hub)
    snapshot = updater.stage_revision("b" * 40)
    manager = VieNeuRuntimeManager()

    def config_factory(path, revision):
        return runtime_config(revision)

    identity = updater.validate_and_activate(manager, config_factory)
    state = store.load()
    assert snapshot.is_dir()
    assert state.active_revision == "b" * 40
    assert state.previous_revision == "a" * 40
    assert identity.model_revision == "b" * 40
    manager.shutdown(force=True)


def test_bad_candidate_is_rejected_previous_restarts_and_same_sha_is_not_retried(
    runtime_config, tmp_path
):
    store = make_store(tmp_path)
    hub = FakeHub()
    updater = VieNeuModelUpdater(store=store, hub=hub)
    updater.stage_revision("b" * 40)
    manager = VieNeuRuntimeManager()

    def config_factory(path, revision):
        extra = ("--bad-wav",) if revision == "b" * 40 else ()
        return runtime_config(revision, extra_args=extra)

    with pytest.raises(VieNeuModelUpdateError, match="rejected"):
        updater.validate_and_activate(manager, config_factory)
    state = store.load()
    assert state.active_revision == "a" * 40
    assert "b" * 40 in state.rejected_revisions
    assert manager.identity and manager.identity.model_revision == "a" * 40
    check = updater.check_for_update()
    assert check.status == "rejected"
    manager.shutdown(force=True)


def test_activation_is_deferred_while_job_is_busy(runtime_config, tmp_path):
    store = make_store(tmp_path)
    updater = VieNeuModelUpdater(store=store, hub=FakeHub())
    updater.stage_revision("b" * 40)
    manager = VieNeuRuntimeManager()
    with manager.acquire(runtime_config("a" * 40)):
        result = updater.validate_and_activate(
            manager, lambda path, revision: runtime_config(revision)
        )
        assert result == "deferred"
        assert store.load().active_revision == "a" * 40
    manager.shutdown(force=True)


def test_manual_rollback_swaps_known_good_revisions_without_deleting_snapshots(tmp_path):
    store = make_store(tmp_path)
    state = store.load()
    previous = store.paths.hf_cache / "snapshots" / ("9" * 40)
    previous.mkdir(parents=True)
    state.previous_revision = "9" * 40
    state.previous_snapshot = store.relative_snapshot(previous)
    active_path = store.resolve_snapshot(state.active_snapshot)
    store.save(state)
    rolled = VieNeuModelUpdater(store=store, hub=FakeHub()).rollback()
    assert rolled.active_revision == "9" * 40
    assert rolled.previous_revision == "a" * 40
    assert previous.is_dir()
    assert active_path.is_dir()


def test_hub_client_disables_symlinks_on_windows(monkeypatch, tmp_path):
    """Windows machines without the symlink privilege must get plain-file caches.

    huggingface_hub probes symlink support lazily per cache dir; a second
    download thread can pass the probe before it finishes and fail with
    WinError 1314, so the client forces the copy path up front.
    """
    import os
    import sys

    from huggingface_hub import constants as hf_constants

    from videocaptioner.core.tts.vieneu.model_updater import HuggingFaceVieNeuClient

    calls = []

    def fake_snapshot_download(**kwargs):
        calls.append(kwargs)
        snapshot = tmp_path / "snapshot"
        snapshot.mkdir(exist_ok=True)
        return str(snapshot)

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot_download)
    monkeypatch.setattr(hf_constants, "HF_HUB_DISABLE_SYMLINKS", False)
    monkeypatch.delenv("HF_HUB_DISABLE_SYMLINKS", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")

    result = HuggingFaceVieNeuClient().snapshot_download("org/repo", "c" * 40, tmp_path / "hf")

    assert result == (tmp_path / "snapshot").resolve()
    assert hf_constants.HF_HUB_DISABLE_SYMLINKS is True
    assert os.environ["HF_HUB_DISABLE_SYMLINKS"] == "1"
    assert calls[0]["repo_id"] == "org/repo"
    assert calls[0]["revision"] == "c" * 40
    assert calls[0]["cache_dir"] == str(tmp_path / "hf")


def test_hub_client_progress_bar_works_without_stderr(monkeypatch, tmp_path):
    """Windowed EXE builds start with sys.stderr=None.

    tqdm then raised inside refresh() while holding its global write lock: every
    model download failed and tqdm's atexit monitor join deadlocked, so the app
    never exited. The client's bar must stay usable and leave the lock free.
    """
    import sys
    import threading

    from videocaptioner.core.tts.vieneu.model_updater import HuggingFaceVieNeuClient

    reports = []
    bar_classes = []

    def fake_snapshot_download(**kwargs):
        bar_class = kwargs["tqdm_class"]
        bar_classes.append(bar_class)
        with bar_class(desc="Fetching 2 files", total=2, unit="it") as bar:
            bar.update(1)
            bar.update(1)
        return str(tmp_path)

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot_download)
    monkeypatch.setattr(sys, "stderr", None)

    HuggingFaceVieNeuClient().snapshot_download(
        "org/repo",
        "c" * 40,
        tmp_path / "hf",
        progress_callback=lambda done, total, name: reports.append((done, total, name)),
    )

    assert reports[-1] == (2, 2, "Fetching 2 files")
    assert bar_classes[0].monitor_interval == 0

    # Another thread must still be able to take the bar class's shared write
    # lock (tqdm.auto and tqdm.std own separate locks, so probe the bar's own).
    acquired = []

    def probe():
        for inner in bar_classes[0].get_lock().locks:
            acquired.append(inner.acquire(timeout=2))
            if acquired[-1]:
                inner.release()

    probe_thread = threading.Thread(target=probe)
    probe_thread.start()
    probe_thread.join(5)
    assert acquired and all(acquired)


def test_hub_client_leaves_symlink_setting_alone_elsewhere(monkeypatch, tmp_path):
    import os
    import sys

    from huggingface_hub import constants as hf_constants

    from videocaptioner.core.tts.vieneu.model_updater import HuggingFaceVieNeuClient

    monkeypatch.setattr("huggingface_hub.snapshot_download", lambda **kwargs: str(tmp_path))
    monkeypatch.setattr(hf_constants, "HF_HUB_DISABLE_SYMLINKS", False)
    monkeypatch.delenv("HF_HUB_DISABLE_SYMLINKS", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")

    HuggingFaceVieNeuClient().snapshot_download("org/repo", "c" * 40, tmp_path / "hf")

    assert hf_constants.HF_HUB_DISABLE_SYMLINKS is False
    assert "HF_HUB_DISABLE_SYMLINKS" not in os.environ
