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

from videocaptioner.core.entities import TranscribeLanguageEnum
from videocaptioner.ui.common.config import cfg
from videocaptioner.ui.thread.local_asr_thread import LocalASRThread
from videocaptioner.ui.thread.worker_lifecycle import cancel_worker, connect_current, retain_worker


class LocalASRDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.stage_status = {}
        self.setWindowTitle(self.tr("Local ASR models"))
        self.resize(740, 440)
        layout = QVBoxLayout(self)
        notice = QLabel(self.tr("Starting Qwen prepares the selected recognition model; subtitle export also prepares the aligner. Speaker models remain optional. This manager can check or install each stage separately; opening it does not download models."))
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.model = QComboBox()
        for label, value in (("Qwen 1.7B — recognition", "qwen-1.7b"), ("Qwen 0.6B — recognition", "qwen-0.6b"),
                             ("Qwen ForcedAligner — alignment", "aligner"), ("Community-1 — diarization", "community-1")):
            self.model.addItem(self.tr(label), value)
        layout.addWidget(self.model)
        self.status = QLabel(self.tr("Not checked. Opening this dialog does not load or download models."))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.model.currentIndexChanged.connect(self.display_stage_status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.buttons = []
        row = QHBoxLayout()
        for label, action in (("Check files", "status"), ("Probe health", "probe"), ("Install in new folder", "install"), ("Choose installed folder", "choose")):
            button = QPushButton(self.tr(label))
            button.clicked.connect(lambda _=False, action=action: self.start_action(action))
            self.buttons.append(button)
            row.addWidget(button)
        layout.addLayout(row)
        self.cancel_button = QPushButton(self.tr("Cancel operation"))
        self.cancel_button.clicked.connect(self.cancel)
        self.prepare_button = QPushButton(self.tr("Prepare / resume selected model"))
        self.prepare_button.clicked.connect(lambda: self.start_action("prepare"))
        self.buttons.append(self.prepare_button)
        layout.addWidget(self.prepare_button)
        layout.addWidget(self.cancel_button)

    def display_stage_status(self):
        self.status.setText(self.stage_status.get(self.model.currentData(),
            self.tr("Not checked. Opening this dialog does not load or download models.")))

    def record_status(self, model, message):
        self.stage_status[model] = message
        if self.model.currentData() == model:
            self.status.setText(message)

    def root_item(self):
        return cfg.local_diarization_root if self.model.currentData() == "community-1" else cfg.local_asr_root

    def start_action(self, action):
        if self.worker is not None:
            return
        model, item = self.model.currentData(), self.root_item()
        root, token = item.value, ""
        if action == "choose":
            path = QFileDialog.getExistingDirectory(self, self.tr("Choose installed runtime"))
            if path:
                cfg.set(item, path)
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
        connect_current(self, "worker", worker, worker.installed, lambda path: cfg.set(item, path))
        worker.finished.connect(lambda: self.done_work(worker))
        for button in self.buttons:
            button.setEnabled(False)
        self.model.setEnabled(False)
        self.progress.setRange(0, 0)
        worker.start()

    def done_work(self, worker):
        worker.wait()
        if self.worker is not worker:
            return
        self.worker = None
        self.progress.setRange(0, 1)
        cancelled = getattr(worker, "_vc_cancel_requested", False)
        if cancelled:
            # Result signals are intentionally suppressed after cancellation.
            self.record_status(worker.model, self.tr("Local operation cancelled."))
        self.progress.setValue(0 if cancelled else 1)
        for button in self.buttons:
            button.setEnabled(True)
        self.model.setEnabled(True)

    def cancel(self):
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
        self.chunk = ComboBoxSettingCard(cfg.local_asr_chunk, FIF.SETTING, self.tr("Local audio chunk"), "",
                                         ["30 s", "60 s", "120 s", "240 s"], group)
        self.timeout = ComboBoxSettingCard(cfg.local_asr_timeout, FIF.SETTING, self.tr("Local stage deadline"), "",
                                           ["60 s", "180 s", "300 s", "600 s", "1800 s", "3600 s"], group)
        self.manager = PushSettingCard(self.tr("Manage models"), FIF.FOLDER, self.tr("Local ASR runtimes"),
                         self.tr("Explicit install, file check and health probe. Opening settings does not start a model."), group)
        self.manager.clicked.connect(self.open_manager)
        self.cards = [self.model, self.language, self.diarize, self.chunk, self.timeout, self.manager]
        for card in (self.model, self.language, self.diarize, self.manager):
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
