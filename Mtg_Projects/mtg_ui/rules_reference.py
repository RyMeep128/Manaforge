"""Shared offline rules browser; all file/network/database work runs off the UI."""
from mtg_ui.loading import LoadingRunnable
from html import escape
import re
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_ui.theme import COLORS, application_stylesheet
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


class RulePreview(W.QStyledItemDelegate):
    """Paint lightweight wrapped previews without allocating a widget per rule."""
    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        label = option.text
        option.text = ''
        style = option.widget.style() if option.widget else W.QApplication.style()
        style.drawControl(W.QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        doc = G.QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setDefaultStyleSheet(f"body {{color: {COLORS['text']};}} a {{color: {COLORS['accent_hover']};}}")
        doc.setHtml(label)
        doc.setTextWidth(max(60, option.rect.width() - 24))
        painter.save()
        painter.setClipRect(option.rect)
        painter.translate(option.rect.left() + 12, option.rect.top() + 8)
        doc.drawContents(painter)
        painter.restore()

    def sizeHint(self, option, index):
        doc = G.QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setHtml(index.data() or '')
        width = option.widget.viewport().width() if option.widget else 280
        doc.setTextWidth(max(60, width - 24))
        return C.QSize(180, int(doc.size().height()) + 16)


def highlighted(text, query):
    """Highlight plain text before inserting it into trusted presentation HTML."""
    terms = re.findall(r'[\w.]+', query)[:30]
    if not terms:
        return escape(text)
    pattern = re.compile('|'.join(re.escape(term) for term in sorted(terms, key=len, reverse=True)), re.I)
    parts, start = [], 0
    for match in pattern.finditer(text):
        parts.extend((escape(text[start:match.start()]),
                      '<span style="background-color:#385747;color:#ffffff">' + escape(match[0]) + '</span>'))
        start = match.end()
    return ''.join(parts) + escape(text[start:])


def rule_html(row):
    """Escape downloaded text before adding local rule-number hyperlinks."""
    text = escape(row['body'])
    text = re.sub(r'\b([1-9]\d{2}\.\d+[a-z]?)\b',
                  lambda m: f'<a href="rule:{m[1]}">{m[1]}</a>', text)
    text = re.sub(r'\b(rule\s+)([1-9]\d{2})\b(?!\.)',
                  lambda m: m[1] + f'<a href="rule:{m[2]}">{m[2]}</a>', text, flags=re.I)
    return '<h2>' + escape(row['number']) + '</h2><p>' + re.sub(r'(?m)^ +', lambda m: '&nbsp;' * len(m[0]), text).replace('\n\n', '</p><p>').replace('\n', '<br>') + '</p>'


class RulesBrowser(W.QDialog):
    def __init__(self, service, parent=None, *, query=''):
        super().__init__(parent)
        self.service = service
        self.setStyleSheet(application_stylesheet())
        self.token = 0
        self._closed = False
        self.offset = 0
        self.history = []
        self.history_position = -1
        self.current_rule = None
        self._open_result = True
        self.section_rows = []
        self.reader_size = 12
        self.current_query = None
        self.rows = []
        self.setWindowTitle('Comprehensive Rules')
        self.resize(1200, 800)
        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)
        layout.setSpacing(10)
        heading = W.QHBoxLayout()
        title = W.QLabel('Comprehensive Rules')
        title.setProperty('role', 'title')
        heading.addWidget(title, 1)
        self.effective = W.QLabel('Offline reference')
        self.effective.setProperty('role', 'subtitle')
        heading.addWidget(self.effective)
        layout.addLayout(heading)
        self.metadata = W.QLabel('Reading installed rules…')
        self.metadata.setTextFormat(C.Qt.TextFormat.PlainText)
        self.metadata.setWordWrap(True)
        self.metadata.setTextInteractionFlags(C.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details = W.QGroupBox('Rules information')
        details_layout = W.QVBoxLayout(self.details)
        details_layout.addWidget(self.metadata)
        self.details.hide()
        search_row = self.search_tools = W.QHBoxLayout()
        self.back = W.QPushButton('Back')
        self.back.setEnabled(False)
        self.back.clicked.connect(self.go_back)
        search_row.addWidget(self.back)
        self.forward = W.QPushButton('Forward')
        self.forward.setEnabled(False)
        self.forward.clicked.connect(self.go_forward)
        search_row.addWidget(self.forward)
        self.query = W.QLineEdit(query)
        self.query.setAccessibleName('Search Comprehensive Rules or jump to a rule')
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
        self.query.returnPressed.connect(self.open_search)
        split = self.split = W.QSplitter()
        navigation = self.navigation = W.QTabWidget()
        navigation.setMinimumWidth(160)
        self.sections = W.QTreeWidget()
        self.sections.setHeaderHidden(True)
        self.sections.setIndentation(16)
        self.sections.setHorizontalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sections.setWordWrap(True)
        self.sections.itemClicked.connect(lambda item, column: self.navigate(item.data(0, C.Qt.ItemDataRole.UserRole)))
        self.sections.itemActivated.connect(lambda item, column: self.navigate(item.data(0, C.Qt.ItemDataRole.UserRole)))
        navigation.addTab(self.sections, 'Sections')
        keywords = W.QWidget()
        keyword_layout = W.QVBoxLayout(keywords)
        self.keyword_filter = W.QLineEdit()
        self.keyword_filter.setPlaceholderText('Find keyword')
        self.keyword_filter.textChanged.connect(self.filter_keywords)
        keyword_layout.addWidget(self.keyword_filter)
        self.keywords = W.QListWidget()
        self.keywords.itemClicked.connect(lambda item: self.navigate(item.data(C.Qt.ItemDataRole.UserRole)))
        self.keywords.itemActivated.connect(lambda item: self.navigate(item.data(C.Qt.ItemDataRole.UserRole)))
        keyword_layout.addWidget(self.keywords)
        navigation.addTab(keywords, 'Keywords')
        split.addWidget(navigation)
        results = self.results_panel = W.QWidget()
        results_layout = W.QVBoxLayout(results)
        self.result_count = W.QLabel('Browse sections or search the rules')
        self.result_count.setWordWrap(True)
        results_layout.addWidget(self.result_count)
        self.results = W.QListWidget()
        self.results.setItemDelegate(RulePreview(self.results))
        self.results.setResizeMode(W.QListView.ResizeMode.Adjust)
        self.results.setVerticalScrollMode(W.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.results.setHorizontalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setStyleSheet(f"QListWidget::item:selected {{background:{COLORS['surface_selected']}; border-left:3px solid {COLORS['accent']};}} QListWidget::item:hover {{background:{COLORS['surface_hover']};}}")
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
        reader = W.QWidget()
        reader_layout = W.QVBoxLayout(reader)
        reader_layout.setContentsMargins(18, 0, 6, 0)
        self.breadcrumb = W.QLabel('Choose a section or search to start reading')
        self.breadcrumb.setWordWrap(True)
        self.breadcrumb.setProperty('role', 'subtitle')
        reader_layout.addWidget(self.breadcrumb)
        reader_tools = W.QHBoxLayout()
        self.previous_rule = W.QPushButton('Previous rule')
        self.previous_rule.clicked.connect(lambda: self.move_rule(-1))
        self.next_rule = W.QPushButton('Next rule')
        self.next_rule.clicked.connect(lambda: self.move_rule(1))
        reader_tools.addWidget(self.previous_rule)
        reader_tools.addWidget(self.next_rule)
        reader_tools.addStretch()
        for label, delta in [('A-', -1), ('A+', 1)]:
            button = W.QPushButton(label)
            button.setAccessibleName('Decrease reader font size' if delta < 0 else 'Increase reader font size')
            button.clicked.connect(lambda checked=False, d=delta: self.resize_reader(d))
            reader_tools.addWidget(button)
        reader_layout.addLayout(reader_tools)
        self.text = W.QTextBrowser()
        self.text.setLineWrapMode(W.QTextEdit.LineWrapMode.WidgetWidth)
        self.text.setHorizontalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text.setFrameShape(W.QFrame.Shape.NoFrame)
        self.text.document().setDocumentMargin(16)
        self.resize_reader(0)
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self.follow_link)
        reader_layout.addWidget(self.text, 1)
        split.addWidget(reader)
        split.setStretchFactor(2, 1)
        split.setCollapsible(2, False)
        split.setSizes([220, 300, 680])
        layout.addWidget(split, 1)
        self.status = W.QLabel('Opening the browser does not download rules.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(C.Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        actions = self.footer_actions = W.QHBoxLayout()
        view = W.QToolButton()
        view.setText('View')
        view.setPopupMode(W.QToolButton.ToolButtonPopupMode.InstantPopup)
        view_menu = W.QMenu(view)
        view.setMenu(view_menu)
        actions.addWidget(view)
        self.panel_actions = []
        for label, panel in [('Navigation', navigation), ('Rule browser', results)]:
            action = view_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(panel.setVisible)
            self.panel_actions.append(action)
        self.focus_reader = W.QPushButton('Expand reader')
        self.focus_reader.setCheckable(True)
        self.focus_reader.toggled.connect(self.set_reading_mode)
        actions.addWidget(self.focus_reader)
        actions.addStretch()
        information = self.information = W.QPushButton('Rules information')
        information.setCheckable(True)
        information.toggled.connect(self.details.setVisible)
        actions.addWidget(information)
        layout.addWidget(self.details)
        self.update_button = W.QPushButton('Download / update from Wizards')
        self.update_button.clicked.connect(self.update_rules)
        details_layout.addWidget(self.update_button)
        self.import_button = W.QPushButton('Import rules TXT…')
        self.import_button.clicked.connect(self.import_rules)
        details_layout.addWidget(self.import_button)
        close = W.QPushButton('Close')
        close.setAutoDefault(False)
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.busy = False
        for button in self.findChildren(W.QPushButton):
            button.setAutoDefault(False)
        self.shortcuts = []
        for sequence, callback in [('Alt+Left', self.go_back), ('Alt+Right', self.go_forward),
                                   ('Ctrl+F', self.query.setFocus)]:
            shortcut = G.QShortcut(G.QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
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
        self.navigation.setEnabled(True)
        self.results_panel.setEnabled(True)
        self.update_button.setEnabled(True)
        self.import_button.setEnabled(True)
        if error:
            self.status.setText('Could not open rules cache. ' + error)
            return
        section_blocker = C.QSignalBlocker(self.sections)
        keyword_blocker = C.QSignalBlocker(self.keywords)
        self.sections.clear()
        self.keywords.clear()
        self.query.setEnabled(True)
        self.section_rows = result['sections']
        metadata = result['metadata']
        if metadata is None:
            self.metadata.setText('No Comprehensive Rules snapshot installed')
            self.text.setPlainText('Download the official English rules or import a rules TXT file. After installation, reading and searching work offline.')
            self.results.clear()
            return
        self.effective.setText('Effective ' + metadata['effective_date'])
        self.metadata.setText(f"Effective: {metadata['effective_date']}  ·  Downloaded/imported (UTC): {metadata['fetched_at'][:19]}\n"
                              f"Source: {metadata['source']}  ·  SHA-256: {metadata['checksum']}  ·  Cache format 1")
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
        del section_blocker, keyword_blocker
        self.filter_keywords(self.keyword_filter.text())
        self.history.clear()
        self.history_position = -1
        self.update_history_buttons()
        self._open_result = True
        self.status.setText('Rules ready for offline reading.')
        self.search()

    def schedule_search(self):
        if not self.busy:
            # Invalidate an in-flight search before the debounce finishes.
            self.token += 1
            self.timer.start()

    def open_search(self):
        self._open_result = True
        self.search()

    def search(self):
        self.timer.stop()
        if self.busy or not self.query.isEnabled():
            return
        query = self.query.text().strip()
        if query != self.current_query:
            self.current_query, self.offset = query, 0
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
        blocker = C.QSignalBlocker(self.results)
        self.results.clear()
        for row in rows:
            body = row['body'].replace('\n', ' ')
            terms = re.findall(r'[\w.]+', self.current_query or '')
            hit = next((body.casefold().find(term.casefold()) for term in terms if term.casefold() in body.casefold()), 0)
            start = max(0, hit - 60)
            preview = ('...' if start else '') + body[start:start + 220] + ('...' if len(body) > start + 220 else '')
            label = f'<div style="color:{COLORS["text"]}">' + '<b>' + highlighted(row['number'], self.current_query or '') + '</b><br>' + highlighted(preview, self.current_query or '') + '</div>'
            item = W.QListWidgetItem(label)
            item.setData(C.Qt.ItemDataRole.UserRole, row['number'])
            item.setToolTip(row['number'] + ' ' + row['title'])
            item.setData(C.Qt.ItemDataRole.AccessibleTextRole, row['number'] + ' ' + preview)
            self.results.addItem(item)
        del blocker
        self.previous.setEnabled(self.offset > 0)
        self.next.setEnabled(len(rows) == 200)
        self.result_count.setText(f'{len(rows)} results ({self.offset + 1}-{self.offset + len(rows)})' if rows else 'No matching rules. Try a number or fewer words.')
        if rows and self._open_result:
            self.results.setCurrentRow(len(rows) - 1 if getattr(self, '_page_selection', 0) == -1 else 0)
            self._page_selection = 0
        else:
            number = self.current_rule['number'] if self.current_rule else None
            for index, row in enumerate(rows):
                if row['number'] == number:
                    blocker = C.QSignalBlocker(self.results)
                    self.results.setCurrentRow(index)
                    del blocker
                    break
        if not rows and self.current_rule is None:
            self.text.setPlainText('No matching rules. Try a rule number, keyword, or fewer search terms.')
        self._open_result = False
        self.highlight_reader()
        self.update_rule_buttons()

    def show_rule(self, index):
        if not 0 <= index < len(self.rows):
            return
        row = self.rows[index]
        self.save_scroll()
        state = {'row': row, 'query': self.current_query, 'offset': self.offset,
                 'rows': self.rows, 'index': index, 'scroll': 0}
        current = self.history[self.history_position] if self.history_position >= 0 else None
        if current and current['row']['number'] == row['number'] and current['query'] == self.current_query:
            self.render_rule(row)
            self.text.verticalScrollBar().setValue(current['scroll'])
            return
        else:
            self.history = self.history[:self.history_position + 1]
            self.history.append(state)
            self.history = self.history[-100:]
            self.history_position = len(self.history) - 1
        self.render_rule(row)
        self.update_history_buttons()

    def render_rule(self, row):
        self.current_rule = row
        number = row['number']
        ancestors = [section['number'] + '. ' + section['title'] for section in self.section_rows
                     if section['number'] == number[:1] or section['number'] == number.split('.')[0]]
        self.breadcrumb.setText(' > '.join(dict.fromkeys(ancestors + [number])))
        content = rule_html(row)
        if row.get('kind') in ('section', 'chapter'):
            children = [entry for entry in self.rows if entry['number'] != number
                        and entry['number'].startswith(number if len(number) == 1 else number + '.')][:8]
            content += '<h3>In this section</h3>' + ''.join(
                '<p><a href="rule:' + escape(entry['number']) + '">' + escape(entry['number']) + '</a>  '
                + escape(entry['title']) + '</p>' for entry in children)
            if not children:
                content += '<p>Choose a subsection in Navigation, or search for a rule number.</p>'
        if re.fullmatch(r'[1-9]\d{2}\.\d+', number):
            nested = [entry for entry in self.rows
                      if re.fullmatch(re.escape(number) + '[a-z]', entry['number'])]
            if nested:
                content += '<h3>Subrules</h3>' + ''.join(
                    '<div style="margin-left:18px">' + rule_html(entry) + '</div>' for entry in nested)
        self.text.setHtml(content)
        self.highlight_reader()
        self.update_rule_buttons()
        # Keep section/keyword selections aligned without triggering another search.
        section_blocker = C.QSignalBlocker(self.sections)
        keyword_blocker = C.QSignalBlocker(self.keywords)
        self.sections.clearSelection()
        self.keywords.clearSelection()
        iterator = W.QTreeWidgetItemIterator(self.sections)
        while iterator.value():
            item = iterator.value()
            if item.data(0, C.Qt.ItemDataRole.UserRole) == number.split('.')[0]:
                self.sections.setCurrentItem(item)
                if item.parent():
                    item.parent().setExpanded(True)
            iterator += 1
        for i in range(self.keywords.count()):
            item = self.keywords.item(i)
            key = item.data(C.Qt.ItemDataRole.UserRole)
            if number == key or number.startswith(key + '.') or re.fullmatch(re.escape(key) + '[a-z]', number):
                self.keywords.setCurrentItem(item)
                break

        del section_blocker, keyword_blocker

    def highlight_reader(self):
        selections = []
        for term in re.findall(r'[\w.]+', self.current_query or '')[:30]:
            cursor = G.QTextCursor(self.text.document())
            while True:
                cursor = self.text.document().find(term, cursor)
                if cursor.isNull():
                    break
                selection = W.QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format.setBackground(G.QColor('#385747'))
                selection.format.setForeground(G.QColor('#ffffff'))
                selections.append(selection)
        self.text.setExtraSelections(selections)

    def resize_reader(self, delta):
        self.reader_size = max(10, min(24, self.reader_size + delta))
        font = self.text.font()
        font.setPointSize(self.reader_size)
        self.text.setFont(font)
        self.text.setStyleSheet(f'QTextBrowser {{font-size:{self.reader_size}pt; background:{COLORS["surface"]}; border:0;}}')
        self.text.document().setDefaultStyleSheet(
            f"p {{line-height:145%; margin-bottom:16px;}} h2 {{color:{COLORS['accent_hover']};}} a {{color:{COLORS['accent_hover']};}}")

    def set_reading_mode(self, enabled):
        if enabled:
            self._panel_visibility = (self.navigation.isHidden(), self.results_panel.isHidden())
            self.navigation.hide()
            self.results_panel.hide()
        else:
            hidden = getattr(self, '_panel_visibility', (False, False))
            self.navigation.setVisible(not hidden[0])
            self.results_panel.setVisible(not hidden[1])
        for action, panel in zip(self.panel_actions, (self.navigation, self.results_panel)):
            blocker = C.QSignalBlocker(action)
            action.setChecked(not panel.isHidden())
            action.setEnabled(not enabled)
            del blocker
        self.focus_reader.setText('Restore panels' if enabled else 'Expand reader')

    def keyPressEvent(self, event):
        if event.key() == C.Qt.Key.Key_Escape and self.focus_reader.isChecked():
            self.focus_reader.setChecked(False)
            event.accept()
        elif event.key() == C.Qt.Key.Key_Escape and not self.details.isHidden():
            self.information.setChecked(False)
            event.accept()
        else:
            super().keyPressEvent(event)

    def move_rule(self, delta):
        index = self.results.currentRow() + delta
        if 0 <= index < len(self.rows):
            self.results.setCurrentRow(index)
        elif (delta > 0 and self.next.isEnabled()) or (delta < 0 and self.previous.isEnabled()):
            self._page_selection = -1 if delta < 0 else 0
            self._open_result = True
            self.page(delta)

    def update_rule_buttons(self):
        index = self.results.currentRow()
        self.previous_rule.setEnabled(index > 0 or self.previous.isEnabled())
        self.next_rule.setEnabled((0 <= index < len(self.rows) - 1) or self.next.isEnabled())

    def navigate(self, query):
        if self.busy:
            return
        self._open_result = True
        blocker = C.QSignalBlocker(self.query)
        self.query.setText(query)
        del blocker
        self.search()

    def follow_link(self, url):
        if url.scheme() == 'rule':
            self.navigate(url.path())

    def save_scroll(self):
        if 0 <= self.history_position < len(self.history):
            self.history[self.history_position]['scroll'] = self.text.verticalScrollBar().value()

    def update_history_buttons(self):
        self.back.setEnabled(self.history_position > 0)
        self.forward.setEnabled(self.history_position < len(self.history) - 1)

    def restore_history(self, delta):
        position = self.history_position + delta
        if self.busy or not 0 <= position < len(self.history):
            return
        self.save_scroll()
        self.timer.stop()
        self.token += 1
        self.history_position = position
        state = self.history[position]
        self.current_query, self.offset = state['query'], state['offset']
        blocker = C.QSignalBlocker(self.query)
        self.query.setText(self.current_query or '')
        del blocker
        self._open_result = False
        self.search_loaded(self.token, state['rows'], '')
        blocker = C.QSignalBlocker(self.results)
        self.results.setCurrentRow(state['index'])
        del blocker
        self.render_rule(state['row'])
        self.text.verticalScrollBar().setValue(state['scroll'])
        self.update_history_buttons()

    def go_back(self):
        self.restore_history(-1)

    def go_forward(self):
        self.restore_history(1)

    def page(self, delta):
        self._open_result = True
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
        self.query.setEnabled(False)
        self.navigation.setEnabled(False)
        self.results_panel.setEnabled(False)
        self.back.setEnabled(False)
        self.forward.setEnabled(False)
        self.update_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.previous_rule.setEnabled(False)
        self.next_rule.setEnabled(False)
        self.status.setText('Installing rules in the background. Existing rules are kept if this fails.')
        self.submit(work, self.installed)

    @C.pyqtSlot(int, object, str)
    def installed(self, token, result, error):
        if self._closed or token != self.token:
            return
        if error:
            self.busy = False
            self.query.setEnabled(True)
            self.navigation.setEnabled(True)
            self.results_panel.setEnabled(True)
            self.previous.setEnabled(self.offset > 0)
            self.next.setEnabled(len(self.rows) == 200)
            self.update_rule_buttons()
            self.update_history_buttons()
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
