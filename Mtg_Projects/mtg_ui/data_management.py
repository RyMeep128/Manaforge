"""First-run setup and shared Data Management UI over the common Qt job queue."""

from pathlib import Path
import shutil

from PyQt6 import QtCore as C, QtWidgets as W

from mtg_core.installation import InstallationEngine
from mtg_core.paths import core_data_root
from .jobs import JobQueue
from .install_progress import InstallationProgress, human_bytes


class DataManagementDialog(W.QDialog):
    def __init__(self, parent=None, *, engine=None, jobs=None, setup=False):
        super().__init__(parent)
        self.engine = engine or InstallationEngine()
        self.jobs = jobs or JobQueue(self)
        self.setup = setup
        self.plan = None
        self.job_id = None
        self.operation = None
        self._closing = False
        self._ready = False
        self._owns_job = False
        self._last_work = None
        self._retry_operation = None
        self._resume_saved = False
        self._saved_artwork_only = False
        self._check_after_health = False
        self._health_details = ""
        self.setWindowTitle("Welcome to Manaforge" if setup else "Data Management")
        self.resize(760, 820)
        outer = W.QVBoxLayout(self)
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(W.QFrame.Shape.NoFrame)
        body = W.QWidget()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        layout = W.QVBoxLayout(body)
        title = W.QLabel(
            "Set up your card library" if setup else "Manage your card library"
        )
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        layout.addWidget(title)
        intro = W.QLabel(
            "Card data and recommendations are the same in both modes. Choose how artwork is stored. Setup can be paused and resumed."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.options = W.QGroupBox("1 · Storage and artwork")
        form = W.QFormLayout(self.options)
        row = W.QHBoxLayout()
        self.location = W.QLineEdit(
            self.engine.state.get("data_location", str(core_data_root() / "datasets"))
        )
        self.location.setAccessibleName("Dataset storage location")
        browse = W.QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        row.addWidget(self.location, 1)
        row.addWidget(browse)
        form.addRow("Data location", row)
        self.mode = W.QComboBox()
        self.mode.addItem("Download artwork as needed (default)", "on_demand")
        self.mode.addItem("Full offline artwork (about 100–200 GB)", "full_offline")
        self.mode.setCurrentIndex(
            max(
                0,
                self.mode.findData(self.engine.state.get("artwork_mode", "on_demand")),
            )
        )
        self.mode.currentIndexChanged.connect(self.invalidate_plan)
        self.location.textChanged.connect(self.invalidate_plan)
        form.addRow("Artwork mode", self.mode)
        if not setup:
            note = W.QLabel(
                "Location changes apply to new dataset generations and artwork. Existing cached files remain accessible; decks and preferences stay in place."
            )
            note.setWordWrap(True)
            form.addRow(note)
        layout.addWidget(self.options)
        self.estimate = W.QLabel(
            "We will check download sizes automatically. Library installation starts when you choose Install."
            if setup
            else "Check for updates to see current datasets and required free space."
        )
        self.estimate.setWordWrap(True)
        layout.addWidget(self.estimate)
        self.versions = W.QLabel()
        self.versions.setWordWrap(True)
        layout.addWidget(self.versions)
        self.install_progress = InstallationProgress(self)
        layout.addWidget(self.install_progress)
        self.status = W.QLabel("")
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.details_toggle = W.QPushButton("Show diagnostic details")
        self.details_toggle.setCheckable(True)
        layout.addWidget(self.details_toggle)
        self.error_details = W.QPlainTextEdit()
        self.error_details.setReadOnly(True)
        self.error_details.setMaximumHeight(110)
        self.error_details.hide()
        self.details_toggle.toggled.connect(self.error_details.setVisible)
        self.details_toggle.toggled.connect(
            lambda checked: self.details_toggle.setText(
                "Hide diagnostic details" if checked else "Show diagnostic details"
            )
        )
        layout.addWidget(self.error_details)
        diagnostics = W.QPushButton("Diagnostics & Repair")
        diagnostics.clicked.connect(self.open_diagnostics)
        layout.addWidget(diagnostics)
        layout.addStretch(1)
        controls = W.QHBoxLayout()
        self.check = W.QPushButton(
            "Check download sizes" if setup else "Check for Updates"
        )
        self.check.clicked.connect(self.check_updates)
        controls.addWidget(self.check)
        self.start = W.QPushButton("Install" if setup else "Apply updates")
        self.start.clicked.connect(self.start_install)
        self.start.setEnabled(False)
        if setup:
            self.start.setDefault(True)
        controls.addWidget(self.start)
        self.pause = W.QPushButton("Pause")
        self.pause.clicked.connect(self.pause_job)
        self.pause.setEnabled(False)
        controls.addWidget(self.pause)
        self.close_button = W.QPushButton("Cancel setup" if setup else "Close")
        self.close_button.clicked.connect(self.finish_or_close)
        controls.addWidget(self.close_button)
        outer.addLayout(controls)
        if setup and self.engine.has_catalog():
            self.existing = W.QPushButton(
                "Continue with existing data (artwork as needed)"
            )
            self.existing.clicked.connect(self.use_existing)
            layout.addWidget(self.existing)
        if not setup:
            actions = W.QHBoxLayout()
            self.missing = W.QPushButton("Download missing artwork")
            self.missing.clicked.connect(
                lambda: self.start_job(
                    "artwork",
                    lambda cancel, report: self.engine.run(
                        cancel=cancel, report=report, artwork_only=True
                    ),
                )
            )
            self.usage = W.QPushButton("Artwork storage usage")
            self.usage.clicked.connect(
                lambda: self.start_job(
                    "usage", lambda cancel, report: self.engine.usage(cancel=cancel)
                )
            )
            self.clear = W.QPushButton("Clear optional artwork copies")
            self.clear.clicked.connect(self.clear_cache)
            for button in (self.missing, self.usage, self.clear):
                actions.addWidget(button)
            layout.addLayout(actions)
        self.jobs.progress.connect(self.on_progress)
        self.jobs.status.connect(self.on_status)
        self.jobs.idle.connect(self.on_idle)
        self.refresh_versions()
        snapshot = self.engine.state.get("installation_progress", {})
        if snapshot and any(
            item["state"] != "completed" for item in snapshot.get("stages", [])
        ):
            self._resume_saved = True
            self._saved_artwork_only = (
                len(snapshot.get("stages", [])) == 1
                and snapshot["stages"][0]["id"] == "artwork"
            )
            failed = snapshot.get("task_state") == "failed"
            restored = dict(snapshot, task_state="failed" if failed else "paused")
            restored["stages"] = [
                dict(
                    item,
                    state="paused" if item["state"] == "running" else item["state"],
                )
                for item in snapshot.get("stages", [])
            ]
            self.install_progress.consume(restored)
            self.status.setText(
                "Previous installation failed during "
                + snapshot.get("operation", "setup")
                + ". Retry rechecks installed data and resumes supported downloads."
                if failed
                else "Interrupted installation found. Resume rechecks installed datasets and continues supported partial downloads."
            )
            self.start.setText("Retry" if failed else "Resume")
            self.start.setEnabled(True)
        elif setup:
            C.QTimer.singleShot(0, self.first_run_checks)
        if self.jobs.busy:
            self.job_id = self.jobs.current_id
            self.operation = "install"
            latest = getattr(self.jobs, "latest_progress", None)
            if isinstance(latest, dict):
                self.install_progress.consume(latest)
            artwork_only = (
                isinstance(latest, dict)
                and len(latest.get("stages", [])) == 1
                and latest["stages"][0]["id"] == "artwork"
            )
            self.operation = "artwork" if artwork_only else "install"
            self._last_work = lambda cancel, report: self.engine.run(
                cancel=cancel, report=report, artwork_only=artwork_only
            )
            self.options.setEnabled(False)
            self.check.setEnabled(False)
            self.start.setEnabled(False)
            self.pause.setEnabled(True)
            self.status.setText(
                "A library update is running in the background. You can pause it here."
            )

    def open_diagnostics(self):
        from .diagnostics import DiagnosticsDialog

        DiagnosticsDialog(self, engine=self.engine, jobs=self.jobs).exec()

    def first_run_checks(self):
        if not self.jobs.busy:
            from mtg_core.health import run_checks
            from .diagnostics import app_version

            self.start_job(
                "health",
                lambda cancel, report: run_checks(
                    self.engine.state,
                    version=app_version(),
                    cancel=cancel,
                    report=report,
                ),
            )

    def refresh_versions(self):
        bulk = self.engine.state.get("bulk_versions", {})
        installed = []
        for source in ("edhrec", "archidekt", "moxfield"):
            item = self.engine.state.installed("recommendations-" + source)
            if item:
                import json

                installed.append(
                    source.title() + ": " + json.loads(item["manifest"])["version"]
                )
        text = [
            key.replace("_", " ").title() + ": " + value for key, value in bulk.items()
        ] + installed
        self.versions.setText(
            "Installed datasets\n" + "\n".join(text)
            if text
            else "No managed dataset versions installed yet."
        )

    def browse(self):
        path = W.QFileDialog.getExistingDirectory(
            self, "Choose data location", self.location.text()
        )
        if path:
            self.location.setText(path)

    def invalidate_plan(self, *args):
        self.plan = None
        self._retry_operation = None
        self._resume_saved = False
        self.start.setText("Install" if self.setup else "Apply updates")
        self.start.setEnabled(False)
        if not self.jobs.busy:
            self.install_progress.hide()
            self.status.setText(
                "Check download sizes for the selected options before installing."
            )
            self.estimate.setText(
                "Check download sizes again for the selected storage and artwork options."
            )

    def check_updates(self):
        mode = self.mode.currentData()

        def work(cancel, report):
            return self.engine.plan(cancel=cancel, report=report, mode=mode)

        self.start_job("plan", work)

    def start_install(self):
        if self._retry_operation and self._last_work:
            self.start_job(self._retry_operation, self._last_work, resume=True)
            return
        if self.plan is None and not self._resume_saved:
            return
        if self._resume_saved and self._saved_artwork_only:
            self.start_job(
                "artwork",
                lambda cancel, report: self.engine.run(
                    cancel=cancel, report=report, artwork_only=True
                ),
                resume=True,
            )
            return
        location, mode = self.location.text().strip(), self.mode.currentData()
        plan = self.plan

        def work(cancel, report):
            self.engine.configure(location, mode)
            return self.engine.run(
                cancel=cancel, report=report, plan=plan, setup=self.setup
            )

        self.start_job("install", work, resume=self._resume_saved)

    def use_existing(self):
        if self.jobs.busy:
            return
        self.engine.configure(self.location.text(), "on_demand")
        self.engine.state.set("setup_complete", True)
        self.accept()

    def start_job(self, operation, work, *, resume=False):
        if self.jobs.busy:
            self.status.setText(
                "A data operation is already running. Wait for it to finish or pause it before starting another."
            )
            return
        self.operation = operation
        self._check_after_health = False
        self._last_work = work
        self._retry_operation = None
        self._owns_job = True
        self.install_progress.show()
        if not resume:
            self.install_progress.reset(
                "Overall setup progress" if self.setup else "Overall update progress"
            )
        self.details_toggle.setChecked(False)
        self.error_details.setPlainText(self._health_details)
        self.options.setEnabled(False)
        self.check.setEnabled(False)
        self.start.setEnabled(False)
        self.pause.setEnabled(True)
        self.status.setText(
            "Looking up download sizes. Installation has not started."
            if operation == "plan"
            else "Please wait while this step completes."
        )
        self.job_id = self.jobs.submit(work)

    def pause_job(self):
        if self.job_id:
            self.jobs.cancel(self.job_id)
            self.status.setText(
                "Pausing after the current operation. Downloaded data will be kept."
            )
            self.pause.setEnabled(False)

    @C.pyqtSlot(str, object)
    def on_progress(self, job_id, value):
        if job_id != self.job_id or not isinstance(value, dict):
            return
        self.install_progress.consume(value)

    @C.pyqtSlot(str, str, object)
    def on_status(self, job_id, state, value):
        if job_id != self.job_id:
            return
        if state == "completed":
            self._resume_saved = False
            self.install_progress.finish("completed")
            self.start.setText("Install" if self.setup else "Apply updates")
            if self.operation == "health":
                from mtg_core.health import overall

                self.status.setText(
                    "Initial checks: "
                    + overall(value)
                    + ". See Diagnostics & Repair for details."
                )
                self._health_details = "Initial installation health\n" + "\n".join(
                    f"{r.name}: {r.status}" for r in value
                )
                self.error_details.setPlainText(self._health_details)
                self.install_progress.task.title.setText("Initial checks complete")
                self._check_after_health = self.setup
            elif self.operation == "plan":
                self.plan = value
                root = Path(self.location.text()).expanduser().resolve()
                while not root.exists() and root != root.parent:
                    root = root.parent
                free = shutil.disk_usage(root).free
                self.estimate.setText(
                    f"Downloads: about {human_bytes(value.download_bytes)}\nEstimated free space needed: {human_bytes(value.required_bytes)} · Available: {human_bytes(free)}"
                    + (
                        "\nArtwork estimate includes up to 200 GiB. Initial artwork collection can take many hours."
                        if value.artwork_bytes
                        else "\nArtwork downloads only when requested; cached images stay available offline."
                    )
                )
                self.status.setText(
                    "Review the sizes above, then choose Install to download and set up your library."
                    if self.setup
                    else "Check complete. Apply available updates, or save the selected mode by applying updates."
                )
                self.install_progress.task.title.setText("Download sizes checked")
            elif self.operation == "usage":
                self.install_progress.task.title.setText(
                    "Artwork storage check complete"
                )
                self.status.setText(
                    f"{value['images']:,} cached artwork assets · {human_bytes(value['bytes'])} (canonical files; optional copies may use additional space)"
                )
            elif self.operation == "clear":
                self.install_progress.task.title.setText(
                    "Optional artwork cleanup complete"
                )
                self.status.setText(
                    f"{value} optional copies cleared. Canonical artwork, decks and preferences were kept."
                )
            else:
                self.install_progress.task.title.setText(
                    "Library ready" if self.setup else "Operation complete"
                )
                self.status.setText(
                    "Your library is ready."
                    if self.setup
                    else "Data operation completed."
                )
                if self.setup and self.engine.state.get("setup_complete", False):
                    self._ready = True
                    self.close_button.setText("Finish and launch Manaforge")
            self.refresh_versions()
        elif state == "failed":
            self.install_progress.finish("failed")
            operation = self.install_progress.last.get(
                "operation", self.operation or "operation"
            )
            self.status.setText(
                f"Could not finish {operation}. Working data was preserved. Select Retry to try again."
            )
            self.error_details.setPlainText(str(value))
            self._retry_operation = self.operation
            self.start.setText("Retry")
        elif state == "cancelled":
            self.install_progress.finish("paused")
            self.status.setText(
                "Paused. Completed data and resumable downloads were kept. Resume continues supported downloads; unsupported transfers may restart."
            )
            self._retry_operation = self.operation
            self.start.setText("Resume")

    @C.pyqtSlot()
    def on_idle(self):
        self.pause.setEnabled(False)
        self.options.setEnabled(True)
        self.check.setEnabled(True)
        self.start.setEnabled(
            (
                self.plan is not None
                or self._retry_operation is not None
                or self._resume_saved
            )
            and not self._ready
        )
        if self._closing:
            super().reject()
        elif self._check_after_health and self._retry_operation is None:
            self._check_after_health = False
            self.check_updates()

    def clear_cache(self):
        if (
            W.QMessageBox.question(
                self,
                "Clear optional artwork copies",
                "Remove reproducible artwork copies? Canonical artwork and all decks and preferences will be kept.",
            )
            == W.QMessageBox.StandardButton.Yes
        ):
            self.start_job(
                "clear",
                lambda cancel, report: self.engine.clear_optional(
                    cancel=cancel, report=report
                ),
            )

    def finish_or_close(self):
        if self._ready:
            self.accept()
        else:
            self.reject()

    def reject(self):
        if self._owns_job and self.job_id and self.jobs.busy:
            self._closing = True
            self.pause_job()
            return
        super().reject()

    def closeEvent(self, event):
        if self._owns_job and self.job_id and self.jobs.busy:
            self._closing = True
            self.pause_job()
            event.ignore()
        else:
            super().closeEvent(event)


def run_initial_setup(parent=None, *, engine=None):
    try:
        engine = engine or InstallationEngine()
        if engine.state.get("setup_complete", False):
            return True
        dialog = DataManagementDialog(parent, engine=engine, setup=True)
        return dialog.exec() == W.QDialog.DialogCode.Accepted
    except Exception:
        from .diagnostics import DiagnosticsDialog

        DiagnosticsDialog(parent).exec()
        return False
