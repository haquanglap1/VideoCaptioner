"""Bing translation with complete batches and bounded authentication recovery."""

from threading import Lock
from typing import Callable, List, Optional

import requests

from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.translate.base import BaseTranslator
from videocaptioner.core.translate.types import TargetLanguage, get_language_code
from videocaptioner.core.utils.cache import generate_cache_key


class BingTranslator(BaseTranslator):
    """Translate through the existing public Bing endpoint."""

    require_complete_result = True

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        target_language: TargetLanguage,
        update_callback: Optional[Callable],
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            update_callback=update_callback,
        )
        self.timeout = 20
        self.session = requests.Session()
        self.auth_endpoint = "https://edge.microsoft.com/translate/auth"
        self.translate_endpoint = (
            "https://api-edge.cognitive.microsofttranslator.com/translate"
        )

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
        }
        self._auth_lock = Lock()
        try:
            self._init_session()
        except Exception:
            self.close()
            raise

    def _init_session(self, stale_authorization: Optional[str] = None) -> None:
        """Only one concurrent chunk refreshes the same expired token."""
        with self._auth_lock:
            if not self.is_running:
                raise RuntimeError("Translation cancelled.")
            if (stale_authorization is not None
                    and self.headers.get("authorization") != stale_authorization):
                return
            try:
                response = self.session.get(self.auth_endpoint, timeout=self.timeout)
            except requests.RequestException:
                raise RuntimeError("Bing authentication request failed; check the connection or select another translator.") from None
            try:
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Bing authentication unavailable (HTTP {response.status_code}). "
                        "Select Google, DeepLX or LLM translation."
                    )
                token = response.text.strip()
                if not token:
                    raise RuntimeError("Bing authentication returned an empty token.")
                self.auth_token = token
                self.headers["authorization"] = f"Bearer {token}"
            finally:
                response.close()

    def _translate_chunk(
        self, subtitle_chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        if not subtitle_chunk:
            return subtitle_chunk
        # Keep the existing per-subtitle cap without silently discarding text.
        if any(len(row.original_text) > 5000 for row in subtitle_chunk):
            raise RuntimeError("Bing subtitles are limited to 5000 characters in the app; split the long subtitle first.")
        params = {
            "to": get_language_code(self.target_language, "bing"),
            "api-version": "3.0",
            "includeSentenceLength": "true",
        }
        for attempt in range(2):
            if not self.is_running:
                raise RuntimeError("Translation cancelled.")
            headers = self.headers.copy()
            try:
                response = self.session.post(
                    self.translate_endpoint,
                    params=params,
                    headers=headers,
                    json=[{"Text": row.original_text} for row in subtitle_chunk],
                    timeout=self.timeout,
                )
            except requests.RequestException:
                raise RuntimeError("Bing translation request failed; check the connection and retry.") from None
            try:
                if response.status_code in (401, 403) and attempt == 0:
                    self._init_session(headers.get("authorization"))
                    continue
                if response.status_code != 200:
                    raise RuntimeError(f"Bing translation failed (HTTP {response.status_code}).")
                try:
                    translations = self._validated_texts(response.json(), subtitle_chunk)
                except (ValueError, TypeError, KeyError, IndexError):
                    raise RuntimeError("Malformed Bing translation response; no translations were applied.") from None
                if not self.is_running:
                    raise RuntimeError("Translation cancelled.")
                # Validate the entire batch before mutating anything or notifying UI/cache.
                for row, text in zip(subtitle_chunk, translations):
                    row.translated_text = text
                return subtitle_chunk
            finally:
                response.close()
        raise RuntimeError("Bing authentication recovery failed.")

    @staticmethod
    def _validated_texts(payload, chunk: List[SubtitleProcessData]) -> List[str]:
        if not isinstance(payload, list) or len(payload) != len(chunk):
            raise ValueError("Batch size mismatch")
        texts = []
        for result, row in zip(payload, chunk):
            text = result["translations"][0]["text"]
            if not isinstance(text, str) or (row.original_text.strip() and not text.strip()):
                raise ValueError("Missing translation")
            texts.append(text)
        return texts

    def _get_cache_key(self, chunk: List[SubtitleProcessData]) -> str:
        # Older versions cached failed/partial responses under the unversioned key.
        return f"{self.__class__.__name__}:validated-v2:{generate_cache_key(chunk)}:{self.target_language.value}"

    def close(self):
        super().close()
        self.session.close()
