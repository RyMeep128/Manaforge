"""Review verified artwork duplicates before reclaiming their disk space."""

from collections import Counter
from contextlib import closing
from pathlib import Path

from PyQt6 import QtCore as C, QtWidgets as W

from mtg_core.artwork_storage import ArtworkStorage


def size(value):
    return f"{value / 1024**3:,.2f} GiB"


def suggested_root(service):
    # Existing installations can retain absolute artwork paths on another drive.
    with closing(service.database.connect()) as db:
        paths = db.execute(
            "SELECT path FROM image_manifest WHERE source='scryfall' AND path IS NOT NULL"
        )
        roots = Counter(
            str(Path(row[0]).parent.parent)
            for row in paths
            if Path(row[0]).is_absolute()
            and Path(row[0]).parent.name == "mtg_core_cache"
        )
    return str(
        Path(roots.most_common(1)[0][0] if roots else service.image_root).resolve()
    )


class ArtworkStorageDialog(W.QDialog):
    def __init__(self, parent, service, jobs):
        super().__init__(parent)
        self.service, self.jobs = service, jobs
        self.job_id = None
        self.storage = None
        self.result_data = None
        self._closing = False
        self.setWindowTitle("Artwork storage")
        self.resize(700, 570)
        layout = W.QVBoxLayout(self)
        intro = W.QLabel(
            "Audit artwork storage, review verified duplicates, then reclaim space. "
            "Legacy paths remain usable. Custom artwork and unknown files are preserved. "
            "A first audit reads the artwork files and may take hours on a large library; "
            "Pause saves verified progress for the next audit."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        row = W.QHBoxLayout()
        self.location = W.QLineEdit(suggested_root(service))
        self.location.setAccessibleName(
            "Artwork folder containing assets and mtg_core_cache"
        )
        self.location.textChanged.connect(self.invalidate)
        row.addWidget(self.location, 1)
        self.browse = W.QPushButton("Browse…")
        self.browse.clicked.connect(self.choose_root)
        row.addWidget(self.browse)
        layout.addLayout(row)
        layout.addWidget(
            W.QLabel("Choose the artwork folder containing assets and mtg_core_cache.")
        )
        self.progress = W.QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = W.QLabel(
            "Choose Audit artwork storage. No artwork is changed by an audit."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.review = W.QPlainTextEdit()
        self.review.setReadOnly(True)
        layout.addWidget(self.review, 1)
        row = W.QHBoxLayout()
        self.audit_button = W.QPushButton("Audit artwork storage")
        self.audit_button.clicked.connect(self.audit)
        row.addWidget(self.audit_button)
        self.reclaim_button = W.QPushButton("Reclaim verified duplicates…")
        self.reclaim_button.setEnabled(False)
        self.reclaim_button.clicked.connect(self.reclaim)
        row.addWidget(self.reclaim_button)
        self.pause = W.QPushButton("Pause")
        self.pause.setEnabled(False)
        self.pause.clicked.connect(lambda: self.jobs.cancel(self.job_id))
        row.addWidget(self.pause)
        close = W.QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        layout.addLayout(row)
        self.jobs.progress.connect(self.on_progress)
        self.jobs.status.connect(self.on_status)
        self.jobs.idle.connect(self.on_idle)
        self.finished.connect(self.disconnect_jobs)

    def disconnect_jobs(self):
        self.jobs.progress.disconnect(self.on_progress)
        self.jobs.status.disconnect(self.on_status)
        self.jobs.idle.disconnect(self.on_idle)

    def invalidate(self):
        self.result_data = None
        self.reclaim_button.setEnabled(False)
        self.review.clear()

    def choose_root(self):
        root = W.QFileDialog.getExistingDirectory(
            self, "Choose artwork folder", self.location.text()
        )
        if root:
            self.location.setText(root)

    def start(self, operation):
        if self.jobs.busy:
            self.status.setText(
                "Another library operation is running. Wait for it to finish first."
            )
            return
        self.result_data = None
        self.reclaim_button.setEnabled(False)
        self.audit_button.setEnabled(False)
        self.location.setEnabled(False)
        self.browse.setEnabled(False)
        self.pause.setEnabled(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText(
            "Auditing artwork…"
            if operation == "audit"
            else "Reclaiming reviewed duplicates…"
        )
        self.job_id = self.jobs.submit(
            lambda cancel, report: getattr(self.storage, operation)(
                cancel=cancel, report=report
            )
        )

    def audit(self):
        if self.jobs.busy:
            self.status.setText("Wait for the active library operation to finish.")
            return
        try:
            self.storage = ArtworkStorage(self.service.database, self.location.text())
            self.start("audit")
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))

    def reclaim(self):
        if not self.result_data or not self.storage or self.jobs.busy:
            return
        if (
            W.QMessageBox.question(
                self,
                "Reclaim verified duplicates",
                f"Replace {self.result_data['duplicates']:,} verified duplicate files with hard links?\n"
                f"Verified reclaimable file bytes: {size(self.result_data['reclaimable_bytes'])}.\n"
                "Both files will be checked again. Unsupported or changed files will be kept. "
                "Existing artwork paths remain usable.",
                W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No,
                W.QMessageBox.StandardButton.No,
            )
            == W.QMessageBox.StandardButton.Yes
        ):
            self.start("reclaim")

    @C.pyqtSlot(str, object)
    def on_progress(self, job_id, value):
        if job_id != self.job_id or not isinstance(value, dict):
            return
        total = value.get("total")
        current = value.get("current", 0)
        self.status.setText(
            f"{value.get('operation', 'Working')} · {current:,}"
            + (f" / {total:,}" if total else "")
        )
        self.progress.setRange(0, 100 if total else 0)
        if total:
            self.progress.setValue(min(100, int(100 * current / total)))

    @C.pyqtSlot(str, str, object)
    def on_status(self, job_id, state, result):
        if job_id != self.job_id:
            return
        if state == "completed":
            self.result_data = result
            lines = [
                f"Artwork folder: {result['root']}",
                f"Inventoried files: {result['files']:,}",
                f"Logical file size: {size(result['logical_bytes'])}",
                f"Unique file storage (hard links counted once): {size(result['unique_bytes'])}",
                "File sizes exclude filesystem compression, sparse allocation, and metadata overhead.",
                f"Verified reclaimable file bytes: {size(result['reclaimable_bytes'])}",
                f"Verified duplicates: {result['duplicates']:,}",
                f"Already hard linked: {result['already_linked']:,}",
                f"Known canonical / legacy files: {result['canonical_files']:,} / {result['legacy_files']:,}",
                f"Unidentified files preserved: {result['unknown_files']:,}",
                f"Preserved candidate files: {result['preserved']:,}",
                f"Problems / skipped paths: {result['problems']:,}",
                f"Resumable audit journal: {result['journal']}",
            ]
            if result.get("needs_audit"):
                lines.insert(
                    0,
                    f"Reclaimed file bytes: {size(result['reclaimed_bytes'])}; {result['linked_files']:,} files linked.",
                )
                lines.insert(
                    1,
                    "Inventory totals above are from the review. Audit again to refresh storage totals.",
                )
            lines += [f"{r['path']}: {r['detail']}" for r in result["examples"]]
            self.review.setPlainText("\n".join(lines))
            self.status.setText(
                "Cleanup complete. Audit again to review current storage."
                if result.get("needs_audit")
                else "Audit complete. Review the results before choosing Reclaim."
            )
        elif state == "failed":
            self.status.setText(
                "Could not finish. Artwork was preserved where replacement was not completed."
            )
            self.review.setPlainText(str(result))
        elif state == "cancelled":
            self.status.setText(
                "Paused. Audit again to resume verification, then review before reclaiming."
            )

    @C.pyqtSlot()
    def on_idle(self):
        self.progress.hide()
        self.pause.setEnabled(False)
        self.audit_button.setEnabled(True)
        self.location.setEnabled(True)
        self.browse.setEnabled(True)
        self.reclaim_button.setEnabled(
            bool(
                self.result_data
                and not self.result_data.get("needs_audit")
                and self.result_data["duplicates"]
            )
        )
        if self._closing:
            super().reject()

    def reject(self):
        if self.job_id and self.jobs.busy and self.jobs.current_id == self.job_id:
            self._closing = True
            self.jobs.cancel(self.job_id)
            self.status.setText("Pausing safely before closing…")
            return
        super().reject()

    def closeEvent(self, event):
        self.reject()
        if self._closing:
            event.ignore()
        else:
            event.accept()
