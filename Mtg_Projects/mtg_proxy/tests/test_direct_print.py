import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6 import QtWidgets
from PyQt6.QtPrintSupport import QPrinter
from reportlab.pdfgen import canvas

from direct_print_dialog import DirectPrintOptionsDialog
from models import ProjectState
from services import direct_print_service


APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _source_pdf(path, pages=3):
    output = canvas.Canvas(str(path))
    for number in range(1, pages + 1):
        output.drawString(72, 720, f'Page {number}')
        output.showPage()
    output.save()


def test_direct_print_renders_selected_page_range_to_qt_printer(tmp_path):
    source = tmp_path / 'source.pdf'
    destination = tmp_path / 'printed.pdf'
    _source_pdf(source)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(destination))
    printer.setFromTo(2, 3)

    printed = direct_print_service.print_pdf(source, printer)

    assert printed == 2
    assert destination.exists()
    assert direct_print_service.pdf_page_count(destination) == 2


def test_direct_print_options_disable_back_choices_without_backs():
    dialog = DirectPrintOptionsDialog(None, backs_enabled=False)
    assert dialog.page_side() == 'front'
    assert not dialog.side.model().item(0).isEnabled()
    assert not dialog.side.model().item(2).isEnabled()
    dialog.close()
    dialog.deleteLater()
    APP.processEvents()


def test_configure_printer_applies_project_page_and_duplex():
    state = ProjectState()
    state.pagesize = 'A4'
    state.orient = 'Landscape'
    state.printer_duplex = 'Short edge'
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)

    direct_print_service.configure_printer(printer, state)

    assert printer.pageLayout().orientation().name == 'Landscape'
    assert printer.pageLayout().pageSize().id().name == 'A4'
    assert printer.duplex() == QPrinter.DuplexMode.DuplexShortSide
