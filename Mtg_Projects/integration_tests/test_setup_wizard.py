import time

from PyQt6 import QtWidgets as W
import pytest

from mtg_core.datasets import InstallationState
from mtg_core.installation import InstallPlan
from mtg_ui.data_management import DataManagementDialog
from mtg_ui.jobs import JobQueue


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


class Engine:
    def __init__(self, path):
        self.state = InstallationState(path / "state.sqlite3")
        self.path = path
        self.configured = []

    def has_catalog(self):
        return False

    def configure(self, location, mode):
        self.configured.append((location, mode))
        self.state.set("artwork_mode", mode)

    def plan(self, **kwargs):
        return InstallPlan({}, {}, 1024, 2048, 0)

    def run(self, *, cancel, report, plan, setup):
        report(
            dict(
                operation="Preparing fixture data",
                phase="initializing",
                current=1,
                total=1,
            )
        )
        self.state.set("setup_complete", True)
        return {}


def drain(app, jobs):
    deadline = time.monotonic() + 5
    while jobs.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    app.processEvents()
    assert not jobs.busy


def test_first_run_requires_success_and_saves_only_when_installing(app, tmp_path):
    engine = Engine(tmp_path)
    dialog = DataManagementDialog(engine=engine, setup=True)
    dialog.location.setText(str(tmp_path))
    assert dialog.mode.currentData() == "on_demand"
    assert not dialog.start.isEnabled()
    dialog.check_updates()
    drain(app, dialog.jobs)
    assert not engine.configured  # Checking sizes does not silently change mode.
    assert dialog.start.isEnabled()
    assert not engine.state.get("setup_complete", False)
    dialog.start_install()
    drain(app, dialog.jobs)
    assert engine.configured == [(str(tmp_path), "on_demand")]
    assert engine.state.get("setup_complete") is True
    assert "Finish" in dialog.close_button.text()
    dialog.finish_or_close()
    assert dialog.result() == W.QDialog.DialogCode.Accepted


def test_failed_setup_can_retry_without_claiming_completion(app, tmp_path, monkeypatch):
    reports = []
    # The error prompt requires a person; capture its request without opening a
    # modal dialog inside the job queue's completion callback.
    monkeypatch.setattr(
        "mtg_ui.feedback.report_problem",
        lambda parent, operation, detail: reports.append((parent, operation, detail)),
    )
    engine = Engine(tmp_path)

    def fail(**kwargs):
        raise OSError("Connection unavailable")

    engine.run = fail
    dialog = DataManagementDialog(engine=engine, setup=True)
    dialog.location.setText(str(tmp_path))
    dialog.check_updates()
    drain(app, dialog.jobs)
    dialog.start_install()
    drain(app, dialog.jobs)
    assert not engine.state.get("setup_complete", False)
    assert "Connection unavailable" in dialog.error_details.toPlainText()
    assert dialog.start.isEnabled()
    assert not reports  # Diagnostics stay collapsed instead of interrupting progress.
    assert dialog.start.text() == "Retry"
    assert dialog.install_progress.task.state == "failed"
    dialog.reject()


def test_closing_settings_does_not_cancel_an_existing_background_job(app, tmp_path):
    import threading

    stop = threading.Event()
    jobs = JobQueue()
    job_id = jobs.submit(lambda cancel, report: stop.wait(5))
    app.processEvents()
    dialog = DataManagementDialog(engine=Engine(tmp_path), jobs=jobs)
    assert dialog.job_id == job_id
    assert dialog.pause.isEnabled()
    dialog.reject()
    assert jobs.busy
    stop.set()
    drain(app, jobs)


def test_large_cached_scans_throttle_gui_progress_but_keep_completion(app):
    jobs = JobQueue()
    seen = []
    jobs.progress.connect(lambda job_id, value: seen.append(value))

    def scan(cancel, report):
        for current in range(10001):
            report(
                dict(operation="Artwork", phase="artwork", current=current, total=10000)
            )

    jobs.submit(scan)
    drain(app, jobs)
    assert seen[-1]["current"] == 10000
    assert len(seen) < 10000


def test_progress_animation_can_outlive_dialog_reference_without_access_violation(app):
    from PyQt6 import sip
    from mtg_ui.install_progress import ProgressCard

    parent = W.QWidget()
    card = ProgressCard("Installing", parent)
    card.update_progress(key="download", title="Downloading", current=1, total=2)
    animation = card.animation
    animation.setCurrentTime(100)
    assert 0 < card.bar.value() <= 500
    sip.delete(parent)
    assert sip.isdeleted(animation)
    app.processEvents()  # Pending animation events must not call deleted widgets.


def test_diagnostics_opens_without_loading_card_or_recommendation_service(
    app, tmp_path
):
    from mtg_ui.diagnostics import DiagnosticsDialog

    engine = Engine(tmp_path)
    # A broken catalog must be inspected read-only, not passed to CardService.
    catalog = tmp_path / "broken.sqlite3"
    catalog.write_bytes(b"broken")
    engine.state.set("catalog_path", str(catalog))
    dialog = DiagnosticsDialog(engine=engine)
    app.processEvents()
    drain(app, dialog.jobs)
    assert any(r.status == "Error" for r in dialog.results)
    assert "Manaforge diagnostic report" in dialog.report()
    assert catalog.read_bytes() == b"broken"
    dialog.reject()


def test_first_run_automatically_checks_local_installation(app, tmp_path):
    dialog = DataManagementDialog(engine=Engine(tmp_path), setup=True)
    app.processEvents()
    drain(app, dialog.jobs)
    assert "Initial installation health" in dialog.error_details.toPlainText()
    assert "Not Checked" in dialog.error_details.toPlainText()
    assert dialog.plan is not None  # Automatically proceeds to size lookup.
    assert dialog.start.isEnabled()
    assert "choose Install" in dialog.status.text()
    assert dialog.install_progress.task.state == "completed"
    assert dialog.install_progress.overall.isHidden()
    assert not dialog.details_toggle.isChecked()
    assert not dialog.engine.configured  # Size lookup never starts installation.
    assert not dialog.engine.state.get("setup_complete", False)
    dialog.reject()


def test_progress_does_not_claim_completion_for_full_transfer_or_verification(app):
    from mtg_ui.install_progress import InstallationProgress

    progress = InstallationProgress()
    progress.consume(
        dict(operation="Cards", phase="downloading", current=100, total=100)
    )
    assert progress.task.measure.text() == "99%"
    assert progress.task.target < 1000
    progress.consume(dict(operation="Cards", phase="verifying", current=100, total=100))
    assert progress.task.bar.maximum() == 0
    assert progress.task.measure.text() == "In progress"
    progress.finish("paused")
    assert progress.task.measure.text() == "Paused"
    assert progress.task.bar.maximum() != 0


def test_unknown_transfer_size_has_no_percentage_or_eta(app):
    from mtg_ui.install_progress import InstallationProgress

    progress = InstallationProgress()
    progress.consume(
        dict(
            operation="Artwork",
            phase="downloading",
            current=1024,
            total=None,
            speed=512,
            remaining=None,
        )
    )
    assert progress.task.bar.maximum() == 0
    assert "total size unavailable" in progress.task.detail.text()
    assert "Estimated remaining" not in progress.task.detail.text()
    assert "/s" in progress.task.detail.text()
