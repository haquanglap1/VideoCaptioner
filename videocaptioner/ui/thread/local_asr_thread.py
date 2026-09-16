"""Explicit install/status/probe work, with persistent cancellation and bounded children."""

from contextvars import copy_context
from pathlib import Path
from threading import Event

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.asr.local.installer import install
from videocaptioner.core.asr.local.prepare import ensure_model
from videocaptioner.core.asr.local.profiles import MODELS
from videocaptioner.core.asr.local.runtime import (
    LocalRuntime,
    LocalRuntimeError,
    default_root,
    locate,
)


class LocalASRThread(QThread):
    status = pyqtSignal(str)
    installed = pyqtSignal(str)

    def __init__(self, action: str, model: str, root: str = "", timeout: int = 180, token: str = ""):
        super().__init__()
        self.action, self.model, self.root, self.timeout = action, model, root, timeout
        self._token = token
        self._cancelled = Event()
        self.context = copy_context()

    def stop(self):
        self._cancelled.set()
        self.requestInterruption()

    def check(self):
        if self._cancelled.is_set() or self.isInterruptionRequested():
            raise LocalRuntimeError("Local operation cancelled.")

    def run(self):
        self.context.run(self._run)

    def _run(self):
        runtime = None
        try:
            self.check()
            if self.action == "prepare":
                self.status.emit(self.tr("Preparing the selected model; checking reusable files..."))
                ensure_model(self.model, self.root, token=self._token, check=self.check, progress=self.status.emit)
                self.check()
                self.status.emit(self.tr("Model files verified; ready for the next task."))
                self.installed.emit(self.root or str(default_root(MODELS[self.model].runtime)))
            elif self.action == "install":
                models = (self.model, "aligner") if self.model.startswith("qwen-") else (self.model,)
                install(Path(self.root), models, token=self._token, check=self.check, progress=self.status.emit)
                self.check()
                self.installed.emit(self.root)
            else:
                self.status.emit(self.tr("Checking local installation..."))
                layout = locate(self.model, self.root, verify=self.action == "probe", check=self.check)
                if self.action == "probe":
                    runtime = LocalRuntime(layout, self.timeout)
                    self.status.emit(self.tr("Loading local model..."))
                    runtime.start(self.check)
                    self.status.emit(self.tr("Health ready. Probe released; inference has not been tested."))
                else:
                    self.status.emit(self.tr("Installed. Health and inference have not been tested."))
        except (OSError, ValueError, RuntimeError) as exc:
            self.status.emit(str(exc))
        finally:
            self._token = ""
            if runtime is not None:
                runtime.close()
