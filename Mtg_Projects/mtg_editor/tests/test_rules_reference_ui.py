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
    dialog.information.setChecked(True)
    QtTest.QTest.mouseClick(dialog.update_button, C.Qt.MouseButton.LeftButton)
    assert 'not replaced' in dialog.status.text()
    assert dialog.text.toPlainText() == before
    assert dialog.update_button.isEnabled()
    dialog.reject()
    app.processEvents()


class ReadingRules(OfflineRules):
    def __init__(self):
        super().__init__()
        self.entries = [
            {'number': '702', 'title': 'Keyword Abilities', 'body': 'Keyword Abilities', 'kind': 'chapter'},
            {'number': '702.9', 'title': 'Flying', 'body': 'Flying', 'kind': 'rule'},
            {'number': '702.9a', 'title': 'Flying example',
             'body': 'Flying refers to rule 100.1a.\n\nExample: <unchanged> & complete.', 'kind': 'rule'},
        ]

    def search_rules(self, query='', *, offset=0):
        self.calls.append((query, offset))
        return [] if query == 'nothing' else self.entries[offset:offset + 200]


def open_reader(monkeypatch, service=None):
    def synchronous(self, work, callback):
        self.token += 1
        callback(self.token, work(), '')
    monkeypatch.setattr(RulesBrowser, 'submit', synchronous)
    return RulesBrowser(service or ReadingRules())


def test_heading_overview_complete_text_and_bidirectional_rule_history(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    dialog = open_reader(monkeypatch)
    assert 'In this section' in dialog.text.toPlainText()
    assert 'href="rule:702.9a"' in dialog.text.toHtml()
    dialog.results.setCurrentRow(2)
    assert '<unchanged> & complete.' in dialog.text.toPlainText()
    assert '702. Keyword Abilities' in dialog.breadcrumb.text()
    dialog.navigate('702')
    assert dialog.current_rule['number'] == '702'
    dialog.go_back()
    assert dialog.current_rule['number'] == '702.9a'
    assert dialog.results.currentRow() == 2
    assert dialog.query.text() == ''
    dialog.go_forward()
    assert dialog.current_rule['number'] == '702'
    assert dialog.query.text() == '702'
    dialog.go_back()
    dialog.results.setCurrentRow(1)
    assert not dialog.forward.isEnabled()
    dialog.reject()
    app.processEvents()


def test_live_search_preserves_reader_and_enter_opens_result(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    dialog = open_reader(monkeypatch)
    dialog.results.setCurrentRow(2)
    before = dialog.text.toPlainText()
    dialog.query.setText('nothing')
    dialog.search()
    assert dialog.text.toPlainText() == before
    assert 'No matching' in dialog.result_count.text()
    dialog.query.setText('Flying')
    dialog.search()
    assert dialog.current_rule['number'] == '702.9a'
    assert dialog.text.extraSelections()
    assert 'background-color' in dialog.results.item(1).text()
    dialog.open_search()
    assert dialog.current_rule['number'] == '702'
    dialog.reject()
    app.processEvents()


def test_reader_controls_restore_panels_and_escape_closes_disclosures(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    dialog = open_reader(monkeypatch)
    dialog.panel_actions[0].setChecked(False)
    dialog.focus_reader.setChecked(True)
    assert dialog.navigation.isHidden() and dialog.results_panel.isHidden()
    QtTest.QTest.keyClick(dialog, C.Qt.Key.Key_Escape)
    assert dialog.navigation.isHidden()
    assert not dialog.results_panel.isHidden()
    dialog.information.setChecked(True)
    QtTest.QTest.keyClick(dialog, C.Qt.Key.Key_Escape)
    assert dialog.details.isHidden()
    original = dialog.reader_size
    dialog.resize_reader(1)
    assert dialog.reader_size == original + 1
    assert dialog.text.horizontalScrollBarPolicy() == C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert dialog.text.lineWrapMode() == W.QTextEdit.LineWrapMode.WidgetWidth
    assert 'a' * 64 in dialog.metadata.text()
    dialog.reject()
    app.processEvents()


def test_stale_search_cannot_replace_new_results_and_no_match_has_guidance(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    dialog = open_reader(monkeypatch)
    rows = dialog.rows
    dialog.search_loaded(dialog.token - 1, [], '')
    assert dialog.rows is rows
    dialog.reject()
    empty = RulesBrowser(ReadingRules(), query='nothing')
    assert 'No matching rules' in empty.text.toPlainText()
    empty.reject()
    app.processEvents()


def test_card_lookup_is_a_distinct_escape_dismissible_control(monkeypatch):
    from mtg_home.rules_workspace import RulesWorkspace
    app = W.QApplication.instance() or W.QApplication([])
    # Install the same offline callback used for the shared dialog.
    seed = open_reader(monkeypatch)
    seed.reject()
    visits = []
    workspace = RulesWorkspace(ReadingRules(), lambda: visits.append('home'))
    assert workspace.card_panel.isHidden()
    workspace.card_toggle.setChecked(True)
    assert not workspace.card_panel.isHidden()
    QtTest.QTest.keyClick(workspace, C.Qt.Key.Key_Escape)
    assert workspace.card_panel.isHidden()
    assert visits == []
    workspace.reject()
    app.processEvents()


def test_reading_history_restores_scroll_without_querying_service(monkeypatch):
    app = W.QApplication.instance() or W.QApplication([])
    service = ReadingRules()
    service.entries[2]['body'] = '\n'.join(f'Example line {i}' for i in range(180))
    dialog = open_reader(monkeypatch, service)
    dialog.show()
    dialog.results.setCurrentRow(2)
    app.processEvents()
    scrollbar = dialog.text.verticalScrollBar()
    assert scrollbar.maximum() > 0
    scrollbar.setValue(scrollbar.maximum() // 2)
    position = scrollbar.value()
    dialog.results.setCurrentRow(0)
    calls = list(service.calls)
    dialog.go_back()
    app.processEvents()
    assert dialog.current_rule['number'] == '702.9a'
    assert scrollbar.value() == position
    assert service.calls == calls
    dialog.reject()
    app.processEvents()
