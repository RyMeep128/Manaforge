"""Reusable, truthful progress cards for setup and dataset updates."""

import math
from PyQt6 import QtCore as C, QtWidgets as W
from .theme import COLORS


def human_bytes(value):
    if value is None:
        return "Size unavailable"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024


def duration(seconds):
    seconds = max(0, math.ceil(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return (
        f"{hours}h {minutes}m"
        if hours
        else f"{minutes}m {seconds}s"
        if minutes
        else f"{seconds}s"
    )


class ProgressCard(W.QFrame):
    def __init__(self, title, parent=None, *, overall=False):
        super().__init__(parent)
        self.overall = overall
        self.key, self.target = None, 0
        self.previous_current = None
        self.setProperty("role", "panel")
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        header = W.QHBoxLayout()
        self.title = W.QLabel(title)
        self.title.setTextFormat(C.Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-weight: 600;")
        self.measure = W.QLabel("Not started")
        self.measure.setAlignment(C.Qt.AlignmentFlag.AlignRight)
        header.addWidget(self.title, 1)
        header.addWidget(self.measure)
        layout.addLayout(header)
        self.bar = W.QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(12 if overall else 8)
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        layout.addWidget(self.bar)
        self.detail = W.QLabel("")
        self.detail.setTextFormat(C.Qt.TextFormat.PlainText)
        self.detail.setWordWrap(True)
        self.detail.setProperty("role", "subtitle")
        layout.addWidget(self.detail)
        self.animation = C.QVariantAnimation(self)
        self.animation.setDuration(240)
        self.animation.setEasingCurve(C.QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._set_bar_value)
        self.set_state("pending")

    @C.pyqtSlot("QVariant")
    def _set_bar_value(self, value):
        # A QObject receiver disconnects before its child widgets are destroyed.
        # A lambda has no receiver lifetime and can access an already deleted bar.
        self.bar.setValue(int(value))

    def hideEvent(self, event):
        self.animation.stop()
        super().hideEvent(event)

    def set_state(self, state):
        self.state = state
        color = (
            COLORS["danger"]
            if state == "failed"
            else COLORS["warning"]
            if state == "paused"
            else COLORS["accent"]
        )
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {COLORS['border']}; border: 0; border-radius: 4px; }} "
            f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
        )
        if state in ("paused", "failed"):
            self.animation.stop()
            if self.bar.maximum() == 0:
                self.bar.setRange(0, 1000)
                self.bar.setValue(0)
            self.measure.setText(state.title())

    def update_progress(
        self,
        *,
        key,
        title,
        current=None,
        total=None,
        state="running",
        detail="",
        steps=False,
    ):
        changed = key != self.key
        self.title.setText(title)
        self.detail.setText(detail)
        self.set_state(state)
        if state in ("paused", "failed"):
            if changed and total and current is not None:
                self.key = key
                self.bar.setRange(0, 1000)
                self.target = min(990, max(0, int(current / total * 1000)))
                self.bar.setValue(self.target)
            return
        if (
            not changed
            and current is not None
            and self.previous_current is not None
            and current < self.previous_current
        ):
            changed = True
            self.detail.setText(
                "Transfer restarted; completed files are retained. " + detail
            )
        self.previous_current = current
        if changed:
            self.animation.stop()
            self.key, self.target = key, 0
        known = isinstance(total, (int, float)) and total > 0 and current is not None
        if state == "completed":
            fraction = 1
        elif known:
            fraction = min(0.999, max(0, current / total))
        else:
            self.animation.stop()
            self.bar.setRange(0, 0)
            self.measure.setText("In progress")
            return
        if self.bar.maximum() == 0 or changed:
            self.bar.setRange(0, 1000)
            self.bar.setValue(0)
        value = 1000 if state == "completed" else min(990, int(fraction * 1000))
        self.target = max(self.target, value)
        self.animation.stop()
        self.animation.setStartValue(self.bar.value())
        self.animation.setEndValue(self.target)
        self.animation.start()
        self.measure.setText(
            f"{int(current or 0)} of {total} stages complete"
            if steps
            else "Complete"
            if state == "completed"
            else f"{min(99, int(fraction * 100))}%"
        )


class InstallationProgress(W.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.overall = ProgressCard("Overall setup progress", self, overall=True)
        self.task = ProgressCard("Current operation", self)
        self.stages = W.QLabel()
        self.stages.setTextFormat(C.Qt.TextFormat.PlainText)
        self.stages.setWordWrap(True)
        layout.addWidget(self.overall)
        layout.addWidget(self.stages)
        layout.addWidget(self.task)
        self.last = {}

    def reset(self, title="Overall setup progress"):
        self.last = {}
        self.overall.key = self.task.key = None
        self.stages.clear()
        self.overall.show()
        self.overall.update_progress(key="overall", title=title)
        self.task.update_progress(key="waiting", title="Preparing operation")

    def consume(self, value):
        self.last = value
        stages = value.get("stages", [])
        if stages:
            done = sum(item["state"] == "completed" for item in stages)
            complete = done == len(stages)
            state = value.get("task_state", "running")
            self.overall.show()
            self.overall.update_progress(
                key=("overall", value.get("plan_key")),
                title=self.overall.title.text(),
                current=done,
                total=len(stages),
                state="completed"
                if complete
                else state
                if state in ("paused", "failed")
                else "running",
                steps=True,
                detail="Stages reflect completed work; stage durations vary.",
            )
            labels = {
                "pending": "Pending",
                "running": "Running",
                "completed": "Complete",
                "paused": "Paused",
                "failed": "Failed",
            }
            self.stages.setText(
                "\n".join(
                    f"{i + 1}. {item['title']}  -  {labels[item['state']]}"
                    for i, item in enumerate(stages)
                )
            )
        else:
            self.overall.hide()
        phase = value.get("phase", "checking")
        title = value.get("operation", "Working")
        phase_name = {
            "initializing": "Validating and indexing",
            "artwork": "Checking artwork",
            "verifying": "Verifying integrity",
            "extracting": "Extracting",
            "downloading": "Downloading",
        }.get(phase, phase.title())
        current, total = value.get("current"), value.get("total")
        detail = []
        unit = value.get("unit") or (
            "bytes" if phase in ("downloading", "extracting") else "records"
        )
        # Download verification reports bytes received, not bytes verified.
        if phase == "verifying" and not value.get("verification_measured"):
            current, total = None, None
        if current is not None and unit == "bytes":
            detail.append(
                human_bytes(current)
                + (
                    " / " + human_bytes(total)
                    if total is not None
                    else " received; total size unavailable"
                )
            )
        elif current is not None and (current or total):
            detail.append(
                f"{current:,}" + (f" / {total:,}" if total else "") + f" {unit}"
            )
        if phase == "downloading" and value.get("speed", 0) > 0:
            detail.append(human_bytes(value["speed"]) + "/s")
            if value.get("remaining") is not None:
                detail.append("Estimated remaining: " + duration(value["remaining"]))
        if value.get("files_total") is not None:
            detail.append(
                f"{value.get('files_completed', 0):,} / {value['files_total']:,} cards checked"
            )
        if not detail:
            detail.append("Working; progress cannot be measured for this operation.")
        state = value.get(
            "task_state", "completed" if phase == "completed" else "running"
        )
        self.task.update_progress(
            key=(value.get("stage"), title, phase, value.get("task_id")),
            title=title + " - " + phase_name,
            current=current,
            total=total,
            state=state,
            detail="  |  ".join(detail),
        )

    def finish(self, state):
        self.overall.setVisible(bool(self.last.get("stages")))
        if state == "completed":
            self.overall.update_progress(
                key=self.overall.key,
                title=self.overall.title.text(),
                state=state,
                detail="All operations completed successfully.",
            )
            self.task.update_progress(
                key="finished", title="Operation complete", state=state
            )
        else:
            self.overall.set_state(state)
            self.task.set_state(state)
