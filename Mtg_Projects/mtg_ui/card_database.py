"""Persistent post-install workspace; first-run setup remains in data_management."""

from PyQt6 import QtWidgets as W

from mtg_core.catalog_workspace import CatalogWorkspace
from .card_browser import CardBrowser
from .data_management import DataManagementDialog
from .jobs import JobQueue
from .install_progress import human_bytes


class CardDatabaseWorkspace(DataManagementDialog):
    def __init__(self, parent=None, *, engine=None, jobs=None):
        super().__init__(parent, engine=engine, jobs=jobs)
        self.setWindowTitle("Card Database")
        self.resize(1180, 800)
        self.setSizeGripEnabled(True)
        outer = self.layout()
        maintenance = outer.takeAt(0).widget()
        controls = outer.takeAt(0).layout()
        self.tabs = W.QTabWidget()
        self.browser = CardBrowser(self.engine.service, self)
        self.browser.downloadRequested.connect(self.request_download)
        self.tabs.addTab(self.browser, "Browse Cards")
        artwork = W.QWidget()
        art = W.QVBoxLayout(artwork)
        title = W.QLabel("Artwork library")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        art.addWidget(title)
        note = W.QLabel(
            "Artwork covers the installed local catalog. Completing the library can require 100–200 GB and many hours. Valid cached and custom images are preserved."
        )
        note.setWordWrap(True)
        art.addWidget(note)
        self.missing.clicked.disconnect()
        self.missing.clicked.connect(self.download_missing)
        for button in (self.missing, self.usage, self.clear):
            art.addWidget(button)
        selected = W.QPushButton("Download selected artwork…")
        selected.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        art.addWidget(selected)
        full = W.QPushButton("Complete offline artwork…")
        full.clicked.connect(self.download_missing)
        art.addWidget(full)
        retry = W.QPushButton("Retry failed downloads…")
        retry.clicked.connect(self.download_missing)
        art.addWidget(retry)
        verify = W.QPushButton("Verify or repair artwork…")
        verify.clicked.connect(self.open_diagnostics)
        art.addWidget(verify)
        preferences = W.QPushButton("Artwork preferences…")
        preferences.clicked.connect(self.artwork_preferences)
        art.addWidget(preferences)
        art.addStretch()
        self.tabs.addTab(artwork, "Artwork")
        self.tabs.addTab(maintenance, "Maintenance")
        self._catalog_summary = "Installed local catalog"
        self._update_summary = ""
        self._artwork_summary = ""
        self.overview = W.QLabel(self._catalog_summary)
        self.overview.setWordWrap(True)
        outer.addWidget(self.overview)
        outer.addWidget(self.tabs, 1)
        # Progress remains visible while navigating any section.
        for widget in (
            self.install_progress,
            self.status,
            self.details_toggle,
            self.error_details,
        ):
            outer.addWidget(widget)
        outer.addLayout(controls)
        for label in maintenance.findChildren(W.QLabel):
            if label.text() == "Manage your card library":
                label.setText("Card data updates and storage")
            elif label.text().startswith("Card data and recommendations are the same"):
                label.setText(
                    "Manage installed datasets. Application updates are available separately in Settings."
                )
        self.check.setText("Check card data updates")
        self.options.setTitle("Storage and artwork mode")
        self.summary_id = None
        self.summary_jobs = JobQueue(self)
        self.summary_jobs.status.connect(self.summary_result)
        self.summary_id = self.summary_jobs.submit(
            lambda cancel, report: CatalogWorkspace(self.engine.service).overview(
                cancel
            ),
            quiet=True,
        )
        self.jobs.status.connect(self.activity)
        self._activity = W.QLabel()
        outer.insertWidget(1, self._activity)
        self.activity("", "", None)
        self.jobs.idle.connect(lambda: self.activity("", "", None))

    def refresh_header(self):
        version = self.engine.state.get("bulk_versions", {}).get("default_cards")
        self.overview.setText(
            " · ".join(
                filter(
                    None,
                    (
                        self._catalog_summary,
                        "Card data: " + version if version else "",
                        self._artwork_summary,
                        self._update_summary,
                    ),
                )
            )
        )

    def summary_result(self, job, state, value):
        if job == self.summary_id and state == "completed":
            self._catalog_summary = (
                f"{value[0]:,} unique cards · {value[1]:,} printings"
            )
            self.refresh_header()
        elif job == self.summary_id and state == "failed":
            self.overview.setText(
                "Catalog unavailable · open Maintenance for diagnostics"
            )

    def on_status(self, job_id, state, value):
        super().on_status(job_id, state, value)
        if job_id != self.job_id or state != "completed":
            return
        if self.operation == "plan":
            installed = self.engine.state.get("bulk_versions", {})
            versions = []
            changed = False
            for key, metadata in value.bulk.items():
                available = metadata.get("updated_at")
                if available:
                    changed = changed or installed.get(key) != available
                    versions.append(
                        f"{key.replace('_', ' ').title()}: installed {installed.get(key) or 'not installed'} → available {available}"
                    )
            if versions:
                self.versions.setText("Checked card datasets\n" + "\n".join(versions))
                self._update_summary = (
                    "Card dataset updates available"
                    if changed
                    else "Checked card datasets are current"
                )
        elif self.operation == "install":
            self._update_summary = ""
            self._artwork_summary = ""
            self.summary_id = self.summary_jobs.submit(
                lambda cancel, report: CatalogWorkspace(self.engine.service).overview(
                    cancel
                ),
                quiet=True,
            )
        elif self.operation in ("artwork", "artwork_selection"):
            self._artwork_summary = ""
        elif self.operation == "usage":
            self._artwork_summary = (
                f"{value['images']:,} artwork assets · {human_bytes(value['bytes'])}"
            )
        self.refresh_header()

    def activity(self, job, state, value):
        if (
            state == "completed"
            and job == self.job_id
            and self.operation in ("artwork", "artwork_selection", "install")
        ):
            self.browser.reload()
        self._activity.setText(
            "Database operation running · browse cards while work continues"
            if self.jobs.busy
            else ""
        )

    def request_download(self, scope, work):
        if self.jobs.busy:
            self.status.setText(
                "A database operation is running. Pause it or wait before starting another download."
            )
            return
        if (
            W.QMessageBox.question(
                self,
                "Download artwork",
                scope
                + "\n\nDownload missing or changed images? Size depends on the selection. Existing custom artwork is preserved.",
            )
            != W.QMessageBox.StandardButton.Yes
        ):
            return
        self.start_job("artwork_selection", work)

    def download_missing(self):
        self.request_download(
            "Scan every supported local printing, including all image-bearing faces. This can take many hours and substantial disk space.",
            lambda cancel, report: self.engine.run(
                cancel=cancel, report=report, artwork_only=True
            ),
        )

    def artwork_preferences(self):
        from .artwork_preferences import edit_artwork_preferences

        edit_artwork_preferences(self, self.engine.service)

    def start_install(self):
        if self.plan is not None and not self._retry_operation:
            if (
                W.QMessageBox.question(
                    self,
                    "Apply card data updates",
                    self.estimate.text() + "\n\nApply this dataset plan?",
                )
                != W.QMessageBox.StandardButton.Yes
            ):
                return
        super().start_install()

    def prepare_to_close(self):
        self.browser.timer.stop()
        self.browser.reads.cancel_all()
        self.summary_jobs.cancel_all()
        ready = not self.browser.reads.busy and not self.summary_jobs.busy
        if ready:
            self.hide()
        return ready

    def reject(self):
        # The launcher retains this workspace and the application owns the queue.
        # Closing the workspace is navigation, not cancellation.
        self.hide()

    def closeEvent(self, event):
        self.hide()
        event.ignore()
