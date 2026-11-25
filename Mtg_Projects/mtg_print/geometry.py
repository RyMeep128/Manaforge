"""Physical dimensions in points/inches; no application configuration or Qt."""
from reportlab.lib.pagesizes import LETTER, A5, A4, A3, LEGAL

page_sizes = {"Letter": LETTER, "A5": A5, "A4": A4, "A3": A3, "Legal": LEGAL}
card_size_with_bleed_inch = (2.72, 3.7)
card_size_without_bleed_inch = (2.48, 3.46)
card_ratio = card_size_without_bleed_inch[0] / card_size_without_bleed_inch[1]
low_dpi_warning_threshold = 300


def sheet_capacity(state):
    """Use the same physical card dimensions for summaries and print editing."""
    width, height = page_sizes[state.pagesize]
    if state.orient == 'Landscape':
        width, height = height, width
    bleed = max(0, float(state.bleed_edge)) / 25.4
    card_width, card_height = (72 * (v + 2 * bleed) for v in card_size_without_bleed_inch)
    return int(width // card_width), int(height // card_height)


def mm_to_inch(mm):
    return mm * 0.0393701


def inch_to_point(inch):
    return inch * 72
