"""Explicit installation stages; no synthetic time or byte weighting."""

import time
import hashlib
import json


class InstallProgress:
    def __init__(self, state, report, *, offline=False, artwork_only=False, reference=True):
        self.state, self.report = state, report
        self.stages = (
            [("artwork", "Download and verify artwork")]
            if artwork_only
            else [
                ("checks", "Check storage and requirements"),
                ("cards", "Prepare card data and rulings"),
                ("reference", "Prepare Oracle Tags and comprehensive rules"),
                ("recommendations", "Prepare recommendation data"),
                (
                    "artwork",
                    "Download offline artwork"
                    if offline
                    else "Prepare artwork on demand",
                ),
                ("finalize", "Verify datasets and finalize setup"),
            ]
        )
        if not reference:
            self.stages = [stage for stage in self.stages if stage[0] != 'reference']
        self.statuses = {key: "pending" for key, _ in self.stages}
        self.previous = state.get("installation_progress", {})
        previous_stages = self.previous.get("stages", [])
        self.resuming = bool(previous_stages) and any(
            item["state"] != "completed" for item in previous_stages
        )
        self.plan_key = self.previous.get("plan_key") if self.resuming else None
        if (
            self.resuming
            and [(s["id"], s["title"]) for s in previous_stages] == self.stages
        ):
            self.statuses.update(
                {
                    s["id"]: "completed"
                    for s in previous_stages
                    if s["state"] == "completed"
                }
            )
        self.active = self.stages[0][0]
        self.last = {}
        self.saved_at = 0

    def begin(self, key):
        self.active = key
        if self.statuses[key] != "completed":
            self.statuses[key] = "running"
        self(
            dict(
                operation=dict(self.stages)[key],
                phase="checking",
                current=0,
                total=None,
            )
        )

    def configure_plan(self, plan):
        identity = json.dumps(
            dict(
                bulk=plan.bulk, recommendations=plan.recommendations, stages=self.stages
            ),
            sort_keys=True,
        )
        key = hashlib.sha256(identity.encode()).hexdigest()
        if self.plan_key != key:
            self.statuses = {stage: "pending" for stage, _ in self.stages}
            self.statuses[self.active] = "running"
        self.plan_key = key

    def complete(self):
        self.statuses[self.active] = "completed"
        self(dict(self.last, task_state="completed"))

    def stop(self, state):
        self.statuses[self.active] = state
        self(dict(self.last, task_state=state))

    def __call__(self, value):
        value = dict(value)
        # Older reporters supplied hard-coded six-step percentages. Stages own this now.
        value.pop("step", None)
        value.pop("steps", None)
        value.update(
            plan_key=self.plan_key,
            stage=self.active,
            stages=[
                dict(id=key, title=title, state=self.statuses[key])
                for key, title in self.stages
            ],
        )
        self.last = value
        now = time.monotonic()
        if now - self.saved_at >= 1 or value.get("task_state") in (
            "completed",
            "paused",
            "failed",
        ):
            self.state.set("installation_progress", dict(value, saved_at=time.time()))
            self.saved_at = now
        self.report(value)
