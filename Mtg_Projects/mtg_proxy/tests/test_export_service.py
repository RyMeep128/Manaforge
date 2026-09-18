import json
import zipfile

from PyQt6 import QtCore, QtGui
from reportlab.pdfgen import canvas

from models import ProjectState
from services import export_service


def test_rasterize_pdf_writes_deterministic_png_pages(tmp_path):
    pdf_path = tmp_path / 'source.pdf'
    output = canvas.Canvas(str(pdf_path), pagesize=(144, 72))
    output.drawString(10, 20, 'one')
    output.showPage()
    output.drawString(10, 20, 'two')
    output.showPage()
    output.save()

    paths = export_service._rasterize(
        pdf_path, tmp_path / 'images', 'sheet', dpi=144)

    assert [path.split('\\')[-1] for path in paths] == [
        'sheet_001.png', 'sheet_002.png']
    image = QtGui.QImage(paths[0])
    assert image.size() == QtCore.QSize(288, 144)


def test_individual_export_includes_unique_front_and_back(tmp_path, monkeypatch):
    source = tmp_path / 'source.png'
    image = QtGui.QImage(63, 88, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtCore.Qt.GlobalColor.green)
    assert image.save(str(source), 'PNG')
    state = ProjectState.from_dict({
        'cards': {'front.png': 2}, 'backside_enabled': True,
        'backsides': {'front.png': 'back.png'},
    })
    monkeypatch.setattr(
        export_service.runtime_images, 'get_processed_path',
        lambda state, name: str(source))

    paths = export_service.export_individual_cards(state, tmp_path / 'cards')

    assert sorted(path.split('\\')[-1] for path in paths) == [
        'back_back.png', 'front_front.png']


def test_zip_contains_manifest_sheets_and_cards(tmp_path, monkeypatch):
    state = ProjectState.from_dict({'cards': {'front.png': 1}})

    def sheets(state, output, print_fn, **kwargs):
        path = output / 'sheet_001.png'
        output.mkdir(parents=True)
        path.write_bytes(b'sheet')
        return [str(path)]

    def cards(state, output, **kwargs):
        path = output / 'front_front.png'
        output.mkdir(parents=True)
        path.write_bytes(b'card')
        return [str(path)]

    monkeypatch.setattr(export_service, 'export_sheets', sheets)
    monkeypatch.setattr(export_service, 'export_individual_cards', cards)

    result = export_service.export_zip(state, tmp_path / 'package.zip', dpi=600)

    with zipfile.ZipFile(result) as archive:
        assert archive.namelist() == [
            'cards/front_front.png', 'manifest.json', 'sheets/sheet_001.png']
        manifest = json.loads(archive.read('manifest.json'))
    assert manifest['dpi'] == 600
    assert manifest['sheet_files'] == ['sheets/sheet_001.png']
