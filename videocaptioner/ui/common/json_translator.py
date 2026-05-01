"""JSON-backed QTranslator.

Workaround for environments where Qt's lrelease tool isn't available to compile
.ts → .qm. We override QTranslator.translate() so PyQt's `tr()` calls resolve
against a plain JSON file shipped with the package.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QTranslator


class JsonTranslator(QTranslator):
    """QTranslator subclass that resolves strings from a JSON dict.

    JSON shape:
        {
            "Context::source string": "translated",   # context-qualified
            "source string": "translated"              # global fallback
        }
    """

    def __init__(self, json_path: Path, parent=None):
        super().__init__(parent)
        self._mapping: dict[str, str] = {}
        try:
            with json_path.open("r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict):
                self._mapping = {str(k): str(v) for k, v in data.items() if v}
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError):
            # Bad JSON should not crash the GUI — fall back to source strings.
            self._mapping = {}

    def isEmpty(self) -> bool:  # noqa: N802 — Qt naming
        return not self._mapping

    def translate(  # noqa: N802 — Qt naming
        self,
        context: Optional[str],
        source_text: Optional[str],
        disambiguation: Optional[str] = None,
        n: int = -1,
    ) -> str:
        if not source_text:
            return ""
        if context:
            keyed = f"{context}::{source_text}"
            if keyed in self._mapping:
                return self._mapping[keyed]
        if source_text in self._mapping:
            return self._mapping[source_text]
        # Since this subclass overrides QTranslator.translate(), returning ""
        # would render an empty string in PyQt instead of falling back.
        return source_text
