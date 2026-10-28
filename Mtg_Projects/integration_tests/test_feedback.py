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
    report['title'] = 'A problem'
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
    assert service.submit(report, 'https://example.com/feedback', invite='test-invitation')['reference'] == '42'
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
    dialog._diag_started = True  # Keep collection scheduling out of synchronous UI contract tests.
    dialog.deleteLater()
    app.processEvents()


def complete_report():
    report = service.new_report('0.3.49-alpha.1')
    report.update(title='Cards disappear', description='After switching decks.')
    return report


def test_local_status_and_prepared_logs_are_never_uploaded():
    report = complete_report()
    report.update(status='failed', reference='17', diagnostic_attachment='private local logs')
    payload = service.validate_report(report)
    assert 'status' not in payload
    assert 'reference' not in payload
    assert 'diagnostic_attachment' not in payload
    assert payload['diagnostics'] == ''


def test_failed_report_keeps_attachments_and_identity_after_restart(tmp_path):
    report = complete_report()
    report.update(status='failed', diagnostic_attachment='prepared locally', diagnostics='approved logs', screenshot='iVBORw0KGgo=')
    service.Store(tmp_path).save(report)
    loaded = list(service.Store(tmp_path).reports())[0]
    assert loaded == report
    assert service.validate_report(loaded)['id'] == report['id']


def test_submitted_report_does_not_make_network_request(monkeypatch):
    report = complete_report()
    report.update(status='submitted', reference='42')
    monkeypatch.setattr(service, 'build_opener', lambda *args: pytest.fail('Already sent'))
    assert service.submit(report, 'https://example.com/feedback', invite='test-invitation')['reference'] == '42'


@pytest.mark.parametrize('field,limit', [('description', 12000), ('steps', 8000), ('diagnostics', 50000)])
def test_client_matches_relay_field_limits(field, limit):
    report = complete_report()
    report[field] = 'x' * (limit + 1)
    with pytest.raises(ValueError, match='too long'):
        service.validate_report(report)


def test_diagnostic_collection_bounds_and_redacts_previous_logs(tmp_path, monkeypatch):
    from mtg_core import paths
    monkeypatch.setattr(service, 'core_data_root', lambda: tmp_path)
    monkeypatch.setattr(paths, 'data_root', lambda: tmp_path)
    logs = tmp_path / 'logs'
    logs.mkdir()
    (logs / 'downloads-previous.log').write_bytes(b'x' * 10000 + b' token=hidden person@example.com')
    result = service.collect_diagnostics('0.3.49-alpha.1', detail='password=private')
    assert len(result) <= 50000
    assert 'hidden' not in result
    assert 'person@example.com' not in result
    assert 'password=private' not in result


def test_dialog_collects_diagnostics_asynchronously_and_feature_excludes_them(monkeypatch):
    from PyQt6 import QtWidgets as W
    from mtg_ui.feedback import FeedbackDialog
    app = W.QApplication.instance() or W.QApplication([])
    dialog = FeedbackDialog()
    work = []
    monkeypatch.setattr(dialog.diagnostic_jobs, 'submit', lambda fn: work.append(fn))
    dialog.category_changed()
    assert len(work) == 1
    dialog.diagnostics_outcome('diagnostics', 'completed', 'sanitized logs')
    assert dialog.diagnostic_text == 'sanitized logs'
    assert not dialog.attach.isChecked()
    dialog.attach.setChecked(True)
    assert dialog.collect()['diagnostics'] == 'sanitized logs'
    dialog.category.setCurrentIndex(1)
    assert dialog.collect()['diagnostics'] == ''
    assert dialog.collect()['diagnostic_attachment'] == 'sanitized logs'
    dialog._diag_started = True  # Keep collection scheduling out of synchronous UI contract tests.
    dialog.deleteLater()
    app.processEvents()


def test_background_diagnostic_failure_does_not_block_basic_feedback():
    from PyQt6 import QtWidgets as W
    from mtg_ui.feedback import FeedbackDialog
    app = W.QApplication.instance() or W.QApplication([])
    dialog = FeedbackDialog()
    dialog.diagnostics_outcome('diagnostics', 'failed', 'permission denied')
    dialog.fields['title'].setText('A bug')
    dialog.fields['description'].setPlainText('Something happened')
    assert service.validate_report(dialog.collect())['diagnostics'] == ''
    dialog._diag_started = True  # Keep collection scheduling out of synchronous UI contract tests.
    dialog.deleteLater()
    app.processEvents()


def test_dialog_failure_saves_report_without_showing_network_exception(tmp_path):
    from PyQt6 import QtWidgets as W
    from mtg_ui.feedback import FeedbackDialog
    app = W.QApplication.instance() or W.QApplication([])
    dialog = FeedbackDialog(diagnostics='sanitized attachment')
    dialog.store = service.Store(tmp_path)
    dialog.fields['title'].setText('Printing failed')
    dialog.fields['description'].setPlainText('The printer stopped')
    dialog.attach.setChecked(True)
    report_id = dialog.report['id']
    dialog.outcome('send', 'failed', 'Traceback: sensitive socket exception')
    loaded = list(service.Store(tmp_path).reports())[0]
    assert loaded['status'] == 'failed'
    assert loaded['id'] == report_id
    assert loaded['diagnostics'] == 'sanitized attachment'
    assert 'Traceback' not in dialog.notice.text()
    assert loaded['last_error'] == dialog.failure_notice.text()
    dialog.save()
    assert dialog.failure_notice.text() == loaded['last_error']
    reopened = FeedbackDialog(report=loaded)
    assert reopened.failure_notice.text() == loaded['last_error']
    reopened._diag_started = True
    reopened.deleteLater()
    dialog._diag_started = True  # Keep collection scheduling out of synchronous UI contract tests.
    dialog.deleteLater()
    app.processEvents()


def test_legacy_draft_loads_without_lifecycle_fields(tmp_path):
    report = complete_report()
    del report['status']
    service.Store(tmp_path).save(report)
    loaded = list(service.Store(tmp_path).reports())[0]
    assert loaded.get('status', 'draft') == 'draft'
    assert service.validate_report(loaded)['id'] == report['id']


def test_total_encoded_payload_limit_includes_unicode_expansion():
    report = complete_report()
    report['diagnostics'] = '\U0001f600' * 50000
    with pytest.raises(ValueError, match='too large'):
        service.validate_report(report)


def test_missing_invitation_explains_setup_without_network(monkeypatch):
    monkeypatch.delenv('MANAFORGE_FEEDBACK_INVITE', raising=False)
    monkeypatch.setattr(service, 'build_opener', lambda *args: pytest.fail('Must not send without invitation'))
    with pytest.raises(ValueError, match='invitation is not configured'):
        service.submit(complete_report(), 'https://example.com/feedback')
