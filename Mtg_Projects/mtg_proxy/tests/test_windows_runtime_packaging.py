"""Qt must not load the legacy VC runtime bundled for Java."""
import importlib.util
from pathlib import Path
import sys

import pytest


@pytest.fixture
def helper():
    path = Path(__file__).resolve().parents[3] / 'tools/align_windows_runtime.py'
    spec = importlib.util.spec_from_file_location('align_windows_runtime', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_alignment_preserves_java_and_newer_python(helper, tmp_path, monkeypatch):
    internal = tmp_path / '_internal'
    qt = internal / 'PyQt6/Qt6/bin'
    java = internal / 'mtg_play/distribution/xmage/java/jre1.8.0_201/bin'
    qt.mkdir(parents=True)
    java.mkdir(parents=True)
    names = ('MSVCP140.dll', 'MSVCP140_1.dll', 'MSVCP140_2.dll',
             'VCRUNTIME140.dll', 'VCRUNTIME140_1.dll')
    for name in names:
        (qt / name).write_bytes(b'14.44')
        (java / name).write_bytes(b'14.10')
    (internal / 'MSVCP140.dll').write_bytes(b'14.10')
    (internal / 'VCRUNTIME140.dll').write_bytes(b'14.50')
    monkeypatch.setattr(helper, 'version', lambda path: tuple(map(int, path.read_text().split('.'))))

    helper.align(tmp_path)
    helper.align(tmp_path)  # Repeat builds must keep the same runtime selection.

    for name in names:
        expected = b'14.50' if name == 'VCRUNTIME140.dll' else b'14.44'
        assert (internal / name).read_bytes() == expected
        assert (java / name).read_bytes() == b'14.10'


def test_incomplete_qt_runtime_blocks_packaging(helper, tmp_path):
    with pytest.raises(ValueError, match='Qt runtime DLL is missing'):
        helper.align(tmp_path)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows DLL version resource')
def test_reads_qt_runtime_file_version(helper):
    import PyQt6

    runtime = Path(PyQt6.__file__).parent / 'Qt6/bin/MSVCP140.dll'
    assert helper.version(runtime) > (14, 10, 25008, 0)
