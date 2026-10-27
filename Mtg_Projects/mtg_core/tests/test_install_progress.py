from mtg_core.install_progress import InstallProgress
from mtg_core.installation import InstallPlan


class State:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value

    def get(self, key, default=None):
        return self.values.get(key, default)


def test_stage_completion_is_explicit_and_pause_is_persisted():
    state, events = State(), []
    progress = InstallProgress(state, events.append)
    progress.begin("checks")
    progress(dict(operation="Metadata", phase="verifying", current=100, total=100))
    assert not any(s["state"] == "completed" for s in events[-1]["stages"])
    progress.complete()
    progress.begin("cards")
    progress.stop("paused")
    saved = state.get("installation_progress")
    assert saved["task_state"] == "paused"
    assert saved["stages"][0]["state"] == "completed"
    assert saved["stages"][1]["state"] == "paused"
    assert "on demand" in next(s for s in saved['stages'] if s['id'] == 'artwork')['title']


def test_resume_preserves_stages_only_for_same_dataset_plan():
    state = State()
    plan = InstallPlan({}, {}, 0, 0, 0)
    progress = InstallProgress(state, lambda value: None)
    progress.begin("checks")
    progress.configure_plan(plan)
    progress.complete()
    progress.begin("cards")
    progress.complete()
    progress.begin("recommendations")
    progress.stop("paused")
    resumed = InstallProgress(state, lambda value: None)
    resumed.begin("checks")
    resumed.configure_plan(plan)
    assert resumed.statuses["cards"] == "completed"
    resumed.configure_plan(InstallPlan({"cards": {"updated_at": "new"}}, {}, 0, 0, 0))
    assert resumed.statuses["cards"] == "pending"


def test_offline_artwork_is_an_explicit_stage_and_failures_are_persisted():
    state, events = State(), []
    progress = InstallProgress(state, events.append, offline=True)
    progress.begin("artwork")
    progress.stop("failed")
    stage = next(s for s in state.get('installation_progress')['stages'] if s['id'] == 'artwork')
    assert stage['state'] == 'failed'
    assert "offline" in stage['title']
