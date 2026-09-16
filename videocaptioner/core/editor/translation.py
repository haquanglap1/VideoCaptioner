"""Version only the source and target data a translation result depends on."""

import hashlib
import json

from .adapters import cue_metadata
from .models import EditorProject


def translation_fingerprint(project: EditorProject, selected_ids: set[str]) -> str:
    payload = {
        "project_id": project.project_id,
        "context": project.conversation_context.to_dict(),
        "cues": [{"id": c.id, "source": c.source_text or c.display_text,
                  "start": c.start_ms, "end": c.end_ms, "speaker": c.speaker,
                  "metadata": metadata.to_dict() if (metadata := cue_metadata(c)) else None,
                  "protected_target": c.display_text if c.id in selected_ids else None}
                 for c in sorted(project.cues, key=lambda c: (c.start_ms, c.end_ms, c.id))],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
