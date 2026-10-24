from PyQt6 import QtCore as C, QtWidgets as W, QtTest

from mtg_ui.rules_reference import RulesBrowser, rule_html


class OfflineRules:
    def __init__(self):
        self.calls = []
        self.row = {'number': '702.9a', 'title': 'Flying',
                    'body': 'Flying refers to rule 100.1a. <unsafe>'}

    def rules_index(self):
        return {'metadata': {'effective_date': '2026-09-25', 'fetched_at': '2026-10-24T12:00:00+00:00',
                             'source': 'local fixture', 'checksum': 'a' * 64},
                'sections': [{'number': '7', 'title': 'Additional Rules', 'kind': 'section'},
                             {'number': '702', 'title': 'Keyword Abilities', 'kind': 'chapter'}],
                'keywords': [{'name': 'Flying', 'number': '702.9'}]}

    def search_rules(self, query='', *, offset=0):
        self.calls.append((query, offset))
        return [self.row]

    def refresh_rules(self):
        raise AssertionError('Opening must never download rules')


def test_browser_navigation_keywords_links_and_local_metadata(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    def synchronous(self, work, callback):
        self.token += 1
        callback(self.token, work(), '')
    monkeypatch.setattr(RulesBrowser, 'submit', synchronous)
    service = OfflineRules()
    dialog = RulesBrowser(service, query='Flying')
    assert service.calls == [('Flying', 0)]
    assert '2026-09-25' in dialog.metadata.text()
    assert dialog.keywords.count() == 1
    dialog.navigate('702.9')
    assert service.calls[-1] == ('702.9', 0)
    dialog.follow_link(C.QUrl('rule:100.1a'))
    assert service.calls[-1] == ('100.1a', 0)
    dialog.go_back()
    assert dialog.query.text() == '702.9'
    html = rule_html(service.row)
    assert 'href="rule:100.1a"' in html
    assert '&lt;unsafe&gt;' in html and '<unsafe>' not in html
    dialog.reject()
    app.processEvents()


def test_browser_explicit_failed_update_keeps_readable_rules(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    def synchronous(self, work, callback):
        self.token += 1
        try:
            result, error = work(), ''
        except Exception as exc:
            result, error = None, str(exc)
        callback(self.token, result, error)
    monkeypatch.setattr(RulesBrowser, 'submit', synchronous)
    dialog = RulesBrowser(OfflineRules())
    before = dialog.text.toPlainText()
    QtTest.QTest.mouseClick(dialog.update_button, C.Qt.MouseButton.LeftButton)
    assert 'not replaced' in dialog.status.text()
    assert dialog.text.toPlainText() == before
    assert dialog.update_button.isEnabled()
    dialog.reject()
    app.processEvents()
