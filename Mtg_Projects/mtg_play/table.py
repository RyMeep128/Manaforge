"""Two-seat game table, object interactions and live inspection.

Zones, choices, combat and results are read from snapshots. This module contains
no legality, timing, costs, damage calculation or automatic decision policy.
"""

from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_ui.theme import COLORS
from .artwork import PlayArtwork
from .decisions import DecisionPanel, opening_hand_request


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


def live_card_text(view, obj):
    """Authorized engine observations only; printed artwork is never current rules."""
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
                "Color: " + c.color if c.color else None,
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
    lookup = {
        item.object_id: object_name(item)
        for item in view.objects
        if item.zone != "hand" or item.owner_id == view.viewer_id
    }
    if obj.attachments:
        rows.append(
            "Attachments: "
            + ", ".join(lookup.get(item, "Card") for item in obj.attachments)
        )
    if obj.attached_to:
        rows.append("Attached to: " + lookup.get(obj.attached_to, "Card"))
    for group in view.combat:
        if obj.object_id in group.attackers:
            rows.append(
                "Attacking: "
                + names.get(
                    group.defender_id, lookup.get(group.defender_id, "Defender")
                )
            )
            rows.append(
                "Blocked by: "
                + (
                    ", ".join(lookup.get(item, "Creature") for item in group.blockers)
                    or "None"
                )
            )
        if obj.object_id in group.blockers:
            rows.append(
                "Blocking: "
                + ", ".join(lookup.get(item, "Creature") for item in group.attackers)
            )
    rows.append("Artwork shows the original printing; live values above may differ.")
    return "\n".join(rows)


class GameCard(W.QAbstractButton):
    inspectRequested = C.pyqtSignal()
    hoverRequested = C.pyqtSignal()
    hoverEnded = C.pyqtSignal()

    def __init__(self, artwork, parent=None):
        super().__init__(parent)
        self.artwork = artwork
        self.obj = None
        self.card_scale = 1.0
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
            self.apply_scale(self.card_scale)
            self.update()

    def apply_scale(self, scale):
        self.card_scale = scale
        height = 132 if self.obj and self.obj.zone == "battlefield" else 185
        self.setFixedSize(round(112 * scale), round(height * scale))
        self.update()

    def paintEvent(self, event):
        if self.obj is None:
            return
        p = G.QPainter(self)
        p.scale(self.card_scale, self.card_scale)
        p.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        border = COLORS["accent"] if self.actionable else COLORS["border_strong"]
        p.setPen(
            G.QPen(
                G.QColor("#efc36d" if self.selected or self.hasFocus() else border),
                3 if self.actionable or self.selected else 1,
            )
        )
        p.setBrush(G.QColor(COLORS["surface_raised"]))
        p.drawRoundedRect(
            C.QRectF(
                0, 0, 112, 132 if self.obj.zone == "battlefield" else 185
            ).adjusted(2, 2, -2, -2),
            7,
            7,
        )
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

    def enterEvent(self, event):
        super().enterEvent(event)
        self.hoverRequested.emit()

    def leaveEvent(self, event):
        self.hoverEnded.emit()
        super().leaveEvent(event)

    def contextMenuEvent(self, event):
        self.inspectRequested.emit()
        event.accept()


class CardLane(W.QScrollArea):
    selected = C.pyqtSignal(str)
    inspected = C.pyqtSignal(str)
    hovered = C.pyqtSignal(str)
    hoverEnded = C.pyqtSignal()

    def __init__(self, artwork, parent=None):
        super().__init__(parent)
        self.artwork = artwork
        self.cards = {}
        self.card_scale = 1.0
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
                card.hoverRequested.connect(
                    lambda value=identifier: self.hovered.emit(value)
                )
                card.hoverEnded.connect(self.hoverEnded)
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

    def fit_cards(self, scale, *, battlefield=False):
        self.card_scale = scale
        self.setFixedHeight(round((132 if battlefield else 185) * scale) + 24)
        for card in self.cards.values():
            card.apply_scale(scale)

    def clear(self):
        self.present((), {}, {}, {})


class OpeningHandFan(W.QWidget):
    selected = C.pyqtSignal(str)
    inspected = C.pyqtSignal(str)
    hovered = C.pyqtSignal(str)
    hoverEnded = C.pyqtSignal()

    def __init__(self, artwork, parent=None):
        super().__init__(parent)
        self.artwork = artwork
        self.cards = {}
        self.setMinimumHeight(180)

    def clear(self):
        for card in self.cards.values():
            card.setEnabled(False)
            card.obj = None
            card.setAccessibleName("")
            card.hide()
            card.deleteLater()
        self.cards.clear()

    def present(self, objects, options):
        identifiers = {obj.object_id for obj in objects}
        for identifier in set(self.cards) - identifiers:
            card = self.cards.pop(identifier)
            card.setEnabled(False)
            card.obj = None
            card.setAccessibleName("")
            card.hide()
            card.deleteLater()
        for obj in objects:
            identifier = obj.object_id
            if identifier not in self.cards:
                card = GameCard(self.artwork, self)
                card.clicked.connect(
                    lambda checked=False, value=identifier: self.selected.emit(value)
                )
                card.inspectRequested.connect(
                    lambda value=identifier: self.inspected.emit(value)
                )
                card.hoverRequested.connect(card.raise_)
                card.hoverRequested.connect(
                    lambda value=identifier: self.hovered.emit(value)
                )
                card.hoverEnded.connect(self.hoverEnded)
                self.cards[identifier] = card
            card = self.cards[identifier]
            card.present(obj, identifier in options, options.get(identifier, False))
            card.show()
        self.cards = {obj.object_id: self.cards[obj.object_id] for obj in objects}
        self._arrange()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange()

    def _arrange(self):
        count = len(self.cards)
        if not count:
            return
        scale = max(0.6, min(1.65, (self.height() - 35) / 185))
        width = round(112 * scale)
        spacing = min(
            width + 8, max(1, (self.width() - width - 16) / max(1, count - 1))
        )
        left = max(4, (self.width() - width - spacing * (count - 1)) / 2)
        center = (count - 1) / 2
        for index, card in enumerate(self.cards.values()):
            card.apply_scale(scale)
            card.move(round(left + index * spacing), round(5 + abs(index - center) * 5))
            card.raise_()


class GameTable(W.QWidget):
    command = C.pyqtSignal(object, str, object)

    def __init__(self, service, parent=None, *, artwork_factory=PlayArtwork):
        super().__init__(parent)
        self.view = None
        self.inspected = None
        self._interactions_pending = False
        self._hover_identifier = None
        self.hover_timer = C.QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.setInterval(300)
        self.hover_timer.timeout.connect(self._show_hover)
        self.hover_preview = W.QFrame(self, C.Qt.WindowType.ToolTip)
        self.hover_preview.setAttribute(
            C.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.hover_preview.setFocusPolicy(C.Qt.FocusPolicy.NoFocus)
        preview_layout = W.QVBoxLayout(self.hover_preview)
        self.hover_image = W.QLabel()
        self.hover_image.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.hover_image)
        self.hover_text = W.QPlainTextEdit()
        self.hover_text.setReadOnly(True)
        self.hover_text.setFocusPolicy(C.Qt.FocusPolicy.NoFocus)
        preview_layout.addWidget(self.hover_text, 1)
        self.action_menu = W.QMenu(self)
        self.view_mode = "focused"
        self._zone_decision = None
        self.artwork = artwork_factory(service, self)
        self.artwork.updated.connect(self._update_image)
        root = W.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        table = W.QWidget()
        self.board = table
        column = W.QVBoxLayout(table)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        self.flow = W.QLabel()
        self.flow.setWordWrap(True)
        self.flow.setTextFormat(C.Qt.TextFormat.PlainText)
        self.flow.setProperty("role", "subtitle")
        top = W.QHBoxLayout()
        top.addWidget(self.flow, 1)
        self.zone_button = W.QPushButton("Other zones")
        top.addWidget(self.zone_button)
        column.addLayout(top)
        self.opponent_label = W.QLabel()
        self.player_label = W.QLabel()
        for label in (self.opponent_label, self.player_label):
            label.setTextFormat(C.Qt.TextFormat.PlainText)
            label.setWordWrap(True)
        column.addWidget(self.opponent_label)
        self.opponent = CardLane(self.artwork)
        column.addWidget(self.opponent)
        self.combat_summary = W.QLabel()
        self.combat_summary.setTextFormat(C.Qt.TextFormat.PlainText)
        self.combat_summary.setWordWrap(True)
        column.addWidget(self.combat_summary)
        self.stack_heading = W.QLabel("Stack")
        column.addWidget(self.stack_heading)
        self.zones_dialog = W.QDialog(self, C.Qt.WindowType.Tool)
        self.zones_dialog.setWindowTitle("Other zones")
        self.zones_dialog.resize(720, 300)
        zone_layout = W.QVBoxLayout(self.zones_dialog)
        self.zones = W.QTabWidget()
        zone_layout.addWidget(self.zones)
        self.zone_button.clicked.connect(self.zones_dialog.show)
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
            if zone == "stack":
                column.addWidget(lane)
            else:
                self.zones.addTab(lane, title)
        self.observations = W.QPlainTextEdit()
        self.observations.setReadOnly(True)
        self.observations.setUndoRedoEnabled(False)
        self.observations.setPlaceholderText(
            "Permitted revealed information will appear here."
        )
        self.zones.addTab(self.observations, "Revealed information")
        column.addStretch(1)
        column.addWidget(self.player_label)
        self.player = CardLane(self.artwork)
        column.addWidget(self.player)
        column.addWidget(W.QLabel("Your hand"))
        self.hand = CardLane(self.artwork)
        column.addWidget(self.hand)
        root.addWidget(table, 1)
        self.inspection_dialog = W.QDialog(self, C.Qt.WindowType.Tool)
        self.inspection_dialog.setWindowTitle("Card inspection")
        self.inspection_dialog.resize(360, 620)
        sidebar = W.QVBoxLayout(self.inspection_dialog)
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
        self.decision_dock = W.QScrollArea()
        self.decision_dock.setWidgetResizable(True)
        self.decision_dock.setWidget(self.decisions)
        self.decision_dock.setMinimumWidth(200)
        self.decision_dock.setMaximumWidth(240)
        root.addWidget(self.decision_dock)
        self.opening_overlay = W.QFrame(self)
        self.opening_overlay.setObjectName("openingOverlay")
        self.opening_overlay.setStyleSheet(
            "QFrame#openingOverlay { background-color: rgba(5, 8, 13, 238); border: 1px solid #3d4c58; border-radius: 10px; }"
        )
        opening_layout = W.QVBoxLayout(self.opening_overlay)
        opening_layout.setContentsMargins(20, 14, 20, 14)
        self.opening_title = W.QLabel("Your opening hand")
        self.opening_title.setProperty("role", "title")
        opening_layout.addWidget(self.opening_title)
        self.opening_status = W.QLabel()
        self.opening_status.setWordWrap(True)
        self.opening_status.setTextFormat(C.Qt.TextFormat.PlainText)
        opening_layout.addWidget(self.opening_status)
        self.opening_hand = OpeningHandFan(self.artwork)
        opening_layout.addWidget(self.opening_hand, 1)
        self.opening_controls = W.QScrollArea()
        self.opening_controls.setWidgetResizable(True)
        self.opening_controls.setMinimumHeight(120)
        self.opening_controls.setMaximumHeight(200)
        opening_layout.addWidget(self.opening_controls)
        self.opening_overlay.hide()
        self.lanes = [self.opponent, self.player, self.hand, *self.zone_lanes.values()]
        self.opening_hand.selected.connect(self.select_object)
        self.opening_hand.inspected.connect(
            lambda identifier: self.select_object(identifier, interact=False)
        )
        self.opening_hand.hovered.connect(self._schedule_hover)
        self.opening_hand.hoverEnded.connect(self._hide_hover)
        self.stack_heading.hide()
        self.zone_lanes["stack"].hide()
        self.combat_summary.hide()
        self.decision_dock.hide()
        for lane in self.lanes:
            lane.hovered.connect(self._schedule_hover)
            lane.hoverEnded.connect(self._hide_hover)
            lane.selected.connect(self.select_object)
            lane.inspected.connect(
                lambda identifier: self.select_object(identifier, interact=False)
            )

    def clear(self):
        self.opening_overlay.hide()
        self.opening_hand.clear()
        self._dock_decisions(False)
        self._hide_hover()
        self.action_menu.clear()
        self.action_menu.hide()
        self.combat_summary.clear()
        self.combat_summary.hide()
        self._zone_decision = None
        self.view = self.inspected = None
        self.zones_dialog.hide()
        self.decision_dock.hide()
        self.stack_heading.hide()
        self.zone_lanes["stack"].hide()
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
        self._interactions_pending = True
        self.opening_hand.setEnabled(False)
        self._hide_hover()
        self.action_menu.hide()
        self.decisions.setEnabled(False)
        self.object_actions.setEnabled(False)
        for lane in self.lanes:
            lane.setEnabled(False)

    def present(self, view):
        self._interactions_pending = False
        self.action_menu.hide()
        self.action_menu.clear()
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
        self.combat_summary.setText(
            f"Combat: {sum(len(group.attackers) for group in view.combat)} attackers ? "
            f"{sum(len(group.blockers) for group in view.combat)} blockers"
        )
        self.combat_summary.setVisible(bool(view.combat))
        if view.result:
            self.flow.setText(
                "Game result: " + view.result.replace("_", " ").capitalize()
            )
        stack_count = len(self.zone_lanes["stack"].cards)
        self.stack_heading.setText(f"Stack ({stack_count})")
        self.stack_heading.setVisible(bool(stack_count))
        self.zone_lanes["stack"].setVisible(bool(stack_count))
        for index in range(self.zones.count()):
            lane = self.zones.widget(index)
            if hasattr(lane, "cards"):
                base = self.zones.tabText(index).split(" (")[0]
                self.zones.setTabText(index, f"{base} ({len(lane.cards)})")
        self.observations.setPlainText(
            "\n".join(
                (observation.name or "Revealed card")
                for observation in view.observations
                if not observation.hidden
            )
        )
        opening = opening_hand_request(view) and not view.result
        self._dock_decisions(opening)
        self.decisions.present(view)
        self.decision_dock.setVisible(
            not opening and (view.decision is not None or bool(view.result))
        )
        self.opening_overlay.setVisible(opening)
        if opening:
            own_hand = tuple(
                obj
                for obj in visible
                if obj.zone == "hand"
                and obj.owner_id == view.viewer_id
                and not obj.hidden
                and not obj.face_down
            )
            bottom = view.decision.family == "target"
            self.opening_title.setText(
                "Choose cards for the bottom of your library"
                if bottom
                else "Your opening hand"
            )
            self.opening_status.setText(
                f"{len(own_hand)} cards in your hand. "
                + (
                    view.decision.prompt
                    if bottom
                    else "Choose for your seat. The AI handles its own opening choices."
                )
            )
            if (
                bottom
                and view.decision.minimum is not None
                and view.decision.maximum is not None
            ):
                selected_count = sum(
                    option.selected for option in view.decision.options
                )
                self.opening_status.setText(
                    self.opening_status.text()
                    + f" Required selection: {view.decision.minimum} to {view.decision.maximum}; {selected_count} selected."
                )
            self.opening_hand.setEnabled(True)
            self.opening_hand.present(own_hand, options)
            self.opening_overlay.setGeometry(self.rect().adjusted(4, 4, -4, -4))
            self.opening_overlay.raise_()
        else:
            self.opening_hand.clear()
        self._fit_board()
        C.QTimer.singleShot(0, self._fit_board)
        decision_id = view.decision.decision_id if view.decision else None
        if decision_id != self._zone_decision and options:
            for zone, lane in self.zone_lanes.items():
                if zone != "stack" and set(lane.cards) & set(options):
                    self.zones.setCurrentWidget(lane)
                    self.zones_dialog.show()
                    break
        self._zone_decision = decision_id
        if self._hover_identifier is not None and not self.hover_timer.isActive():
            self._show_hover()
        if self.inspected and any(obj.object_id == self.inspected for obj in visible):
            self.select_object(self.inspected, interact=False, show_inspection=False)
        else:
            self._clear_inspection()

    def _dock_decisions(self, opening):
        target = self.opening_controls if opening else self.decision_dock
        source = self.decision_dock if opening else self.opening_controls
        if target.widget() is not self.decisions:
            source.takeWidget()
            target.setWidget(self.decisions)
            self.decisions.show()

    def _schedule_hover(self, identifier):
        if self._interactions_pending:
            return
        self._hover_identifier = identifier
        self.hover_timer.start()

    def _hide_hover(self):
        self.hover_timer.stop()
        self._hover_identifier = None
        self.hover_preview.hide()
        self.hover_image.clear()
        self.hover_text.clear()

    def _show_hover(self):
        self.hover_timer.stop()
        view = self.view
        obj = (
            next(
                (
                    obj
                    for obj in view.objects
                    if obj.object_id == self._hover_identifier
                ),
                None,
            )
            if view
            else None
        )
        if (
            obj is None
            or obj.hidden
            or obj.face_down
            or self._interactions_pending
            or (obj.zone == "hand" and obj.owner_id != view.viewer_id)
        ):
            self._hide_hover()
            return
        self.hover_text.setPlainText(live_card_text(view, obj))
        self._update_hover_image(obj)
        screen = (
            G.QGuiApplication.screenAt(G.QCursor.pos())
            or G.QGuiApplication.primaryScreen()
        )
        available = screen.availableGeometry()
        self.hover_preview.resize(
            min(360, available.width() - 16), min(620, available.height() - 24)
        )
        position = G.QCursor.pos() + C.QPoint(20, 16)
        position.setX(
            max(
                available.left(),
                min(position.x(), available.right() - self.hover_preview.width()),
            )
        )
        position.setY(
            max(
                available.top(),
                min(position.y(), available.bottom() - self.hover_preview.height()),
            )
        )
        self.hover_preview.move(position)
        self.hover_preview.show()

    def _update_hover_image(self, obj):
        image = self.artwork.get(obj, detailed=True)
        self.hover_image.clear()
        if image is not None and not image.isNull():
            self.hover_image.setPixmap(
                image.scaled(
                    270,
                    370,
                    C.Qt.AspectRatioMode.KeepAspectRatio,
                    C.Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.hover_image.setText(
                "Local artwork unavailable"
                if image is not None
                else "Loading local artwork..."
            )

    def set_view_mode(self, mode):
        if mode != "focused":
            raise ValueError("Only Focused View is currently supported")
        self.view_mode = mode

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "opening_overlay"):
            self.opening_overlay.setGeometry(self.rect().adjusted(4, 4, -4, -4))
        self._fit_board()

    def _fit_board(self):
        if not hasattr(self, "zone_lanes"):
            return
        stack = bool(self.zone_lanes["stack"].cards)
        scale = round(
            max(
                0.55,
                min(
                    1.0,
                    max(0.0, self.board.width() - 30) / 826,
                    (self.height() - 190) / (449 + (185 if stack else 0)),
                ),
            ),
            2,
        )
        self.opponent.fit_cards(scale, battlefield=True)
        self.player.fit_cards(scale, battlefield=True)
        self.hand.fit_cards(scale)
        self.zone_lanes["stack"].fit_cards(scale)

    def _clear_inspection(self, *, hide=True):
        if hide:
            self.inspection_dialog.hide()
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

    def select_object(self, identifier, *, interact=True, show_inspection=True):
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
        self.action_menu.hide()
        self.action_menu.clear()
        self._clear_inspection(hide=False)
        offered_count = (
            sum(action.object_id == identifier for action in view.actions)
            + sum(option.object_id == identifier for option in view.decision.options)
            if view.decision
            else 0
        )
        if show_inspection and (not interact or offered_count == 0):
            self._hide_hover()
            self.inspection_dialog.show()
        self.inspected = identifier
        self.inspection.setPlainText(live_card_text(view, obj))
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
            label = labels.get(action.kind, action.label)
            if (
                sum(other.kind == action.kind for other in actions) > 1
                and action.label
                and action.label != object_name(obj)
            ):
                label += ": " + action.label
            self._action_button(
                label,
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
        if interact and len(options) + len(actions) > 1:
            self._hide_hover()
            self.action_menu.clear()
            for index in range(self.action_rows.count()):
                button = self.action_rows.itemAt(index).widget()
                action = self.action_menu.addAction(button.text())
                action.triggered.connect(
                    lambda checked=False, target=button: (
                        target.click() if target.isEnabled() else None
                    )
                )
            self.action_menu.popup(G.QCursor.pos())
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
        if (
            self._hover_identifier is not None
            and self.hover_preview.isVisible()
            and self.view is not None
        ):
            obj = next(
                (
                    obj
                    for obj in self.view.objects
                    if obj.object_id == self._hover_identifier
                ),
                None,
            )
            if (
                obj is not None
                and not obj.hidden
                and not obj.face_down
                and (obj.zone != "hand" or obj.owner_id == self.view.viewer_id)
            ):
                self._update_hover_image(obj)
            else:
                self._hide_hover()
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
            self._hide_hover()
            self.action_menu.hide()
            self._clear_inspection()
            event.accept()
        else:
            super().keyPressEvent(event)
