# pyright: reportAttributeAccessIssue=false
"""Native Video Editor navigation page and UI-thread orchestration."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QKeySequence, QPalette
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    CommandBar,
    FlowLayout,
    InfoBar,
    InfoBarPosition,
    MessageBox,
    PushButton,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

from videocaptioner.config import CACHE_PATH
from videocaptioner.core.editor.adapters import update_cues_from_groups
from videocaptioner.core.editor.commands import (
    AddCueCommand,
    AddLayerCommand,
    CommandStack,
    CompositeCommand,
    DeleteCueCommand,
    DeleteLayerCommand,
    EditCueTimingCommand,
    EditLayerCommand,
    SplitCueCommand,
)
from videocaptioner.core.editor.media import cleanup_preview_files, fast_preview_range
from videocaptioner.core.editor.models import (
    EditorLayerKind,
    EditorProject,
)
from videocaptioner.core.editor.presenter import (
    DEFAULT_BLUR_STRENGTH,
    FX_TRACK_ID,
    MASK_MODES,
    CuePlacementError,
    inspector_commands,
    layer_index,
    layer_list_label,
    layer_pending_changes,
    layer_properties,
    layer_range,
    new_cue,
    new_layer,
    preview_output_path,
    split_position,
    suggested_ass_path,
    suggested_export_path,
    suggested_project_path,
    track_locked,
    track_state_command,
)
from videocaptioner.core.editor.project_store import EditorProjectStore
from videocaptioner.ui.components.editor import (
    EditorTimelineView,
    EditorTrackHeader,
    EditorVideoPreview,
    LayerInspector,
    SubtitleInspector,
)
from videocaptioner.ui.task_factory import TaskFactory
from videocaptioner.ui.thread.editor_media_thread import EditorMediaThread, EditorRenderThread
from videocaptioner.ui.thread.editor_voice_thread import EditorVoiceThread

EDITOR_DARK_STYLE = """
QWidget#VideoEditorInterface {
    background: #08111f;
    color: #dbe7f5;
}
QWidget#EditorCommandScroll {
    background: #0d1726;
    border: 1px solid #20344d;
    border-radius: 8px;
}
QSplitter#EditorVerticalSplitter::handle,
QSplitter#EditorHorizontalSplitter::handle {
    background: #17283e;
}
QSplitter#EditorVerticalSplitter::handle:hover,
QSplitter#EditorHorizontalSplitter::handle:hover {
    background: #2c4b6d;
}
QWidget#EditorVideoPreview {
    background: #0b1421;
    border: 1px solid #20344d;
    border-radius: 9px;
    padding: 8px;
}
QWidget#EditorVideoPreview QLabel {
    color: #9fb0c5;
}
QWidget#EditorVideoPreview QSlider::groove:horizontal {
    height: 4px;
    background: #263b55;
    border-radius: 2px;
}
QWidget#EditorVideoPreview QSlider::sub-page:horizontal {
    background: #45cdb6;
    border-radius: 2px;
}
QWidget#EditorVideoPreview QSlider::handle:horizontal {
    background: #e8f4f3;
    border: 2px solid #35a895;
    width: 12px;
    margin: -5px 0;
    border-radius: 7px;
}
QTabWidget#EditorContextTabs::pane {
    background: #0d1726;
    border: 1px solid #20344d;
    border-radius: 8px;
    top: -1px;
}
QTabWidget#EditorContextTabs QTabBar::tab {
    color: #8fa3ba;
    background: #0a1320;
    border: 1px solid #20344d;
    padding: 8px 14px;
    min-width: 74px;
}
QTabWidget#EditorContextTabs QTabBar::tab:selected {
    color: #e7f8f5;
    background: #153149;
    border-bottom: 2px solid #48d0b8;
}
QWidget#EditorTimelineShell {
    background: #0b1421;
    border: 1px solid #20344d;
    border-radius: 8px;
}
QWidget#EditorStatusBar, QWidget#EditorStatusBar QLabel {
    color: #91a6bd;
    background: transparent;
}
QWidget#EditorStatusBar QProgressBar {
    color: #dbe7f5;
    background: #101d2e;
    border: 1px solid #29405d;
    border-radius: 5px;
    text-align: center;
}
QWidget#EditorStatusBar QProgressBar::chunk {
    background: #3ec6ad;
    border-radius: 4px;
}
QWidget#EditorLayerPanel, QListWidget#EditorLayerList {
    color: #dbe7f5;
    background: #0d1726;
    border: none;
}
QListWidget#EditorLayerList::item {
    background: #101d2e;
    border: 1px solid #263d58;
    border-radius: 5px;
    padding: 7px;
    margin: 2px;
}
QListWidget#EditorLayerList::item:selected {
    background: #1b4d57;
    border-color: #48d0b8;
}
"""


class VideoEditorInterface(QWidget):
    projectOpened = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VideoEditorInterface")
        self.setWindowTitle(self.tr("Video Editor"))
        self.project: EditorProject | None = None
        self.project_path = ""
        self.command_stack = CommandStack()
        self.command_stack.add_changed_callback(self._refresh_from_model)
        self._signatures: dict[str, str] = {}
        self._pending_media: set[str] = set()
        self._threads: set = set()
        self._render_thread: EditorRenderThread | None = None
        self._selected_layer_id = ""
        self._pending_project_path = ""
        self._preview_offset_ms = 0
        self._build_ui()
        self._connect_ui()
        self._setup_shortcuts()
        self._set_empty_state()
        application = QApplication.instance()
        if application is not None:
            # Navigation pages never get closeEvent when the window quits.
            application.aboutToQuit.connect(self.shutdown)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self.command_bar = CommandBar(self)
        self.command_bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.open_action = Action(FIF.FOLDER_ADD, self.tr("Open"), triggered=self.open_dialog)
        self.save_action = Action(FIF.SAVE, self.tr("Save project"), triggered=self.save_project)
        self.save_ass_action = Action(FIF.DOCUMENT, self.tr("Save as ASS"), triggered=self.save_as_ass)
        self.undo_action = Action(FIF.LEFT_ARROW, self.tr("Undo"), triggered=self.undo)
        self.redo_action = Action(FIF.RIGHT_ARROW, self.tr("Redo"), triggered=self.redo)
        self.preview_action = Action(FIF.PLAY, self.tr("Fast Preview"), triggered=self.fast_preview)
        self.export_action = Action(FIF.VIDEO, self.tr("Export"), triggered=self.export_video)
        self.cancel_action = Action(FIF.CANCEL, self.tr("Cancel render"), triggered=self.cancel_render)
        self.exit_preview_action = Action(
            FIF.RETURN, self.tr("Exit preview"), triggered=self.exit_rendered_preview
        )
        for action in (
            self.open_action,
            self.save_action,
            self.undo_action,
            self.redo_action,
            self.preview_action,
            self.export_action,
            self.cancel_action,
            self.exit_preview_action,
        ):
            self.command_bar.addAction(action)
        self.cancel_action.setEnabled(False)
        self.exit_preview_action.setEnabled(False)
        self.exit_preview_action.setVisible(False)
        self.command_bar.addHiddenAction(self.save_ass_action)
        for kind, label in (
            (EditorLayerKind.BLUR, "Add Blur"),
            (EditorLayerKind.LOGO, "Add Logo"),
            (EditorLayerKind.MASK, "Add Mask"),
            (EditorLayerKind.TEXT, "Add Text"),
        ):
            self.command_bar.addHiddenAction(
                Action(
                    FIF.ADD,
                    self.tr(label),
                    triggered=lambda _checked=False, layer_kind=kind: self.add_visual_layer(layer_kind),
                )
            )
        self.command_bar.setMinimumHeight(42)
        self.command_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.command_scroll = QWidget(self)
        self.command_scroll.setObjectName("EditorCommandScroll")
        self.command_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.command_scroll.setFixedHeight(54)
        command_layout = QHBoxLayout(self.command_scroll)
        command_layout.setContentsMargins(8, 5, 8, 5)
        command_layout.addWidget(self.command_bar, 1)
        layout.addWidget(self.command_scroll)

        self.vertical_splitter = QSplitter(Qt.Vertical, self)
        self.vertical_splitter.setObjectName("EditorVerticalSplitter")
        self.vertical_splitter.setHandleWidth(6)
        self.horizontal_splitter = QSplitter(Qt.Horizontal, self.vertical_splitter)
        self.horizontal_splitter.setObjectName("EditorHorizontalSplitter")
        self.horizontal_splitter.setHandleWidth(6)
        self.preview = EditorVideoPreview(self.horizontal_splitter)
        self.preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.context_tabs = QTabWidget(self.horizontal_splitter)
        self.context_tabs.setObjectName("EditorContextTabs")
        self.context_tabs.setDocumentMode(True)
        self.inspector = SubtitleInspector(self.context_tabs)
        self.context_tabs.addTab(self.inspector, self.tr("Cue"))
        self.layer_inspector = LayerInspector(self.context_tabs)
        self.layer_panel = self._build_layer_panel()
        self.context_tabs.addTab(self.layer_panel, self.tr("Layers"))
        self.horizontal_splitter.addWidget(self.preview)
        self.horizontal_splitter.addWidget(self.context_tabs)
        self.horizontal_splitter.setStretchFactor(0, 3)
        self.horizontal_splitter.setStretchFactor(1, 1)
        self.horizontal_splitter.setSizes([760, 300])

        timeline_shell = QWidget(self.vertical_splitter)
        timeline_shell.setObjectName("EditorTimelineShell")
        timeline_layout = QHBoxLayout(timeline_shell)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_layout.setSpacing(0)
        self.track_header = EditorTrackHeader(timeline_shell)
        self.timeline = EditorTimelineView(timeline_shell)
        timeline_layout.addWidget(self.track_header)
        timeline_layout.addWidget(self.timeline, 1)
        self.vertical_splitter.addWidget(self.horizontal_splitter)
        self.vertical_splitter.addWidget(timeline_shell)
        self.vertical_splitter.setStretchFactor(0, 3)
        self.vertical_splitter.setStretchFactor(1, 2)
        self.vertical_splitter.setSizes([470, 260])
        layout.addWidget(self.vertical_splitter, 1)

        status_bar = QWidget(self)
        status_bar.setObjectName("EditorStatusBar")
        status_row = QHBoxLayout(status_bar)
        status_row.setContentsMargins(2, 2, 2, 2)
        self.status_label = QLabel("", self)
        self.status_label.setMinimumWidth(0)
        self.status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(260)
        self.zoom_out_button = PushButton("−", self)
        self.zoom_in_button = PushButton("+", self)
        self.fit_button = PushButton("Fit", self)
        self.zoom_label = QLabel("100%", self)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.progress)
        status_row.addWidget(self.zoom_out_button)
        status_row.addWidget(self.zoom_label)
        status_row.addWidget(self.zoom_in_button)
        status_row.addWidget(self.fit_button)
        layout.addWidget(status_bar)
        self.setStyleSheet(EDITOR_DARK_STYLE)

    def _build_layer_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("EditorLayerPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        hint = QLabel(
            self.tr("Layers cover the selected range, or 5s from the playhead."), panel
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8fa3ba; font-size:11px;")
        layout.addWidget(hint)
        # FlowLayout reports one button as its minimum, so a large default font
        # (offscreen Qt, accessibility scaling) wraps the row instead of widening
        # the tab and starving the video preview.
        add_row = FlowLayout(needAni=False)
        add_row.setHorizontalSpacing(4)
        add_row.setVerticalSpacing(4)
        self.add_layer_buttons: dict[EditorLayerKind, PushButton] = {}
        for kind, label in (
            (EditorLayerKind.BLUR, self.tr("Blur")),
            (EditorLayerKind.LOGO, self.tr("Logo")),
            (EditorLayerKind.MASK, self.tr("Mask")),
            (EditorLayerKind.TEXT, self.tr("Text")),
        ):
            button = PushButton(label, panel)
            button.clicked.connect(
                lambda _checked=False, layer_kind=kind: self.add_visual_layer(layer_kind)
            )
            add_row.addWidget(button)
            self.add_layer_buttons[kind] = button
        layout.addLayout(add_row)
        self.layer_list = QListWidget(panel)
        # An ID selector outranks the QFluentWidgets app stylesheet, which otherwise
        # leaves the viewport white; a translucent viewport would leak the sibling tab.
        self.layer_list.setObjectName("EditorLayerList")
        self.layer_list.setMaximumHeight(132)
        self.layer_list.setFrameShape(QListWidget.NoFrame)
        list_palette = self.layer_list.palette()
        list_palette.setColor(QPalette.Base, QColor("#0d1726"))
        list_palette.setColor(QPalette.Text, QColor("#dbe7f5"))
        self.layer_list.setPalette(list_palette)
        self.layer_list.viewport().setAutoFillBackground(True)
        layout.addWidget(self.layer_list)
        self.layer_inspector.setParent(panel)
        layout.addWidget(self.layer_inspector, 1)
        return panel

    def _connect_ui(self) -> None:
        self.timeline.cueSelected.connect(self.select_cue)
        self.timeline.layerSelected.connect(self.select_layer)
        self.timeline.layerTimingRequested.connect(self._apply_layer_timeline_timing)
        self.timeline.seekRequested.connect(self.preview.set_position)
        self.timeline.cueTimingRequested.connect(self._apply_timeline_timing)
        self.timeline.selectionRangeChanged.connect(self._on_selection_range)
        self.timeline.zoomChanged.connect(lambda value: self.zoom_label.setText(f"{value}%"))
        self.preview.positionChanged.connect(self.timeline.set_playhead)
        self.preview.activeCueChanged.connect(self._on_active_cue)
        self.preview.playbackError.connect(self._show_error)
        self.inspector.applyRequested.connect(self._apply_inspector)
        self.inspector.regenerateRequested.connect(self.regenerate_voice)
        self.inspector.splitRequested.connect(self.split_cue)
        self.inspector.deleteRequested.connect(self.delete_cue)
        self.inspector.addRequested.connect(self.add_cue)
        self.track_header.trackStateRequested.connect(self._apply_track_state)
        self.preview.renderedPreviewChanged.connect(self._on_rendered_preview_changed)
        self.layer_inspector.applyRequested.connect(self._apply_layer_inspector)
        self.layer_inspector.deleteRequested.connect(self.delete_layer)
        self.layer_list.currentRowChanged.connect(self._on_layer_row_changed)
        self.zoom_in_button.clicked.connect(self.timeline.zoom_in)
        self.zoom_out_button.clicked.connect(self.timeline.zoom_out)
        self.fit_button.clicked.connect(self.timeline.fit_timeline)

    def _setup_shortcuts(self) -> None:
        for sequence, callback in (
            (QKeySequence.Undo, self.undo),
            (QKeySequence.Redo, self.redo),
            (QKeySequence.Save, self.save_project),
            (QKeySequence(Qt.Key_Space), self.preview.toggle_playback),
            (QKeySequence(Qt.Key_Delete), self._delete_selection),
            (QKeySequence("Ctrl++"), self.timeline.zoom_in),
            (QKeySequence("Ctrl+-"), self.timeline.zoom_out),
        ):
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(callback)

    def _delete_selection(self) -> None:
        """Delete follows the active context tab so it never removes the wrong object."""
        if self.context_tabs.currentWidget() is self.layer_panel:
            self.delete_selected_layer()
            return
        self.delete_cue(self.inspector.cue_id)

    def _set_empty_state(self) -> None:
        self.status_label.setText(self.tr("Open a video and SRT to start editing"))
        self.progress.setValue(0)
        self._set_actions_enabled(False)

    def _set_actions_enabled(self, enabled: bool) -> None:
        for action in (
            self.save_action,
            self.save_ass_action,
            self.preview_action,
            self.export_action,
        ):
            action.setEnabled(enabled)
        for button in self.add_layer_buttons.values():
            button.setEnabled(enabled)
        self._update_undo_redo()

    def _update_undo_redo(self) -> None:
        self.undo_action.setEnabled(self.command_stack.can_undo)
        self.redo_action.setEnabled(self.command_stack.can_redo)

    def _confirm_discard_changes(self) -> bool:
        """Ask before dropping edits; ``is_dirty`` is the model's own flag."""
        if not self.project or not self.project.is_dirty:
            return True
        box = MessageBox(
            self.tr("Unsaved editor changes"),
            self.tr("The current project has unsaved changes. Discard them?"),
            self.window(),
        )
        box.yesButton.setText(self.tr("Discard"))
        box.cancelButton.setText(self.tr("Keep editing"))
        return bool(box.exec())

    def open_dialog(self) -> None:
        if not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Open video or editor project"),
            "",
            self.tr("Editor Project (*.vceditor.json);;Video (*.mp4 *.mkv *.mov *.avi *.webm)"),
        )
        if not path:
            return
        if path.lower().endswith(EditorProjectStore.project_suffix):
            self._pending_project_path = path
            self._start_media("load-project", {"project_path": path})
            return
        subtitle, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Open subtitles"),
            str(Path(path).parent),
            self.tr("Subtitles with optional ASR metadata (*.srt *.json)"),
        )
        if subtitle:
            self.open_in_editor(path, subtitle)

    def open_in_editor(self, video_path: str, subtitle_path: str) -> None:
        if not self._confirm_discard_changes():
            return
        self.project_path = ""
        self._pending_project_path = ""
        self._start_media(
            "open",
            {"video_path": str(video_path), "subtitle_path": str(subtitle_path)},
        )

    def _start_media(self, action: str, payload: dict) -> None:
        signature = uuid4().hex
        self._signatures[action] = signature
        self._pending_media.add(action)
        self.status_label.setText(self.tr("Loading editor media..."))
        self.progress.setRange(0, 0)
        thread = EditorMediaThread(signature, action, payload, self)
        self._retain_thread(thread)
        thread.completed.connect(lambda sig, data, name=action: self._on_media_completed(name, sig, data))
        thread.failed.connect(lambda sig, error, name=action: self._on_worker_failed(name, sig, error))
        thread.start()

    def _retain_thread(self, thread) -> None:
        self._threads.add(thread)
        thread.finished.connect(lambda current=thread: self._threads.discard(current))

    def _on_media_completed(self, action: str, signature: str, data) -> None:
        self._pending_media.discard(action)
        if self._signatures.get(action) != signature:
            self._restore_project_status()
            return
        if action in {"open", "load-project"}:
            self._accept_project(data)
        elif action == "waveform":
            _fingerprint, samples, duration = data
            self.timeline.set_waveform(samples, duration)
        elif action == "thumbnails":
            _fingerprint, items = data
            self.timeline.set_thumbnails(items)
            if items:
                self.preview.set_poster(items[0][1])
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self._restore_project_status()

    def _restore_project_status(self) -> None:
        """The loading text used to stay up forever once the workers finished."""
        if self._pending_media or not self.project:
            return
        self.status_label.setText(
            self.tr("Loaded {count} cues — V1 / A1 / TS1").format(count=len(self.project.cues))
        )

    def _accept_project(self, project: EditorProject) -> None:
        self.project = project
        self.project_path = getattr(self, "_pending_project_path", "")
        self._pending_project_path = ""
        self._selected_layer_id = ""
        self.command_stack.clear()
        self.preview.set_project(project)
        self.timeline.set_project(project)
        self.track_header.set_project(project)
        self._refresh_layer_list()
        self.layer_inspector.set_layer(None, project.duration_ms)
        self._set_actions_enabled(True)
        self.status_label.setText(
            self.tr("Loaded {count} cues — V1 / A1 / TS1").format(count=len(project.cues))
        )
        if project.cues:
            self.select_cue(project.cues[0].id)
        self.projectOpened.emit(project.video_path, project.subtitle_path)
        cache_root = str(CACHE_PATH / "editor_media" / "v1")
        self._start_media("waveform", {"video_path": project.video_path, "cache_root": cache_root})
        self._start_media(
            "thumbnails",
            {
                "video_path": project.video_path,
                "duration_ms": project.duration_ms,
                "cache_root": cache_root,
            },
        )

    def _on_worker_failed(self, action: str, signature: str, error: str) -> None:
        self._pending_media.discard(action)
        if self._signatures.get(action) != signature:
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._show_error(error)

    def _show_error(self, message: str) -> None:
        message = str(message or self.tr("Unknown editor error"))
        self.status_label.setText(message)
        InfoBar.error(
            title=self.tr("Video Editor error"),
            content=message,
            isClosable=True,
            duration=-1,
            position=InfoBarPosition.BOTTOM,
            parent=self,
        )

    def _show_success(self, message: str) -> None:
        self.status_label.setText(message)
        InfoBar.success(
            title=self.tr("Video Editor"),
            content=message,
            duration=4000,
            position=InfoBarPosition.BOTTOM,
            parent=self,
        )

    def select_cue(self, cue_id: str) -> None:
        if not self.project or not cue_id:
            return
        try:
            cue = self.project.cue_by_id(cue_id)
        except KeyError:
            return
        self.timeline.select_cue(cue_id)
        self.inspector.set_cue(cue, self.project.duration_ms)

    def _on_active_cue(self, cue_id: str) -> None:
        if cue_id and cue_id != self.inspector.cue_id:
            self.select_cue(cue_id)

    def _on_selection_range(self, start_ms: int, end_ms: int) -> None:
        if self.project:
            self.project.selection_start_ms = int(start_ms)
            self.project.selection_end_ms = int(end_ms)
            self.status_label.setText(
                self.tr("Selected range: {start:.3f}s – {end:.3f}s").format(
                    start=start_ms / 1000.0, end=end_ms / 1000.0
                )
            )

    def _apply_timeline_timing(
        self, cue_id: str, start_ms: int, end_ms: int, operation: str
    ) -> None:
        if not self.project:
            return
        try:
            command = EditCueTimingCommand(self.project, cue_id, start_ms, end_ms)
            command.description = "Move cue" if operation == "move" else "Resize cue"
            self.command_stack.execute(command)
        except Exception as exc:
            self._show_error(str(exc))

    def _apply_inspector(self, cue_id: str, values: dict) -> None:
        if not self.project:
            return
        try:
            commands = inspector_commands(self.project, cue_id, values)
            if commands:
                self.command_stack.execute(CompositeCommand(commands, "Edit cue in inspector"))
            else:
                self.status_label.setText(self.tr("No cue changes"))
        except Exception as exc:
            self._show_error(str(exc))

    def _apply_track_state(self, track_id: str, field_name: str, value: bool) -> None:
        if not self.project:
            return
        try:
            self.command_stack.execute(
                track_state_command(self.project, track_id, field_name, value)
            )
        except Exception as exc:
            self._show_error(str(exc))

    def add_cue(self) -> None:
        if not self.project:
            return
        try:
            cue = new_cue(self.project, self.project.playhead_ms)
        except CuePlacementError as exc:
            self._show_error(
                self.tr("Playhead is inside an existing cue")
                if exc.reason == "inside_cue"
                else self.tr("No free timeline space for a new cue")
            )
            return
        try:
            self.command_stack.execute(AddCueCommand(self.project, cue))
            self.select_cue(cue.id)
        except Exception as exc:
            self._show_error(str(exc))

    def split_cue(self, cue_id: str) -> None:
        if not self.project or not cue_id:
            return
        split_ms = split_position(self.project.cue_by_id(cue_id), self.project.playhead_ms)
        try:
            self.command_stack.execute(SplitCueCommand(self.project, cue_id, split_ms))
            self.select_cue(cue_id)
        except Exception as exc:
            self._show_error(str(exc))

    def delete_cue(self, cue_id: str) -> None:
        if not self.project or not cue_id:
            return
        try:
            self.command_stack.execute(DeleteCueCommand(self.project, cue_id))
            self.inspector.set_cue(None, self.project.duration_ms)
        except Exception as exc:
            self._show_error(str(exc))

    def undo(self) -> None:
        self.command_stack.undo()

    def redo(self) -> None:
        self.command_stack.redo()

    def _refresh_from_model(self) -> None:
        if not self.project:
            return
        selected = self.inspector.cue_id
        self.timeline.refresh_project()
        self.track_header.set_project(self.project)
        self.preview.surface.overlay.set_state(self.project, self.project.playhead_ms)
        self._refresh_layer_list()
        if selected:
            try:
                self.inspector.set_cue(self.project.cue_by_id(selected), self.project.duration_ms)
            except KeyError:
                self.inspector.set_cue(None, self.project.duration_ms)
        self._refresh_layer_inspector()
        self._update_undo_redo()

    def _refresh_layer_inspector(self) -> None:
        if not self.project:
            return
        layer = self._selected_layer()
        self.layer_inspector.set_layer(layer, self.project.duration_ms)
        self.preview.surface.overlay.set_selected_layer(layer.id if layer else "")
        self.timeline.select_layer(layer.id if layer else "")

    def save_project(self) -> None:
        if not self.project:
            return
        path = self.project_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self,
                self.tr("Save editor project"),
                suggested_project_path(self.project.video_path),
                self.tr("Editor Project (*.vceditor.json)"),
            )
        if not path:
            return
        try:
            project_path, srt_path = EditorProjectStore().save(self.project, path)
            self.project_path = project_path
            self._show_success(self.tr("Saved project and SRT: ") + srt_path)
        except Exception as exc:
            self._show_error(str(exc))

    def save_as_ass(self) -> None:
        if not self.project:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Explicit Save as ASS"),
            suggested_ass_path(self.project.video_path),
            self.tr("Advanced SubStation Alpha (*.ass)"),
        )
        if not path:
            return
        try:
            output = EditorProjectStore().save_as_ass(
                self.project, path, style_str=TaskFactory.get_ass_style("default")
            )
            self._show_success(self.tr("Saved ASS explicitly: ") + output)
        except Exception as exc:
            self._show_error(str(exc))

    def fast_preview(self) -> None:
        if not self.project or self._render_thread is not None:
            return
        signature = uuid4().hex
        self._signatures["preview"] = signature
        output = preview_output_path(CACHE_PATH, self.project.project_id, signature)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Every run used to leave an mp4 behind; drop the ones no player holds.
        self.preview.exit_rendered_preview()
        cleanup_preview_files(output.parent)
        self._preview_offset_ms = fast_preview_range(self.project)[0]
        thread = EditorRenderThread(signature, "preview", self.project, str(output), parent=self)
        self._start_render_thread("preview", thread)

    def export_video(self) -> None:
        if not self.project or self._render_thread is not None:
            return
        output, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export current editor state"),
            suggested_export_path(self.project.video_path),
            self.tr("MP4 Video (*.mp4)"),
        )
        if not output:
            return
        signature = uuid4().hex
        self._signatures["export"] = signature
        dubbing_config = TaskFactory.create_dubbing_config()
        thread = EditorRenderThread(
            signature,
            "export",
            self.project,
            output,
            dubbing_config=dubbing_config,
            parent=self,
        )
        self._start_render_thread("export", thread)

    def _start_render_thread(self, action: str, thread: EditorRenderThread) -> None:
        self._retain_thread(thread)
        self._render_thread = thread
        thread.progress.connect(self._on_progress)
        thread.completed.connect(lambda sig, output, name=action: self._on_render_completed(name, sig, output))
        thread.failed.connect(lambda sig, error, name=action: self._on_worker_failed(name, sig, error))
        thread.cancelled.connect(lambda _sig, name=action: self._on_render_cancelled(name))
        thread.finished.connect(lambda current=thread: self._on_render_finished(current))
        self.status_label.setText(self.tr("Rendering from current editor state..."))
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.cancel_action.setEnabled(True)
        self.preview_action.setEnabled(False)
        self.export_action.setEnabled(False)
        thread.start()

    def exit_rendered_preview(self) -> None:
        self.preview.exit_rendered_preview()

    def cancel_render(self) -> None:
        thread = self._render_thread
        if thread is None or not thread.isRunning():
            return
        self.cancel_action.setEnabled(False)
        self.status_label.setText(self.tr("Cancelling render..."))
        thread.cancel()

    def _on_render_finished(self, thread) -> None:
        if self._render_thread is thread:
            self._render_thread = None
        self.cancel_action.setEnabled(False)
        if self.project is not None:
            self.preview_action.setEnabled(True)
            self.export_action.setEnabled(True)

    def _on_render_cancelled(self, action: str) -> None:
        self.progress.setValue(0)
        self.status_label.setText(
            self.tr("Fast Preview cancelled") if action == "preview" else self.tr("Export cancelled")
        )

    def _on_progress(self, value: int, message: str) -> None:
        self.progress.setValue(max(0, min(100, int(value))))
        self.status_label.setText(str(message))

    def _on_render_completed(self, action: str, signature: str, output: str) -> None:
        if self._signatures.get(action) != signature:
            return
        self.progress.setValue(100)
        if action == "preview":
            # Played through the offset-aware preview mode so the playhead stays project-local.
            self.preview.play_rendered_preview(output, getattr(self, "_preview_offset_ms", 0))
            self._show_success(self.tr("Fast Preview uses current editor state: ") + output)
        else:
            self._show_success(self.tr("Export completed: ") + output)

    def _on_rendered_preview_changed(self, active: bool) -> None:
        self.exit_preview_action.setVisible(active)
        self.exit_preview_action.setEnabled(active)
        if active:
            self.status_label.setText(self.tr("Playing rendered preview — Exit preview to resume"))

    def regenerate_voice(self, cue_id: str) -> None:
        if not self.project or not cue_id:
            return
        config = TaskFactory.create_dubbing_config()
        if config is None:
            self._show_error(self.tr("Enable and configure Dubbing before regenerating voice"))
            return
        signature = uuid4().hex
        self._signatures["voice"] = signature
        output_dir = CACHE_PATH / "editor_voice" / "v1" / self.project.project_id
        thread = EditorVoiceThread(
            signature,
            self.project,
            {cue_id},
            config,
            output_dir,
            self,
        )
        self._retain_thread(thread)
        thread.progress.connect(self._on_progress)
        thread.completed.connect(self._on_voice_completed)
        thread.failed.connect(lambda sig, error: self._on_worker_failed("voice", sig, error))
        thread.start()

    def _on_voice_completed(self, signature: str, groups) -> None:
        if self._signatures.get("voice") != signature or not self.project:
            return
        update_cues_from_groups(self.project, groups)
        self._refresh_from_model()
        self.progress.setValue(100)
        self._show_success(self.tr("Regenerated only the selected cue/group"))

    def add_visual_layer(self, kind: EditorLayerKind) -> None:
        if not self.project:
            return
        if track_locked(self.project, FX_TRACK_ID):
            self._show_error(self.tr("FX1 track is locked"))
            return
        start_ms, end_ms = layer_range(self.project)
        if end_ms <= start_ms:
            self._show_error(self.tr("Visual layer range is empty"))
            return
        value = self._ask_layer_value(kind)
        if value is None:
            return
        layer = new_layer(self.project, kind, layer_properties(kind, value), start_ms, end_ms)
        try:
            self.command_stack.execute(AddLayerCommand(self.project, layer))
            self.select_layer(layer.id)
            self.context_tabs.setCurrentWidget(self.layer_panel)
        except Exception as exc:
            self._show_error(str(exc))

    def _ask_layer_value(self, kind: EditorLayerKind):
        """The one dialog input a new layer needs; ``None`` when cancelled."""
        if kind == EditorLayerKind.TEXT:
            text, ok = QInputDialog.getText(self, self.tr("Add Text"), self.tr("Text:"))
            return text if ok else None
        if kind == EditorLayerKind.LOGO:
            path, _ = QFileDialog.getOpenFileName(
                self, self.tr("Add Logo"), "", self.tr("Image (*.png *.jpg *.jpeg *.webp)")
            )
            return path or None
        if kind == EditorLayerKind.MASK:
            mode, ok = QInputDialog.getItem(
                self, self.tr("Add Mask"), self.tr("Mode:"), list(MASK_MODES), 0, False
            )
            return mode if ok else None
        strength, ok = QInputDialog.getInt(
            self, self.tr("Add Blur"), self.tr("Strength:"), DEFAULT_BLUR_STRENGTH, 1, 50
        )
        return strength if ok else None

    def select_layer(self, layer_id: str) -> None:
        if not self.project or not layer_id:
            return
        index = layer_index(self.project, layer_id)
        if index < 0:
            return
        self._selected_layer_id = layer_id
        self.layer_list.blockSignals(True)
        self.layer_list.setCurrentRow(index)
        self.layer_list.blockSignals(False)
        self._refresh_layer_inspector()

    def _on_layer_row_changed(self, row: int) -> None:
        if not self.project:
            return
        self._selected_layer_id = (
            self.project.layers[row].id if 0 <= row < len(self.project.layers) else ""
        )
        self._refresh_layer_inspector()

    def _apply_layer_timeline_timing(
        self, layer_id: str, start_ms: int, end_ms: int, operation: str
    ) -> None:
        if not self.project:
            return
        try:
            command = EditLayerCommand(
                self.project, layer_id, {"start_ms": int(start_ms), "end_ms": int(end_ms)}
            )
            command.description = "Move layer" if operation == "move" else "Resize layer"
            self.command_stack.execute(command)
            self.select_layer(layer_id)
        except Exception as exc:
            self._show_error(str(exc))

    def _apply_layer_inspector(self, layer_id: str, changes: dict) -> None:
        if not self.project:
            return
        try:
            pending = layer_pending_changes(self.project.layer_by_id(layer_id), changes)
            if not pending:
                self.status_label.setText(self.tr("No layer changes"))
                return
            self.command_stack.execute(EditLayerCommand(self.project, layer_id, pending))
            self.select_layer(layer_id)
        except Exception as exc:
            self._show_error(str(exc))

    def delete_layer(self, layer_id: str) -> None:
        if not self.project or not layer_id:
            return
        try:
            self.command_stack.execute(DeleteLayerCommand(self.project, layer_id))
            self._selected_layer_id = ""
            self._refresh_layer_inspector()
        except Exception as exc:
            self._show_error(str(exc))

    def _selected_layer(self):
        if not self.project or not self._selected_layer_id:
            return None
        try:
            return self.project.layer_by_id(self._selected_layer_id)
        except KeyError:
            return None

    def delete_selected_layer(self) -> None:
        layer = self._selected_layer()
        if layer:
            self.delete_layer(layer.id)

    def _refresh_layer_list(self) -> None:
        # Rebuilding the list used to drop the selection and silently disable Edit/Delete.
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        selected_row = -1
        if self.project:
            for index, layer in enumerate(self.project.layers):
                item = QListWidgetItem(layer_list_label(layer))
                item.setData(Qt.UserRole, layer.id)
                self.layer_list.addItem(item)
                if layer.id == self._selected_layer_id:
                    selected_row = index
        if selected_row < 0:
            self._selected_layer_id = ""
        self.layer_list.setCurrentRow(selected_row)
        self.layer_list.blockSignals(False)

    def shutdown(self) -> None:
        """Stop playback and workers; also runs on app quit, where closeEvent never fires."""
        self.preview.player.stop()
        for thread in tuple(self._threads):
            if not thread.isRunning():
                continue
            cancel = getattr(thread, "cancel", None)
            if callable(cancel):
                cancel()
            else:
                thread.requestInterruption()
            thread.wait(5000)
        self._threads.clear()
        self._render_thread = None

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)
