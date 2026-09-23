import logging
from types import SimpleNamespace

from PyQt6 import QtWidgets as W

from mtg_editor import card_details, card_views, decklist_dialogs, gui, project_browser


def fail(*args, **kwargs):
    raise RuntimeError('Local read failed')


def test_workers_preserve_tracebacks_context_and_concise_errors(monkeypatch, caplog):
    app = W.QApplication.instance() or W.QApplication([])
    for module in (card_details, card_views, decklist_dialogs, gui, project_browser):
        monkeypatch.setattr(module, 'get_logger', lambda name: logging.getLogger('worker-test.' + name))
    observed = []
    task = gui.Task(fail, operation='deck_insights', context={'deck_id': 'deck-123'})
    task.completed.connect(lambda result, error: observed.append(error))
    task.run()
    load = card_details.Load(1, fail, lambda token, result, error: observed.append(error),
                             context={'card_id': 'card-123'})
    load.run()
    reader = card_views.ImageReader(SimpleNamespace(get_image_bytes=fail), ('card-123', 'asset-456'), None)
    reader.failed.connect(lambda key, error, delay: observed.append(error))
    reader.run()
    monkeypatch.setattr(project_browser, 'project_catalog', fail)
    catalog = project_browser.CatalogWorker('deck-root', 'project-root', None)
    catalog.run()
    observed.extend(catalog.result[1])
    monkeypatch.setattr(decklist_dialogs, 'fetch_public_deck', fail)
    importer = decklist_dialogs.ImportWorker('', object(), False, public_url='https://example.com/deck/123')
    importer.run()
    observed.append(importer.error)
    assert observed == ['Local read failed'] * 5
    records = [record for record in caplog.records if record.name.startswith('worker-test.')]
    assert len(records) == 5 and all(r.exc_info and r.exc_info[2] for r in records)
    for context in ('deck_insights', 'deck-123', 'card-123', 'asset-456', 'project-root', '/deck/123'):
        assert context in caplog.text
    app.processEvents()


def test_cancelled_import_is_not_reported_as_failure(monkeypatch, caplog):
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(decklist_dialogs, 'resolve_decklist', fail)
    worker = decklist_dialogs.ImportWorker('', object(), False)
    worker.cancelled.set()
    worker.run()
    assert not caplog.records
    app.processEvents()


def test_invalid_source_url_does_not_mask_import_error(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    monkeypatch.setattr(decklist_dialogs, 'fetch_public_deck', fail)
    worker = decklist_dialogs.ImportWorker('', object(), False, public_url='https://[')
    worker.run()
    assert worker.error == 'Local read failed'
    app.processEvents()
