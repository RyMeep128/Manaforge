"""Generate a physical front/back alignment test independent of card projects."""
from reportlab.pdfgen import canvas

from constants import card_size_without_bleed_inch, page_sizes
from models import as_project_state
from util import mm_to_point


def _cross(pdf, x, y, radius=18):
    pdf.line(x - radius, y, x + radius, y)
    pdf.line(x, y - radius, x, y + radius)
    pdf.circle(x, y, radius, stroke=1, fill=0)
    pdf.circle(x, y, radius / 2, stroke=1, fill=0)


def _card_test_rects(width, height):
    """Return a centered 3x3 sheet of true-size MTG trim rectangles."""
    card_width, card_height = (dimension * 72
                               for dimension in card_size_without_bleed_inch)
    left = (width - 3 * card_width) / 2
    bottom = (height - 3 * card_height) / 2
    return [
        (left + column * card_width, bottom + row * card_height,
         card_width, card_height)
        for row in range(3) for column in range(3)
    ]


def _draw_card_tests(pdf, width, height, *, side):
    for index, (x, y, card_width, card_height) in enumerate(
            _card_test_rects(width, height), start=1):
        pdf.setLineWidth(0.7)
        pdf.rect(x, y, card_width, card_height)
        cut = mm_to_point(3)
        for corner_x, direction_x in ((x, -1), (x + card_width, 1)):
            pdf.line(corner_x, y - cut, corner_x, y + cut)
            pdf.line(corner_x, y + card_height - cut,
                     corner_x, y + card_height + cut)
            pdf.line(corner_x - direction_x * cut, y,
                     corner_x + direction_x * cut, y)
            pdf.line(corner_x - direction_x * cut, y + card_height,
                     corner_x + direction_x * cut, y + card_height)
        pdf.setFont('Helvetica-Bold', 11)
        label_offset = 50 if index == 5 else 5
        pdf.drawCentredString(x + card_width / 2,
                              y + card_height / 2 + label_offset,
                              f'{side} TEST CARD {index}')
        pdf.setFont('Helvetica', 8)
        pdf.drawCentredString(x + card_width / 2,
                              y + card_height / 2 + label_offset - 13,
                              'Trim size: 63 x 88 mm')


def _draw_page(pdf, width, height, *, side, dx=0, dy=0, duplex='Long edge',
               bleed_mm=0):
    pdf.saveState()
    pdf.translate(dx, dy)
    inset = mm_to_point(5)
    center_x, center_y = width / 2, height / 2
    pdf.setLineWidth(0.5)
    pdf.rect(inset, inset, width - 2 * inset, height - 2 * inset)
    for x, y in ((inset, inset), (inset, height - inset),
                 (width - inset, inset), (width - inset, height - inset)):
        _cross(pdf, x, y, radius=10)
    _cross(pdf, center_x, center_y, radius=12)

    _draw_card_tests(pdf, width, height, side=side)

    # A millimetre scale around the centre makes drift directly measurable.
    for millimetres in range(-10, 11):
        delta = mm_to_point(millimetres)
        tick = 8 if millimetres % 5 == 0 else 4
        pdf.line(center_x + delta, center_y - tick, center_x + delta, center_y + tick)
        pdf.line(center_x - tick, center_y + delta, center_x + tick, center_y + delta)
        if millimetres % 5 == 0:
            pdf.setFont('Helvetica', 7)
            pdf.drawCentredString(center_x + delta, center_y - 18, str(millimetres))
            pdf.drawRightString(center_x - 12, center_y + delta - 2, str(millimetres))

    pdf.setFont('Helvetica-Bold', 14)
    pdf.drawCentredString(center_x, height - inset - 24,
                          f'Manaforge calibration - {side}')
    pdf.setFont('Helvetica', 9)
    pdf.drawCentredString(
        center_x, inset + 12,
        f'Actual size / 100% | Duplex: {duplex} | '
        f'Back X {dx / mm_to_point(1):+.2f} mm, Y {dy / mm_to_point(1):+.2f} mm | '
        f'Configured bleed {float(bleed_mm):g} mm')
    # The asymmetric marker exposes an unexpected rotation by the print driver.
    arrow_x = width - inset - mm_to_point(8)
    arrow_y = height - inset - mm_to_point(15)
    pdf.setLineWidth(1.2)
    pdf.line(arrow_x, arrow_y, arrow_x, arrow_y + mm_to_point(10))
    pdf.line(arrow_x, arrow_y + mm_to_point(10), arrow_x - 5,
             arrow_y + mm_to_point(10) - 7)
    pdf.line(arrow_x, arrow_y + mm_to_point(10), arrow_x + 5,
             arrow_y + mm_to_point(10) - 7)
    pdf.setFont('Helvetica-Bold', 8)
    pdf.drawCentredString(arrow_x, arrow_y - 10, 'TOP')
    pdf.restoreState()


def generate_calibration_pdf(project_like, pdf_path, *, horizontal_mm=None,
                             vertical_mm=None):
    state = as_project_state(project_like)
    size = page_sizes[state.pagesize]
    if state.orient == 'Landscape':
        size = tuple(reversed(size))
    horizontal = float(state.backside_offset if horizontal_mm is None else horizontal_mm)
    vertical = float(state.backside_vertical_offset if vertical_mm is None else vertical_mm)
    output = canvas.Canvas(str(pdf_path), pagesize=size)
    _draw_page(output, *size, side='FRONT', duplex=state.printer_duplex,
               bleed_mm=state.bleed_edge)
    output.showPage()
    _draw_page(output, *size, side='BACK', dx=mm_to_point(horizontal),
               dy=mm_to_point(vertical), duplex=state.printer_duplex,
               bleed_mm=state.bleed_edge)
    output.showPage()
    output.save()
    return str(pdf_path)
