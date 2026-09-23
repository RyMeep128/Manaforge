"""Review all category memberships without touching global Oracle tags."""
from PyQt6 import QtCore as C, QtWidgets as W


class RoleEditor(W.QDialog):
    def __init__(self, document, entry_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edit roles/categories')
        entries = [e for e in document.deck.entries if e.entry_id in entry_ids]
        layout = W.QVBoxLayout(self)
        note = W.QLabel(
            f'{len(entries)} selected. Checked: assign to all; unchecked: remove from all; '
            'partially checked: keep each card\'s current assignment.\n'
            'The current primary stays first if kept; removing it promotes the next category. '
            'Changed cards become manual and are protected from Auto Categorize.\n'
            'User tags are separate (Edit user tags); global Oracle tags and card types stay unchanged.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.listing = W.QListWidget()
        self.items = {}
        self.initial = {}
        for category in sorted(document.deck.categories, key=lambda c: (c.sort_order, c.name.casefold())):
            count = sum(category.category_id in e.category_ids for e in entries)
            item = W.QListWidgetItem(f'{category.name} ({count}/{len(entries)})')
            item.setFlags(item.flags() | C.Qt.ItemFlag.ItemIsUserCheckable)
            if len(entries) > 1:
                item.setFlags(item.flags() | C.Qt.ItemFlag.ItemIsUserTristate)
            state = (C.Qt.CheckState.Unchecked if not count else
                     C.Qt.CheckState.Checked if count == len(entries) else C.Qt.CheckState.PartiallyChecked)
            item.setCheckState(state)
            self.listing.addItem(item)
            self.items[category.category_id] = item
            self.initial[category.category_id] = state
        layout.addWidget(self.listing)
        if not self.items:
            layout.addWidget(W.QLabel('No categories yet. Add one with Manage categories or Auto Categorize.'))
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok |
                                    W.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 460)

    def choices(self):
        return {cid: item.checkState() == C.Qt.CheckState.Checked
                for cid, item in self.items.items()
                if item.checkState() != self.initial[cid]
                and item.checkState() != C.Qt.CheckState.PartiallyChecked}
