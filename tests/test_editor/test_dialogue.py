"""Dialogue ownership survives editor persistence without repeating speech per cue."""

import pytest

from videocaptioner.core.editor.commands import CommandStack, EditCueTextCommand
from videocaptioner.core.editor.dialogue import dialogue_from_project
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.core.translate.dialogue import DialogueCue, DialogueDocument, SpeechBlock


def test_editor_dialogue_roundtrip_and_explicit_wording_edit(tmp_path):
    document = DialogueDocument((DialogueCue("a", "Nếu mai", "Nếu mai", 0, 1000),
                                 DialogueCue("b", "trời mưa.", "trời mưa.", 1000, 2000)),
                                (SpeechBlock(("a", "b"), "Nếu mai trời mưa."),), "vi")
    source = tmp_path / "source.dialogue.json"
    document.save(source)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"synthetic")
    store = EditorProjectStore()
    project = store.create_from_media(str(video), str(source), duration_ms=5000)
    assert [c.tts_text for c in project.cues] == ["Nếu mai trời mưa.", ""]
    assert [c.display_text for c in project.cues] == ["Nếu mai", "trời mưa."]
    assert dialogue_from_project(project) == document
    path, _ = store.save(project, tmp_path / "edit.json")
    restored = store.load(path)
    assert dialogue_from_project(restored) == document
    stack = CommandStack()
    stack.execute(EditCueTextCommand(restored, "a", "tts_text", "Nếu ngày mai trời mưa."))
    assert dialogue_from_project(restored).blocks[0].text == "Nếu ngày mai trời mưa."
    stack.undo()
    assert dialogue_from_project(restored) == document
    stack.execute(EditCueTextCommand(restored, "b", "tts_text", "Lời bị lặp."))
    with pytest.raises(ValueError, match="cue đầu"):
        dialogue_from_project(restored)


def test_editor_rejects_stale_membership_after_cue_deletion(tmp_path):
    document = DialogueDocument((DialogueCue("a", "A", "A", 0, 1000),
                                 DialogueCue("b", "B", "B", 1000, 2000)),
                                (SpeechBlock(("a", "b"), "A B"),), "vi")
    source = tmp_path / "source.dialogue.json"
    document.save(source)
    project = EditorProjectStore().create_from_media(str(tmp_path / "video.mp4"), str(source), duration_ms=5000)
    project.cues.pop()
    with pytest.raises(ValueError, match="thêm/xóa"):
        dialogue_from_project(project)


def test_dialogue_audio_is_played_once_with_actual_duration_and_preview_offset(tmp_path):
    import wave

    from videocaptioner.core.editor.dialogue import existing_dialogue_audio
    document = DialogueDocument((DialogueCue("a", "A", "A", 0, 1000),
                                 DialogueCue("b", "B", "B", 1000, 2000)),
                                (SpeechBlock(("a", "b"), "A B"),), "vi")
    source = tmp_path / "source.dialogue.json"
    document.save(source)
    project = EditorProjectStore().create_from_media(str(tmp_path / "video.mp4"), str(source), duration_ms=5000)
    audio = tmp_path / "speech.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x01\x00" * 72000)
    for cue in project.cues:
        cue.audio_path = str(audio)
    result = existing_dialogue_audio(project, 0, 5000)
    assert len(result) == 1
    assert result[0]["end_time"] == 3
    preview = existing_dialogue_audio(project, 1000, 2500)
    assert len(preview) == 1 and preview[0]["audio_offset"] == 1
