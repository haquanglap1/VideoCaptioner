"""Context-aware translation producing display cues and source-owned speech blocks."""

from __future__ import annotations

import json
import re
from dataclasses import replace

import json_repair

from videocaptioner.core.prompts import get_prompt
from videocaptioner.core.translate.dialogue import (
    POLICY,
    DialogueCue,
    DialogueDocument,
    SpeechBlock,
    fingerprint,
    hard_boundary,
    validate_blocks,
)
from videocaptioner.core.translate.llm_translator import LLMTranslator


class DialogueTranslator(LLMTranslator):
    """Use one response for both display translation and the proposed spoken wording."""

    def _prepare(self, translate_data_list):
        self.dialogue_document = None
        self._source = {item.cue_id: item for item in translate_data_list}
        self._positions = {item.cue_id: i for i, item in enumerate(translate_data_list)}
        self._scenes = {}
        if self.conversation_snapshot:
            for scene in self.conversation_snapshot.context.scenes:
                if scene.evidence.status in ("confirmed", "locked"):
                    for cid in scene.cue_ids:
                        self._scenes[cid] = self._scenes.get(cid, "") + "/" + scene.id
        self._prompt = get_prompt("translate/dialogue", target_language=self.target_language.value,
                                  custom_prompt=self.custom_prompt)
        if self.is_reflect:
            self._prompt += "\nSilently review awkward literal wording and cross-cue coherence before returning the same final schema."
        self.source_signature = fingerprint([self._cue(item).__dict__ for item in translate_data_list])

    def _cue(self, item, translated=""):
        return DialogueCue(item.cue_id, item.original_text, translated, item.start_ms, item.end_ms,
                           item.speaker, self._scenes.get(item.cue_id, ""))

    def _boundary(self, previous, current):
        return (self._positions[current.cue_id] != self._positions[previous.cue_id] + 1
                or hard_boundary(self._cue(previous), self._cue(current)))

    def _split_chunks(self, translate_data_list):
        chunks, current = [], []
        budget = max(1, self.batch_num)
        for item in translate_data_list:
            if current and (self._boundary(current[-1], item)
                            or len(current) >= 2 * budget
                            or sum(len(c.original_text) for c in current) + len(item.original_text) > 4000
                            or (len(current) >= budget and re.search(r"[.!?。！？][\"'”’)]*$", current[-1].original_text))):
                chunks.append(current)
                current = []
            current.append(item)
        if current:
            chunks.append(current)
        return chunks

    def _get_cache_key(self, chunk):
        return "dialogue:" + fingerprint({
            "policy": POLICY, "prompt": self._prompt, "source": self.source_signature,
            "context": self.conversation_snapshot.fingerprint if self.conversation_snapshot else "",
            "owned": [item.cue_id for item in chunk], "model": self.model,
            "endpoint": self._credentials.base_url if self._credentials else "",
        })

    def _parse(self, payload, chunk):
        if not isinstance(payload, dict) or set(payload) != {"subtitle_translations", "speech_blocks"}:
            raise ValueError("Return subtitle_translations and speech_blocks only.")
        translations = payload["subtitle_translations"]
        if (not isinstance(translations, dict) or set(translations) != {item.cue_id for item in chunk}
                or not all(isinstance(text, str) and text.strip() and len(text) <= 8000 for text in translations.values())):
            raise ValueError("Every owned cue requires exactly one nonempty display translation.")
        if not isinstance(payload["speech_blocks"], list):
            raise ValueError("speech_blocks must be a list.")
        blocks = []
        for value in payload["speech_blocks"]:
            if (not isinstance(value, dict) or set(value) != {"cue_ids", "text"}
                    or not isinstance(value["cue_ids"], list)
                    or not all(isinstance(cid, str) for cid in value["cue_ids"])):
                raise ValueError("Each speech block requires cue_ids and text.")
            blocks.append(SpeechBlock(tuple(value["cue_ids"]), value["text"]))
        cues = tuple(self._cue(item, translations[item.cue_id]) for item in chunk)
        validate_blocks(cues, tuple(blocks))
        first_members = {block.cue_ids[0]: block for block in blocks}
        return [replace(item, translated_text=translations[item.cue_id],
                        speech_block=first_members.get(item.cue_id)) for item in chunk]

    def _safe_translate_chunk(self, chunk):
        if not self.is_running:
            raise RuntimeError("Translation cancelled.")
        key = self._get_cache_key(chunk)
        try:
            payload = self._cache.get(key, default=None)
            result = self._parse(payload, chunk) if payload is not None else None
        except (ValueError, TypeError, KeyError, AttributeError):
            result = None
        if result is None:
            result = self._translate_chunk(chunk)
            payload = {"subtitle_translations": {item.cue_id: item.translated_text for item in result},
                       "speech_blocks": [{"cue_ids": list(item.speech_block.cue_ids), "text": item.speech_block.text}
                                         for item in result if item.speech_block]}
        if not self.is_running:
            raise RuntimeError("Translation cancelled.")
        self._cache.set(key, payload, expire=86400 * 7)
        if self.update_callback:
            self.update_callback(result)
        return result

    def _translate_chunk(self, subtitle_chunk):
        owned = []
        for index, item in enumerate(subtitle_chunk):
            cue = self._cue(item)
            owned.append({"id": cue.cue_id, "text": cue.source_text, "start_ms": cue.start_ms,
                          "end_ms": cue.end_ms, "speaker": cue.speaker,
                          "boundary_before": index == 0 or self._boundary(subtitle_chunk[index - 1], item)})
        context = self.conversation_snapshot.request_data(tuple(item.cue_id for item in subtitle_chunk)) if self.conversation_snapshot else {}
        messages = [{"role": "system", "content": self._prompt},
                    {"role": "user", "content": json.dumps({"owned_cues": owned, "context_read_only": context}, ensure_ascii=False)}]
        for _ in range(self.MAX_STEPS):
            if not self.is_running:
                raise RuntimeError("Translation cancelled.")
            response = self._request(messages)
            payload = json_repair.loads(response.choices[0].message.content.strip())
            try:
                return self._parse(payload, subtitle_chunk)
            except ValueError as exc:
                messages.extend([{"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
                                 {"role": "user", "content": str(exc) + " Repair the complete JSON; keep all owned information."}])
        raise ValueError("Malformed dialogue translation after 3 responses; review required.")

    def _finish_translation(self, source, segments, translated_list):
        records = sorted(translated_list, key=lambda item: item.index)
        document = DialogueDocument(tuple(self._cue(item, item.translated_text) for item in records),
                                    tuple(item.speech_block for item in records if item.speech_block),
                                    self.target_language.value)
        document.validate()
        self.dialogue_document = document
        return source.with_segments(segments)
