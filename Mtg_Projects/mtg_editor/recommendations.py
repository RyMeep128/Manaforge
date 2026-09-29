"""Local recommendation browsing with inspectable statistics and explicit Add."""

from datetime import datetime
import uuid

from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckEntry
from mtg_core.categorization import apply_categories
from mtg_core.sections import DeckSection
from .organization import card_facts
from mtg_core.recommendation_scoring import context, score, settings


def load_recommendations(service, document, store, query="", *, sources=None):
    commanders = [
        e
        for e in document.deck.entries
        if e.entry_id in document.deck.commander_entry_ids
        or e.section == DeckSection.COMMANDER
    ]
    commander_ids = [e.oracle_id for e in commanders if e.oracle_id]
    from mtg_core.recommendation_sources import default_sources, recommend

    snapshot = recommend(
        default_sources(store) if sources is None else sources,
        commander_ids,
        exclude=[e.oracle_id for e in document.deck.entries],
        limit=2000,
        seeds=[
            e.oracle_id
            for e in document.deck.entries
            if e.oracle_id
            and e.quantity > 0
            and e.section == DeckSection.MAINBOARD
            and "Basic Land" not in (e.extras.get("facts", {}).get("type_line") or "")
        ],
    )
    color_identity = set()
    color_known = bool(commanders)
    for entry in commanders:
        payload = service.get_card(card_id=entry.card_id) if entry.card_id else None
        if payload is None or "color_identity" not in payload:
            color_known = False
        else:
            color_identity.update(payload["color_identity"])
    allowed = None
    if query.strip():
        matches = service.search_cards(
            query, dict(scryfall_syntax=True, allow_remote=False, limit=10000)
        )
        allowed = {row.oracle_id for row in matches}
    rows = []
    for row in snapshot["results"]:
        if allowed is not None and row["oracle_id"] not in allowed:
            continue
        payload = service.choose_preferred_print(row["oracle_id"])
        if not payload:
            continue
        if color_known and (
            "color_identity" not in payload
            or not set(payload["color_identity"]) <= color_identity
        ):
            continue
        entry = DeckEntry(
            str(uuid.uuid4()),
            payload["name"],
            card_id=payload["id"],
            oracle_id=row["oracle_id"],
            set_code=payload.get("set"),
            collector_number=payload.get("collector_number"),
            pre_cropped=True,
            extras={"facts": card_facts(payload)},
        )
        rows.append(dict(row, entry=entry))
        if len(rows) >= 200:
            break
    proposals = service.analyze_entries([row["entry"] for row in rows])
    for row in rows:
        row["roles"] = proposals.get(row["entry"].entry_id, [])
        row["statistical_score"] = row["score"]
    current_proposals = service.analyze_entries(document.deck.entries)
    records = {
        entry.card_id: service.get_card(card_id=entry.card_id) or {}
        for entry in document.deck.entries
        if entry.card_id
    }
    snapshot.update(
        results=rows,
        color_filtered=color_known,
        deck_context=context(document, current_proposals, records),
    )
    return snapshot


class RecommendationsDialog(W.QDialog):
    def __init__(self, snapshot, editor):
        super().__init__(editor)
        self.editor, self.rows = editor, list(snapshot["results"])
        self.preferences = settings(editor.document)
        self.deck_context = snapshot["deck_context"]
        self.all_rows = list(self.rows)
        self.setWindowTitle("Deck recommendations")
        self.resize(800, 640)
        layout = W.QVBoxLayout(self)
        latest = max((item["imported"] for item in snapshot["sources"]), default=None)
        stamp = (
            datetime.fromtimestamp(latest).isoformat(timespec="seconds")
            if latest
            else "never"
        )
        text = (
            f"{snapshot['source']} · {snapshot['decks']} decks · last import {stamp}\n"
            "Heuristics, not legality advice. Small samples can be misleading. "
            "Ranking up to 200 resolved cards from 2,000 statistical candidates; search matches are capped at 10,000.\n"
            + (
                "Commander color identity applied."
                if snapshot["color_filtered"]
                else "Commander color identity unavailable; no color restriction applied."
            )
        )
        text += "\n" + "\n".join(
            f"{item['source']}: {item['status']}" for item in snapshot["source_status"]
        )
        text += (
            f"\nRelevant local decks: {snapshot['local_relevant']} / 15 minimum; "
            f"local signal {'active' if snapshot['local_enabled'] else 'inactive'}."
        )
        label = W.QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        toggle = W.QPushButton("Adjust ranking weights")
        toggle.setCheckable(True)
        layout.addWidget(toggle)
        panel = W.QWidget()
        controls = W.QFormLayout(panel)
        panel.setVisible(False)
        toggle.toggled.connect(panel.setVisible)
        self.weights = {}
        for key, value in self.preferences["weights"].items():
            spin = W.QDoubleSpinBox()
            spin.setRange(0, 2)
            spin.setSingleStep(0.05)
            spin.setValue(value)
            controls.addRow(key.title() + " weight", spin)
            self.weights[key] = spin
        self.use_local = W.QCheckBox(
            "Use local supplement when at least 15 relevant decks are available"
        )
        self.use_local.setChecked(self.preferences["local_enabled"])
        controls.addRow(self.use_local)
        layout.addWidget(panel)
        self.filter = W.QLineEdit()
        self.filter.setPlaceholderText(
            "Filter loaded candidates by name, role, or theme"
        )
        layout.addWidget(self.filter)
        self.list = W.QListWidget()
        layout.addWidget(self.list, 1)
        self.details = W.QPlainTextEdit()
        self.details.setReadOnly(True)
        layout.addWidget(self.details, 1)
        buttons = W.QHBoxLayout()
        for label, callback in [
            ("Inspect / preview", self.inspect),
            ("Add to Deck", self.add),
            ("Dismiss card", self.dismiss),
            ("Restore dismissed", self.restore),
            ("Save preferences", self.save_preferences),
        ]:
            button = W.QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.notice = W.QLabel(
            "Archidekt is the primary dataset. Local imports supplement it only at 15 relevant decks; local data never replaces it."
        )
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.formula = snapshot["formula"]
        self.sources = "\n".join(item["source"] for item in snapshot["sources"])
        self.list.currentRowChanged.connect(self.selection)
        self.list.itemDoubleClicked.connect(lambda _: self.inspect())
        for spin in self.weights.values():
            spin.valueChanged.connect(self.refresh)
        self.use_local.toggled.connect(self.refresh)
        self.filter.textChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.preferences["weights"] = {
            key: spin.value() for key, spin in self.weights.items()
        }
        self.preferences["local_enabled"] = self.use_local.isChecked()
        query = self.filter.text().casefold().strip()
        rows = []
        for row in self.all_rows:
            if row["oracle_id"] in self.preferences["dismissed"]:
                continue
            text = (
                row["entry"].name
                + " "
                + " ".join(item["name"] for item in row["roles"])
            )
            if query not in text.casefold():
                continue
            raw = dict(
                row,
                statistical_score=row["score"]
                if self.use_local.isChecked()
                else row["primary_score"],
            )
            rows.append(score(raw, self.deck_context, self.preferences["weights"]))
        self.rows = sorted(rows, key=lambda row: (-row["score"], row["oracle_id"]))
        self.list.clear()
        self.list.addItems(
            [f"{row['entry'].name} — {row['score']:.3f}" for row in self.rows]
        )
        if self.rows:
            self.list.setCurrentRow(0)
        else:
            self.details.setPlainText(
                "No candidates match the filter or dismissal preferences. Clear the filter or restore dismissed cards."
                if self.all_rows
                else "No resolved public candidates are available for this deck/search. Check the primary source status and local card catalog."
            )

    def selected(self):
        index = self.list.currentRow()
        return self.rows[index] if 0 <= index < len(self.rows) else None

    def selection(self, _index):
        row = self.selected()
        if row:
            self.details.setPlainText(
                f"Commander inclusion: {row['inclusion']:.1%} ({row['sample']} decks; commander {row['commander'] or 'none'})\n"
                f"Baseline popularity: {row['baseline']:.1%}\nSynergy difference: {row['synergy']:+.1%}\n"
                f"Available statistical formula: {self.formula}\nPublic component: {row['primary_score']:.3f}; local component: {row['local_score']:.3f}\n"
                + f"Local blend used: {bool(row['local_enabled'] and self.use_local.isChecked())}\n"
                + "\nRoles / themes:\n"
                + "\n".join(
                    f"{item['name']}: {item['reason']}" for item in row["roles"]
                )
                + "\n\nCached sources (no automatic refresh):\n"
                + self.sources
                + "\n\nWeighted score components:\n"
                + "\n".join(
                    f"{key}: {value:+.3f}"
                    for key, value in row["contributions"].items()
                )
                + "\n\n"
                + "\n".join(row["context_reasons"])
            )

    def inspect(self):
        row = self.selected()
        if row:
            from .card_details import CardDetails

            CardDetails(self.editor.service, row["entry"], self).exec()

    def add(self):
        row = self.selected()
        if row is None:
            return
        entry = row["entry"]

        def apply(document):
            entry.sort_order = (
                max((e.sort_order for e in document.deck.entries), default=-1) + 1
            )
            document.deck.entries.append(entry)
            apply_categories(document, {entry.entry_id: row["roles"]})

        self.editor.edit(apply)
        self.all_rows = [
            item for item in self.all_rows if item["oracle_id"] != row["oracle_id"]
        ]
        self.notice.setText(
            f"Added {entry.name}. Undo is available. Reopen to update deck-context scores."
        )
        self.refresh()

    def save_preferences(self):
        from copy import deepcopy

        saved = deepcopy(self.preferences)
        self.editor.edit(
            lambda document: document.editor_preferences.update(recommendations=saved)
        )
        self.notice.setText(
            "Recommendation preferences saved with the deck. Undo is available."
        )

    def dismiss(self):
        row = self.selected()
        if row:
            self.preferences["dismissed"].append(row["oracle_id"])
            self.save_preferences()
            self.refresh()

    def restore(self):
        self.preferences["dismissed"].clear()
        self.save_preferences()
        self.refresh()
