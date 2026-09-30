"""Discovery selection through the editor's existing single history command."""

from copy import deepcopy
import uuid

from PyQt6 import QtWidgets as W
from mtg_core.categorization import apply_categories
from mtg_core.commander import compatible, eligible, set_commanders
from mtg_core.sections import DeckSection


def commanders(document):
    return [e for e in document.deck.entries
            if e.section == DeckSection.COMMANDER or e.entry_id in document.deck.commander_entry_ids]


def apply_selection(document, candidate, *, second=False, change_format=False):
    """Move one copy, preserving existing artwork, categories and other copies."""
    current = commanders(document)
    existing = next((e for e in document.deck.entries
                     if (candidate.oracle_id and e.oracle_id == candidate.oracle_id)
                     or (candidate.card_id and e.card_id == candidate.card_id)), None)
    if existing is not None:
        entry = existing
        if entry.quantity > 1:
            entry = deepcopy(existing)
            entry.entry_id = str(uuid.uuid4())
            entry.quantity = 1
            entry.owned = min(1, existing.owned)
            existing.quantity -= 1
            existing.owned = max(0, existing.owned - entry.owned)
            document.deck.entries.append(entry)
        else:
            entry.quantity = 1
    else:
        entry = deepcopy(candidate)
        entry.entry_id = str(uuid.uuid4())
        entry.quantity = 1
        entry.sort_order = max((e.sort_order for e in document.deck.entries), default=-1) + 1
        document.deck.entries.append(entry)
        apply_categories(document, {entry.entry_id: entry.extras.pop("category_suggestion", [])})
    ids = [e.entry_id for e in current] if second else []
    set_commanders(document, [*ids, entry.entry_id])
    document.deck.extras["commander_colors"] = {
        key: value for key, value in document.deck.extras.get("commander_colors", {}).items()
        if key in document.deck.commander_entry_ids}
    if document.deck.extras.get("companion_entry_id") == entry.entry_id:
        document.deck.extras.pop("companion_entry_id", None)
    if change_format:
        document.deck.format = "Commander"


def select_commander(editor, candidate, *, second=False):
    """Resolve rules off-thread, explicitly confirm replacement, then edit once."""
    candidate = deepcopy(candidate)
    document = editor.document
    snapshot = document.to_dict()
    current = commanders(document)
    if any((e.oracle_id and e.oracle_id == candidate.oracle_id)
           or (e.card_id and e.card_id == candidate.card_id) for e in current):
        editor.statusBar().showMessage(f"{candidate.name} is already a commander.", 5000)
        return
    if second and len(current) != 1:
        W.QMessageBox.information(editor, "Second commander", "Choose one commander first, then select a compatible partner or Background.")
        return

    def resolve():
        payload = editor.service.get_card(card_id=candidate.card_id) or {}
        partner = (editor.service.get_card(card_id=current[0].card_id) or {}) if second else None
        proposals = editor.service.analyze_entries([candidate])
        return payload, partner, proposals.get(candidate.entry_id, [])

    def resolved(data):
        if editor.document is not document or document.to_dict() != snapshot:
            editor.statusBar().showMessage("Deck changed; select the commander again.", 5000)
            return
        payload, partner, proposals = data
        candidate.extras["category_suggestion"] = proposals
        valid = compatible(partner, payload) if second else eligible(payload)
        if valid is not True:
            W.QMessageBox.information(editor, "Commander selection",
                "Local rules cannot establish this pairing." if second else
                "This card cannot be established as a standalone commander. Backgrounds need a compatible commander.")
            return
        if (payload.get("legalities") or {}).get("commander") != "legal":
            if W.QMessageBox.question(editor, "Review local legality",
                    "This card is not marked legal in the local Commander data. Use it under house rules?",
                    W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No,
                    W.QMessageBox.StandardButton.No) != W.QMessageBox.StandardButton.Yes:
                return
        if current and not second:
            if W.QMessageBox.question(editor, "Replace commander?",
                    f"Set {candidate.name} as commander?\nThe current commander(s), "
                    + ", ".join(e.name for e in current) + ", will move to the mainboard.",
                    W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No,
                    W.QMessageBox.StandardButton.No) != W.QMessageBox.StandardButton.Yes:
                return
        change_format = document.deck.format not in ("Commander", "Custom")
        if change_format and W.QMessageBox.question(editor, "Change deck format?",
                "Change this deck's format to Commander and apply this selection?",
                W.QMessageBox.StandardButton.Yes | W.QMessageBox.StandardButton.No,
                W.QMessageBox.StandardButton.No) != W.QMessageBox.StandardButton.Yes:
            return
        # Confirmation runs a nested event loop; never apply to a replaced deck.
        if editor.document is not document or document.to_dict() != snapshot:
            return
        editor.edit(lambda d: apply_selection(d, candidate, second=second, change_format=change_format))
        editor.sync_fields()
        editor.statusBar().showMessage(f"Set {candidate.name} as commander. Undo is available.", 5000)

    editor.run_task(resolve, resolved)
