from PyQt6 import QtCore, QtGui
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPrintSupport import QPrinter


PAGE_SIZE_IDS = {
    'Letter': QtGui.QPageSize.PageSizeId.Letter,
    'Legal': QtGui.QPageSize.PageSizeId.Legal,
    'A5': QtGui.QPageSize.PageSizeId.A5,
    'A4': QtGui.QPageSize.PageSizeId.A4,
    'A3': QtGui.QPageSize.PageSizeId.A3,
}


def configure_printer(printer, state):
    page_id = PAGE_SIZE_IDS.get(state.pagesize, QtGui.QPageSize.PageSizeId.Letter)
    printer.setPageSize(QtGui.QPageSize(page_id))
    orientation = (
        QtGui.QPageLayout.Orientation.Landscape
        if state.orient == 'Landscape'
        else QtGui.QPageLayout.Orientation.Portrait)
    printer.setPageOrientation(orientation)
    duplex = {
        'Long edge': QPrinter.DuplexMode.DuplexLongSide,
        'Short edge': QPrinter.DuplexMode.DuplexShortSide,
        'Off': QPrinter.DuplexMode.DuplexNone,
    }.get(state.printer_duplex, QPrinter.DuplexMode.DuplexLongSide)
    printer.setDuplex(duplex)
    printer.setFullPage(True)
    supported = sorted(set(printer.supportedResolutions()))
    usable = [resolution for resolution in supported if resolution <= 600]
    if usable:
        printer.setResolution(usable[-1])


def selected_page_indexes(printer, page_count):
    first, last = printer.fromPage(), printer.toPage()
    if first <= 0 or last <= 0:
        indexes = list(range(page_count))
    else:
        indexes = list(range(max(0, first - 1), min(page_count, last)))
    if printer.pageOrder() == QPrinter.PageOrder.LastPageFirst:
        indexes.reverse()
    return indexes


def pdf_page_count(pdf_path):
    document = QPdfDocument(None)
    error = document.load(str(pdf_path))
    if error != QPdfDocument.Error.None_:
        raise ValueError(f'Could not load the generated print document ({error.name}).')
    count = document.pageCount()
    document.close()
    return count


def print_pdf(pdf_path, printer):
    document = QPdfDocument(None)
    error = document.load(str(pdf_path))
    if error != QPdfDocument.Error.None_:
        raise ValueError(f'Could not load the generated print document ({error.name}).')
    indexes = selected_page_indexes(printer, document.pageCount())
    if not indexes:
        raise ValueError('The selected page range contains no printable pages.')
    painter = QtGui.QPainter()
    if not painter.begin(printer):
        raise OSError('The printer did not accept the print job.')
    try:
        for position, page_index in enumerate(indexes):
            if position and not printer.newPage():
                raise OSError('The printer could not start the next page.')
            rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            pixel_size = rect.size().toSize()
            image = document.render(page_index, pixel_size)
            if image.isNull():
                raise OSError(f'Could not render print page {page_index + 1}.')
            painter.drawImage(rect, image)
    finally:
        painter.end()
        document.close()
    return len(indexes)
