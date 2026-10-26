"""Feedback persistence and transport contracts; executed by GitHub CI."""
import json
import pytest
from mtg_ui import feedback_service as service


def test_drafts_survive_restart_and_delete(tmp_path):
    report = service.new_report('0.3.2-alpha.1', 'Print export', 'token=secret')
    service.Store(tmp_path).save(report)
    loaded = list(service.Store(tmp_path).reports())
    assert loaded == [report]
    assert 'secret' not in report['description']
    service.Store(tmp_path).delete(report['id'])
    assert list(service.Store(tmp_path).reports()) == []


def test_store_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        service.Store(tmp_path).delete('../other')


@pytest.mark.parametrize('url', ['', 'http://example.com', 'https://user:pass@example.com', 'https://example.com?token=x'])
def test_transport_requires_safe_https(url, monkeypatch):
    monkeypatch.delenv('MANAFORGE_FEEDBACK_URL', raising=False)
    with pytest.raises(ValueError):
        service.submit(service.new_report('0.3.2-alpha.1'), endpoint=url)


def test_transport_redacts_and_preserves_stable_id(monkeypatch):
    report = service.new_report('0.3.2-alpha.1')
    report['description'] = 'password=verysecret person@example.com'
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            return json.dumps(dict(id=report['id'], reference='42')).encode()
    class Opener:
        def open(self, request, timeout):
            requests.append(json.loads(request.data))
            return Response()
    monkeypatch.setattr(service, 'build_opener', lambda *args: Opener())
    assert service.submit(report, 'https://example.com/feedback')['reference'] == '42'
    assert requests[0]['id'] == report['id']
    assert 'verysecret' not in requests[0]['description']
    assert 'person@example.com' not in requests[0]['description']
    assert 'verysecret' in report['description']


def test_dialog_defaults_to_no_diagnostic_consent():
    from PyQt6 import QtWidgets as W
    app = W.QApplication.instance() or W.QApplication([])
    from mtg_ui.feedback import FeedbackDialog
    dialog = FeedbackDialog(diagnostics='private diagnostic information')
    assert not dialog.attach.isChecked()
    assert dialog.collect()['diagnostics'] == ''
    dialog.attach.setChecked(True)
    assert dialog.collect()['diagnostics'] == 'private diagnostic information'
    dialog.deleteLater()
    app.processEvents()
