"""Google translation with complete, validated batches."""

import html
import re
from typing import Callable, List, Optional

import requests

from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.translate.base import BaseTranslator
from videocaptioner.core.translate.types import TargetLanguage, get_language_code
from videocaptioner.core.utils.cache import generate_cache_key


class GoogleTranslator(BaseTranslator):
    """Translate through the existing public Google endpoint."""

    require_complete_result = True

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        target_language: TargetLanguage,
        timeout: int,
        update_callback: Optional[Callable],
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            update_callback=update_callback,
        )
        self.timeout = timeout
        self.session = requests.Session()
        self.endpoint = "https://translate.google.com/m"
        self.headers = {
            "User-Agent": "Mozilla/4.0 (compatible;MSIE 6.0;Windows NT 5.1;SV1;.NET CLR 1.1.4322;.NET CLR 2.0.50727;.NET CLR 3.0.04506.30)"
        }

    def _translate_chunk(
        self, subtitle_chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        """Validate the entire chunk before applying any translations."""
        if any(len(row.original_text) > 5000 for row in subtitle_chunk):
            raise RuntimeError("Google subtitles are limited to 5000 characters in the app; split the long subtitle first.")
        target_lang = get_language_code(self.target_language, "google")
        translations = []

        for data in subtitle_chunk:
            if not self.is_running:
                raise RuntimeError("Translation cancelled.")
            try:
                response = self.session.get(
                    self.endpoint,
                    params={"tl": target_lang, "sl": "auto", "q": data.original_text},
                    headers=self.headers,
                    timeout=self.timeout,
                )
            except requests.RequestException:
                raise RuntimeError("Google translation request failed; check the connection and retry.") from None
            try:
                if response.status_code != 200:
                    raise RuntimeError(f"Google translation failed (HTTP {response.status_code}).")
                # Require a complete text container, not a prefix before unexpected markup.
                re_result = re.findall(
                    r'(?s)class="(?:t0|result-container)">([^<]*)</div\s*>', response.text
                )
                if len(re_result) != 1:
                    raise RuntimeError("Malformed Google translation response; no translations were applied.")
                text = html.unescape(re_result[0])
                if data.original_text.strip() and not text.strip():
                    raise RuntimeError("Malformed Google translation response; no translations were applied.")
                translations.append(text)
            finally:
                response.close()

        if not self.is_running:
            raise RuntimeError("Translation cancelled.")
        for data, text in zip(subtitle_chunk, translations):
            data.translated_text = text
        return subtitle_chunk

    def _get_cache_key(self, chunk: List[SubtitleProcessData]) -> str:
        # Older entries may contain failed responses or silently truncated input.
        return f"{self.__class__.__name__}:validated-v2:{generate_cache_key(chunk)}:{self.target_language.value}"

    def close(self):
        super().close()
        self.session.close()
