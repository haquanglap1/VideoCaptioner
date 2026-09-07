"""Explicit model management. Token input is never an argument or persisted setting."""

import getpass

from videocaptioner.cli import exit_codes as EXIT
from videocaptioner.cli import output
from videocaptioner.core.asr.local.installer import install
from videocaptioner.core.asr.local.profiles import MODELS
from videocaptioner.core.asr.local.runtime import LocalRuntime, locate


def run(args) -> int:
    try:
        if args.action == "install":
            if args.root is None:
                output.error("Choose a new --root directory for this installation.")
                return EXIT.USAGE_ERROR
            if len({MODELS[model].runtime for model in args.models}) != 1:
                output.error("Choose --models for one runtime: Qwen/aligner or Community-1. Install them in separate new directories.")
                return EXIT.USAGE_ERROR
            token = getpass.getpass("Hugging Face read token (conditions must already be accepted): ") if "community-1" in args.models else ""
            install(args.root, tuple(args.models), token=token, progress=output.info)
            return EXIT.SUCCESS
        success = True
        for model in args.models:
            runtime = None
            try:
                layout = locate(model, args.root or "", verify=args.action == "probe")
                if args.action == "probe":
                    runtime = LocalRuntime(layout, args.timeout)
                    runtime.start()
                    output.info(f"{model}: health ready; probe released on completion (no inference).")
                else:
                    output.info(f"{model}: installed; health/inference not probed.")
            except (OSError, ValueError, RuntimeError) as exc:
                success = False
                output.error(str(exc))
            finally:
                if runtime is not None:
                    runtime.close()
        return EXIT.SUCCESS if success else EXIT.RUNTIME_ERROR
    except (OSError, ValueError, RuntimeError) as exc:
        output.error(str(exc))
        return EXIT.RUNTIME_ERROR
