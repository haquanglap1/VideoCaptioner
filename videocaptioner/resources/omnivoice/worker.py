"""Isolated OmniVoice JSON-line worker. Never imported by the Qt application."""
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false

import argparse
import contextlib
import json
import logging
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()
    scratch = Path(args.scratch).resolve()
    output = sys.stdout

    def send(value):
        output.write("VC_OMNI " + json.dumps(value, ensure_ascii=False) + "\n")
        output.flush()

    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import soundfile as sf
        import torch
        from omnivoice import OmniVoice

        logging.disable(logging.INFO)
        model = OmniVoice.from_pretrained(args.model, device_map="cuda:0", dtype=torch.float16,
                                          load_asr=False, local_files_only=True)
        send({"status": "ready", "sample_rate": model.sampling_rate})
        prompt = None
        for line in sys.stdin:
            try:
                request = json.loads(line)
                operation = request["operation"]
                if operation == "configure":
                    ref_audio, ref_text = request.get("reference_audio"), request.get("reference_text")
                    if bool(ref_audio) != bool(ref_text):
                        raise ValueError("Both reference audio and transcript are required")
                    if ref_audio:
                        if not Path(ref_audio).resolve().is_relative_to(scratch):
                            raise ValueError("Reference must be an owned snapshot")
                        prompt = model.create_voice_clone_prompt(ref_audio=ref_audio, ref_text=ref_text)
                    send({"status": "configured"})
                    continue
                if operation != "synthesize":
                    raise ValueError("Unknown worker operation")
                destination = Path(request["output"]).resolve()
                if not destination.is_relative_to(scratch) or destination.suffix != ".wav":
                    raise ValueError("Output must be an owned WAV file")
                voice = request.get("voice", "auto")
                if voice not in ("auto", "male", "female"):
                    raise ValueError("Select auto, male or female for OmniVoice")
                torch.manual_seed(request["seed"])
                audio = model.generate(text=request["text"], language=request["language"],
                    voice_clone_prompt=prompt, instruct=voice if prompt is None and voice != "auto" else None,
                    speed=request["speed"], num_step=request["steps"])[0]
                if not len(audio) or not np.isfinite(audio).all():
                    raise ValueError("OmniVoice produced invalid audio")
                sf.write(str(destination), audio, model.sampling_rate, subtype="PCM_16")
                send({"status": "complete", "sample_rate": model.sampling_rate,
                      "samples": len(audio)})
            except Exception as exc:
                # Do not echo private text, reference paths, or a provider traceback.
                send({"status": "error", "error_type": type(exc).__name__})


if __name__ == "__main__":
    main()
