import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6 import QtWidgets
import pytest

from calibration_dialog import PrinterCalibrationDialog
from models import ProjectState
from services import calibration_service, printer_profiles


APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_calibration_pdf_has_front_and_offset_back(monkeypatch, tmp_path):
    instances = []
    class Canvas:
        def __init__(self, path, pagesize):
            self.path, self.pagesize, self.translations, self.pages = path, pagesize, [], 0
            instances.append(self)
        def translate(self, x, y): self.translations.append((x, y))
        def showPage(self): self.pages += 1
        def save(self): pass
        def __getattr__(self, name): return lambda *args, **kwargs: None
    monkeypatch.setattr(calibration_service.canvas, 'Canvas', Canvas)
    state = ProjectState.from_dict({
        'pagesize': 'Letter', 'backside_offset': '1.5',
        'backside_vertical_offset': '-2.25'})

    calibration_service.generate_calibration_pdf(state, tmp_path / 'calibration.pdf')

    assert instances[0].pages == 2
    assert instances[0].translations[0] == (0, 0)
    from util import mm_to_point
    assert instances[0].translations[1] == (
        mm_to_point(1.5), mm_to_point(-2.25))


def test_calibration_card_targets_use_manaforge_trim_size():
    from constants import card_size_without_bleed_inch, page_sizes

    rectangles = calibration_service._card_test_rects(*page_sizes['Letter'])

    assert len(rectangles) == 9
    assert all(rectangle[2:] == tuple(
        dimension * 72 for dimension in card_size_without_bleed_inch)
        for rectangle in rectangles)


@pytest.mark.parametrize('paper', ['Letter', 'A4'])
@pytest.mark.parametrize('orientation', ['Portrait', 'Landscape'])
@pytest.mark.parametrize('duplex', ['Long edge', 'Short edge'])
def test_calibration_matrix_preserves_paper_orientation_and_duplex(
        monkeypatch, tmp_path, paper, orientation, duplex):
    from constants import page_sizes
    instances = []

    class Canvas:
        def __init__(self, path, pagesize):
            self.pagesize = pagesize
            self.labels = []
            self.pages = 0
            instances.append(self)

        def drawCentredString(self, x, y, text):
            self.labels.append(text)

        def showPage(self):
            self.pages += 1

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    monkeypatch.setattr(calibration_service.canvas, 'Canvas', Canvas)
    state = ProjectState.from_dict({
        'pagesize': paper, 'orient': orientation,
        'printer_duplex': duplex, 'backside_enabled': True,
    })

    calibration_service.generate_calibration_pdf(
        state, tmp_path / f'{paper}-{orientation}-{duplex}.pdf')

    expected_size = page_sizes[paper]
    if orientation == 'Landscape':
        expected_size = tuple(reversed(expected_size))
    assert instances[0].pagesize == expected_size
    assert instances[0].pages == 2
    assert sum(f'Duplex: {duplex}' in label for label in instances[0].labels) == 2
    assert any('FRONT TEST CARD 5' == label for label in instances[0].labels)
    assert any('BACK TEST CARD 5' == label for label in instances[0].labels)


def test_calibration_dialog_applies_and_saves_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(printer_profiles, 'path', lambda: tmp_path / 'profiles.json')
    state = ProjectState()
    dialog = PrinterCalibrationDialog(None, state)
    dialog.horizontal.setValue(-1.2)
    dialog.vertical.setValue(0.8)
    dialog.profile_name.setText('Desk printer')

    dialog.apply_and_save_profile()

    assert state.backside_offset == '-1.2'
    assert state.backside_vertical_offset == '0.8'
    saved = printer_profiles.load()['Desk printer']
    assert saved['backside_offset'] == '-1.2'
    assert saved['backside_vertical_offset'] == '0.8'
    dialog.close()
    dialog.deleteLater()
    APP.processEvents()
