from pathlib import Path
import urllib.error
from PyQt6 import QtCore as C, QtGui as G, QtWidgets as W
from mtg_editor.card_views import ImageReader, Thumbnails


def image_bytes():
    image = G.QImage(600, 840, G.QImage.Format.Format_RGB32)
    image.fill(G.QColor('green'))
    data = C.QByteArray()
    buffer = C.QBuffer(data)
    buffer.open(C.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(data)


def test_exact_asset_precedes_printing_cache_and_decodes_small():
    calls = []
    class Service:
        def get_image_bytes(self, asset):
            calls.append(asset)
            return image_bytes()
        def get_image_path(self, card):
            raise AssertionError('Exact art must win')
    results = []
    reader = ImageReader(Service(), ('card', 'chosen-art'), None)
    reader.loaded.connect(lambda key, image: results.append(image))
    reader.run()
    assert calls == ['chosen-art']
    assert results[0].size() == C.QSize(300, 420)


def test_missing_cached_image_downloads_only_that_printing(tmp_path):
    path = tmp_path / 'card.png'
    path.write_bytes(image_bytes())
    calls = []
    class Service:
        def get_image_path(self, card):
            return None
        def ensure_image(self, card, allow_remote):
            calls.append((card, allow_remote))
            return str(path)
    results = []
    reader = ImageReader(Service(), ('exact-print', None), None)
    reader.loaded.connect(lambda key, image: results.append(image))
    reader.run()
    assert calls == [('exact-print', True)]
    assert not results[0].isNull()


def test_rate_limit_retry_after_is_preserved_through_wrapped_error():
    class Service:
        def get_image_path(self, card):
            try:
                raise urllib.error.HTTPError('https://example.invalid', 429, 'limited', {'Retry-After': '120'}, None)
            except urllib.error.HTTPError as exc:
                raise OSError('download failed') from exc
    errors = []
    reader = ImageReader(Service(), ('card', None), None)
    reader.failed.connect(lambda key, error, delay: errors.append(delay))
    reader.run()
    assert errors == [120]


def test_cache_bound_stale_queue_and_explicit_retry():
    app = W.QApplication.instance() or W.QApplication([])
    cache = Thumbnails(object())
    image = G.QImage(30, 42, G.QImage.Format.Format_RGB32)
    for i in range(200):
        cache.loaded((str(i), None), image)
    assert len(cache.cache) == 128
    cache.pending[('old', None)] = None
    cache.pending[('new', None)] = None
    cache.set_visible('deck', [('new', None)])
    assert list(cache.pending) == [('new', None)]
    cache.errors[('199', None)] = 'failure'
    cache.retry('199')
    assert ('199', None) not in cache.errors
    assert ('199', None) not in cache.cache
    cache.stop()
