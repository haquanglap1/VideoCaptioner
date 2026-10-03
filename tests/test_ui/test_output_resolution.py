"""One persisted resolution choice reaches both output workflows."""

import json

from videocaptioner.core.dubbing.config import DubbingConfig
from videocaptioner.core.entities import SynthesisConfig
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.view.video_synthesis_interface import VideoSynthesisInterface


def test_existing_settings_keep_original_resolution():
    assert DubbingConfig().output_resolution == SynthesisConfig().output_resolution == 0


def test_factory_captures_resolution_for_both_outputs(monkeypatch):
    monkeypatch.setattr(cfg.output_resolution, "value", 1080)
    monkeypatch.setattr(cfg.dubbing_enabled, "value", True)
    synthesis = TaskFactory.create_synthesis_task("video.mp4", "subtitle.srt")
    dubbing = TaskFactory.create_dubbing_task("video.mp4", "subtitle.srt")
    assert synthesis.synthesis_config.output_resolution == 1080
    assert dubbing.dubbing_config.output_resolution == 1080
    monkeypatch.setattr(cfg.output_resolution, "value", 720)
    assert synthesis.synthesis_config.output_resolution == dubbing.dubbing_config.output_resolution == 1080


def test_resolution_menu_persists_selection(qapp, monkeypatch):
    monkeypatch.setattr(cfg.output_resolution, "value", 0)
    page = VideoSynthesisInterface()
    page.resolution_menu.menuActions()[2].trigger()
    assert page.resolution_button.text() == "1080p"
    assert json.loads(cfg.file.read_text(encoding="utf-8"))["Video"]["OutputResolution"] == 1080
    page.close()
