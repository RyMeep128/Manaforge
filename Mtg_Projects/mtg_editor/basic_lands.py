"""Resolve automatic basics without blocking card edits or creating undo steps."""
from copy import deepcopy
from time import monotonic

from PyQt6 import QtCore as C
from mtg_core.basic_lands import AUTOMATION, MANAGED_COPIES, BASICS, reconcile_basic_lands
from mtg_core.diagnostics import get_logger
from .organization import card_facts
from .tasks import Task


class AutomaticBasicLands(C.QObject):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.templates = {}
        self.retry_after = {}
        self.worker = None
        self.observed_state = None
        self.timer = C.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.resolve)

    def hydrate(self):
        changed = False
        for entry in self.editor.document.deck.entries:
            payload = self.templates.get(entry.name)
            if payload and entry.extras.get(MANAGED_COPIES) and not entry.card_id:
                entry.card_id = payload['id']
                entry.oracle_id = payload.get('oracle_id')
                entry.set_code = payload.get('set')
                entry.collector_number = payload.get('collector_number')
                entry.extras['facts'] = card_facts(payload)
                changed = True
        return changed

    def missing(self):
        return sorted(name for name in BASICS.values() if name not in self.templates
                      and self.retry_after.get(name, 0) <= monotonic())

    def changed(self):
        if self.editor.closing:
            return
        state = (self.editor.document.deck.deck_id, self.editor.document.deck.extras.get(AUTOMATION, False) is True)
        if self.observed_state is not None and self.observed_state[0] == state[0] and self.observed_state != state:
            self.editor.statusBar().showMessage('Automatic basic lands restored.' if state[1] else
                'Automatic basic lands stopped because a land was removed. Undo restores automation.', 8000)
        self.observed_state = state
        if not state[1]:
            self.timer.stop()
            return
        self.hydrate()
        reconcile_basic_lands(self.editor.document, self.templates)
        if self.worker is None and self.missing():
            self.timer.start()

    def resolve(self):
        if (self.editor.closing or self.worker is not None
                or self.editor.document.deck.extras.get(AUTOMATION, False) is not True):
            return
        names = self.missing()
        service = self.editor.service
        if not names or not callable(getattr(service, 'get_card', None)):
            return
        for name in names:
            self.retry_after[name] = monotonic() + 60
        def load():
            payloads, missing = {}, []
            for name in names:
                try:
                    payload = service.get_card(exact_name=name)
                    if not payload and callable(getattr(service, 'fetch_missing_card', None)):
                        payload = service.fetch_missing_card(exact_name=name)
                    if not payload or not payload.get('id') or 'Basic' not in (payload.get('type_line') or '').split():
                        missing.append(name)
                    else:
                        payloads[name] = deepcopy(payload)
                except Exception:
                    get_logger(__name__).exception('Could not resolve automatic basic land %s', name)
                    missing.append(name)
            return payloads, missing
        self.worker = Task(load, self, operation='automatic basic land metadata')
        self.worker.completed.connect(self.completed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def completed(self, result, error):
        if self.editor.closing:
            return
        payloads, missing = result if not error else ({}, self.missing())
        self.templates.update(payloads)
        self.hydrate()
        if payloads:
            self.editor.changed()
        if missing or error:
            self.editor.statusBar().showMessage('Automatic basics are waiting for legal catalog data for '
                                               + (', '.join(missing) if missing else 'some lands') + '.', 8000)

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.changed()

    def stop(self):
        self.timer.stop()
