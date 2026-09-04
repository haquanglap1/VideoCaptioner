"""Offscreen regression tests for the subtitle style tab's presenter wiring.

The style directory is redirected to ``tmp_path`` (the view persists a
``default`` style on first run) and preview rendering is replaced by a
recorder, so no worker thread, FFmpeg or Pillow rendering runs here.
"""

import json
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QUrl

from videocaptioner.core.entities import SubtitleRenderModeEnum
from videocaptioner.core.subtitle.style_manager import StyleMode
from videocaptioner.ui.common.config import cfg


@pytest.fixture
def interface(qapp, tmp_path, monkeypatch):
    from videocaptioner.ui.view import subtitle_style_interface as module

    styles_dir = tmp_path / "styles"
    monkeypatch.setattr(module, "SUBTITLE_STYLE_PATH", styles_dir)
    # Probing every system family through Pillow is slow and irrelevant here.
    monkeypatch.setattr(module, "pil_can_load_font", lambda name, size=12: False)
    renders = []
    monkeypatch.setattr(
        module.SubtitleStyleInterface,
        "updatePreview",
        lambda self: renders.append(self._current_style()),
    )
    cfg.set(cfg.subtitle_render_mode, SubtitleRenderModeEnum.ASS_STYLE)
    cfg.set(cfg.subtitle_style_name, "default")

    view = module.SubtitleStyleInterface()
    view.renders = renders
    view.styles_dir = styles_dir
    yield view
    view.deleteLater()


def _switch_to_rounded(view):
    view.renderModeCard.comboBox.setCurrentText(
        view._display_for_render_mode(SubtitleRenderModeEnum.ROUNDED_BG)
    )


def test_first_run_persists_widget_defaults_as_default_style(interface):
    view = interface
    assert (view.styles_dir / "ass-default.json").is_file()
    assert [view.styleNameComboBox.comboBox.itemText(i) for i in range(view.styleNameComboBox.comboBox.count())] == ["default"]
    assert cfg.get(cfg.subtitle_style_name) == "default"
    assert view._current_style().mode is StyleMode.ASS
    assert view.renders, "constructing the view renders a preview"
    assert view.assPrimaryGroup.isVisibleTo(view)
    assert not view.roundedBgGroup.isVisibleTo(view)


def test_switching_render_mode_swaps_groups_and_style_list(interface):
    view = interface
    _switch_to_rounded(view)
    assert cfg.get(cfg.subtitle_render_mode) is SubtitleRenderModeEnum.ROUNDED_BG
    assert view.roundedBgGroup.isVisibleTo(view)
    assert not view.assPrimaryGroup.isVisibleTo(view)
    assert (view.styles_dir / "rounded-default.json").is_file()
    assert view._current_style().mode is StyleMode.ROUNDED
    assert view.renders[-1].mode is StyleMode.ROUNDED


def test_load_style_applies_file_values_to_widgets(interface):
    view = interface
    (view.styles_dir / "ass-anime.json").write_text(
        json.dumps(
            {
                "mode": "ass",
                "font_name": "Noto Sans SC",
                "font_size": 61,
                "primary_color": "#ff00ff",
                "margin_bottom": 77,
                "secondary": {"font_name": "Noto Sans SC", "font_size": 33},
            }
        ),
        encoding="utf-8",
    )
    view.loadStyle("anime")
    assert view.assPrimarySizeCard.spinBox.value() == 61
    assert view.assVerticalSpacingCard.spinBox.value() == 77
    assert view.assSecondarySizeCard.spinBox.value() == 33
    assert view.assPrimaryColorCard.colorPicker.color.name() == "#ff00ff"
    assert cfg.get(cfg.subtitle_style_name) == "anime"
    assert "Style: Default,Noto Sans SC,61," in view._current_style().to_ass_string()
    assert not view._loading_style


def test_rounded_change_persists_cfg_and_style_file(interface):
    view = interface
    _switch_to_rounded(view)
    rendered_before = len(view.renders)
    view.roundedCornerRadiusCard.spinBox.setValue(33)
    assert cfg.get(cfg.rounded_bg_corner_radius) == 33
    saved = json.loads((view.styles_dir / "rounded-default.json").read_text(encoding="utf-8"))
    assert saved["mode"] == "rounded"
    assert saved["corner_radius"] == 33
    assert len(view.renders) == rendered_before + 1
    assert view.renders[-1].corner_radius == 33


def test_dropping_an_image_sets_the_preview_background(interface, tmp_path):
    view = interface
    image = tmp_path / "bg.png"
    image.write_bytes(b"png")
    urls = [QUrl.fromLocalFile(str(tmp_path / "notes.txt")), QUrl.fromLocalFile(str(image))]
    event = SimpleNamespace(mimeData=lambda: SimpleNamespace(hasUrls=lambda: True, urls=lambda: urls))
    rendered_before = len(view.renders)
    view.dropEvent(event)
    assert cfg.get(cfg.subtitle_preview_image) == image.as_posix() or cfg.get(
        cfg.subtitle_preview_image
    ) == str(image)
    assert len(view.renders) == rendered_before + 1
