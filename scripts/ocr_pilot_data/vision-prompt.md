Read only the subtitle text visibly present in this single image. Return JSON only:
{"lines": [{"text": "exact visible text", "uncertain_spans": []}], "unreadable": false}

Keep the visible script (simplified or traditional), names, numerals, punctuation,
and line order. Do not translate, explain the scene, assign speakers, normalize
characters, repair grammar, or infer obscured/missing text. Mark an unreadable
span with U+FFFD and describe its position in uncertain_spans. If no subtitle is
visible, return an empty lines array. You receive no reference answer or adjacent
transcript. Do not derive timestamps from the image.
