import os
import io
from enum import Enum
from mtg_print import layout as print_layout
from functools import cache

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from util import inch_to_point, mm_to_inch, mm_to_point
from config import CFG
from constants import card_size_without_bleed_inch
from image import read_image, image_to_bytes, rotate_image, Rotation
from models import ProjectState, as_project_state
import runtime_images


class CrossSegment(Enum):
    TopLeft = (1, -1)
    TopRight = (-1, -1)
    BottomRight = (-1, 1)
    BottomLeft = (1, 1)


def draw_line(can, fx, fy, tx, ty, s=1):
    dash = [s, s]
    can.setLineWidth(s)

    # First layer
    can.setDash(dash)
    can.setStrokeColorRGB(0.75, 0.75, 0.75)
    can.line(fx, fy, tx, ty)

    # Second layer with phase offset
    can.setDash(dash, s)
    can.setStrokeColorRGB(0, 0, 0)
    can.line(fx, fy, tx, ty)


# Draws black-white dashed cross segment at `(x, y)`, with a width of `c`, and a thickness of `s`
def draw_cross(can, x, y, segment, c=6, s=1):
    (dx, dy) = segment.value
    (tx, ty) = (x + c * dx, y + c * dy)

    draw_line(can, x, y, tx, y, s)
    draw_line(can, x, y, x, ty, s)


def generate(print_dict, size, pdf_path, print_fn, *, page_side="both"):
    state = as_project_state(print_dict)
    backside_offset = mm_to_point(float(state.backside_offset))
    backside_vertical_offset = mm_to_point(float(state.backside_vertical_offset))

    bleed_edge = float(state.bleed_edge)
    has_bleed_edge = bleed_edge > 0

    b = 0
    if has_bleed_edge:
        b = mm_to_inch(bleed_edge)
    (w, h) = card_size_without_bleed_inch
    w, h = inch_to_point((w + 2 * b)), inch_to_point((h + 2 * b))
    b = inch_to_point(b)
    rotate = bool(state.orient == "Landscape")
    size = tuple(size[::-1]) if rotate else size
    pw, ph = size
    pages = canvas.Canvas(pdf_path, pagesize=size)
    cols, rows = int(pw // w), int(ph // h)
    rx, ry = round((pw - (w * cols)) / 2), round((ph - (h * rows)) / 2)
    ry = ph - ry

    front_pages = distribute_cards_to_pages(state, cols, rows)
    render_pages = make_render_page_sequence(state, front_pages)
    if page_side == "front":
        render_pages = [page for page in render_pages if not page["backside"]]
    elif page_side == "back":
        render_pages = [page for page in render_pages if page["backside"]]
    elif page_side != "both":
        raise ValueError(f"Unknown PDF page side: {page_side}")

    extended_guides = state.extended_guides

    @cache
    def get_img(img_path, rotation):
        if rotation is None:
            return img_path

        img = read_image(img_path)
        img = rotate_image(img, rotation)
        img = image_to_bytes(img)
        img = ImageReader(io.BytesIO(img))
        return img

    for page in render_pages:
        page_images = page["cards"]
        is_backside_page = page["backside"]
        render_fmt = (
            "Rendering backside for page {page}...\nImage number {img_idx} - {img_name}"
            if is_backside_page
            else "Rendering page {page}...\nImage number {img_idx} - {img_name}"
        )

        def draw_image(
            img, oversized, i, x, y, dx=0.0, dy=0.0, is_short_edge=False, backside=False
        ):
            print_fn(render_fmt.format(page=page["front_page_number"], img_idx=i + 1, img_name=img))
            img_path = runtime_images.get_processed_path(state, img)
            if img_path and os.path.exists(img_path):
                rotation = get_card_rotation(backside, oversized, is_short_edge)
                img = get_img(img_path, rotation)

                x = rx + x * w + dx
                y = ry - y * h + dy - h
                cw = 2 * w if oversized else w
                ch = h

                pages.drawImage(
                    img,
                    x,
                    y,
                    cw,
                    ch,
                )

        def draw_cross_at_grid(ix, iy, segment, dx=0.0, dy=0.0):
            x = rx + ix * w + dx
            y = ry - iy * h + dy
            draw_cross(pages, x, y, segment)
            if extended_guides:
                if ix == 0:
                    draw_line(pages, x, y, 0, y)
                if ix == cols:
                    draw_line(pages, x, y, pw, y)
                if iy == 0:
                    draw_line(pages, x, y, x, ph)
                if iy == rows:
                    draw_line(pages, x, y, x, 0)

        card_grid = distribute_cards_to_grid(page_images, not is_backside_page, cols, rows)

        i = 0
        for y in range(0, rows):
            for x in range(0, cols):
                if card := card_grid[y][x]:
                    (card_name, is_short_edge, is_oversized) = card
                    if card_name is None:
                        continue

                    draw_image(
                        card_name,
                        is_oversized,
                        i,
                        x,
                        y,
                        dx=backside_offset if is_backside_page else 0.0,
                        dy=backside_vertical_offset if is_backside_page else 0.0,
                        is_short_edge=is_short_edge,
                        backside=is_backside_page,
                    )
                    i = i + 1

                    if is_backside_page:
                        continue

                    if is_oversized:
                        ob = 2 * b
                        draw_cross_at_grid(
                            x + 2, y + 0, CrossSegment.TopRight, -ob, -ob
                        )
                        draw_cross_at_grid(
                            x + 2, y + 1, CrossSegment.BottomRight, -ob, +ob
                        )
                    else:
                        ob = b
                        draw_cross_at_grid(
                            x + 1, y + 0, CrossSegment.TopRight, -ob, -ob
                        )
                        draw_cross_at_grid(
                            x + 1, y + 1, CrossSegment.BottomRight, -ob, +ob
                        )

                    draw_cross_at_grid(x, y + 0, CrossSegment.TopLeft, +ob, -ob)
                    draw_cross_at_grid(x, y + 1, CrossSegment.BottomLeft, +ob, +ob)

        # Next page
        pages.showPage()

    return pages


def distribute_cards_to_pages(print_dict, columns, rows):
    return print_layout.distribute_cards_to_pages(as_project_state(print_dict), columns, rows)


def make_backside_pages(print_dict, pages):
    return print_layout.make_backside_pages(as_project_state(print_dict), pages)


def make_render_page_sequence(print_dict, front_pages):
    return print_layout.make_render_page_sequence(as_project_state(print_dict), front_pages)


def distribute_cards_to_grid(cards, left_to_right, columns, rows):
    return print_layout.distribute_cards_to_grid(cards, left_to_right, columns, rows)


def get_grid_coords(idx, columns, left_to_right):
    return print_layout.get_grid_coords(idx, columns, left_to_right)


def get_card_rotation(backside, is_oversized, is_short_edge):
    if backside:
        if is_short_edge:
            if is_oversized:
                return Rotation.RotateClockwise_90
            else:
                return Rotation.Rotate_180
        elif is_oversized:
            return Rotation.RotateCounterClockwise_90
    elif is_oversized:
        return Rotation.RotateClockwise_90

    return None
