"""Randomize worker lifecycle regressions, for GitHub Actions only."""

from copy import deepcopy
from threading import Event, get_ident
from types import SimpleNamespace as NS

import pytest
from PyQt6 import QtWidgets as W
from mtg_core.decks import DeckDocument, DeckEntry
from mtg_play.adapter import AdapterError
from mtg_play.opponents import OpponentRandomizer
from mtg_play.tests.test_presentation import drain


@pytest.fixture
def app():
    return W.QApplication.instance() or W.QApplication([])


def documents():
    rows = tuple(DeckDocument() for _ in range(3))
    for index, row in enumerate(rows):
        row.deck.name = str(index)
        row.deck.entries = [DeckEntry("forest", "Forest", 60)]
    return rows


class Owner:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []
        self.closed = False
        self.fail_close = False
        self.gate = None
        self.entered = Event()

    def __enter__(self):
        self.calls.append(("enter", get_ident()))
        return self

    def validate_deck(self, document, format, **kwargs):
        self.calls.append((format, get_ident()))
        self.entered.set()
        if self.gate is not None:
            assert self.gate.wait(5)
        index = int(document.deck.name)
        document.deck.entries.clear()  # Mutating a worker copy must be harmless.
        outcome = self.outcomes[index]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self):
        self.calls.append(("close", get_ident()))
        if self.fail_close:
            raise AdapterError("RUNTIME_CLEANUP_TIMEOUT")
        self.closed = True


def test_randomize_only_applies_verified_choice_after_cleanup_off_gui_thread(app):
    owner = Owner((True, False, True))
    picker = OpponentRandomizer(adapter_factory=lambda: owner)
    rows = documents()
    before = deepcopy([row.to_dict() for row in rows])
    selected = []
    picker.selected.connect(lambda index: selected.append((index, owner.closed)))
    assert picker.start(rows, "freeform", current=0)
    assert not picker.start(rows, "freeform")
    drain(app, lambda: not picker.busy)
    assert selected == [(2, True)]
    assert all(thread != get_ident() for _, thread in owner.calls)
    assert [row.to_dict() for row in rows] == before


@pytest.mark.parametrize(
    "outcomes", [(False, False, False), (True, RuntimeError("PRIVATE"), True)]
)
def test_empty_or_failed_preflight_preserves_selection_and_private_data(app, outcomes):
    owner = Owner(outcomes)
    picker = OpponentRandomizer(adapter_factory=lambda: owner)
    selected, messages = [], []
    picker.selected.connect(selected.append)
    picker.message.connect(messages.append)
    picker.start(documents(), "commander", current=0)
    drain(app, lambda: not picker.busy)
    assert not selected and owner.closed
    assert "PRIVATE" not in str(messages)
    assert "selection has been kept" in messages[-1]


def test_cancel_waits_for_inflight_validation_and_closes_before_idle(app):
    owner = Owner((True, True, True))
    owner.gate = Event()
    picker = OpponentRandomizer(adapter_factory=lambda: owner)
    selected = []
    picker.selected.connect(selected.append)
    picker.start(documents(), "freeform")
    drain(app, owner.entered.is_set)
    picker.cancel()
    assert picker.busy and not owner.closed
    owner.gate.set()
    drain(app, lambda: not picker.busy)
    assert not selected and owner.closed
    assert len([kind for kind, _ in owner.calls if kind == "freeform"]) == 1


def test_unconfirmed_cleanup_retains_runtime_and_requires_retry_before_selection(app):
    owner = Owner((True, True, True))
    owner.fail_close = True
    picker = OpponentRandomizer(adapter_factory=lambda: owner)
    selected = []
    picker.selected.connect(selected.append)
    picker.start(documents(), "freeform")
    drain(app, lambda: not picker.jobs.busy)
    assert picker.busy and picker.cleanup_pending and not selected
    assert not picker.start(documents(), "freeform")
    owner.fail_close = False
    picker.retry_cleanup()
    drain(app, lambda: not picker.busy)
    assert owner.closed and not selected


def test_cancelled_queued_cleanup_retry_keeps_runtime_blocked(app):
    owner = Owner((True, True, True))
    owner.fail_close = True
    picker = OpponentRandomizer(adapter_factory=lambda: owner)
    picker.start(documents(), "freeform")
    drain(app, lambda: not picker.jobs.busy)
    picker.retry_cleanup()
    picker.cancel()  # Cancel the queued retry before its worker starts.
    drain(app, lambda: not picker.jobs.busy)
    assert picker.cleanup_pending and picker.busy and not owner.closed
    owner.fail_close = False
    picker.retry_cleanup()
    drain(app, lambda: not picker.busy)
    assert owner.closed


def test_cancel_interrupts_runtime_startup_and_reaps_owner_before_return(app):
    class StartingOwner(Owner):
        def set_cancel_event(self, cancel):
            self.cancel_event = cancel

        def __enter__(self):
            self.entered.set()
            assert self.cancel_event.wait(5)
            raise AdapterError("RUNTIME_CANCELLED")

    owner = StartingOwner((True, True, True))
    picker = OpponentRandomizer(adapter_factory=lambda: owner)
    selected = []
    picker.selected.connect(selected.append)
    picker.start(documents(), "commander")
    drain(app, owner.entered.is_set)
    picker.cancel()
    drain(app, lambda: not picker.busy)
    assert owner.cancel_event.is_set() and owner.closed and not selected
