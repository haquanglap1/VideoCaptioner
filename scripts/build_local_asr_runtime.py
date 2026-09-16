"""Install pinned S5 models in a new machine-local Windows runtime."""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from videocaptioner.core.asr.local.installer import install  # noqa: E402
from videocaptioner.core.asr.local.profiles import MODELS  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--models", nargs="+", required=True,
                        choices=["qwen-1.7b", "qwen-0.6b", "aligner", "community-1"])
    args = parser.parse_args()
    if len({MODELS[model].runtime for model in args.models}) != 1:
        parser.error("Install Qwen/aligner and Community-1 in separate new directories.")
    token = getpass.getpass("Hugging Face read token (conditions must already be accepted): ") if "community-1" in args.models else ""
    install(args.output, tuple(args.models), token=token, progress=print)


if __name__ == "__main__":
    main()
