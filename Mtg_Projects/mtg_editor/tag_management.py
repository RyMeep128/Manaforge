"""Shared lightweight picker and deck-local organization management."""
from copy import deepcopy
from PyQt6 import QtCore as C, QtWidgets as W

from .tag_model import (choices, preferences, hold_delay, apply_choice,
                        rename_choice, delete_choice, STARTERS)


class TagPicker(W.QDialog):
    def __init__(self, document, ids=(), parent=None, *, tags=False):
        super().__init__(parent)
        self.document, self.ids = document, set(ids)
        self.setWindowTitle('Add Tag')
        self.resize(420, 390)
        layout = W.QVBoxLayout(self)
        self.mode = W.QComboBox()
        self.mode.addItems(['Primary Role', 'Additional Tag'])
        self.mode.setCurrentIndex(int(tags))
        layout.addWidget(self.mode)
        self.search = W.QLineEdit()
        self.search.setPlaceholderText('Search existing choices or enter a new name')
        layout.addWidget(self.search)
        self.listing = W.QListWidget()
        layout.addWidget(self.listing, 1)
        self.assign = W.QCheckBox(f'Assign to {len(self.ids)} selected cards')
        self.assign.setChecked(bool(self.ids))
        self.assign.setEnabled(bool(self.ids))
        layout.addWidget(self.assign)
        self.clear_role = False
        self.clear_button = W.QPushButton('Clear Primary Role')
        self.clear_button.clicked.connect(self.clear_primary)
        layout.addWidget(self.clear_button)
        self.starter = W.QCheckBox('Offer in the empty-deck palette')
        layout.addWidget(self.starter)
        self.note = W.QLabel('Primary Role controls grouping. Additional Tags keep the current role.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Apply | W.QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(W.QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.manage_requested = False
        manage = W.QPushButton('Manage Tags / Customize Quick Menu…')
        manage.clicked.connect(self.manage)
        layout.addWidget(manage)
        self.mode.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.listing.itemClicked.connect(lambda item: self.search.setText(item.data(C.Qt.ItemDataRole.UserRole)))
        self.listing.itemDoubleClicked.connect(lambda item: self.accept())
        self.refresh()

    def refresh(self):
        query = self.search.text().strip().casefold()
        self.listing.clear()
        self.clear_button.setVisible(bool(self.ids) and not self.mode.currentIndex())
        self.starter.setVisible(not self.document.deck.entries and not self.mode.currentIndex())
        for choice in choices(self.document, bool(self.mode.currentIndex()), active=False):
            if query in choice.name.casefold():
                item = W.QListWidgetItem(f'{choice.name}   ·   {choice.count} cards')
                item.setData(C.Qt.ItemDataRole.UserRole, choice.name)
                self.listing.addItem(item)
        self.buttons.button(W.QDialogButtonBox.StandardButton.Apply).setEnabled(bool(query))

    def accept(self):
        if self.search.text().strip():
            super().accept()

    def manage(self):
        self.manage_requested = True
        self.reject()

    def clear_primary(self):
        self.clear_role = True
        super().accept()

    def apply(self, document):
        if self.clear_role:
            apply_choice(document, self.ids, '', False)
            return
        apply_choice(document, self.ids if self.assign.isChecked() else set(),
                     self.search.text().strip(), bool(self.mode.currentIndex()))
        if not document.deck.entries and not self.mode.currentIndex() and self.starter.isChecked():
            from .tag_model import unique_names
            prefs = document.editor_preferences.setdefault('quick_menu', {})
            prefs['starters'] = unique_names([*prefs.get('starters', STARTERS), self.search.text().strip()])


class OrganizationManager(W.QDialog):
    def __init__(self, document, parent=None, *, customize=False):
        super().__init__(parent)
        self.draft = deepcopy(document)
        self.setWindowTitle('Manage Tags')
        self.resize(600, 540)
        layout = W.QVBoxLayout(self)
        self.tabs = W.QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.lists = []
        for title in ('In Use', 'Available'):
            listing = W.QListWidget()
            self.lists.append(listing)
            self.tabs.addTab(listing, title)
        panel = W.QWidget()
        form = W.QVBoxLayout(panel)
        note = W.QLabel('Drag to order clockwise from the top. Checked choices enter the ring (up to 8); others use More. Inactive choices keep their settings without taking a slot.')
        note.setWordWrap(True)
        form.addWidget(note)
        self.mode = W.QComboBox()
        self.mode.addItems(['Start with Primary Roles', 'Start with Additional Tags'])
        form.addWidget(self.mode)
        delay_row = W.QHBoxLayout()
        delay_row.addWidget(W.QLabel('Right-hold delay'))
        self.delay = W.QSpinBox()
        self.delay.setRange(150, 1500)
        self.delay.setSingleStep(50)
        self.delay.setSuffix(' ms')
        delay_row.addWidget(self.delay)
        form.addLayout(delay_row)
        columns = W.QHBoxLayout()
        self.orders = []
        for title in ('Primary Roles', 'Additional Tags'):
            column = W.QVBoxLayout()
            column.addWidget(W.QLabel(title))
            listing = W.QListWidget()
            listing.setDragDropMode(W.QAbstractItemView.DragDropMode.InternalMove)
            listing.setDefaultDropAction(C.Qt.DropAction.MoveAction)
            column.addWidget(listing)
            columns.addLayout(column)
            self.orders.append(listing)
        form.addLayout(columns, 1)
        actions = W.QHBoxLayout()
        preview = W.QPushButton('Preview')
        preview.clicked.connect(self.preview)
        actions.addWidget(preview)
        reset = W.QPushButton('Restore defaults')
        reset.clicked.connect(self.reset)
        actions.addWidget(reset)
        form.addLayout(actions)
        self.tabs.addTab(panel, 'Customize Quick Menu')
        actions = W.QHBoxLayout()
        for label, callback in (('Add', self.add), ('Rename', self.rename), ('Delete', self.delete),
                                ('Up', lambda: self.move(-1)), ('Down', lambda: self.move(1))):
            button = W.QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        box = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok | W.QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.refresh()
        if customize:
            self.tabs.setCurrentIndex(2)

    def refresh(self):
        for listing in self.lists + self.orders:
            listing.clear()
        prefs = preferences(self.draft)
        self.mode.setCurrentIndex(int(prefs.get('initial_mode') == 'tags'))
        self.delay.setValue(hold_delay(self.draft))
        for tags in (False, True):
            hidden = set(prefs.get('tags_overflow' if tags else 'roles_overflow', []))
            for choice in choices(self.draft, tags, active=False, configured=False):
                title = f'{choice.name}   ·   {"Tag" if tags else "Role"}   ·   {choice.count} cards'
                item = W.QListWidgetItem(title)
                item.setData(C.Qt.ItemDataRole.UserRole, choice)
                self.lists[0 if choice.count else 1].addItem(item)
            for choice in choices(self.draft, tags, active=False):
                slot = W.QListWidgetItem(choice.name + (' (unused)' if not choice.count else ''))
                slot.setToolTip(choice.name)
                slot.setData(C.Qt.ItemDataRole.UserRole, choice)
                slot.setFlags(slot.flags() | C.Qt.ItemFlag.ItemIsUserCheckable)
                slot.setCheckState(C.Qt.CheckState.Unchecked if choice.key in hidden else C.Qt.CheckState.Checked)
                self.orders[int(tags)].addItem(slot)

    def save_config(self):
        prefs = self.draft.editor_preferences.setdefault('quick_menu', {})
        prefs['initial_mode'] = 'tags' if self.mode.currentIndex() else 'roles'
        prefs['hold_delay'] = self.delay.value()
        for index, prefix in enumerate(('roles', 'tags')):
            listing = self.orders[index]
            items = [listing.item(i) for i in range(listing.count())]
            current = [item.data(C.Qt.ItemDataRole.UserRole).key for item in items]
            previous = prefs.get(prefix + '_order', [])
            prefs[prefix + '_order'] = current + [key for key in previous if key not in current]
            # Keep preferences for choices temporarily unavailable or deleted.
            keys = set(current)
            old = preferences(self.draft).get(prefix + '_overflow', [])
            prefs[prefix + '_overflow'] = [key for key in old if key not in keys] + [
                item.data(C.Qt.ItemDataRole.UserRole).key for item in items if item.checkState() != C.Qt.CheckState.Checked]

    def selected(self):
        index = self.tabs.currentIndex()
        if index >= 2:
            return None
        item = self.lists[index].currentItem()
        return item.data(C.Qt.ItemDataRole.UserRole) if item else None

    def add(self):
        self.save_config()
        dialog = TagPicker(self.draft, parent=self)
        if dialog.exec() == W.QDialog.DialogCode.Accepted:
            dialog.apply(self.draft)
            self.refresh()

    def rename(self):
        choice = self.selected()
        if choice is None:
            return
        name, ok = W.QInputDialog.getText(self, 'Rename', 'Name:', text=choice.name)
        if ok:
            self.save_config()
            try:
                rename_choice(self.draft, choice, name)
            except ValueError as exc:
                W.QMessageBox.information(self, 'Name unavailable', str(exc))
            self.refresh()

    def delete(self):
        choice = self.selected()
        if choice and W.QMessageBox.question(self, 'Delete tag',
                f'Delete “{choice.name}” and its assignments? Cards will be kept.') == W.QMessageBox.StandardButton.Yes:
            self.save_config()
            delete_choice(self.draft, choice)
            self.refresh()

    def move(self, delta):
        choice = self.selected()
        if choice is None or choice.tags:
            return
        self.save_config()
        if choice.starter:
            names = list(preferences(self.draft).get('starters', STARTERS))
            index = next(i for i, name in enumerate(names) if name.casefold() == choice.name.casefold())
            target = index + delta
            if 0 <= target < len(names):
                names[index], names[target] = names[target], names[index]
                self.draft.editor_preferences['quick_menu']['starters'] = names
        else:
            categories = sorted(self.draft.deck.categories, key=lambda c: c.sort_order)
            index = next(i for i, category in enumerate(categories) if category.category_id == choice.key)
            target = index + delta
            if 0 <= target < len(categories):
                categories[index], categories[target] = categories[target], categories[index]
                for order, category in enumerate(categories):
                    category.sort_order = order
        self.refresh()

    def preview(self):
        from .quick_tags import QuickTagMenu
        self.save_config()
        self.preview_menu = QuickTagMenu(self.draft, set(), self)
        self.preview_menu.popup(self.mapToGlobal(self.rect().center()))

    def reset(self):
        self.draft.editor_preferences.pop('quick_menu', None)
        self.refresh()

    def accept(self):
        self.save_config()
        super().accept()
