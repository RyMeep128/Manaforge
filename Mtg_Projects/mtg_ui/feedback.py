"""Approachable feedback composer and an explicitly submitted local outbox."""
import base64
import json
from pathlib import Path
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.repair import redact
from .diagnostics import app_version
from .feedback_service import CATEGORIES, MAX_SCREENSHOT, Store, new_report, submit
from .jobs import JobQueue


class FeedbackDialog(W.QDialog):
    def __init__(self, parent=None, *, report=None, diagnostics='', operation='', detail=''):
        super().__init__(parent)
        self.setWindowTitle('Send Feedback')
        self.resize(650, 740)
        self.store = Store()
        self.report = report or new_report(app_version(), operation, detail)
        self.diagnostic_text = diagnostics or self.report.get('diagnostics', '')
        self.jobs = JobQueue(self)
        self.jobs.status.connect(self.outcome)
        self.jobs.idle.connect(lambda: self.send.setEnabled(True))
        layout = W.QVBoxLayout(self)
        intro = W.QLabel('Tell us what happened or what would make Manaforge better. Contact details are optional.\nPlease leave out passwords, keys, and tokens. Saved drafts stay on this computer.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = W.QFormLayout()
        self.category = W.QComboBox()
        self.category.addItems(CATEGORIES)
        self.category.setCurrentText(self.report['category'])
        form.addRow('Type', self.category)
        self.fields = {}
        for key, label in [('title', 'Short title'), ('description', 'Tell us more'), ('steps', 'Steps to try (optional)'), ('behavior', 'Expected / actual (optional)'), ('contact', 'Contact (optional)')]:
            field = W.QPlainTextEdit() if key in ('description', 'steps', 'behavior') else W.QLineEdit()
            if isinstance(field, W.QPlainTextEdit):
                field.setMaximumHeight(90)
                field.setPlainText(self.report.get(key, ''))
            else:
                field.setText(self.report.get(key, ''))
            self.fields[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        self.attach = W.QCheckBox('Upload redacted diagnostics (optional; explicit consent)')
        self.attach.setEnabled(bool(self.diagnostic_text))
        self.attach.setChecked(bool(self.report.get('diagnostics')))
        layout.addWidget(self.attach)
        diag = W.QPushButton('Prepare local diagnostic report…')
        diag.clicked.connect(self.prepare_diagnostics)
        layout.addWidget(diag)
        screen = W.QPushButton('Choose screenshot… (PNG/JPEG, up to 350 KB)')
        screen.clicked.connect(self.screenshot)
        layout.addWidget(screen)
        remove = W.QPushButton('Remove screenshot')
        remove.clicked.connect(lambda: self.report.update(screenshot=''))
        layout.addWidget(remove)
        self.notice = W.QLabel('Submission requires a review. Pending reports are never sent automatically.')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        row = W.QHBoxLayout()
        self.send = W.QPushButton('Review and send…')
        self.send.clicked.connect(self.review_send)
        save = W.QPushButton('Save for later')
        save.clicked.connect(self.save)
        pending = W.QPushButton('Pending reports…')
        pending.clicked.connect(lambda: pending_reports(self))
        close = W.QPushButton('Close')
        close.clicked.connect(self.reject)
        for button in (self.send, save, pending, close):
            row.addWidget(button)
        layout.addLayout(row)

    def collect(self):
        self.report.update(category=self.category.currentText())
        for key, field in self.fields.items():
            self.report[key] = field.toPlainText() if isinstance(field, W.QPlainTextEdit) else field.text()
        self.report['diagnostics'] = redact(self.diagnostic_text) if self.attach.isChecked() else ''
        return self.report

    def save(self):
        try:
            self.store.save(self.collect())
            self.notice.setText('Saved on this computer. Open Pending reports to review, send, or delete it.')
            return True
        except (OSError, ValueError) as exc:
            self.notice.setText('Could not save: ' + str(exc))
            return False

    def prepare_diagnostics(self):
        from .diagnostics import DiagnosticsDialog
        dialog = DiagnosticsDialog(self)
        dialog.exec()
        self.diagnostic_text = dialog.report()
        self.attach.setEnabled(True)
        self.attach.setChecked(False)
        self.notice.setText('Diagnostics prepared locally. Check the attachment box to include them.')

    def screenshot(self):
        filename, _ = W.QFileDialog.getOpenFileName(self, 'Choose screenshot', '', 'Screenshots (*.png *.jpg *.jpeg)')
        if not filename:
            return
        try:
            with Path(filename).open('rb') as stream:
                data = stream.read(MAX_SCREENSHOT + 1)
            if len(data) > MAX_SCREENSHOT or not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')):
                raise ValueError('Choose a PNG or JPEG smaller than 350 KB.')
            self.report['screenshot'] = base64.b64encode(data).decode('ascii')
            self.notice.setText('Screenshot attached. Check it for private information before sending.')
        except (OSError, ValueError) as exc:
            self.notice.setText(str(exc))

    def review_send(self):
        if self.jobs.busy:
            return
        report = self.collect()
        if not report['title'].strip() or not report['description'].strip():
            self.notice.setText('Please add a title and description.')
            return
        import os
        endpoint = os.environ.get('MANAFORGE_FEEDBACK_URL', '(not configured)')
        review = W.QMessageBox(self)
        review.setWindowTitle('Review your report')
        review.setTextFormat(C.Qt.TextFormat.PlainText)
        review.setText(f'Send to {endpoint}\nPrivate maintainer storage; GitHub receives only category, version and reference.\nDiagnostics: {bool(report["diagnostics"])}; Screenshot: {bool(report["screenshot"])}\nContact: {report["contact"] or "Anonymous"}\nReview the details below before choosing Yes.')
        preview = dict(report)
        preview['screenshot'] = '(attached image; review the selected original)' if report['screenshot'] else ''
        review.setDetailedText(redact(json.dumps(preview, indent=2)))
        review.setStandardButtons(W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No)
        review.setDefaultButton(W.QMessageBox.StandardButton.No)
        if review.exec() != W.QMessageBox.StandardButton.Yes or not self.save():
            return
        # Freeze the snapshot while the worker runs; closing is blocked until it finishes.
        snapshot = json.loads(json.dumps(report))
        for widget in self.findChildren(W.QWidget):
            if widget is not self.notice:
                widget.setEnabled(False)
        self.jobs.submit(lambda cancel, progress: submit(snapshot))
        self.notice.setText('Sending… Your local copy is kept until submission is confirmed.')

    @C.pyqtSlot(str, str, object)
    def outcome(self, job_id, state, result):
        if state == 'completed':
            try:
                self.store.delete(self.report['id'])
            except OSError:
                pass  # Stable server reference prevents duplication if deletion fails.
            W.QMessageBox.information(self, 'Thank you', 'Feedback received. Reference: ' + str(result['reference']))
            self.accept()
        elif state == 'failed':
            for widget in self.findChildren(W.QWidget):
                widget.setEnabled(True)
            self.attach.setEnabled(bool(self.diagnostic_text))
            self.notice.setText('Could not send. Your report is saved. Retry here or through Pending reports when online.')

    def reject(self):
        if self.jobs.busy:
            return
        if any((field.toPlainText() if isinstance(field, W.QPlainTextEdit) else field.text()).strip() for field in self.fields.values()) or self.report.get('screenshot'):
            if not self.save():
                return
        super().reject()

    def closeEvent(self, event):
        if self.jobs.busy:
            event.ignore()
        else:
            self.reject()
            event.ignore() if self.isVisible() else event.accept()


def pending_reports(parent):
    dialog = W.QDialog(parent)
    dialog.setWindowTitle('Pending feedback — review before sending')
    layout = W.QVBoxLayout(dialog)
    items = W.QListWidget()
    layout.addWidget(items)
    store = Store()
    def refresh():
        items.clear()
        for report in store.reports():
            item = W.QListWidgetItem(report.get('title') or 'Untitled report')
            item.setData(C.Qt.ItemDataRole.UserRole, report)
            items.addItem(item)
    def selected():
        return items.currentItem().data(C.Qt.ItemDataRole.UserRole) if items.currentItem() else None
    def edit():
        if selected():
            FeedbackDialog(dialog, report=selected()).exec()
            refresh()
    def delete():
        if selected() and W.QMessageBox.question(dialog, 'Delete report?', 'Delete this local draft?') == W.QMessageBox.StandardButton.Yes:
            try:
                store.delete(selected()['id'])
                refresh()
            except OSError as exc:
                W.QMessageBox.warning(dialog, 'Could not delete', str(exc))
    for title, action in [('Review / retry', edit), ('Delete', delete), ('Close', dialog.accept)]:
        button = W.QPushButton(title)
        button.clicked.connect(action)
        layout.addWidget(button)
    refresh()
    dialog.exec()


def report_problem(parent, operation, detail):
    box = W.QMessageBox(parent)
    box.setWindowTitle('Something went wrong')
    box.setTextFormat(C.Qt.TextFormat.PlainText)
    box.setText('Manaforge could not finish ' + operation + '. You can retry or send a report for help.')
    box.setDetailedText(redact(detail))
    report = box.addButton('Report This Problem', W.QMessageBox.ButtonRole.ActionRole)
    box.addButton(W.QMessageBox.StandardButton.Close)
    box.exec()
    if box.clickedButton() == report:
        FeedbackDialog(parent, operation=operation, detail=detail).exec()
