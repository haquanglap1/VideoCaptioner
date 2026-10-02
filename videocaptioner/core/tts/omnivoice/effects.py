"""Optional pitch and punctuation tails; preserve speech and measure the final WAV."""

import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from videocaptioner.core.asr.alignment.audio import stop_process
from videocaptioner.core.utils.subprocess_helper import _NO_WINDOW, child_environment

POLICY = "omnivoice-pitch-terminal-pause-v1"


def terminal_pause_ms(text: str, base_ms: int) -> int:
    terminal = text.rstrip().rstrip('\"\'”’)]}').rstrip()
    if terminal.endswith((".", "?", "!", "…")):
        return base_ms * 2
    return base_ms if terminal.endswith((",", ";", ":")) else 0


def apply_effects(source, destination, text, options, check=lambda: None):
    """Use native pitch processing at tempo1; a failed filter never silently bypasses the option."""
    source, destination = Path(source), Path(destination)
    check()
    pause = terminal_pause_ms(text, options.punctuation_pause_ms)
    if not options.pitch_semitones and not pause:
        shutil.copyfile(source, destination)
        return
    with tempfile.TemporaryDirectory(prefix="effects-", dir=source.parent) as directory:
        processed = source
        if options.pitch_semitones:
            processed = Path(directory) / "pitch.wav"
            ratio = 2 ** (options.pitch_semitones / 12)
            try:
                process = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source),
                    "-af", f"rubberband=tempo=1:pitch={ratio:.12g}:formant=preserved",
                    "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(processed)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=child_environment(), creationflags=_NO_WINDOW)
            except OSError:
                raise RuntimeError("OmniVoice pitch requires FFmpeg with the rubberband filter") from None
            try:
                deadline = time.monotonic() + options.timeout
                while process.poll() is None:
                    check()
                    if time.monotonic() >= deadline:
                        raise RuntimeError("OmniVoice pitch processing timed out")
                    try:
                        process.wait(timeout=0.1)
                    except subprocess.TimeoutExpired:
                        pass
                if process.returncode:
                    raise RuntimeError("OmniVoice pitch failed; verify FFmpeg rubberband support")
            finally:
                stop_process(process)
        check()
        if not pause:
            shutil.copyfile(processed, destination)
            return
        with wave.open(str(processed), "rb") as original, wave.open(str(destination), "wb") as output:
            if original.getnchannels() != 1 or original.getsampwidth() != 2 or original.getframerate() != 24000:
                raise RuntimeError("Pitch processing returned an unexpected WAV format")
            output.setparams(original.getparams())
            while data := original.readframes(24000):
                check()
                output.writeframes(data)
            output.writeframes(b"\0\0" * (24000 * pause // 1000))
