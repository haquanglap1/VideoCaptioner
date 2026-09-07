"""Connection probe using the same request/parser contract as file ASR."""

from videocaptioner.config import ASSETS_PATH
from videocaptioner.core.asr.api_profiles import ASRAPIError, resolve_profile
from videocaptioner.core.asr.api_transcription import (
    build_request,
    create_client,
    parse_response,
    submit_transcription,
)

TEST_AUDIO_PATH = ASSETS_PATH / "en.mp3"


def check_whisper_connection(
    base_url: str, api_key: str, model: str, *,
    provider: str = "custom", request_profile: str = "auto",
) -> tuple[bool, str]:
    """Recognize bundled public English audio; report observed timing separately.

    Deliberately omit the subtitle preflight: text-only recognition can succeed.
    No user transcript or arbitrary provider error body is included in the result.
    """
    try:
        profile = resolve_profile(model, request_profile, provider)
        request = build_request(
            TEST_AUDIO_PATH.read_bytes(), model, profile, language="en", word_timing=True,
        )
        with create_client(base_url, api_key) as client:
            response = submit_transcription(client, request)
        result = parse_response(response)
        if result.timing_level == "none":
            if not result.text:
                return True, "Recognition request succeeded but returned no speech or timestamps; subtitle timing was not verified."
            return True, "Recognition succeeded without timestamps. Subtitle export needs alignment (S2), not available yet."
        return True, f"Recognition succeeded with {result.timing_level} timestamps."
    except ASRAPIError as exc:
        return False, str(exc)
    except OSError:
        return False, "Bundled test audio is unavailable."
    except Exception:
        return False, "ASR connection check failed. Check provider and request profile."
