"""DeepLX translator."""

import os
from typing import Callable, List, Optional

import requests

from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.translate.base import BaseTranslator
from videocaptioner.core.translate.types import TargetLanguage, get_language_code
from videocaptioner.core.utils.cache import generate_cache_key


class DeepLXTranslator(BaseTranslator):
    """DeepLX translator."""

    require_complete_result = True

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        target_language: TargetLanguage,
        timeout: int,
        update_callback: Optional[Callable],
        endpoint: str = "",
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            update_callback=update_callback,
        )
        self.timeout = timeout
        self.session = requests.Session()
        # Explicit endpoint first; DEEPLX_ENDPOINT is only read, never written.
        self.endpoint = (
            (endpoint or "").strip()
            or os.getenv("DEEPLX_ENDPOINT", "").strip()
            or "https://api.deeplx.org/translate"
        )

    def _translate_chunk(
        self, subtitle_chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        """Validate the entire chunk before applying any translations."""
        target_lang = get_language_code(self.target_language, "deeplx")
        translations = []

        for data in subtitle_chunk:
            if not self.is_running:
                raise RuntimeError("Translation cancelled.")
            try:
                response = self.session.post(
                    self.endpoint,
                    json={
                        "text": data.original_text,
                        "source_lang": "auto",
                        "target_lang": target_lang,
                    },
                    timeout=self.timeout,
                )
            except requests.RequestException:
                raise RuntimeError("DeepLX translation request failed; check the connection and retry.") from None
            try:
                if response.status_code != 200:
                    raise RuntimeError(f"DeepLX translation failed (HTTP {response.status_code}).")
                try:
                    payload = response.json()
                except ValueError:
                    raise RuntimeError("Malformed DeepLX translation response; no translations were applied.") from None
                if not isinstance(payload, dict) or payload.get("code", 200) != 200:
                    raise RuntimeError("Malformed DeepLX translation response; no translations were applied.")
                text = payload.get("data")
                if not isinstance(text, str) or (data.original_text.strip() and not text.strip()):
                    raise RuntimeError("Malformed DeepLX translation response; no translations were applied.")
                translations.append(text)
            finally:
                response.close()

        if not self.is_running:
            raise RuntimeError("Translation cancelled.")
        for data, text in zip(subtitle_chunk, translations):
            data.translated_text = text
        return subtitle_chunk

    def _get_cache_key(self, chunk: List[SubtitleProcessData]) -> str:
        """Skip legacy failures and separate configured services without exposing URLs."""
        class_name = self.__class__.__name__
        chunk_key = generate_cache_key(chunk)
        endpoint_key = generate_cache_key(self.endpoint)
        lang = self.target_language.value
        return f"{class_name}:validated-v2:{endpoint_key}:{chunk_key}:{lang}"

    def close(self):
        super().close()
        self.session.close()
