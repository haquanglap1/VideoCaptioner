"""CLI model lifecycle for the managed VieNeu Local runtime."""

from __future__ import annotations

import json
from argparse import Namespace

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.core.tts.vieneu.model_updater import VieNeuModelUpdateError
from videocaptioner.core.tts.vieneu.service import get_vieneu_service


def run(args: Namespace) -> int:
    action = getattr(args, "vieneu_action", None)
    if not action:
        output.error("Missing VieNeu model action: status, update, or rollback")
        return EXIT.USAGE_ERROR
    service = get_vieneu_service()
    try:
        if action == "status":
            print(json.dumps(service.model_state().to_dict(), ensure_ascii=False, indent=2))
            return EXIT.SUCCESS
        if action == "rollback":
            service.shutdown()
            state = service.updater.rollback()
            output.info(f"VieNeu active revision: {state.active_revision}")
            return EXIT.SUCCESS
        if action == "update":
            service.prepare_update_prerequisites()
            requested_revision = str(getattr(args, "revision", "") or "")
            if requested_revision:
                service.updater.stage_revision(
                    requested_revision,
                    cancel_event=service._cancel_event,
                    manual_retry_rejected=bool(getattr(args, "retry_rejected", False)),
                )
            else:
                check = service.updater.stage_latest(
                    cancel_event=service._cancel_event,
                    manual_retry_rejected=bool(getattr(args, "retry_rejected", False)),
                )
                if check.status != "staged":
                    output.info(check.message or f"VieNeu model status: {check.status}")
                    return EXIT.SUCCESS
            state = service.model_state()
            result = service.updater.validate_and_activate(
                service.manager,
                lambda snapshot, revision: service.launch_config(
                    state, snapshot=snapshot, revision=revision
                ),
                cancel_event=service._cancel_event,
            )
            if result == "deferred":
                output.info("VieNeu candidate staged; activation deferred until the active job ends")
            else:
                output.info(f"VieNeu activated revision: {result.model_revision}")
            return EXIT.SUCCESS
        output.error(f"Unknown VieNeu action: {action}")
        return EXIT.USAGE_ERROR
    except VieNeuModelUpdateError as exc:
        output.error(str(exc))
        return EXIT.RUNTIME_ERROR
    except Exception as exc:
        output.error(str(exc))
        return EXIT.RUNTIME_ERROR
    finally:
        service.shutdown()
