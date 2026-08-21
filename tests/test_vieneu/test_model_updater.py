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
