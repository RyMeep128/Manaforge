"""Shared offline rules browser; all file/network/database work runs off the UI."""
from mtg_ui.loading import LoadingRunnable
from html import escape
import re
from PyQt6 import QtCore as C, QtWidgets as W
from mtg_core.diagnostics import get_logger


class _Signals(C.QObject):
    ready = C.pyqtSignal(int, object, str)


class _Task(LoadingRunnable):
    def __init__(self, token, work, callback):
        super().__init__()
        self.token, self.work = token, work
        self.signals = _Signals()
        self.signals.ready.connect(callback, C.Qt.ConnectionType.QueuedConnection)

    def run(self):
        try:
            self.signals.ready.emit(self.token, self.work(), '')
        except Exception as exc:
            get_logger(__name__).exception('Rules reference operation failed')
            self.signals.ready.emit(self.token, None, str(exc))


def rule_html(row):
    """Escape downloaded text before adding local rule-number hyperlinks."""
    text = escape(row['body'])
    text = re.sub(r'\b([1-9]\d{2}\.\d+[a-z]?)\b',
                  lambda m: f'<a href="rule:{m[1]}">{m[1]}</a>', text)
    text = re.sub(r'\b(rule\s+)([1-9]\d{2})\b(?!\.)',
                  lambda m: m[1] + f'<a href="rule:{m[2]}">{m[2]}</a>', text, flags=re.I)
    return '<h3>' + escape(row['number']) + '</h3><p>' + text.replace('\n', '<br>') + '</p>'


class RulesBrowser(W.QDialog):
    def __init__(self, service, parent=None, *, query=''):
        super().__init__(parent)
        self.service = service
        self.token = 0
        self._closed = False
        self.offset = 0
        self.back_queries = []
        self.current_query = None
        self.rows = []
        self.setWindowTitle('Comprehensive Rules')
        self.resize(1200, 800)
        layout = W.QVBoxLayout(self)
        self.metadata = W.QLabel('Reading installed rules…')
        self.metadata.setTextFormat(C.Qt.TextFormat.PlainText)
        self.metadata.setWordWrap(True)
        layout.addWidget(self.metadata)
        search_row = W.QHBoxLayout()
        self.back = W.QPushButton('Back')
        self.back.setEnabled(False)
        self.back.clicked.connect(self.go_back)
        search_row.addWidget(self.back)
        self.query = W.QLineEdit(query)
        self.query.setPlaceholderText('Rule number (702.9), keyword, or text')
        self.query.setClearButtonEnabled(True)
        self.query.setEnabled(False)
        search_row.addWidget(self.query, 1)
        layout.addLayout(search_row)
        self.timer = C.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.search)
        self.query.textChanged.connect(self.schedule_search)
        self.query.returnPressed.connect(self.search)
        split = W.QSplitter()
        navigation = W.QTabWidget()
        self.sections = W.QTreeWidget()
        self.sections.setHeaderHidden(True)
        self.sections.itemClicked.connect(lambda item, column: self.navigate(item.data(0, C.Qt.ItemDataRole.UserRole)))
        navigation.addTab(self.sections, 'Sections')
        keywords = W.QWidget()
        keyword_layout = W.QVBoxLayout(keywords)
        self.keyword_filter = W.QLineEdit()
        self.keyword_filter.setPlaceholderText('Find keyword')
        self.keyword_filter.textChanged.connect(self.filter_keywords)
        keyword_layout.addWidget(self.keyword_filter)
        self.keywords = W.QListWidget()
        self.keywords.itemClicked.connect(lambda item: self.navigate(item.data(C.Qt.ItemDataRole.UserRole)))
        keyword_layout.addWidget(self.keywords)
        navigation.addTab(keywords, 'Keywords')
        split.addWidget(navigation)
        results = W.QWidget()
        results_layout = W.QVBoxLayout(results)
        self.results = W.QListWidget()
        self.results.currentRowChanged.connect(self.show_rule)
        results_layout.addWidget(self.results, 1)
        pages = W.QHBoxLayout()
        self.previous = W.QPushButton('Previous results')
        self.previous.clicked.connect(lambda: self.page(-1))
        pages.addWidget(self.previous)
        self.next = W.QPushButton('More results')
        self.next.clicked.connect(lambda: self.page(1))
        pages.addWidget(self.next)
        results_layout.addLayout(pages)
        split.addWidget(results)
        self.text = W.QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self.follow_link)
        split.addWidget(self.text)
        split.setSizes([240, 320, 620])
        layout.addWidget(split, 1)
        self.status = W.QLabel('Opening the browser does not download rules.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        actions = W.QHBoxLayout()
        self.update_button = W.QPushButton('Download / update from Wizards')
        self.update_button.clicked.connect(self.update_rules)
        actions.addWidget(self.update_button)
        self.import_button = W.QPushButton('Import rules TXT…')
        self.import_button.clicked.connect(self.import_rules)
        actions.addWidget(self.import_button)
        close = W.QPushButton('Close')
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.busy = False
        self.load_index()

    def submit(self, work, callback):
        self.token += 1
        C.QThreadPool.globalInstance().start(_Task(self.token, work, callback))

    def load_index(self):
        self.submit(self.service.rules_index, self.index_loaded)

    @C.pyqtSlot(int, object, str)
    def index_loaded(self, token, result, error):
        if self._closed or token != self.token:
            return
        self.busy = False
        self.update_button.setEnabled(True)
        self.import_button.setEnabled(True)
        if error:
            self.status.setText('Could not open rules cache. ' + error)
            return
        self.sections.clear()
        self.keywords.clear()
        self.query.setEnabled(True)
        metadata = result['metadata']
        if metadata is None:
            self.metadata.setText('No Comprehensive Rules snapshot installed')
            self.text.setPlainText('Download the official English rules or import a rules TXT file. After installation, reading and searching work offline.')
            self.results.clear()
            return
        self.metadata.setText(f"Effective: {metadata['effective_date']}  ·  Downloaded/imported (UTC): {metadata['fetched_at'][:19]}\n"
                              f"Source: {metadata['source']}  ·  SHA-256: {metadata['checksum'][:12]}  ·  Cache format 1")
        parents = {}
        for row in result['sections']:
            item = W.QTreeWidgetItem([row['number'] + '. ' + row['title']])
            item.setData(0, C.Qt.ItemDataRole.UserRole, row['number'])
            if row['kind'] == 'section':
                self.sections.addTopLevelItem(item)
                parents[row['number']] = item
            else:
                parent = parents.get(row['number'][0])
                if parent is not None:
                    parent.addChild(item)
                else:
                    self.sections.addTopLevelItem(item)
        for row in result['keywords']:
            item = W.QListWidgetItem(row['name'])
            item.setData(C.Qt.ItemDataRole.UserRole, row['number'])
            self.keywords.addItem(item)
        self.filter_keywords(self.keyword_filter.text())
        self.search()

    def schedule_search(self):
        if not self.busy:
            # Invalidate an in-flight search before the debounce finishes.
            self.token += 1
            self.timer.start()

    def search(self, *, remember=True):
        self.timer.stop()
        if self.busy or not self.query.isEnabled():
            return
        query = self.query.text().strip()
        if query != self.current_query:
            if remember and self.current_query is not None:
                self.back_queries.append(self.current_query)
            self.current_query, self.offset = query, 0
        self.back.setEnabled(bool(self.back_queries))
        service, offset = self.service, self.offset
        self.submit(lambda: service.search_rules(query, offset=offset), self.search_loaded)

    @C.pyqtSlot(int, object, str)
    def search_loaded(self, token, rows, error):
        if self._closed or token != self.token:
            return
        if error:
            self.status.setText('Could not search the local rules. ' + error)
            return
        self.rows = rows
        self.results.clear()
        for row in rows:
            summary = row['title'].replace('\n', ' ')
            self.results.addItem(row['number'] + '  ' + summary[:100])
        self.previous.setEnabled(self.offset > 0)
        self.next.setEnabled(len(rows) == 200)
        self.status.setText(f'{len(rows)} local results, starting at {self.offset + 1}.' if rows else 'No matching local rules.')
        if rows:
            self.results.setCurrentRow(0)
        else:
            self.text.setPlainText('No matching rules. Try a rule number, keyword, or fewer search terms.')

    def show_rule(self, index):
        if 0 <= index < len(self.rows):
            self.text.setHtml(rule_html(self.rows[index]))

    def navigate(self, query):
        blocker = C.QSignalBlocker(self.query)
        self.query.setText(query)
        del blocker
        self.search()

    def follow_link(self, url):
        if url.scheme() == 'rule':
            self.navigate(url.path())

    def go_back(self):
        if self.back_queries:
            query = self.back_queries.pop()
            blocker = C.QSignalBlocker(self.query)
            self.query.setText(query)
            del blocker
            self.search(remember=False)

    def page(self, delta):
        self.offset = max(0, self.offset + delta * 200)
        self.search()

    def filter_keywords(self, query):
        for i in range(self.keywords.count()):
            item = self.keywords.item(i)
            item.setHidden(query.casefold() not in item.text().casefold())

    def update_rules(self):
        self.install(self.service.refresh_rules)

    def import_rules(self):
        path, _ = W.QFileDialog.getOpenFileName(self, 'Import Comprehensive Rules', '', 'Text files (*.txt)')
        if path:
            service = self.service
            self.install(lambda: service.import_rules(path))

    def install(self, work):
        if self.busy:
            return
        self.timer.stop()
        self.busy = True
        self.update_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.status.setText('Installing rules in the background. Existing rules are kept if this fails.')
        self.submit(work, self.installed)

    @C.pyqtSlot(int, object, str)
    def installed(self, token, result, error):
        if self._closed or token != self.token:
            return
        if error:
            self.busy = False
            self.update_button.setEnabled(True)
            self.import_button.setEnabled(True)
            self.status.setText('Rules were not replaced. ' + error)
            return
        self.index_loaded(token, result, '')

    def done(self, result):
        self._closed = True
        self.token += 1
        self.timer.stop()
        super().done(result)
