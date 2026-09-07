from typing import Any, Callable, Optional, Union

from .api_profiles import (
    ASRAPIError,
    fingerprint,
    normalize_endpoint,
    require_subtitle_timing,
    resolve_profile,
)
from .api_transcription import (
    build_request,
    create_client,
    effective_language,
    effective_prompt,
    parse_response,
    submit_transcription,
)
from .asr_data import ASRDataSeg
from .base import BaseASR


class WhisperAPI(BaseASR):
    """OpenAI-compatible ASR with explicit subtitle timing requirements."""

    def __init__(
        self,
        audio_input: Union[str, bytes],
        whisper_model: str,
        need_word_time_stamp: bool = False,
        language: str = "zh",
        prompt: str = "",
        base_url: str = "",
        api_key: str = "",
        use_cache: bool = False,
        provider: str = "custom",
        request_profile: str = "auto",
    ):
        self.profile = resolve_profile(whisper_model, request_profile, provider)
        require_subtitle_timing(self.profile)
        self.base_url = normalize_endpoint(base_url)
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ASRAPIError("ASR API key must be set.")
        self.model = whisper_model.strip()
        self.language = effective_language(language)
        self.prompt = effective_prompt(self.language, prompt)
        self.provider = provider
        self.need_word_time_stamp = need_word_time_stamp
        super().__init__(audio_input, use_cache)

    def _get_audio_duration(self) -> float:
        # This provider has no duration rate limiter; byte validation needs no FFmpeg.
        return 0.0

    def _run(self, callback: Optional[Callable[[int, str], None]] = None, **kwargs: Any) -> dict:
        return self._submit()

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        return parse_response(resp_data).subtitle_segments(self.need_word_time_stamp)

    def _get_key(self) -> str:
        return fingerprint(
            self.file_binary or b"", self.base_url, self.model, self.language,
            self.prompt, self.profile, self.need_word_time_stamp, self.provider,
        )

    def _submit(self) -> dict:
        request = build_request(
            self.file_binary or b"", self.model, self.profile,
            language=self.language, prompt=self.prompt, word_timing=self.need_word_time_stamp,
        )
        with create_client(self.base_url, self.api_key) as client:
            response = submit_transcription(client, request)
        # Validate timing before the base class persists a successful subtitle result.
        self._make_segments(response)
        return {k: response[k] for k in ("text", "words", "segments") if k in response}
