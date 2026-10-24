from concurrent.futures import ThreadPoolExecutor
import logging

import pytest

from mtg_core import diagnostics


@pytest.fixture
def isolated_diagnostics(tmp_path, monkeypatch):
    parent = logging.getLogger('manaforge')
    old_handlers, old_level = parent.handlers[:], parent.level
    for handler in old_handlers:
        parent.removeHandler(handler)
    monkeypatch.setattr(diagnostics, '_handler', None)
    monkeypatch.setattr(diagnostics, 'core_data_root', lambda: tmp_path)
    yield parent
    for handler in parent.handlers[:]:
        parent.removeHandler(handler)
        handler.close()
    for handler in old_handlers:
        parent.addHandler(handler)
    parent.setLevel(old_level)


def test_concurrent_initialization_has_one_rotating_log_with_traceback(tmp_path, isolated_diagnostics):
    with ThreadPoolExecutor(max_workers=8) as pool:
        loggers = list(pool.map(diagnostics.get_logger, ['worker'] * 20))
    assert len(isolated_diagnostics.handlers) == 1
    handler = isolated_diagnostics.handlers[0]
    assert handler.maxBytes == 5_000_000 and handler.backupCount == 3
    try:
        raise ValueError('test failure')
    except ValueError:
        loggers[0].exception('operation=read card_id=test-card')
    handler.flush()
    text = next((tmp_path / 'logs').glob('diagnostics-*.log')).read_text(encoding='utf-8')
    assert text.count('operation=read card_id=test-card') == 1
    assert 'Traceback' in text and 'ValueError: test failure' in text


def test_unwritable_log_falls_back_without_masking_operation(isolated_diagnostics, monkeypatch, caplog):
    def unavailable(*args, **kwargs):
        raise PermissionError('read-only directory')
    monkeypatch.setattr(diagnostics, 'RotatingFileHandler', unavailable)
    logger = diagnostics.get_logger('worker')
    logger.error('Original operation failed')
    assert 'using stderr' in caplog.text and 'Original operation failed' in caplog.text
