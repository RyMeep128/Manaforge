"""Diagnostics stays available without constructing a catalog or recommendation service."""
from pathlib import Path
from PyQt6 import QtCore as C, QtWidgets as W

from mtg_core.datasets import InstallationState
from mtg_core.health import Check, overall, report_text, run_checks
from mtg_core.paths import core_data_root
from mtg_core.repair import ACTIONS, RepairService, recent_operations
from .jobs import JobQueue


def app_version():
    try:
        from mtg_proxy.constants import APP_VERSION
        return APP_VERSION
    except Exception:
        return "Unavailable (application version could not load)"


class DiagnosticsDialog(W.QDialog):
    def __init__(self, parent=None, *, engine=None, jobs=None):
        super().__init__(parent)
        self.engine = engine
        self.jobs = jobs or JobQueue(self)
        self.job_id = None
        self.results = []
        self._closing = False
        self._checking = False
        self.setWindowTitle('Diagnostics & Repair')
        self.resize(850, 700)
        layout = W.QVBoxLayout(self)
        self.summary = W.QLabel('Not Checked — run local diagnostics to inspect this installation.')
        self.summary.setTextFormat(C.Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.output = W.QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)
        checks = W.QHBoxLayout()
        self.local = W.QPushButton('Rerun diagnostics')
        self.local.clicked.connect(lambda: self.check(False))
        self.online = W.QPushButton('Check online services')
        self.online.clicked.connect(lambda: self.check(True))
        for button in (self.local, self.online):
            checks.addWidget(button)
        layout.addLayout(checks)
        row = W.QHBoxLayout()
        self.actions = W.QComboBox()
        for key, (title, _) in ACTIONS.items():
            self.actions.addItem(title, key)
        row.addWidget(self.actions, 1)
        self.repair = W.QPushButton('Review repair…')
        self.repair.clicked.connect(self.review_repair)
        row.addWidget(self.repair)
        layout.addLayout(row)
        self.progress = W.QProgressBar()
        layout.addWidget(self.progress)
        bottom = W.QHBoxLayout()
        self.cancel = W.QPushButton('Cancel operation')
        self.cancel.clicked.connect(lambda: self.jobs.cancel(self.job_id) if self.job_id else None)
        self.copy = W.QPushButton('Copy report')
        self.copy.clicked.connect(lambda: W.QApplication.clipboard().setText(self.report()))
        self.export = W.QPushButton('Export Diagnostic Report')
        self.export.clicked.connect(self.export_report)
        feedback = W.QPushButton('Send Feedback')
        feedback.clicked.connect(self.send_feedback)
        bottom.addWidget(feedback)
        close = W.QPushButton('Close')
        close.clicked.connect(self.reject)
        for button in (self.cancel, self.copy, self.export, close):
            bottom.addWidget(button)
        layout.addLayout(bottom)
        self.jobs.progress.connect(self.on_progress)
        self.jobs.status.connect(self.on_status)
        self.jobs.idle.connect(self.on_idle)
        self.cancel.setEnabled(False)
        C.QTimer.singleShot(0, lambda: self.check(False))

    def send_feedback(self):
        from .feedback import FeedbackDialog
        FeedbackDialog(self, diagnostics=self.report()).exec()

    def state(self):
        return self.engine.state if self.engine else InstallationState()

    def check(self, online=False):
        def work(cancel, report):
            try:
                state = self.state()
            except Exception as exc:
                return [Check('Installation state', 'Error', f'{exc}. State was preserved. Export this report for help; reinstalling the application must retain local data.')]
            return run_checks(state, version=app_version(), cancel=cancel, report=report, online=online)
        self.start(work, checking=True)

    def start(self, work, *, checking=False):
        if self.jobs.busy:
            self.summary.setText('A data operation is running. Wait or pause it in Data Management before starting diagnostics or repair.')
            return
        self._checking = checking
        self.local.setEnabled(False)
        self.online.setEnabled(False)
        self.repair.setEnabled(False)
        self.cancel.setEnabled(True)
        self.progress.setRange(0, 0)
        self.job_id = self.jobs.submit(work)

    def review_repair(self):
        action = self.actions.currentData()
        title, explanation = ACTIONS[action]
        if W.QMessageBox.question(self, title, explanation + '\n\nProceed?',
                                  W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No,
                                  W.QMessageBox.StandardButton.No) != W.QMessageBox.StandardButton.Yes:
            return
        def work(cancel, report):
            if self.engine is None:
                from mtg_core.installation import InstallationEngine
                self.engine = InstallationEngine()
            return RepairService(self.engine).run(action, cancel=cancel, report=report)
        self.start(work)

    def report(self):
        roots = []
        try:
            state = self.state()
            roots = [state.storage_root(c) for c in ('cards', 'recommendations', 'artwork')]
            roots.append(state.get('catalog_path', ''))
        except Exception:
            pass
        return report_text(self.results, version=app_version(), events=recent_operations(), roots=roots)

    def export_report(self):
        filename, _ = W.QFileDialog.getSaveFileName(self, 'Export diagnostic report', 'Manaforge-diagnostics.txt', 'Text files (*.txt)')
        if filename:
            try:
                Path(filename).write_text(self.report(), encoding='utf-8')
            except OSError as exc:
                W.QMessageBox.warning(self, 'Report could not be saved', str(exc))

    @C.pyqtSlot(str, object)
    def on_progress(self, job_id, value):
        if job_id != self.job_id or not isinstance(value, dict):
            return
        self.summary.setText(value.get('operation', 'Working…'))
        total = value.get('total')
        self.progress.setRange(0, 100 if total else 0)
        if total:
            self.progress.setValue(min(100, int(value.get('current', 0) * 100 / total)))

    @C.pyqtSlot(str, str, object)
    def on_status(self, job_id, state, value):
        if job_id != self.job_id:
            return
        if state == 'completed':
            if isinstance(value, list):
                if self._checking:
                    self.results = value
                else:
                    names = {r.name for r in value}
                    self.results = [r for r in self.results if r.name not in names] + value
            else:
                self.results.append(Check('Repair outcome', 'Warning' if 'missing or damaged' in str(value) else 'Healthy', str(value)))
            self.summary.setText('Overall installation health: ' + overall(self.results))
            self.output.setPlainText(self.report())
        elif state in ('failed', 'cancelled'):
            detail = str(value) if state == 'failed' else 'Cancelled. Completed work and resumable downloads were kept.'
            self.results.append(Check('Last operation', 'Error' if state == 'failed' else 'Warning', detail + ' You can retry.'))
            if state == 'failed':
                from .feedback import report_problem
                report_problem(self, 'diagnostics or repair', detail)
            self.summary.setText(detail)
            self.output.setPlainText(self.report())

    @C.pyqtSlot()
    def on_idle(self):
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.local.setEnabled(True)
        self.online.setEnabled(True)
        self.repair.setEnabled(True)
        self.cancel.setEnabled(False)
        if self._closing:
            super().reject()

    def reject(self):
        if self.job_id and self.jobs.busy:
            self._closing = True
            self.jobs.cancel(self.job_id)
            return
        super().reject()

    def closeEvent(self, event):
        if self.job_id and self.jobs.busy:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
