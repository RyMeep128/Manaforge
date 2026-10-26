"""First-run setup and shared Data Management UI over the common Qt job queue."""

from pathlib import Path
import shutil

from PyQt6 import QtCore as C, QtWidgets as W

from mtg_core.installation import InstallationEngine
from mtg_core.paths import core_data_root
from .jobs import JobQueue


def human_bytes(value):
    if value is None:
        return "unknown size"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024


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
        self.setWindowTitle("Welcome to Manaforge" if setup else "Data Management")
        self.resize(700, 590)
        layout = W.QVBoxLayout(self)
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
            "Check download sizes to see current datasets and required free space."
        )
        self.estimate.setWordWrap(True)
        layout.addWidget(self.estimate)
        self.versions = W.QLabel()
        self.versions.setWordWrap(True)
        layout.addWidget(self.versions)
        self.operation_label = W.QLabel("2 · Download, verify and initialize")
        self.operation_label.setTextFormat(C.Qt.TextFormat.PlainText)
        layout.addWidget(self.operation_label)
        self.progress = W.QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        self.overall = W.QProgressBar()
        self.overall.setFormat("Overall: %p%")
        layout.addWidget(self.overall)
        self.status = W.QLabel("")
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
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
        controls.addWidget(self.start)
        self.pause = W.QPushButton("Pause")
        self.pause.clicked.connect(self.pause_job)
        self.pause.setEnabled(False)
        controls.addWidget(self.pause)
        self.close_button = W.QPushButton("Cancel setup" if setup else "Close")
        self.close_button.clicked.connect(self.finish_or_close)
        controls.addWidget(self.close_button)
        layout.addLayout(controls)
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
        if self.jobs.busy:
            self.job_id = self.jobs.current_id
            self.operation = "install"
            self.options.setEnabled(False)
            self.check.setEnabled(False)
            self.pause.setEnabled(True)
            self.status.setText(
                "A library update is running in the background. You can pause it here."
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
        self.start.setEnabled(False)

    def check_updates(self):
        mode = self.mode.currentData()

        def work(cancel, report):
            return self.engine.plan(cancel=cancel, report=report, mode=mode)

        self.start_job("plan", work)

    def start_install(self):
        if self.plan is None:
            return
        location, mode = self.location.text().strip(), self.mode.currentData()

        def work(cancel, report):
            self.engine.configure(location, mode)
            return self.engine.run(
                cancel=cancel, report=report, plan=self.plan, setup=self.setup
            )

        self.start_job("install", work)

    def use_existing(self):
        if self.jobs.busy:
            return
        self.engine.configure(self.location.text(), "on_demand")
        self.engine.state.set("setup_complete", True)
        self.accept()

    def start_job(self, operation, work):
        if self.jobs.busy:
            self.status.setText(
                "A data operation is already running. Wait for it to finish or pause it before starting another."
            )
            return
        self.operation = operation
        self._owns_job = True
        self.options.setEnabled(False)
        self.check.setEnabled(False)
        self.start.setEnabled(False)
        self.pause.setEnabled(True)
        self.progress.setRange(0, 0)
        self.status.setText("Working…")
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
        self.operation_label.setText(value.get("operation", "Working"))
        current, total = value.get("current", 0), value.get("total")
        self.progress.setRange(0, 100 if total else 0)
        if total:
            self.progress.setValue(min(100, int(current * 100 / total)))
        if value.get("phase") in ("downloading", "verifying", "extracting"):
            detail = f"{human_bytes(current)} / {human_bytes(total)}"
        else:
            detail = f"{current:,}" + (f" / {total:,}" if total else "")
        if value.get("speed"):
            detail += " · " + human_bytes(value["speed"]) + "/s"
        if value.get("remaining") is not None:
            detail += f" · about {max(0, int(value['remaining'] // 60))} min remaining"
        self.status.setText(detail)
        if value.get("steps"):
            fraction = current / total if total else 0
            self.overall.setValue(
                min(100, int((value.get("step", 0) + fraction) * 100 / value["steps"]))
            )

    @C.pyqtSlot(str, str, object)
    def on_status(self, job_id, state, value):
        if job_id != self.job_id:
            return
        if state == "completed":
            if self.operation == "plan":
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
                    "Ready to install."
                    if self.setup
                    else "Check complete. Apply available updates, or save the selected mode by applying updates."
                )
            elif self.operation == "usage":
                self.status.setText(
                    f"{value['images']:,} cached artwork assets · {human_bytes(value['bytes'])} (canonical files; optional copies may use additional space)"
                )
            elif self.operation == "clear":
                self.status.setText(
                    f"{value} optional copies cleared. Canonical artwork, decks and preferences were kept."
                )
            else:
                self.status.setText(
                    "Your library is ready."
                    if self.setup
                    else "Data operation completed."
                )
                self.overall.setValue(100)
                if self.setup and self.engine.state.get("setup_complete", False):
                    self._ready = True
                    self.close_button.setText("Finish and launch Manaforge")
            self.refresh_versions()
        elif state == "failed":
            self.status.setText(
                "Could not complete the operation. "
                + str(value)
                + " Existing working data was preserved. You can retry."
            )
        elif state == "cancelled":
            self.status.setText(
                "Paused. Completed downloads and installed data were kept. Select Resume to continue."
            )
            if self.operation == "install":
                self.start.setText("Resume")

    @C.pyqtSlot()
    def on_idle(self):
        self.pause.setEnabled(False)
        self.options.setEnabled(True)
        self.check.setEnabled(True)
        self.start.setEnabled(self.plan is not None and not self._ready)
        if self._closing:
            super().reject()

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
    engine = engine or InstallationEngine()
    if engine.state.get("setup_complete", False):
        return True
    dialog = DataManagementDialog(parent, engine=engine, setup=True)
    return dialog.exec() == W.QDialog.DialogCode.Accepted
