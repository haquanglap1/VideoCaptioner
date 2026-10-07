"""Local settings and an explicit model manager; all IO happens in workers."""

from pathlib import Path
from uuid import uuid4

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import ComboBoxSettingCard, PushSettingCard, SettingCardGroup, SwitchSettingCard
from qfluentwidgets import FluentIcon as FIF

from videocaptioner.core.asr.local.runtime import managed_root
from videocaptioner.core.entities import TranscribeLanguageEnum
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.thread.local_asr_thread import LocalASRThread
from videocaptioner.ui.thread.worker_lifecycle import cancel_worker, connect_current, retain_worker

# Pipeline order; the data value is the pinned model id used by the core.
STAGES = (
    ("Step 1 — Recognition: Qwen 1.7B (recommended)", "qwen-1.7b"),
    ("Step 1 — Recognition: Qwen 0.6B (smaller, faster)", "qwen-0.6b"),
    ("Step 2 — Timing: Qwen ForcedAligner (needed for SRT/ASS)", "aligner"),
    ("Step 3 — Speakers: Community-1 (optional, needs Hugging Face token)", "community-1"),
)
STAGE_NAMES = {
    "qwen-1.7b": "Recognition (Qwen 1.7B)",
    "qwen-0.6b": "Recognition (Qwen 0.6B)",
    "aligner": "Timing (ForcedAligner)",
    "community-1": "Speakers (Community-1)",
}
RECOGNIZERS = ("qwen-1.7b", "qwen-0.6b")


class LocalASRDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.stage_status = {}
        self._queue: list[str] = []
        self.setWindowTitle(self.tr("Local ASR models"))
        self.resize(780, 560)
        layout = QVBoxLayout(self)
        notice = QLabel(self.tr(
            "Qwen3-ASR runs on this computer in three steps: 1) recognition writes the text, "
            "2) ForcedAligner adds timing for SRT/ASS, 3) Community-1 labels speakers (optional). "
            "Starting a transcription prepares step 1 automatically (download, verify, resumable) and "
            "step 2 when subtitles are exported; TXT output needs only step 1. "
            "Opening this window does not download or load anything."))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.model = QComboBox()
        for label, value in STAGES:
            self.model.addItem(self.tr(label), value)
        layout.addWidget(self.model)
        self.storage = QLabel()
        self.storage.setWordWrap(True)
        layout.addWidget(self.storage)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.buttons = []
        row = QHBoxLayout()
        self.prepare_button = self._add_button(row, "Prepare / resume selected model", lambda: self.start_action("prepare"))
        self.prepare_button.setDefault(True)
        self.check_button = self._add_button(row, "Check files", lambda: self.start_action("status"))
        self.check_all_button = self._add_button(row, "Check all steps", self.check_all)
        layout.addLayout(row)
        self.advanced_button = QPushButton(self.tr("Advanced…"))
        self.advanced_button.setCheckable(True)
        layout.addWidget(self.advanced_button)
        self.advanced = QWidget()
        advanced = QVBoxLayout(self.advanced)
        advanced.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(self.tr(
            "Advanced: probe loads the model on the GPU once; install creates a separate runtime folder; "
            "choose points to a runtime prepared elsewhere."))
        hint.setWordWrap(True)
        advanced.addWidget(hint)
        row = QHBoxLayout()
        for label, action in (("Probe health", "probe"), ("Install in new folder", "install"),
                              ("Choose installed folder", "choose")):
            self._add_button(row, label, lambda action=action: self.start_action(action))
        advanced.addLayout(row)
        self.advanced.hide()
        self.advanced_button.toggled.connect(self.advanced.setVisible)
        layout.addWidget(self.advanced)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.cancel_button = QPushButton(self.tr("Cancel operation"))
        self.cancel_button.clicked.connect(self.cancel)
        layout.addWidget(self.cancel_button)
        self.model.currentIndexChanged.connect(self.display_stage_status)
        self.display_stage_status()
        self.refresh_summary()

    def _add_button(self, row, label, callback):
        button = QPushButton(self.tr(label))
        button.clicked.connect(lambda _checked=False: callback())
        self.buttons.append(button)
        row.addWidget(button)
        return button

    def display_stage_status(self):
        model = self.model.currentData()
        self.status.setText(self.stage_status.get(model,
            self.tr("Not checked. Opening this dialog does not load or download models.")))
        self.storage.setText(self.tr("Models are stored in: {0}").format(self.storage_root(model)))

    def storage_root(self, model) -> str:
        """Where this stage lives: an explicit folder as chosen, else the managed sibling of the default root."""
        root = self.root_item(model).value
        if root:
            return root
        try:
            return str(managed_root(model))
        except (OSError, KeyError, ValueError):
            return self.tr("default folder next to the application")

    def record_status(self, model, message):
        self.stage_status[model] = message
        if self.model.currentData() == model:
            self.status.setText(message)
        self.refresh_summary()

    def refresh_summary(self):
        lines = [self.tr("Readiness by step (last check):")]
        for model, name in STAGE_NAMES.items():
            lines.append(f"• {self.tr(name)}: {self.stage_status.get(model, '—')}")
        self.summary.setText("\n".join(lines))

    def root_item(self, model=None):
        model = model or self.model.currentData()
        return cfg.local_diarization_root if model == "community-1" else cfg.local_asr_root

    def check_all(self):
        """Queue a file check for every step; each one runs in its own worker, in order."""
        if self.worker is not None:
            return
        current = self.model.currentData()
        recognizer = current if current in RECOGNIZERS else cfg.local_asr_model.value
        self._queue = [recognizer, "aligner", "community-1"]
        self._next_queued()

    def _next_queued(self):
        if self._queue and self.worker is None:
            self.start_action("status", self._queue.pop(0))

    def start_action(self, action, model=None):
        if self.worker is not None:
            return
        model = model or self.model.currentData()
        item = self.root_item(model)
        root, token = item.value, ""
        if action == "choose":
            path = QFileDialog.getExistingDirectory(self, self.tr("Choose installed runtime"))
            if path:
                cfg.set(item, path)
                self.display_stage_status()
                self.start_action("status")
            return
        if action == "install":
            parent = QFileDialog.getExistingDirectory(self, self.tr("Choose parent for a new runtime folder"))
            if not parent:
                return
            root = str(Path(parent) / f"local-{model}-{uuid4().hex[:8]}")
        if action in ("install", "prepare") and model == "community-1":
            token, ok = QInputDialog.getText(self, self.tr("Hugging Face access"),
                    self.tr("First accept Community-1 conditions on Hugging Face. Enter a read token here; it is used only for this download and is not saved."), QLineEdit.Password)
            if not ok or not token:
                return
        worker = LocalASRThread(action, model, root, cfg.local_asr_timeout.value, token)
        self.worker = retain_worker(worker)
        connect_current(self, "worker", worker, worker.status, lambda message: self.record_status(model, message))
        connect_current(self, "worker", worker, worker.installed, lambda path: self._record_root(item, path))
        worker.finished.connect(lambda: self.done_work(worker))
        for button in self.buttons:
            button.setEnabled(False)
        self.model.setEnabled(False)
        self.progress.setRange(0, 0)
        worker.start()

    def _record_root(self, item, path):
        cfg.set(item, path)
        self.display_stage_status()

    def done_work(self, worker):
        worker.wait()
        if self.worker is not worker:
            return
        self.worker = None
        self.progress.setRange(0, 1)
        cancelled = getattr(worker, "_vc_cancel_requested", False)
        if cancelled:
            # Result signals are intentionally suppressed after cancellation.
            self._queue.clear()
            self.record_status(worker.model, self.tr("Local operation cancelled."))
        self.progress.setValue(0 if cancelled else 1)
        for button in self.buttons:
            button.setEnabled(True)
        self.model.setEnabled(True)
        self._next_queued()

    def cancel(self):
        self._queue.clear()
        if self.worker is not None:
            cancel_worker(self.worker)
            self.status.setText(self.tr("Cancelling; waiting for owned processes to stop..."))

    def reject(self):
        self.cancel()
        super().reject()

    def closeEvent(self, event):
        self.cancel()
        super().closeEvent(event)


class LocalASRCards(QWidget):
    def __init__(self, group):
        super().__init__(group)
        self.hide()
        self.model = ComboBoxSettingCard(cfg.local_asr_model, FIF.MICROPHONE, self.tr("Qwen local recognition"),
                        self.tr("Chinese (zh). Model choice is explicit; no automatic fallback."), ["Qwen 1.7B", "Qwen 0.6B"], group)
        self.language = ComboBoxSettingCard(cfg.transcribe_language, FIF.LANGUAGE, self.tr("Ngôn ngữ nguồn Qwen"),
                        self.tr("Qwen hiện hỗ trợ tiếng Trung (zh). Tự động trong giao diện dùng tiếng Trung cho Qwen."),
                        [self.tr(language.value) for language in TranscribeLanguageEnum], group)
        self.diarize = SwitchSettingCard(FIF.PEOPLE, self.tr("Local speaker diarization"),
                        self.tr("Community-1 for Qwen or Whisper API. Ambiguous speakers remain unknown for review."),
                        configItem=cfg.local_asr_diarize, parent=group)
        self.naming = SwitchSettingCard(FIF.ROBOT, self.tr("Name speakers with the LLM"),
                        self.tr("After diarization, one request to the configured LLM proposes a name, role and gender "
                                "per cluster. Confident names are applied; the rest wait in the review table."),
                        configItem=cfg.local_asr_name_speakers, parent=group)
        self.chunk = ComboBoxSettingCard(cfg.local_asr_chunk, FIF.SETTING, self.tr("Local audio chunk"),
                        self.tr("Audio is recognized in windows of this length. Longer windows keep more context; "
                                "shorter ones recover faster after a timeout."),
                        ["30 s", "60 s", "120 s", "240 s"], group)
        self.timeout = ComboBoxSettingCard(cfg.local_asr_timeout, FIF.SETTING, self.tr("Local stage deadline"),
                        self.tr("Maximum wait for each step (model load, recognition, alignment). "
                                "Raise it for slow GPUs or long files."),
                        ["60 s", "180 s", "300 s", "600 s", "1800 s", "3600 s"], group)
        self.manager = PushSettingCard(self.tr("Manage models"), FIF.FOLDER, self.tr("Local ASR runtimes"),
                         self.tr("Explicit install, file check and health probe. Opening settings does not start a model."), group)
        self.manager.clicked.connect(self.open_manager)
        self.cards = [self.model, self.language, self.diarize, self.naming, self.chunk, self.timeout, self.manager]
        for card in self.cards:
            card.contentLabel.setWordWrap(True)
            card.contentLabel.setMinimumHeight(44)
            card.setFixedHeight(102)

    def open_manager(self):
        dialog = LocalASRDialog(self.window())
        dialog.exec_()


class LocalASRSettingWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        group = SettingCardGroup(self.tr("Local ASR"), self)
        self.controls = LocalASRCards(group)
        for card in self.controls.cards:
            group.addSettingCard(card)
        layout.addWidget(group)
