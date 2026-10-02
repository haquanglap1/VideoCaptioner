"""OmniVoice adapter for the existing measured dubbing pipeline."""

from dataclasses import replace
from pathlib import Path

from videocaptioner.core.tts.base import BaseTTS

from .runtime import get_omnivoice_service
from .voices import ALIASES


def plan_batches(segments, options, default_voice):
    """Keep order and bound padded text length; oversized utterances run intact alone."""
    batch = []
    voice = ""
    longest = 0
    for index, segment in enumerate(segments):
        selected_voice = segment.voice or default_voice or "auto"
        selected = ALIASES.get(selected_voice, selected_voice)
        size = len(segment.text)
        if batch and (selected != voice or len(batch) >= options.batch_size
            or max(longest, size) * (len(batch) + 1) > options.batch_max_chars):
            yield voice, batch
            batch, longest = [], 0
        voice = selected
        batch.append((index, segment))
        longest = max(longest, size)
    if batch:
        yield voice, batch


class OmniVoiceTTS(BaseTTS):
    def __init__(self, config):
        # The orchestration cache includes model/voice identity; avoid the older
        # BaseTTS cache whose key does not include all managed runtime settings.
        super().__init__(replace(config, use_cache=False, response_format="wav", sample_rate=24000))

    def _synthesize(self, segment, output_path):
        segment.audio_duration = get_omnivoice_service().synthesize(segment.text, output_path,
            voice=segment.voice or self.config.voice or "auto", speed=self.config.speed)
        segment.audio_path = output_path

    def synthesize(self, tts_data, output_dir, callback=None, max_workers=1):
        # Request concurrency is deliberately separate from actual model batch size.
        service = get_omnivoice_service()
        if service.options is None:
            raise RuntimeError("OmniVoice is not acquired")
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        progress = callback or (lambda *args: None)
        total, done = len(tts_data.segments), 0
        for voice, batch in plan_batches(tts_data.segments, service.options, self.config.voice or "auto"):
            service.check()
            paths = {str(index): str(output / self._generate_filename(segment.text, index)) for index, segment in batch}
            segments = {str(index): segment for index, segment in batch}

            def receive(item_id, duration, error, warnings):
                nonlocal done
                segment = segments[item_id]
                segment.error = f"OmniVoice synthesis failed ({error})" if error else ""
                segment.warnings.extend(warnings)
                if not error:
                    segment.audio_path, segment.audio_duration = paths[item_id], duration
                done += 1
                progress(int(done * 100 / total), f"OmniVoice: batch <= {service.options.batch_size if service.options else 1}")

            try:
                service.synthesize_batch([(str(index), segment.text, paths[str(index)]) for index, segment in batch],
                    receive, voice=voice, speed=self.config.speed)
            except BaseException:
                # The orchestrator's finally persists already accepted WAVs and marks pending groups failed.
                for segment in tts_data.segments:
                    if not segment.audio_path and not segment.error:
                        segment.error = "OmniVoice batch interrupted; audio incomplete"
                raise
        progress(100, "OmniVoice: completed")
        return tts_data
