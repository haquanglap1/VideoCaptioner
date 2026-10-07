"""GUI side of speaker naming: settings switch, task snapshot and the review table; no LLM calls."""

import pytest

from videocaptioner.core.asr.asr_data import ASRData, ASRDataSeg
from videocaptioner.core.asr.local.speaker_naming import apply_naming
from videocaptioner.core.asr.metadata import (
    ASRMetadata,
    SpeakerAssociation,
    SpeakerNaming,
    SpeakerProfile,
    StageProvenance,
)
from videocaptioner.core.entities import LLMServiceEnum, TranscribeModelEnum
from videocaptioner.ui.common.config import cfg

STAGE = StageProvenance("pyannote", "repo", "rev", "policy")
RECOGNITION = StageProvenance("qwen-local", "repo", "rev", "qwen-text-v1")


def cue(text, start, end, label, cue_id):
    association = SpeakerAssociation(STAGE, "scope", "assigned", (label,), 900_000)
    return ASRDataSeg(text, start, end, cue_id=cue_id, metadata=ASRMetadata(
        "qwen-local", "scope", label, recognition=RECOGNITION, diarization=association))


def named_document():
    data = ASRData([cue("师父，弟子知错了。", 0, 1000, "SPEAKER_00", "c1"), cue("清宵，起来吧。", 1000, 2000, "SPEAKER_01", "c2"),
                    cue("是，师父。", 2000, 3000, "SPEAKER_00", "c3")])
    naming = SpeakerNaming("fixture-model", "sha", (
        SpeakerProfile("pyannote:scope:SPEAKER_00", "SPEAKER_00", "清宵", "弟子", "male", "teen", 0.95, ("c2",)),
        SpeakerProfile("pyannote:scope:SPEAKER_01", "SPEAKER_01", "", "师父", "unknown", "adult", 0.4, ("c1", "c3"))), 3, False)
    return apply_naming(data, naming)


@pytest.fixture(autouse=True)
def forbid_llm(monkeypatch):
    monkeypatch.setattr("videocaptioner.core.llm.owned_request.OwnedLLMRequest.__call__",
                        lambda *a, **kw: pytest.fail("GUI review must not call the LLM"))


def test_settings_switch_exists_and_local_config_requires_diarization(qapp, monkeypatch):
    from videocaptioner.ui.common.local_asr_settings import local_config
    from videocaptioner.ui.components.local_asr_cards import LocalASRSettingWidget

    widget = LocalASRSettingWidget()
    try:
        assert widget.controls.naming in widget.controls.cards
        assert widget.controls.naming.configItem is cfg.local_asr_name_speakers
    finally:
        widget.close()
    assert cfg.local_asr_name_speakers.defaultValue is True
    monkeypatch.setattr(cfg.transcribe_model, "value", TranscribeModelEnum.QWEN_LOCAL)
    monkeypatch.setattr(cfg.local_asr_name_speakers, "value", True)
    monkeypatch.setattr(cfg.local_asr_diarize, "value", True)
    assert local_config().name_speakers is True
    monkeypatch.setattr(cfg.local_asr_diarize, "value", False)
    assert local_config().name_speakers is False
    monkeypatch.setattr(cfg.local_asr_diarize, "value", True)
    monkeypatch.setattr(cfg.transcribe_model, "value", TranscribeModelEnum.FASTER_WHISPER)
    assert local_config().diarize is False and local_config().name_speakers is False


def test_task_factory_snapshots_the_selected_llm_only_when_configured(qapp, monkeypatch, tmp_path):
    from videocaptioner.ui.task_factory import TaskFactory

    video = tmp_path / "ep1.mp4"
    video.write_bytes(b"v")
    monkeypatch.setattr(cfg.transcribe_model, "value", TranscribeModelEnum.QWEN_LOCAL)
    monkeypatch.setattr(cfg.local_asr_diarize, "value", True)
    monkeypatch.setattr(cfg.local_asr_name_speakers, "value", True)
    monkeypatch.setattr(cfg.llm_service, "value", LLMServiceEnum.OPENAI)
    monkeypatch.setattr(cfg.openai_api_key, "value", "sk-fixture-only")
    monkeypatch.setattr(cfg.openai_api_base, "value", "https://fixture.invalid/v1")
    monkeypatch.setattr(cfg.openai_model, "value", "fixture-model")
    monkeypatch.setattr(cfg.llm_request_timeout, "value", 90)
    monkeypatch.setattr(cfg.translate_series_context, "value", "清宵 = đệ tử")
    task = TaskFactory.create_transcribe_task(str(video))
    settings = task.transcribe_config.speaker_naming
    assert settings is not None and settings.model == "fixture-model" and settings.timeout == 90
    assert settings.credentials.api_key == "sk-fixture-only" and "清宵 = đệ tử" in settings.context_notes
    assert task.transcribe_config.local_asr.name_speakers is True
    monkeypatch.setattr(cfg.openai_api_key, "value", "")
    assert TaskFactory.create_transcribe_task(str(video)).transcribe_config.speaker_naming is None
    monkeypatch.setattr(cfg.openai_api_key, "value", "sk-fixture-only")
    monkeypatch.setattr(cfg.local_asr_name_speakers, "value", False)
    assert TaskFactory.create_transcribe_task(str(video)).transcribe_config.speaker_naming is None


def test_dialog_lists_pending_first_and_reports_only_decisions(qapp):
    from videocaptioner.ui.components.speaker_naming_dialog import SpeakerNamingDialog

    document = named_document()
    dialog = SpeakerNamingDialog(document)
    try:
        assert dialog.table.rowCount() == 2
        assert dialog.table.item(0, 0).text() == "SPEAKER_01" and dialog.table.item(0, 2).text() == ""
        assert dialog.table.item(1, 0).text() == "SPEAKER_00" and dialog.table.item(1, 2).text() == "清宵"
        assert "清宵，起来吧。" in dialog.table.item(0, 8).text() and dialog.table.item(0, 1).text() == "1"
        dialog.table.item(0, 2).setText(" 老道 ")
        dialog.apply()
        assert dialog.decisions == {"pyannote:scope:SPEAKER_01": "老道"}
    finally:
        dialog.deleteLater()


def test_view_applies_user_names_through_the_context_stack_and_keeps_them_in_json(qapp, tmp_path, monkeypatch):
    from videocaptioner.ui.components import speaker_naming_dialog
    from videocaptioner.ui.view.subtitle_interface import SubtitleInterface

    document = named_document()
    path = tmp_path / "named.json"
    document.save(str(path))
    view = SubtitleInterface()
    try:
        view.load_subtitle_file(str(path))
        assert view._context_data.speaker_naming is not None and len(view._context_data.speaker_naming.pending) == 1

        def fake_exec(self):
            self.table.item(0, 2).setText("老道")
            self.apply()
            return 1
        monkeypatch.setattr(speaker_naming_dialog.SpeakerNamingDialog, "exec_", fake_exec)
        view.review_speaker_names()
        current = view.current_context_document()
        mapping = next(m for m in current.conversation_context.mappings if m.speaker_id == "pyannote:scope:SPEAKER_01")
        assert mapping.evidence.source == "user" and mapping.evidence.status == "confirmed"
        assert sorted(c.label for c in current.conversation_context.characters) == ["清宵", "老道"]
        assert not current.speaker_naming.pending
        assert view._context_stack.undo()
        assert len(view.current_context_document().speaker_naming.pending) == 1
        assert view._context_stack.redo()
        out = tmp_path / "saved.json"
        from videocaptioner.core.entities import SubtitleLayoutEnum
        from videocaptioner.core.subtitle.editing import export_subtitle
        current = view.current_context_document()
        export_subtitle(view.model._data, str(out), SubtitleLayoutEnum.ONLY_ORIGINAL,
                        context=current.conversation_context, speaker_naming=current.speaker_naming)
        reopened = ASRData.from_subtitle_file(str(out))
        assert reopened.speaker_naming == current.speaker_naming
        assert reopened.conversation_context.to_dict() == current.conversation_context.to_dict()
        srt = tmp_path / "saved.srt"
        export_subtitle(view.model._data, str(srt), SubtitleLayoutEnum.ONLY_ORIGINAL, speaker_naming=current.speaker_naming)
        assert "老道" not in srt.read_text(encoding="utf-8")
    finally:
        view.deleteLater()
