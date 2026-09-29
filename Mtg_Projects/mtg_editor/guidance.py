"""Deck-local, reversible guidance settings and explainable suggestions."""

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.guidance import GuidanceSettings, guidance


class GuidanceDialog(W.QDialog):
    def __init__(self, document, proposals, parent=None):
        super().__init__(parent)
        self.document, self.proposals = document, proposals
        self.settings = GuidanceSettings.from_document(document)
        self.setWindowTitle("Deck guidance")
        self.resize(720, 650)
        layout = W.QVBoxLayout(self)
        note = W.QLabel(
            "Heuristics for mainboard + commanders, including owned cards. "
            "Manual roles override local tag/text inference. Targets are editable "
            "starting points, not format rules. Saved changes support Undo/Redo."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = W.QFormLayout()
        self.targets = {}
        for key, value in self.settings.targets.items():
            spin = W.QSpinBox()
            spin.setRange(0, 1000)
            spin.setValue(value)
            self.targets[key] = spin
            form.addRow(f"{key.title()} target (0 disables)", spin)
        self.theme_minimum = W.QSpinBox()
        self.theme_minimum.setRange(1, 1000)
        self.theme_minimum.setValue(self.settings.theme_minimum)
        form.addRow("Theme minimum distinct cards", self.theme_minimum)
        layout.addLayout(form)
        self.summary = W.QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.suggestions = W.QListWidget()
        self.suggestions.setWordWrap(True)
        layout.addWidget(self.suggestions, 1)
        self.evidence = W.QPlainTextEdit()
        self.evidence.setReadOnly(True)
        layout.addWidget(self.evidence, 1)
        actions = W.QHBoxLayout()
        dismiss = W.QPushButton("Dismiss selected")
        dismiss.clicked.connect(self.dismiss)
        restore = W.QPushButton("Restore dismissed suggestions")
        restore.clicked.connect(self.restore)
        actions.addWidget(dismiss)
        actions.addWidget(restore)
        layout.addLayout(actions)
        buttons = W.QDialogButtonBox(
            W.QDialogButtonBox.StandardButton.Save
            | W.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for spin in [*self.targets.values(), self.theme_minimum]:
            spin.valueChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.settings.targets = {
            key: spin.value() for key, spin in self.targets.items()
        }
        self.settings.theme_minimum = self.theme_minimum.value()
        result = guidance(self.document, self.proposals, self.settings)
        self.summary.setText(
            f"{result['total']} copies in scope. "
            + " · ".join(f"{key}: {value}" for key, value in result["counts"].items())
            + f"\n{result['unknown']} copies have no local classification data; missing tags can also undercount roles."
        )
        self.suggestions.clear()
        for suggestion in result["suggestions"]:
            item = W.QListWidgetItem(suggestion["title"] + "\n" + suggestion["reason"])
            item.setData(C.Qt.ItemDataRole.UserRole, suggestion["id"])
            self.suggestions.addItem(item)
        self.evidence.setPlainText(
            "\n\n".join(
                key.title()
                + "\n"
                + (
                    "\n".join(
                        f"{row['quantity']}× {row['name']}: "
                        + "; ".join(row["reasons"])
                        for row in rows
                    )
                    or "No matching copies"
                )
                for key, rows in result["evidence"].items()
            )
        )

    def dismiss(self):
        item = self.suggestions.currentItem()
        if item is not None:
            self.settings.dismissed.append(item.data(C.Qt.ItemDataRole.UserRole))
            self.refresh()

    def restore(self):
        self.settings.dismissed.clear()
        self.refresh()
