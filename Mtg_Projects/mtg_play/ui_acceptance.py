"""CI-only UI pilot reusing established fixture policies through actual controls.

This is test automation, never imported by the product. The existing scenarios
retain their evidence assertions; their commands click Manaforge controls instead
of calling the engine session. Only the workspace controller talks to the engine.
"""

from __future__ import annotations
import argparse
import json
import logging
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from uuid import uuid4

from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.decks import DeckStore
from mtg_home.home import HomeWindow
from mtg_home.launcher import ModuleController
from .adapter import AdapterError, LocalGameAdapter
from .contracts import CommandResult
from .setup import saved_decks
from .lobby import offline_lobby
from .workspace import PlayWorkspace


def wait(app, predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.001)
    if not predicate():
        raise AdapterError("UI_WAIT_TIMEOUT")


class UIAdapter:
    def __init__(self, app, runtime, root, *, screenshot_root=None):
        self.app, self.runtime, self.root = app, runtime, root
        self.home = self.workspace = None
        self.receipts = []
        self.viewer_id = None
        self.closed = False
        self.screenshot_root = screenshot_root
        self.captured = set()

    def capture(self, name):
        if self.screenshot_root is None or name in self.captured:
            return
        self.screenshot_root.mkdir(parents=True, exist_ok=True)
        if not self.home.grab().save(str(self.screenshot_root / (name + ".png"))):
            raise AdapterError("UI_SCREENSHOT_FAILED")
        self.captured.add(name)

    def create_game(self, setup, documents):
        if (
            len(setup.seats) != 2
            or len(documents) != 2
            or setup.seats[0].controller != "local_human"
            or setup.seats[1].controller != "engine_ai"
        ):
            raise AdapterError("UI_FIXTURE_REQUIRES_OFFLINE_AI")
        self.viewer_id = setup.seats[0].seat_id
        for seat, document in zip(setup.seats, documents):
            DeckStore().save(
                self.root / "decks" / (seat.seat_id + ".manaforge.json"), document
            )
        # Synthetic fixture printing IDs deliberately exercise the artwork fallback.
        service = SimpleNamespace(
            database=SimpleNamespace(get_oracle_card=lambda oracle_id: None),
            get_image_path=lambda *args: None,
            ensure_image=lambda *args, **kwargs: None,
            ensure_face_image=lambda *args, **kwargs: None,
            get_card=lambda **kwargs: {},
        )
        self.home = HomeWindow()
        self.home.resize(1440, 1000)

        def factory():
            self.workspace = PlayWorkspace(
                service,
                lambda: controller.show_home(),
                adapter_factory=lambda: self.runtime,
                deck_provider=lambda: saved_decks(self.root),
                lobby=offline_lobby(
                    seat_ids=tuple(seat.seat_id for seat in setup.seats)
                ),
            )
            return self.workspace

        controller = ModuleController(
            self.home, service=service, factories={"play": factory}
        )
        self.controller = controller
        self.home.show()
        self.home.tiles["play"].click()
        if self.workspace is None:
            raise AdapterError("UI_PLAY_NAVIGATION_FAILED")
        wait(self.app, lambda: not self.workspace.catalog_jobs.busy)
        self.capture("landing")
        self.workspace.landing_page.offline_button.click()
        if self.workspace.pages.currentWidget() is not self.workspace.format_page:
            raise AdapterError("UI_OFFLINE_NAVIGATION_FAILED")
        self.workspace.format.setCurrentIndex(
            self.workspace.format.findData(setup.format)
        )
        self.capture("format")
        self.workspace.format_continue.click()
        if self.workspace.pages.currentWidget() is not self.workspace.setup_page:
            raise AdapterError("UI_LOBBY_NAVIGATION_FAILED")
        for seat, selector in zip(setup.seats, self.workspace.selectors):
            index = next(
                index
                for index, item in enumerate(self.workspace._decks)
                if item.path.name == seat.seat_id + ".manaforge.json"
            )
            selector.setCurrentIndex(index + 1)
        self.workspace.session.commandFinished.connect(self.receipts.append)
        self.workspace.session.startupProgress.connect(
            lambda progress: (
                self.capture("loading") if progress["state"] == "started" else None
            )
        )
        self.capture("setup")
        self.workspace.start_button.click()
        wait(self.app, lambda: not self.workspace.session.busy, timeout=300)
        self.workspace.session.timer.stop()
        if not self.workspace.session.active:
            raise AdapterError("UI_GAME_START_FAILED")
        return self

    def _activate(self, player):
        if self.closed:
            raise AdapterError("SESSION_CLOSED")
        workspace = self.workspace
        if player != self.viewer_id:
            raise AdapterError("UNAUTHORIZED_SEAT")
        workspace.session.timer.stop()
        wait(self.app, lambda: not workspace.session.busy)
        if workspace.session._blocked:
            raise AdapterError("UI_SESSION_FAILED")

    def poll(self, player, timeout=0):
        self._activate(player)
        self.workspace.session.refresh()
        wait(self.app, lambda: not self.workspace.session.busy)
        return ()

    def snapshot(self, player):
        self._activate(player)
        view = self.workspace._view
        if view is None:
            raise AdapterError("SNAPSHOT_NOT_READY")
        if view.viewer_id != player:
            raise AdapterError("UI_FOREIGN_VIEW")
        if view.status == "failed":
            raise AdapterError("UI_SESSION_FAILED")
        # Confirm actual widgets, not merely the snapshot used by the pilot.
        expected_hand = {
            obj.object_id
            for obj in view.objects
            if obj.zone == "hand" and not obj.hidden and obj.owner_id == player
        }
        if set(self.workspace.table.hand.cards) != expected_hand:
            raise AdapterError("UI_HAND_PRESENTATION_MISMATCH")
        self.capture("table-local")
        if view.decision and "mulligan" in view.decision.prompt.lower():
            self.capture("opening-hand")
        if any(obj.zone == "stack" for obj in view.objects):
            self.capture("stack")
        if view.combat:
            self.capture("combat")
        if view.result:
            self.capture("result-" + player)
        return view

    def _send(self, player, decision, method, args):
        self._activate(player)
        view = self.workspace._view
        if (
            view is None
            or view.decision is None
            or view.decision.decision_id != decision
        ):
            return CommandResult(uuid4().hex, "rejected", "STALE_OR_INVALID_DECISION")
        table = self.workspace.table
        if method == "perform":
            action = next(
                (item for item in view.actions if item.action_id == args[0]), None
            )
            if action and action.object_id:
                table.select_object(action.object_id, interact=False)
        elif method == "select_mana_source":
            table.select_object(args[0], interact=False)
            offered = next(
                (action for action in view.actions if action.object_id == args[0]), None
            )
            if offered is not None:
                method, args = "perform", (offered.action_id,)
        elif method == "choose_number":
            table.decisions.findChild(W.QSpinBox).setValue(args[0])
        elif method == "choose_amounts":
            for spin, value in zip(table.decisions.findChildren(W.QSpinBox), args[0]):
                spin.setValue(value)
        match = next(
            (
                button
                for button in table.findChildren(W.QPushButton)
                if button.isEnabled()
                and getattr(button, "play_method", None) == method
                and (
                    method in ("choose_number", "choose_amounts")
                    or getattr(button, "play_args", None) == args
                )
            ),
            None,
        )
        if match is None:
            raise AdapterError("UI_COMMAND_CONTROL_MISSING")
        previous = len(self.receipts)
        match.click()
        wait(self.app, lambda: not self.workspace.session.busy)
        if len(self.receipts) == previous:
            raise AdapterError("UI_COMMAND_RECEIPT_MISSING")
        return self.receipts[-1]

    def perform(self, player, decision, value):
        return self._send(player, decision, "perform", (value,))

    def choose(self, player, decision, value):
        return self._send(player, decision, "choose", (value,))

    def select_mana_source(self, player, decision, value):
        return self._send(player, decision, "select_mana_source", (value,))

    def choose_number(self, player, decision, value):
        return self._send(player, decision, "choose_number", (value,))

    def choose_amounts(self, player, decision, values):
        return self._send(player, decision, "choose_amounts", (values,))

    def finish_selection(self, player, decision):
        return self._send(player, decision, "finish_selection", ())

    def cancel(self, player, decision):
        return self._send(player, decision, "cancel", ())

    def concede(self, player):
        self.poll(player)
        deadline = time.monotonic() + 30
        while self.workspace._view is None and time.monotonic() < deadline:
            self.poll(player)
        if self.workspace._view is None:
            raise AdapterError("UI_CONCESSION_STATE_UNAVAILABLE")

        def confirm():
            dialog = self.app.activeModalWidget()
            if isinstance(dialog, W.QMessageBox):
                dialog.button(W.QMessageBox.StandardButton.Yes).click()

        C.QTimer.singleShot(0, confirm)
        previous = len(self.receipts)
        self.workspace.concede_button.click()
        wait(self.app, lambda: not self.workspace.session.busy)
        if len(self.receipts) == previous:
            raise AdapterError("UI_CONCESSION_RECEIPT_MISSING")
        return self.receipts[-1]

    def close(self):
        if self.workspace is not None:
            self.workspace._approved_close = True
            self.workspace.close_button.click()
            wait(self.app, lambda: not self.workspace.session.busy, timeout=90)
            if self.workspace.session.active:
                raise AdapterError("UI_ENGINE_CLEANUP_FAILED")
            wait(self.app, self.workspace.prepare_to_close, timeout=90)
        if self.home is not None:
            self.home.close()
        self.closed = True


def main():
    from . import ai_acceptance

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("ai-freeform", "ai-commander", "ai-blockers"),
        required=True,
    )
    parser.add_argument("--xmage-root", type=Path, required=True)
    parser.add_argument("--jdk-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["MANAFORGE_ENABLE_LOCAL_PLAY"] = "1"
    app = W.QApplication.instance() or W.QApplication([])
    from mtg_ui.theme import application_stylesheet

    app.setStyle("Fusion")
    app.setStyleSheet(application_stylesheet())
    app.setQuitOnLastWindowClosed(False)
    runtime = LocalGameAdapter(bundle=args.xmage_root, jdk=args.jdk_path)
    result = {"scenario": args.scenario, "success": False}
    with tempfile.TemporaryDirectory(prefix="manaforge-ui-") as directory:
        os.environ["PRINT_PROXY_PREP_DATA_DIR"] = directory
        pilot = UIAdapter(
            app,
            runtime,
            Path(directory),
            screenshot_root=args.output.parent / ("ui-" + args.scenario),
        )
        try:
            result["gameplay"] = {
                "ai-freeform": ai_acceptance.freeform,
                "ai-commander": ai_acceptance.commander,
                "ai-blockers": ai_acceptance.blockers,
            }[args.scenario](pilot)
            result["authorized_viewer"] = pilot.viewer_id
            result["success"] = True
        except Exception as exc:
            result["error"] = (
                getattr(exc, "code", None) or "UI_ACCEPTANCE_FAILED"
            ).split(":", 1)[0]
            if isinstance(exc, ai_acceptance.AIAcceptanceError):
                result["failure_context"] = exc.context
        finally:
            try:
                pilot.close()
            except Exception:
                result["success"] = False
                result["cleanup_error"] = "UI_CLEANUP_NOT_CONFIRMED"
            result["lifecycle"] = runtime.lifecycle.records
            if runtime.result is not None:
                result["runtime"] = runtime.result.to_dict()
                if (
                    not runtime.result.success
                    or runtime.result.forced_cleanup
                    or any(
                        name.startswith("peer_")
                        for name, _ in runtime.result.process_exit_codes
                    )
                ):
                    result["success"] = False
            # This standalone pilot owns the process logging lifecycle. Windows
            # cannot remove its temporary data directory while handlers are open.
            logging.shutdown()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if not result["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
