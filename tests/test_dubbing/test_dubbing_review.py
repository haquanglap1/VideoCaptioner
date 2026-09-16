"""Review/resume uses local WAV fixtures; no provider, model, or media rendering."""

import wave
from copy import deepcopy
from pathlib import Path

import pytest

from videocaptioner.core.dubbing.cache import build_tts_cache_key
from videocaptioner.core.dubbing.config import DubbingConfig, TTSProviderEnum
from videocaptioner.core.dubbing.engine import DubbingEngine
from videocaptioner.core.dubbing.models import (
    DubbingProviderError,
    DubbingReviewRequired,
    UnresolvedFitPolicy,
)
from videocaptioner.core.dubbing.orchestrator import DubbingOrchestrator
from videocaptioner.core.dubbing.review import (
    DubbingResumeError,
    DubbingReview,
    synthesis_cache_key,
)
from videocaptioner.core.llm.context import clear_task_context, get_task_context, set_task_context
from videocaptioner.core.tts import TTSConfig


def write_wav(path, duration):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * round(duration * 8000))


class Cancelled(Exception):
    pass


class FixtureProvider:
    def __init__(self, job):
        self.job = job

    def synthesize(self, data, output_dir, callback, max_workers):
        assert self.job.config.tts_config.use_cache is False
        for index, segment in enumerate(data.segments):
            self.job.calls.append(segment.text)
            self.job.contexts.append(get_task_context())
            duration = self.job.durations.get(segment.text)
            if duration is not None:
                segment.audio_path = str(Path(output_dir) / f"{index}.wav")
                write_wav(segment.audio_path, duration)
            if self.job.interrupt_after == index:
                if self.job.cancel:
                    callback(30, "cancel-at-provider")
                raise RuntimeError("fixture provider interrupted")


class FixtureRewrite:
    configured = True

    def rewrite(self, request, *, rescue):
        return "Reviewed first" if request.subtitle_text == "Spoken A Spoken B" else None


class Job:
    def __init__(self, root):
        self.root = root
        self.video = root / "input.mp4"
        self.video.write_bytes(b"media-fixture")
        self.subtitle = root / "spoken.srt"
        self.subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:00,500\nOriginal A\nSpoken A\n\n"
            "2\n00:00:00,550 --> 00:00:01,000\nOriginal B\nSpoken B\n\n"
            "3\n00:00:03,000 --> 00:00:04,000\nOriginal C\nSpoken C\n\n"
            "4\n00:00:06,000 --> 00:00:07,000\nOriginal D\nSpoken D\n", encoding="utf-8"
        )
        self.display = root / "display.srt"
        self.display.write_bytes(self.subtitle.read_bytes())
        self.cache = root / "cache"
        self.calls, self.contexts = [], []
        self.interrupt_after, self.cancel = None, False
        self.durations = {"Spoken A Spoken B": 5, "Reviewed first": 2.6,
                          "Spoken C": 1, "Spoken D": 4, "Edited last": 2}
        self.config = DubbingConfig(
            tts_config=TTSConfig("fixture", "never-save-this-key", "https://tts.invalid/v1", voice="test",
                                 sample_rate=8000, response_format="wav"),
            strip_cjk=False, rewrite_enabled=True, natural_max_speed=1,
            unresolved_policy=UnresolvedFitPolicy.SEQUENTIAL, target_language="vi",
        )
        self.engine = self.new_engine()

    def new_engine(self):
        return DubbingEngine(
            tts_provider_factory=lambda config: FixtureProvider(self),
            rewrite_service_factory=lambda config: FixtureRewrite(), cache_root=self.cache,
        )

    def run(self, review=None, **kwargs):
        def progress(value, message):
            if self.cancel and message == "cancel-at-provider":
                raise Cancelled("user cancelled")
        return self.engine.dub(str(self.video), str(self.subtitle), str(self.root / "output.mp4"), self.config,
                               progress, review=review, display_subtitle_path=str(self.display), **kwargs)

    def initial_review(self):
        with pytest.raises(DubbingReviewRequired):
            self.run()
        assert self.engine.last_review is not None
        return self.engine.last_review


@pytest.fixture
def job(tmp_path, monkeypatch):
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.shutil.which", lambda tool: tool)
    monkeypatch.setattr(DubbingOrchestrator, "_video_duration", staticmethod(lambda *args: 9.0))
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.build_voice_track", lambda *args, **kwargs: True)
    def mix(video, voice, output, **kwargs):
        Path(output).write_bytes(b"mock-mix")
        return True
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.mix_audio_tracks", mix)
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.adjust_audio_speed",
                        lambda *args: pytest.fail("1x sequential job must keep one native tempo"))
    return Job(tmp_path)


def test_rewritten_wording_survives_fresh_engine_resume_and_unchanged_cache_hits(job, monkeypatch):
    review = job.initial_review()
    assert [g.tts_text for g in review.groups] == ["Reviewed first", "Spoken C", "Spoken D"]
    assert review.groups[0].original_tts_text == "Spoken A Spoken B"
    assert len(review.groups[0].cue_ids) == 2
    assert review.groups[0].source_text == "Original A Original B"
    assert review.groups[0].subtitle_text == "Spoken A Spoken B"
    assert len(job.calls) == 4
    job.calls.clear()
    job.engine = job.new_engine()
    monkeypatch.setattr(job.engine, "_create_rewrite_service", lambda *a: pytest.fail("resume must preserve wording"))
    with pytest.raises(DubbingReviewRequired):
        job.run(DubbingReview.from_report(review.to_dict()))
    assert job.calls == []
    assert job.engine.last_report["summary"]["cache_hits"] == 3
    assert job.engine.last_report["summary"]["output_created"] is False
    assert job.engine.last_review.groups[-1].needs_review
    assert all(group.applied_speed == 1 for group in job.engine.last_review.groups)


def test_editing_one_group_synthesizes_only_that_group_and_keeps_display(job):
    review = job.initial_review()
    source_bytes, display_bytes = job.subtitle.read_bytes(), job.display.read_bytes()
    edited = review.with_group_text("g-0003", "Edited last")
    assert review.groups[-1].tts_text == "Spoken D"
    assert edited.groups[-1].tts_text == "Edited last"
    assert edited.groups[:-1] == review.groups[:-1]
    job.calls.clear()
    set_task_context("review-job", "input.mp4", "dubbing")
    try:
        expected_context = get_task_context()
        job.run(edited)
    finally:
        clear_task_context()
    assert job.calls == ["Edited last"]
    assert job.contexts[-1] == expected_context
    assert job.engine.last_report["summary"]["cache_hits"] == 2
    assert job.engine.last_report["summary"]["output_created"] is True
    assert job.subtitle.read_bytes() == source_bytes and job.display.read_bytes() == display_bytes
    assert all(not group.needs_review for group in job.engine.last_review.groups)
    assert list(job.root.glob("*.json")) == []


def test_save_load_is_explicit_detached_and_credential_free(job):
    review = job.initial_review().with_group_text("g-0003", "Edited last")
    path = job.root / "requested-review.json"
    review.save(path)
    assert "never-save-this-key" not in path.read_text(encoding="utf-8")
    loaded = DubbingReview.load(path)
    assert loaded.to_dict() == review.to_dict()
    loaded.plan.groups[0].tts_text = "mutation outside review"
    assert loaded.groups[0].tts_text == "Reviewed first"
    job.calls.clear()
    job.run(loaded)
    assert job.calls == ["Edited last"]


@pytest.mark.parametrize("kind", ["media", "subtitle", "display", "voice", "speed", "provider_identity", "group", "cue", "source_text", "timeline"])
def test_mismatch_rejected_before_provider_creation_and_review_kept(job, monkeypatch, kind):
    review = job.initial_review()
    raw = review.to_dict()
    if kind in ("media", "subtitle", "display"):
        path = {"media": job.video, "subtitle": job.subtitle, "display": job.display}[kind]
        path.write_bytes(path.read_bytes() + b"\nchanged")
    elif kind == "voice":
        job.config.tts_config.voice = "other"
    elif kind == "speed":
        job.config.tts_config.speed = 1.1
    elif kind == "provider_identity":
        job.config.managed_tts_identity = {"model_revision": "different"}
    elif kind == "group":
        raw["groups"][0]["group_id"] = "unrelated-group"
    elif kind == "cue":
        raw["groups"][0]["cue_ids"] = [101, 102]
    elif kind == "source_text":
        raw["groups"][0]["source_text"] = "unrelated source"
    elif kind == "timeline":
        raw["groups"][0]["subtitle_end_time"] = 1.1
    review = DubbingReview.from_report(raw)
    job.calls.clear()
    monkeypatch.setattr(job.engine, "_create_tts_provider", lambda *a: pytest.fail("invalid review reached provider"))
    with pytest.raises(DubbingResumeError, match="mismatch"):
        job.run(review)
    assert job.calls == []
    assert job.engine.last_review.to_dict() == review.to_dict()
    assert job.engine.last_report == review.to_dict()


def test_explicit_config_change_reuses_only_matching_configuration(job):
    review = job.initial_review()
    job.config.tts_config.voice = "other-voice"
    job.calls.clear()
    with pytest.raises(DubbingReviewRequired):
        job.run(review, allow_config_change=True)
    assert job.calls == ["Reviewed first", "Spoken C", "Spoken D"]
    rebound = job.engine.last_review
    job.calls.clear()
    with pytest.raises(DubbingReviewRequired):
        job.run(rebound)
    assert job.calls == []


@pytest.mark.parametrize("field,value", [("response_format", "mp3"), ("base_url", "https://tts.invalid/custom/v1"),
                                        ("custom_prompt", "Speak clearly"), ("sample_rate", 16000)])
def test_explicit_synthesis_option_changes_cannot_reuse_old_audio(job, field, value):
    review = job.initial_review()
    setattr(job.config.tts_config, field, value)
    with pytest.raises(DubbingResumeError, match="settings mismatch"):
        job.run(review)
    job.calls.clear()
    with pytest.raises(DubbingReviewRequired):
        job.run(review, allow_config_change=True)
    assert job.calls == ["Reviewed first", "Spoken C", "Spoken D"]
    assert job.config.tts_config.use_cache is True


def test_managed_wav_checkpoint_cache_key_is_unchanged(job):
    job.config.tts_provider = TTSProviderEnum.OMNIVOICE_LOCAL
    job.config.managed_tts_identity = {"model_revision": "pinned", "seed": 0}
    tts = job.config.tts_config
    assert synthesis_cache_key("final wording", job.config) == build_tts_cache_key(
        text="final wording", provider="omnivoice-local", model=tts.model, voice=tts.voice,
        api_base=tts.base_url, speed=tts.speed, sample_rate=tts.sample_rate,
        runtime_identity=job.config.managed_tts_identity,
    )


def test_report_audio_path_cache_key_and_fit_claims_are_never_trusted(job):
    review = job.initial_review()
    raw = review.to_dict()
    forged_audio = job.root / "do-not-use.wav"
    write_wav(forged_audio, 0.1)
    for group in raw["groups"]:
        group.update(audio_path=str(forged_audio), cache_key="../../do-not-use", measured_duration=0.1,
                     fit_status="fit", needs_review=False, fit_ratio=0.01)
    raw["command"] = "this JSON is data only"
    job.calls.clear()
    with pytest.raises(DubbingReviewRequired):
        job.run(DubbingReview.from_report(raw))
    assert job.calls == []
    assert job.engine.last_review.groups[-1].measured_duration == 4
    assert job.engine.last_review.groups[-1].needs_review


@pytest.mark.parametrize("damage", ["missing", "bad-json", "json-list", "truncated-wav"])
def test_missing_or_corrupt_cache_resynthesizes_one_group(job, damage):
    review = job.initial_review()
    key = review.groups[1].cache_key
    wav, metadata = job.cache / f"{key}.wav", job.cache / f"{key}.json"
    if damage == "missing":
        wav.unlink()
    elif damage == "bad-json":
        metadata.write_text("{invalid", encoding="utf-8")
    elif damage == "json-list":
        metadata.write_text("[]", encoding="utf-8")
    else:
        wav.write_bytes(wav.read_bytes()[:45])
    job.calls.clear()
    with pytest.raises(DubbingReviewRequired):
        job.run(review)
    assert job.calls == ["Spoken C"]
    assert job.engine.last_report["summary"]["cache_hits"] == 2


@pytest.mark.parametrize("cancel", [False, True])
def test_partial_provider_exception_or_callback_cancellation_keeps_review_and_completed_cache(job, cancel):
    job.config.rewrite_enabled = False
    job.interrupt_after, job.cancel = 0, cancel
    with pytest.raises(Cancelled if cancel else RuntimeError):
        job.run()
    review = job.engine.last_review
    assert review.can_resume
    assert [g.tts_text for g in review.groups] == ["Spoken A Spoken B", "Spoken C", "Spoken D"]
    assert job.engine.last_report["summary"]["output_created"] is False
    assert review.groups[1].needs_review
    assert (job.cache / f"{review.groups[0].cache_key}.wav").is_file()
    job.calls.clear()
    job.cancel, job.interrupt_after = False, None
    with pytest.raises(DubbingReviewRequired):
        job.run(review)
    assert job.calls == ["Spoken C", "Spoken D"]


def test_provider_missing_audio_preserves_edited_wording_for_retry(job):
    review = job.initial_review().with_group_text("g-0003", "No audio yet")
    with pytest.raises(DubbingProviderError):
        job.run(review)
    failed = job.engine.last_review
    assert failed.groups[-1].tts_text == "No audio yet"
    assert failed.groups[-1].needs_review
    job.durations["No audio yet"] = 2
    job.calls.clear()
    job.run(failed)
    assert job.calls == ["No audio yet"]


def legacy_report(review):
    raw = review.to_dict()
    raw.pop("resume_metadata")
    for group in raw["groups"]:
        group.pop("original_tts_text")
    return DubbingReview.from_report(raw)


def test_legacy_checkpoint_requires_explicit_import_with_honest_provenance(job, monkeypatch):
    review = legacy_report(job.initial_review())
    assert not review.can_resume
    assert "no source/settings fingerprints" in review.provenance_note
    with pytest.raises(DubbingResumeError, match="explicit import"):
        job.run(review)
    job.calls.clear()
    monkeypatch.setattr(job.engine, "_create_tts_provider", lambda *args: pytest.fail("import cannot synthesize"))
    imported = job.engine.import_review(review, video_path=str(job.video), subtitle_path=str(job.subtitle),
                                        display_subtitle_path=str(job.display), config=job.config)
    assert imported.can_resume
    assert imported.plan.resume_metadata.provenance == "legacy-user-bound"
    assert "historical media identity" in imported.provenance_note
    assert imported.groups[0].tts_text == "Reviewed first"
    assert imported.groups[0].original_tts_text == "Spoken A Spoken B"
    assert not imported.plan.summary["output_created"]
    assert job.calls == []
    job.engine = job.new_engine()
    with pytest.raises(DubbingReviewRequired):
        job.run(imported)
    assert job.calls == []
    assert job.engine.last_review.plan.resume_metadata.provenance == "legacy-user-bound"


@pytest.mark.parametrize("change", ["missing-key", "speed", "membership", "provider"])
def test_legacy_import_rejects_unverifiable_evidence(job, change):
    raw = legacy_report(job.initial_review()).to_dict()
    if change == "missing-key":
        raw["groups"][0]["cache_key"] = ""
    elif change == "speed":
        job.config.tts_config.speed = 1.1
    elif change == "membership":
        raw["groups"][0]["cue_ids"] = ["other-cue"]
    else:
        raw["provider_identity"] = {"model_revision": "other"}
    review = DubbingReview.from_report(raw)
    job.calls.clear()
    with pytest.raises(DubbingResumeError):
        job.engine.import_review(review, video_path=str(job.video), subtitle_path=str(job.subtitle), config=job.config)
    assert job.calls == []
    assert job.engine.last_review.to_dict() == review.to_dict()


@pytest.mark.parametrize("change", ["schema", "plan-schema", "duplicate-group", "duplicate-cue", "nan", "empty-text", "metadata-schema", "bool-timing"])
def test_malformed_report_is_rejected_with_domain_error(job, change):
    raw = job.initial_review().to_dict()
    if change == "schema":
        raw["schema_version"] = "unknown"
    elif change == "plan-schema":
        raw["plan_schema_version"] = "unknown"
    elif change == "duplicate-group":
        raw["groups"].append(deepcopy(raw["groups"][0]))
    elif change == "duplicate-cue":
        raw["groups"][1]["cue_ids"] = raw["groups"][0]["cue_ids"]
    elif change == "nan":
        raw["groups"][0]["measured_duration"] = float("nan")
    elif change == "bool-timing":
        raw["groups"][0]["start_time"] = True
    elif change == "metadata-schema":
        raw["resume_metadata"]["schema_version"] = "future"
    else:
        raw["groups"][0]["tts_text"] = " \n "
    with pytest.raises(DubbingResumeError):
        DubbingReview.from_report(raw)


def test_duplicate_json_fields_are_rejected(job):
    path = job.root / "ambiguous.json"
    path.write_text('{"groups": [], "groups": []}', encoding="utf-8")
    with pytest.raises(DubbingResumeError, match="Duplicate JSON field"):
        DubbingReview.load(path)


def test_failed_explicit_report_write_still_keeps_ram_review(job, monkeypatch):
    job.config.report_path = str(job.root / "report.json")
    def denied(*args, **kwargs):
        raise PermissionError("fixture report cannot be saved")
    monkeypatch.setattr("videocaptioner.core.dubbing.orchestrator.os.replace", denied)
    # Cache writes also use os.replace: retain a report even when disk writes fail early.
    with pytest.raises(PermissionError):
        job.run()
    assert job.engine.last_review.can_resume
    assert job.engine.last_report["summary"]["output_created"] is False
    assert job.engine.last_review.groups[0].tts_text
