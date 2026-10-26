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


def test_failed_setup_can_retry_without_claiming_completion(app, tmp_path):
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
    assert "Connection unavailable" in dialog.status.text()
    assert dialog.start.isEnabled()
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
