#!/usr/bin/env python3
"""Force a real candidate validation failure and prove automatic known-good restart."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from videocaptioner.core.tts.vieneu.model_updater import (
    VieNeuModelPaths,
    VieNeuModelUpdateError,
    VieNeuStateStore,
)
from videocaptioner.core.tts.vieneu.runtime_manager import VieNeuRuntimeManager
from videocaptioner.core.tts.vieneu.service import VieNeuManagedService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--bridge", required=True)
    parser.add_argument("--model-root", required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    store = VieNeuStateStore(VieNeuModelPaths.under(args.model_root))
    service = VieNeuManagedService(
        manager=VieNeuRuntimeManager(),
        store=store,
        explicit_runtime=args.runtime,
        explicit_bridge=args.bridge,
    )
    before = store.load()
    active_revision = before.active_revision
    if not active_revision:
        raise RuntimeError("Forced rollback acceptance requires an active model")
    snapshot = service.updater.stage_revision(args.candidate_revision)
    missing_dependency = store.paths.candidates / "intentionally-missing-tokenizer"

    def config_factory(path: Path, revision: str):
        config = service.launch_config(store.load(), snapshot=path, revision=revision)
        if revision == args.candidate_revision:
            return replace(config, tokenizer_snapshot=missing_dependency)
        return config

    error = ""
    try:
        service.updater.validate_and_activate(service.manager, config_factory)
        raise RuntimeError("Candidate unexpectedly passed forced failure")
    except VieNeuModelUpdateError as exc:
        error = str(exc)
    state = store.load()
    result = {
        "active_before": active_revision,
        "active_after": state.active_revision,
        "candidate_revision": args.candidate_revision,
        "candidate_snapshot_preserved": snapshot.is_dir(),
        "rejected_recorded": args.candidate_revision in state.rejected_revisions,
        "rollback_runtime_revision": (
            service.manager.identity.model_revision if service.manager.identity else ""
        ),
        "sanitized_error_present": bool(error) and str(missing_dependency) not in error,
    }
    service.shutdown()
    result["owned_processes_after_shutdown"] = service.manager.owned_processes_alive()
    if not all(
        (
            result["active_after"] == active_revision,
            result["candidate_snapshot_preserved"],
            result["rejected_recorded"],
            result["rollback_runtime_revision"] == active_revision,
            result["sanitized_error_present"],
            not result["owned_processes_after_shutdown"],
        )
    ):
        raise RuntimeError(f"Forced rollback acceptance failed: {result}")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
