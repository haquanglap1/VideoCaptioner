"""QThread boundary for managed VieNeu start/update/model operations."""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.tts.vieneu.model_updater import describe_download_progress
from videocaptioner.core.tts.vieneu.models import VieNeuRuntimeState, sanitize_error
from videocaptioner.core.tts.vieneu.service import (
    VieNeuManagedService,
    get_vieneu_service,
)


class VieNeuRuntimeThread(QThread):
    progress = pyqtSignal(int, str)
    runtime_state = pyqtSignal(str, str)
    result = pyqtSignal(str, object)
    error = pyqtSignal(str, str)

    def __init__(
        self,
        action: str,
        *,
        service: VieNeuManagedService | None = None,
        manual_retry_rejected: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.action = action
        self.service = service or get_vieneu_service()
        self.manual_retry_rejected = manual_retry_rejected

    def _on_state(self, state: VieNeuRuntimeState, message: str) -> None:
        self.runtime_state.emit(state.value, message)

    def _download_reporter(self, base: int, span: int, what: str):
        """Map hub bar updates (file counts or bytes) onto one monotonic range."""
        best = 0.0

        def report(done: int, total: int, name: str) -> None:
            nonlocal best
            fraction, detail = describe_download_progress(done, total, name)
            best = max(best, fraction)
            self.progress.emit(
                base + int(best * span), f"Downloading VieNeu {what}: {detail}"
            )

        return report

    def run(self) -> None:
        self.service.manager.add_state_callback(self._on_state)
        try:
            if self.action == "start":
                self.progress.emit(10, "Starting VieNeu Local...")
                identity = self.service.ensure_ready()
                self.result.emit(self.action, identity)
            elif self.action == "stop":
                self.service.shutdown()
                self.result.emit(self.action, {"state": "stopped"})
            elif self.action == "voices":
                self.progress.emit(10, "Ensuring VieNeu Local is ready...")
                self.result.emit(self.action, self.service.voices())
            elif self.action == "check":
                self.progress.emit(10, "Checking VieNeu model revision...")
                check = self.service.updater.check_for_update(
                    manual_retry_rejected=self.manual_retry_rejected
                )
                self.result.emit(self.action, check)
            elif self.action == "update":
                self.progress.emit(2, "Provisioning pinned VieNeu dependencies...")
                self.service.prepare_update_prerequisites(
                    progress_callback=self._download_reporter(2, 8, "dependency")
                )
                self.progress.emit(10, "Checking VieNeu model revision...")
                check = self.service.updater.stage_latest(
                    cancel_event=self.service._cancel_event,
                    manual_retry_rejected=self.manual_retry_rejected,
                    progress_callback=self._download_reporter(10, 60, "model"),
                )
                if check.status != "staged":
                    self.result.emit(self.action, check)
                    return
                self.progress.emit(75, "Validating VieNeu candidate on the GPU...")
                state = self.service.model_state()
                activation = self.service.updater.validate_and_activate(
                    self.service.manager,
                    lambda snapshot, revision: self.service.launch_config(
                        state, snapshot=snapshot, revision=revision
                    ),
                    cancel_event=self.service._cancel_event,
                )
                self.result.emit(self.action, activation)
            elif self.action == "rollback":
                self.service.shutdown()
                self.result.emit(self.action, self.service.updater.rollback())
            elif self.action == "status":
                self.result.emit(self.action, self.service.model_state())
            else:
                raise ValueError(f"Unsupported VieNeu runtime action: {self.action}")
            self.progress.emit(100, "VieNeu operation completed")
        except Exception as exc:
            self.error.emit(self.action, sanitize_error(exc))
        finally:
            self.service.manager.remove_state_callback(self._on_state)
