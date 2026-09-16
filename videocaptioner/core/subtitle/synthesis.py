"""Load subtitle inputs with explicit knowledge of a pipeline's SRT layout."""

from pathlib import Path

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.entities import SubtitleLayoutEnum


def load_synthesis_subtitles(
    path: str, *, input_layout: SubtitleLayoutEnum | None = None
) -> ASRData:
    """Restore parsed display SRT roles before applying a rendering layout.

    Raw standalone inputs retain the existing parser contract. Only a producer
    may supply the layout marker; neither filenames nor language order imply it.
    Monolingual exports have lost the other language, so keep every visible line
    as the renderer's monolingual fallback. JSON/ASS retain their own semantics.
    """
    data = ASRData.from_subtitle_file(path)
    if input_layout is None or Path(path).suffix.lower() != ".srt":
        return data
    for segment in data.segments:
        if input_layout == SubtitleLayoutEnum.TRANSLATE_ON_TOP and segment.translated_text:
            segment.text, segment.translated_text = segment.translated_text, segment.text
        elif input_layout in (SubtitleLayoutEnum.ONLY_ORIGINAL, SubtitleLayoutEnum.ONLY_TRANSLATE):
            if segment.translated_text:
                segment.text = f"{segment.text}\n{segment.translated_text}"
                segment.translated_text = ""
    return data
