"""Compact feedback composer backed by the shared local outbox and relay."""
import base64
import json
from pathlib import Path
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_core.repair import redact
from .diagnostics import app_version
from .feedback_service import (CATEGORIES, MAX_SCREENSHOT, Store, new_report,
                               submit, collect_diagnostics, validate_report)
from .jobs import JobQueue


class FeedbackDialog(W.QDialog):
    def __init__(self, parent=None, *, report=None, diagnostics='', operation='', detail=''):
        super().__init__(parent)
        self.setWindowTitle('Send Feedback')
        self.resize(560, 520)
        self.setAcceptDrops(True)
        self.store = Store()
        self.report = dict(report) if report else new_report(app_version(), operation, detail)
        self.diagnostic_text = self.report.get('diagnostic_attachment', self.report.get('diagnostics', '')) or diagnostics
        self.extra_diagnostics = diagnostics
        self._sending = False
        self._closing = False
        self._send_after_collection = False
        self._diag_started = False
        self.jobs = JobQueue(self)
        self.jobs.status.connect(self.outcome)
        self.jobs.idle.connect(self.on_idle)
        self.diagnostic_jobs = JobQueue(self)
        self.diagnostic_jobs.status.connect(self.diagnostics_outcome)
        self.diagnostic_jobs.idle.connect(self.on_idle)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        intro = W.QLabel('Help make Manaforge better')
        font = intro.font()
        font.setPointSize(font.pointSize() + 3)
        font.setBold(True)
        intro.setFont(font)
        layout.addWidget(intro)
        self.editor = W.QWidget()
        body = W.QVBoxLayout(self.editor)
        body.setContentsMargins(0, 0, 0, 0)
        form = W.QFormLayout()
        self.category = W.QComboBox()
        for label, value in zip(('Bug Report', 'Feature Request', 'General Feedback'), CATEGORIES):
            self.category.addItem(label, value)
        self.category.setCurrentIndex(max(0, self.category.findData(self.report['category'])))
        form.addRow('What kind of feedback?', self.category)
        self.fields = {}
        for key in ('title', 'description', 'steps', 'behavior', 'contact'):
            field = W.QPlainTextEdit() if key in ('description', 'steps', 'behavior') else W.QLineEdit()
            if isinstance(field, W.QPlainTextEdit):
                field.setPlainText(self.report.get(key, ''))
                field.setFixedHeight(130 if key == 'description' else 55)
                field.setTabChangesFocus(True)
            else:
                field.setText(self.report.get(key, ''))
            self.fields[key] = field
        self.fields['title'].setMaxLength(120)
        self.fields['contact'].setMaxLength(250)
        self.fields['title'].setPlaceholderText('Cards disappear when switching decks')
        self.fields['description'].setPlaceholderText("Tell us what happened or what you'd like to see improved...")
        form.addRow('Title', self.fields['title'])
        form.addRow('Description', self.fields['description'])
        body.addLayout(form)
        attachments = W.QHBoxLayout()
        screen = W.QPushButton('Attach screenshot...')
        screen.clicked.connect(self.screenshot)
        attachments.addWidget(screen)
        self.preview = W.QLabel()
        self.preview.setFixedSize(92, 58)
        attachments.addWidget(self.preview)
        self.remove_image = W.QPushButton('Remove')
        self.remove_image.clicked.connect(self.remove_screenshot)
        attachments.addWidget(self.remove_image)
        attachments.addStretch()
        body.addLayout(attachments)
        self.more = W.QToolButton()
        self.more.setText('Additional details')
        self.more.setToolButtonStyle(C.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.more.setCheckable(True)
        self.more.setArrowType(C.Qt.ArrowType.RightArrow)
        body.addWidget(self.more)
        self.advanced = W.QWidget()
        advanced = W.QFormLayout(self.advanced)
        advanced.setContentsMargins(0, 0, 0, 0)
        for key, label in (('steps', 'Steps to reproduce'), ('behavior', 'Expected / actual'), ('contact', 'Contact (optional)')):
            advanced.addRow(label, self.fields[key])
        self.attach = W.QCheckBox('Include sanitized logs with this report')
        self.attach.setChecked(bool(self.report.get('diagnostics')))
        self.attach.setEnabled(bool(self.diagnostic_text))
        self.diagnostic_status = W.QLabel('Logs are prepared locally. You choose what to share before sending.')
        self.diagnostic_status.setWordWrap(True)
        self.view_logs = W.QPushButton('Review logs')
        self.view_logs.clicked.connect(self.review_diagnostics)
        advanced.addRow(self.diagnostic_status)
        advanced.addRow(self.attach, self.view_logs)
        body.addWidget(self.advanced)
        self.advanced.hide()
        self.more.toggled.connect(self.toggle_details)
        layout.addWidget(self.editor)
        self.notice = W.QLabel('Drafts stay on this computer. Nothing is sent without your approval.')
        self.notice.setTextFormat(C.Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        row = W.QHBoxLayout()
        pending = W.QToolButton()
        self.pending_button = pending
        pending.setText('Saved reports')
        pending.clicked.connect(lambda: pending_reports(self))
        row.addWidget(pending)
        row.addStretch()
        self.save_button = W.QPushButton('Save Draft')
        self.save_button.clicked.connect(self.save)
        row.addWidget(self.save_button)
        self.send = W.QPushButton('Send Feedback')
        self.send.setProperty('buttonRole', 'primary')
        self.send.setDefault(True)
        self.send.setShortcut('Ctrl+Return')
        self.send.clicked.connect(self.review_send)
        row.addWidget(self.send)
        layout.addLayout(row)
        self.category.currentIndexChanged.connect(self.category_changed)
        self.refresh_screenshot()
        W.QWidget.setTabOrder(self.category, self.fields['title'])
        W.QWidget.setTabOrder(self.fields['title'], self.fields['description'])
        self.fields['title'].setFocus()
        # Timed start keeps construction cheap and all collection off the GUI thread.
        C.QTimer.singleShot(0, self.category_changed)

    def toggle_details(self, checked):
        self.advanced.setVisible(checked)
        self.more.setArrowType(C.Qt.ArrowType.DownArrow if checked else C.Qt.ArrowType.RightArrow)
        self.resize(self.width(), 780 if checked else 520)

    def category_changed(self):
        bug = self.category.currentData() == CATEGORIES[0]
        if not bug:
            self.attach.setChecked(False)
        if bug and not self._diag_started and not (self.report.get('diagnostic_attachment') or self.report.get('diagnostics')):
            self._diag_started = True
            self.diagnostic_status.setText('Preparing logs locally... You can still write your report.')
            version = app_version()
            operation = self.report.get('operation', '')
            detail = self.report.get('description', '')
            extra = self.extra_diagnostics
            self.diagnostic_jobs.submit(lambda cancel, progress: collect_diagnostics(version, operation, detail, extra))
        self.attach.setEnabled(bug and bool(self.diagnostic_text))
        self.view_logs.setEnabled(bool(self.diagnostic_text))

    @C.pyqtSlot(str, str, object)
    def diagnostics_outcome(self, job_id, state, value):
        if state == 'completed':
            self.diagnostic_text = value
            self.diagnostic_status.setText('Sanitized logs are ready. Review them or leave them out.')
            self.attach.setEnabled(self.category.currentData() == CATEGORIES[0])
            self.view_logs.setEnabled(bool(value))
        elif state in ('failed', 'cancelled'):
            self.diagnostic_status.setText('Logs are unavailable. You can still send feedback.')

    def review_diagnostics(self):
        dialog = W.QDialog(self)
        dialog.setWindowTitle('Review sanitized logs')
        dialog.resize(650, 440)
        layout = W.QVBoxLayout(dialog)
        text = W.QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(self.diagnostic_text)
        layout.addWidget(text)
        close = W.QPushButton('Close')
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def collect(self):
        self.report.update(category=self.category.currentData())
        for key, field in self.fields.items():
            self.report[key] = field.toPlainText() if isinstance(field, W.QPlainTextEdit) else field.text()
        self.report['diagnostic_attachment'] = redact(self.diagnostic_text)
        self.report['diagnostics'] = redact(self.diagnostic_text) if self.attach.isChecked() and self.category.currentData() == CATEGORIES[0] else ''
        return self.report

    def save(self):
        try:
            self.store.save(self.collect())
            self.notice.setText('Draft saved. Find it in Saved reports when ready.')
            return True
        except (OSError, ValueError):
            self.notice.setText('Could not save your draft. Check available disk space and folder permissions.')
            return False

    def screenshot(self):
        filename, _ = W.QFileDialog.getOpenFileName(self, 'Choose screenshot', '', 'Screenshots (*.png *.jpg *.jpeg)')
        if filename:
            self.attach_screenshot(filename)

    def attach_screenshot(self, filename):
        try:
            with Path(filename).open('rb') as stream:
                data = stream.read(MAX_SCREENSHOT + 1)
            if len(data) > MAX_SCREENSHOT or not data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
                raise ValueError('Choose a PNG or JPEG smaller than 350 KB.')
            self.report['screenshot'] = base64.b64encode(data).decode('ascii')
            self.refresh_screenshot()
            self.notice.setText('Screenshot attached. Check it for private information before sending.')
        except (OSError, ValueError):
            self.notice.setText('Choose a readable PNG or JPEG smaller than 350 KB.')

    def refresh_screenshot(self):
        pixmap = G.QPixmap()
        try:
            pixmap.loadFromData(base64.b64decode(self.report.get('screenshot', ''), validate=True))
        except ValueError:
            pass
        self.preview.setPixmap(pixmap.scaled(92, 58, C.Qt.AspectRatioMode.KeepAspectRatio, C.Qt.TransformationMode.SmoothTransformation))
        self.remove_image.setVisible(bool(self.report.get('screenshot')))

    def remove_screenshot(self):
        self.report['screenshot'] = ''
        self.refresh_screenshot()

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if not self._sending and len(urls) == 1 and urls[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self._sending and event.mimeData().hasUrls():
            self.attach_screenshot(event.mimeData().urls()[0].toLocalFile())
            event.acceptProposedAction()

    def review_send(self):
        if self._sending or self.report.get('status') == 'submitted':
            return
        try:
            validate_report(self.collect())
        except ValueError as exc:
            self.notice.setText(str(exc))
            return
        if self.diagnostic_jobs.busy and self.category.currentData() == CATEGORIES[0]:
            self._send_after_collection = True
            self.send.setEnabled(False)
            self.notice.setText('Finishing your logs... The review will open in a moment.')
            return
        review = W.QDialog(self)
        review.setWindowTitle('Review your feedback')
        review.resize(510, 450)
        layout = W.QVBoxLayout(review)
        summary = W.QLabel('Your feedback is stored privately in Cloudflare for the maintainer. GitHub receives only a category, version and reference. Screenshots are not scrubbed. Review attachments for private information.')
        summary.setWordWrap(True)
        layout.addWidget(summary)
        metadata = self.report['metadata']
        shared = W.QLabel(f"Also shared: Manaforge {metadata['version']}, {metadata.get('os', '')}, platform and Python version, and your report reference.")
        shared.setWordWrap(True)
        shared.setTextFormat(C.Qt.TextFormat.PlainText)
        layout.addWidget(shared)
        preview = W.QPlainTextEdit()
        preview.setReadOnly(True)
        payload = validate_report(self.collect())
        preview.setPlainText('\n\n'.join(f'{key.capitalize()}: {payload[key]}' for key in ('title', 'description', 'steps', 'behavior', 'contact') if payload[key]))
        layout.addWidget(preview)
        image = W.QLabel()
        pixmap = G.QPixmap()
        pixmap.loadFromData(base64.b64decode(self.report.get('screenshot', '')))
        if not pixmap.isNull():
            image.setPixmap(pixmap.scaled(450, 140, C.Qt.AspectRatioMode.KeepAspectRatio, C.Qt.TransformationMode.SmoothTransformation))
            layout.addWidget(image)
        consent = W.QCheckBox('Include sanitized logs (may contain personal information)')
        consent.setChecked(self.attach.isChecked())
        consent.setEnabled(bool(self.diagnostic_text) and self.category.currentData() == CATEGORIES[0])
        layout.addWidget(consent)
        logs = W.QPushButton('Review sanitized logs')
        logs.setEnabled(consent.isEnabled())
        logs.clicked.connect(self.review_diagnostics)
        layout.addWidget(logs)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Cancel)
        confirm = buttons.addButton('Confirm and Send', W.QDialogButtonBox.ButtonRole.AcceptRole)
        confirm.setProperty('buttonRole', 'primary')
        buttons.accepted.connect(review.accept)
        buttons.rejected.connect(review.reject)
        layout.addWidget(buttons)
        if review.exec() != W.QDialog.DialogCode.Accepted:
            return
        self.attach.setChecked(consent.isChecked())
        self.collect()
        self.report['status'] = 'pending'
        if not self.save():
            return
        snapshot = json.loads(json.dumps(self.report))
        self._sending = True
        self.editor.setEnabled(False)
        self.send.setEnabled(False)
        self.save_button.setEnabled(False)
        self.pending_button.setEnabled(False)
        def send_snapshot(cancel, progress):
            try:
                return submit(snapshot)
            except ValueError as exc:
                return {'error': str(exc)}
        self.jobs.submit(send_snapshot)
        self.notice.setText('Sending feedback... Your local copy is saved.')

    @C.pyqtSlot(str, str, object)
    def outcome(self, job_id, state, result):
        friendly_error = ''
        if state == 'completed' and result.get('error'):
            friendly_error = result['error']
            state = 'failed'
        if state == 'completed':
            self.report.update(status='submitted', reference=str(result['reference']))
            try:
                self.store.save(self.report)
            except OSError:
                # The server also deduplicates this stable ID after a disk failure.
                pass
            self.notice.setText('Thanks! Your feedback has been sent. Reference: ' + self.report['reference'])
            self._closing = True
        elif state in ('failed', 'cancelled'):
            self.report['status'] = 'failed'
            saved = self.save()
            suffix = ' Your report has been saved, and you can try again later.' if saved else ' Your report is still open; save it before closing.'
            self.notice.setText("Couldn't send feedback." + suffix + (" " + friendly_error if friendly_error else ""))

    @C.pyqtSlot()
    def on_idle(self):
        if self.jobs.busy or self.diagnostic_jobs.busy:
            return
        self._sending = False
        self.editor.setEnabled(True)
        self.send.setEnabled(self.report.get('status') != 'submitted')
        self.save_button.setEnabled(True)
        self.pending_button.setEnabled(True)
        if self._closing:
            if self.report.get('status') != 'submitted' and (self.report.get('title') or self.report.get('description') or self.report.get('screenshot')):
                if not self.save():
                    self._closing = False
                    self.setEnabled(True)
                    return
            if self.report.get('status') == 'submitted':
                W.QMessageBox.information(self, 'Thank you', 'Thanks! Your feedback has been sent. Reference: ' + self.report['reference'])
            super().accept()
        elif self._send_after_collection:
            self._send_after_collection = False
            self.review_send()

    def reject(self):
        if self._sending:
            return
        if any((field.toPlainText() if isinstance(field, W.QPlainTextEdit) else field.text()).strip() for field in self.fields.values()) or self.report.get('screenshot'):
            if not self.save():
                return
        if self.diagnostic_jobs.busy:
            self._closing = True
            self._send_after_collection = False
            self.notice.setText('Saving your draft and prepared logs...')
            self.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event):
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
            item = W.QListWidgetItem(f"[{report.get('status', 'draft').capitalize()}] {report.get('title') or 'Untitled report'}")
            item.setData(C.Qt.ItemDataRole.UserRole, report)
            items.addItem(item)
    def selected():
        return items.currentItem().data(C.Qt.ItemDataRole.UserRole) if items.currentItem() else None
    def edit():
        if selected() and selected().get('status') == 'submitted':
            W.QMessageBox.information(dialog, 'Already sent', 'This feedback has already been sent. Reference: ' + str(selected().get('reference', '')))
        elif selected():
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
