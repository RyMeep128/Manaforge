"""Two-seat game table, object interactions and live inspection.

Zones, choices, combat and results are read from snapshots. This module contains
no legality, timing, costs, damage calculation or automatic decision policy.
"""

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_ui.theme import COLORS
from .artwork import PlayArtwork
from .decisions import DecisionPanel


def object_name(obj):
    if obj.hidden or obj.face_down:
        return "Face-down card"
    return (
        obj.characteristics.name
        if obj.characteristics and obj.characteristics.name
        else "Card"
    )


def is_land(obj):
    return bool(
        not obj.hidden
        and not obj.face_down
        and obj.characteristics
        and "Land" in (obj.characteristics.type_line or "")
    )


class GameCard(W.QAbstractButton):
    inspectRequested = C.pyqtSignal()

    def __init__(self, artwork, parent=None):
        super().__init__(parent)
        self.artwork = artwork
        self.obj = None
        self.actionable = self.selected = False
        self.combat = ""
        self.setFixedSize(112, 185)
        self.setFocusPolicy(C.Qt.FocusPolicy.StrongFocus)
        self.setCursor(C.Qt.CursorShape.PointingHandCursor)
        self.setAccessibleDescription(
            "Click for an available action. Right click to inspect without acting."
        )
        artwork.updated.connect(self.update)

    def present(self, obj, actionable=False, selected=False, combat=""):
        changed = (self.obj, self.actionable, self.selected, self.combat) != (
            obj,
            actionable,
            selected,
            combat,
        )
        self.obj, self.actionable, self.selected, self.combat = (
            obj,
            actionable,
            selected,
            combat,
        )
        self.setAccessibleName(
            object_name(obj)
            + (" · Available action" if actionable else "")
            + (" · Selected" if selected else "")
            + (" · Tapped" if obj.tapped else "")
            + (" · " + combat if combat else "")
        )
        if changed:
            self.setFixedSize(112, 132 if obj.zone == "battlefield" else 185)
            self.update()

    def paintEvent(self, event):
        if self.obj is None:
            return
        p = G.QPainter(self)
        p.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        border = COLORS["accent"] if self.actionable else COLORS["border_strong"]
        p.setPen(
            G.QPen(
                G.QColor("#efc36d" if self.selected or self.hasFocus() else border),
                3 if self.actionable or self.selected else 1,
            )
        )
        p.setBrush(G.QColor(COLORS["surface_raised"]))
        p.drawRoundedRect(C.QRectF(self.rect()).adjusted(2, 2, -2, -2), 7, 7)
        compact = self.obj.zone == "battlefield"
        rect = C.QRect(7, 7, 98, 83 if compact else 137)
        image = self.artwork.get(self.obj)
        if image is not None and not image.isNull():
            scaled = image.scaled(
                rect.size(),
                C.Qt.AspectRatioMode.KeepAspectRatio,
                C.Qt.TransformationMode.SmoothTransformation,
            )
            p.save()
            if self.obj.tapped:
                p.translate(rect.center())
                p.rotate(90)
                scaled = image.scaled(
                    80 if compact else 132,
                    80 if compact else 92,
                    C.Qt.AspectRatioMode.KeepAspectRatio,
                    C.Qt.TransformationMode.SmoothTransformation,
                )
                p.drawPixmap(-scaled.width() // 2, -scaled.height() // 2, scaled)
            else:
                p.drawPixmap(
                    rect.center().x() - scaled.width() // 2, rect.top(), scaled
                )
            p.restore()
        else:
            p.setPen(G.QColor(COLORS["text_secondary"]))
            p.drawText(
                rect.adjusted(4, 4, -4, -4),
                C.Qt.AlignmentFlag.AlignCenter | C.Qt.TextFlag.TextWordWrap,
                object_name(self.obj),
            )
        p.setPen(G.QColor(COLORS["text"]))
        c = (
            self.obj.characteristics
            if not self.obj.hidden and not self.obj.face_down
            else None
        )
        badge = []
        if self.selected:
            badge.append("Selected")
        elif self.actionable:
            badge.append("Available")
        if c and "Land" in (c.type_line or ""):
            badge.append("Land")
        if c and c.power is not None and c.toughness is not None:
            badge.append(f"{c.power}/{c.toughness}")
        if self.obj.tapped:
            badge.append("Tapped")
        if self.obj.damage:
            badge.append(f"{self.obj.damage} damage")
        if c and c.counters:
            badge.extend(f"{count} {name}" for name, count in c.counters)
        if self.combat:
            badge.append(self.combat)
        p.drawText(
            C.QRect(6, 94 if compact else 145, 100, 36),
            C.Qt.AlignmentFlag.AlignCenter | C.Qt.TextFlag.TextWordWrap,
            " · ".join(badge) or object_name(self.obj),
        )

    def contextMenuEvent(self, event):
        self.inspectRequested.emit()
        event.accept()


class CardLane(W.QScrollArea):
    selected = C.pyqtSignal(str)
    inspected = C.pyqtSignal(str)

    def __init__(self, artwork, parent=None):
        super().__init__(parent)
        self.artwork = artwork
        self.cards = {}
        self.order = ()
        self.setWidgetResizable(True)
        self.setMinimumHeight(211)
        self.setMaximumHeight(222)
        self.setVerticalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = W.QWidget()
        self.row = W.QHBoxLayout(self.content)
        self.row.setContentsMargins(3, 3, 3, 3)
        self.row.addStretch()
        self.section_labels = {}
        for title in ("Lands", "Other permanents"):
            label = W.QLabel(title)
            label.setWordWrap(True)
            label.setMaximumWidth(64)
            label.hide()
            self.section_labels[title] = label
        self.setWidget(self.content)

    def present(self, objects, actions, options, combat, *, separate_lands=False):
        identifiers = tuple(obj.object_id for obj in objects)
        for identifier in set(self.cards) - set(identifiers):
            card = self.cards.pop(identifier)
            card.setEnabled(False)
            card.hide()
            card.obj = None
            card.setAccessibleName("")
            card.clicked.disconnect()
            card.inspectRequested.disconnect()
            self.row.removeWidget(card)
            card.deleteLater()
        for obj in objects:
            if obj.object_id not in self.cards:
                card = GameCard(self.artwork)
                identifier = obj.object_id
                card.clicked.connect(
                    lambda checked=False, value=identifier: self.selected.emit(value)
                )
                card.inspectRequested.connect(
                    lambda value=identifier: self.inspected.emit(value)
                )
                self.cards[identifier] = card
            self.cards[obj.object_id].present(
                obj,
                obj.object_id in actions or obj.object_id in options,
                options.get(obj.object_id, False),
                combat.get(obj.object_id, ""),
            )
        groups = (
            tuple("Lands" if is_land(obj) else "Other permanents" for obj in objects)
            if separate_lands
            else ()
        )
        layout_key = identifiers, groups
        if layout_key != self.order:
            for card in self.cards.values():
                self.row.removeWidget(card)
            for label in self.section_labels.values():
                self.row.removeWidget(label)
                label.hide()
            position = 0
            for index, identifier in enumerate(identifiers):
                if groups and (index == 0 or groups[index] != groups[index - 1]):
                    label = self.section_labels[groups[index]]
                    self.row.insertWidget(position, label)
                    label.show()
                    position += 1
                self.row.insertWidget(position, self.cards[identifier])
                position += 1
            self.order = layout_key

    def clear(self):
        self.present((), {}, {}, {})


class GameTable(W.QWidget):
    command = C.pyqtSignal(object, str, object)

    def __init__(self, service, parent=None, *, artwork_factory=PlayArtwork):
        super().__init__(parent)
        self.view = None
        self.inspected = None
        self.artwork = artwork_factory(service, self)
        self.artwork.updated.connect(self._update_image)
        root = W.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        table = W.QWidget()
        column = W.QVBoxLayout(table)
        self.flow = W.QLabel()
        self.flow.setWordWrap(True)
        self.flow.setTextFormat(C.Qt.TextFormat.PlainText)
        self.flow.setProperty("role", "subtitle")
        column.addWidget(self.flow)
        self.opponent_label = W.QLabel()
        self.player_label = W.QLabel()
        for label in (self.opponent_label, self.player_label):
            label.setTextFormat(C.Qt.TextFormat.PlainText)
            label.setWordWrap(True)
        column.addWidget(self.opponent_label)
        self.opponent = CardLane(self.artwork)
        column.addWidget(self.opponent)
        self.zones = W.QTabWidget()
        self.zone_lanes = {}
        for zone, title in [
            ("stack", "Stack"),
            ("graveyard", "Graveyards"),
            ("exile", "Exile"),
            ("command", "Command zones"),
            ("decision", "Revealed choices / Pile 1"),
            ("decision_pile_2", "Pile 2"),
        ]:
            lane = CardLane(self.artwork)
            self.zone_lanes[zone] = lane
            self.zones.addTab(lane, title)
        self.observations = W.QPlainTextEdit()
        self.observations.setReadOnly(True)
        self.observations.setUndoRedoEnabled(False)
        self.observations.setPlaceholderText(
            "Permitted revealed information will appear here."
        )
        self.zones.addTab(self.observations, "Revealed information")
        column.addWidget(self.zones)
        column.addWidget(self.player_label)
        self.player = CardLane(self.artwork)
        column.addWidget(self.player)
        column.addWidget(W.QLabel("Your hand"))
        self.hand = CardLane(self.artwork)
        column.addWidget(self.hand)
        table_scroll = W.QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setWidget(table)
        table_scroll.setMinimumHeight(460)
        root.addWidget(table_scroll, 1)
        side = W.QWidget()
        side.setMinimumWidth(260)
        side.setMaximumWidth(360)
        sidebar = W.QVBoxLayout(side)
        self.inspection_image = W.QLabel()
        self.inspection_image.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.inspection_image.setMinimumHeight(180)
        self.inspection_image.setMaximumHeight(320)
        sidebar.addWidget(self.inspection_image)
        self.inspection = W.QPlainTextEdit()
        self.inspection.setReadOnly(True)
        self.inspection.setUndoRedoEnabled(False)
        self.inspection.setPlaceholderText("Select a card to inspect its live state.")
        self.inspection.setMinimumHeight(140)
        sidebar.addWidget(self.inspection)
        self.object_actions = W.QWidget()
        self.action_rows = W.QVBoxLayout(self.object_actions)
        self.action_rows.setContentsMargins(0, 0, 0, 0)
        sidebar.addWidget(self.object_actions)
        self.decisions = DecisionPanel()
        self.decisions.command.connect(self.command)
        scroll = W.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.decisions)
        scroll.setMinimumHeight(240)
        sidebar.addWidget(scroll, 1)
        root.addWidget(side)
        self.lanes = [self.opponent, self.player, self.hand, *self.zone_lanes.values()]
        for lane in self.lanes:
            lane.selected.connect(self.select_object)
            lane.inspected.connect(
                lambda identifier: self.select_object(identifier, interact=False)
            )

    def clear(self):
        self.view = self.inspected = None
        self.artwork.conceal()
        for lane in self.lanes:
            lane.clear()
        self.flow.clear()
        self.opponent_label.clear()
        self.player_label.clear()
        self.observations.clear()
        self.decisions.clear()
        self._clear_inspection()

    def pending(self):
        self.decisions.setEnabled(False)
        self.object_actions.setEnabled(False)
        for lane in self.lanes:
            lane.setEnabled(False)

    def present(self, view):
        if self.view and self.view.viewer_id != view.viewer_id:
            self.clear()
        self.view = view
        for lane in self.lanes:
            lane.setEnabled(True)
        self.object_actions.setEnabled(True)
        names = {player.player_id: player.name for player in view.players}
        flow = [
            f"Turn {view.turn}" if view.turn is not None else "",
            view.phase or "",
            view.step or "",
            "Active: " + names.get(view.active_player_id, "Waiting"),
            "Priority: " + names.get(view.priority_player_id, "Waiting"),
        ]
        self.flow.setText(
            " · ".join(
                value.replace("_", " ").title() if index in (1, 2) else value
                for index, value in enumerate(flow)
                if value
            )
        )
        for player in view.players:
            text = f"{player.name} · {player.life} life · Hand {player.hand_count} · Library {player.library_count}"
            if player.mana:
                text += " · Mana: " + ", ".join(
                    f"{amount} {kind}" for kind, amount in player.mana
                )
            if player.counters:
                text += " · " + ", ".join(
                    f"{amount} {kind}" for kind, amount in player.counters
                )
            commanders = [
                commander
                for commander in view.commanders or ()
                if commander.owner_id == player.player_id
            ]
            for commander in commanders:
                text += "\nCommander: " + (commander.name or "Commander")
                if commander.command_zone_plays is not None:
                    text += f" · Cast from command zone: {commander.command_zone_plays}"
                if commander.additional_cast_cost is not None:
                    text += " · Additional cost: " + commander.additional_cast_cost
                if commander.damage_dealt:
                    text += " · Damage dealt: " + ", ".join(
                        f"{names.get(seat, 'Player')} {amount}"
                        for seat, amount in commander.damage_dealt
                    )
            (
                self.player_label
                if player.player_id == view.viewer_id
                else self.opponent_label
            ).setText(text)
        # Defensively exclude concealed zones even if a malformed fake includes identities.
        visible = tuple(
            obj
            for obj in view.objects
            if (not obj.hidden or obj.zone == "battlefield")
            and (obj.zone != "hand" or obj.owner_id == view.viewer_id)
        )
        self.artwork.show_objects(visible)
        actions = {action.object_id for action in view.actions if action.object_id}
        options = (
            {
                option.object_id: option.selected
                for option in view.decision.options
                if option.object_id
            }
            if view.decision
            else {}
        )
        combat = {}
        for group in view.combat:
            for identifier in group.attackers:
                combat[identifier] = "Attacking " + names.get(
                    group.defender_id, "defender"
                )
            for identifier in group.blockers:
                combat[identifier] = "Blocking"

        def battlefield(seat):
            return tuple(
                sorted(
                    (
                        obj
                        for obj in visible
                        if obj.zone == "battlefield" and obj.controller_id == seat
                    ),
                    key=lambda obj: (
                        not is_land(obj),
                        obj.object_id,
                    ),
                )
            )

        self.player.present(
            battlefield(view.viewer_id), actions, options, combat, separate_lands=True
        )
        opponent_objects = tuple(
            obj
            for obj in visible
            if obj.zone == "battlefield" and obj.controller_id != view.viewer_id
        )
        self.opponent.present(
            tuple(
                sorted(
                    opponent_objects,
                    key=lambda obj: not is_land(obj),
                )
            ),
            actions,
            options,
            combat,
            separate_lands=True,
        )
        self.hand.present(
            tuple(obj for obj in visible if obj.zone == "hand"),
            actions,
            options,
            combat,
        )
        for zone, lane in self.zone_lanes.items():
            objects = tuple(obj for obj in visible if obj.zone == zone)
            lane.present(objects, actions, options, combat)
        self.zones.setTabText(0, f"Stack ({len(self.zone_lanes['stack'].cards)})")
        self.observations.setPlainText(
            "\n".join(
                (observation.name or "Revealed card")
                for observation in view.observations
                if not observation.hidden
            )
        )
        self.decisions.present(view)
        if self.inspected and any(obj.object_id == self.inspected for obj in visible):
            self.select_object(self.inspected, interact=False)
        else:
            self._clear_inspection()

    def _clear_inspection(self):
        self.inspected = None
        self.inspection.clear()
        self.inspection_image.clear()
        while self.action_rows.count():
            item = self.action_rows.takeAt(0)
            if item.widget():
                item.widget().setEnabled(False)
                item.widget().hide()
                item.widget().clicked.disconnect()
                item.widget().setText("")
                item.widget().deleteLater()

    def select_object(self, identifier, *, interact=True):
        view = self.view
        if view is None:
            return
        obj = next(
            (
                obj
                for obj in view.objects
                if obj.object_id == identifier
                and (not obj.hidden or obj.zone == "battlefield")
                and (obj.zone != "hand" or obj.owner_id == view.viewer_id)
            ),
            None,
        )
        if obj is None:
            return
        self._clear_inspection()
        self.inspected = identifier
        names = {player.player_id: player.name for player in view.players}
        c = obj.characteristics if not obj.face_down and not obj.hidden else None
        rows = [
            object_name(obj),
            "Live game information",
            "Zone: " + obj.zone.replace("_", " ").title(),
            "Owner: " + names.get(obj.owner_id, "Unknown"),
            "Controller: " + names.get(obj.controller_id, "Unknown"),
        ]
        if c:
            rows.extend(
                value
                for value in [
                    c.type_line,
                    f"{c.power}/{c.toughness}" if c.power is not None else None,
                    "Transformed" if c.transformed else None,
                    "Copy" if c.is_copy else None,
                    "Flipped" if c.flipped else None,
                ]
                if value
            )
            rows.extend(f"{count} {kind} counters" for kind, count in c.counters or ())
            if c.current_abilities is not None:
                rows.append("Current abilities")
                rows.extend(c.current_abilities or ("None reported",))
            if c.engine_view_text:
                rows.append("Engine card notes (may be incomplete)")
                rows.extend(c.engine_view_text)
            if c.loyalty is not None:
                rows.append("Loyalty: " + c.loyalty)
            if c.defense is not None:
                rows.append("Defense: " + c.defense)
        if obj.damage is not None:
            rows.append(f"Damage: {obj.damage}")
        lookup = {item.object_id: object_name(item) for item in view.objects}
        if obj.attachments:
            rows.append(
                "Attachments: "
                + ", ".join(lookup.get(item, "Card") for item in obj.attachments)
            )
        if obj.attached_to:
            rows.append("Attached to: " + lookup.get(obj.attached_to, "Card"))
        for group in view.combat:
            if identifier in group.attackers:
                rows.append(
                    "Attacking: "
                    + names.get(
                        group.defender_id, lookup.get(group.defender_id, "Defender")
                    )
                )
                rows.append(
                    "Blocked by: "
                    + (
                        ", ".join(
                            lookup.get(item, "Creature") for item in group.blockers
                        )
                        or "None"
                    )
                )
            if identifier in group.blockers:
                rows.append(
                    "Blocking: "
                    + ", ".join(
                        lookup.get(item, "Creature") for item in group.attackers
                    )
                )
        rows.append(
            "Artwork shows the original printing; live values above may differ."
        )
        self.inspection.setPlainText("\n".join(rows))
        self._update_image()
        options = (
            [
                option
                for option in view.decision.options
                if option.object_id == identifier
            ]
            if view.decision
            else []
        )
        actions = [action for action in view.actions if action.object_id == identifier]
        for option in options:
            self._action_button(
                "Deselect target" if option.selected else "Select target",
                view,
                "choose",
                (option.option_id,),
            )
        labels = {
            "play_land": "Play land",
            "cast_spell": "Cast spell",
            "activate_ability": "Activate ability",
            "declare_attacker": "Attack",
            "declare_blocker": "Block",
            "pay_mana": "Use mana ability",
            "select_object": "Use card",
        }
        for action in actions:
            self._action_button(
                labels.get(action.kind, action.label),
                view,
                "perform",
                (action.action_id,),
            )
        if (
            view.decision
            and view.decision.family == "mana"
            and obj.zone == "battlefield"
            and not actions
        ):
            self._action_button(
                "Select mana source", view, "select_mana_source", (identifier,)
            )
        # A single engine-offered target/action is direct; multiple options stay explicit.
        if interact and len(options) + len(actions) == 1:
            if options:
                self.command.emit(view, "choose", (options[0].option_id,))
            else:
                self.command.emit(view, "perform", (actions[0].action_id,))

    def _action_button(self, label, view, method, args):
        button = W.QPushButton(label)
        button.play_method, button.play_args = method, args
        button.clicked.connect(lambda: self.command.emit(view, method, args))
        self.action_rows.addWidget(button)

    @C.pyqtSlot()
    def _update_image(self):
        if self.view is None or self.inspected is None:
            return
        obj = next(
            (obj for obj in self.view.objects if obj.object_id == self.inspected), None
        )
        if obj is None:
            return
        image = self.artwork.get(obj, detailed=True)
        if image is not None and not image.isNull():
            self.inspection_image.setPixmap(
                image.scaled(
                    240,
                    320,
                    C.Qt.AspectRatioMode.KeepAspectRatio,
                    C.Qt.TransformationMode.SmoothTransformation,
                )
            )

        else:
            self.inspection_image.setText(
                "Artwork unavailable"
                if image is not None or not obj.card_identity
                else "Loading artwork…"
            )

    def keyPressEvent(self, event):
        if event.key() == C.Qt.Key.Key_Escape:
            self._clear_inspection()
            event.accept()
        else:
            super().keyPressEvent(event)
