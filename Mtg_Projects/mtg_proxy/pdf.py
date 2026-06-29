import os
import io
from enum import Enum
from copy import deepcopy
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


def generate(print_dict, size, pdf_path, print_fn):
    state = as_project_state(print_dict)
    backside_offset = mm_to_point(float(state.backside_offset))

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


def has_active_oversized_cards(print_dict):
    state = as_project_state(print_dict)
    if not state.oversized_enabled:
        return False

    oversized_dict = state.oversized
    for card_name, count in state.cards.items():
        if card_name.startswith("__"):
            continue
        if int(count) <= 0:
            continue
        if oversized_dict.get(card_name, False):
            return True
    return False


def needs_oversized_landscape_warning(print_dict):
    state = as_project_state(print_dict)
    return has_active_oversized_cards(state) and state.orient != "Landscape"


def distribute_cards_to_pages(print_dict, columns, rows):
    state = as_project_state(print_dict)
    images_per_page = columns * rows
    oversized_images_per_page = (columns // 2) * rows

    short_edge_dict = state.backside_short_edge
    oversized_dict = state.oversized if state.oversized_enabled else {}

    # throw all images n times into a list
    images = []
    card_sort = getattr(state, "card_sort", "Alphabetical (A-Z)")
    card_names = list(state.cards.keys())
    if card_sort == "Alphabetical (A-Z)":
        card_names = sorted(
            card_names,
            key=lambda name: (state.get_card_metadata(name) or {}).get("name", name).casefold(),
        )
    elif card_sort == "Alphabetical (Z-A)":
        card_names = sorted(
            card_names,
            key=lambda name: (state.get_card_metadata(name) or {}).get("name", name).casefold(),
            reverse=True,
        )

    for img in card_names:
        num = state.cards[img]
        is_short_edge = short_edge_dict[img] if img in short_edge_dict else False
        is_oversized = oversized_dict[img] if img in oversized_dict else False
        images.extend([(img, is_short_edge, is_oversized)] * num)

    oversized_images = [image for image in images if image[2]]
    regular_images = [image for image in images if not image[2]]
    pages = []

    while oversized_images or regular_images:
        page = {"regular": [], "oversized": []}
        used_single_spaces = 0

        while (
            oversized_images
            and len(page["oversized"]) < oversized_images_per_page
            and used_single_spaces + 2 <= images_per_page
        ):
            img, is_short_edge, _is_oversized = oversized_images.pop(0)
            page["oversized"].append((img, is_short_edge))
            used_single_spaces += 2

        while regular_images and used_single_spaces < images_per_page:
            img, is_short_edge, _is_oversized = regular_images.pop(0)
            page["regular"].append((img, is_short_edge))
            used_single_spaces += 1

        pages.append(page)

    return pages


def make_backside_pages(print_dict, pages):
    state = as_project_state(print_dict)
    back_dict = state.backsides

    def backside_of_img(img_pair):
        (img, is_short_edge) = img_pair
        return (
            (back_dict[img] if img in back_dict else state.backside_default),
            is_short_edge,
        )

    backside_pages = deepcopy(pages)
    for page in backside_pages:
        page["regular"] = [backside_of_img(img) for img in page["regular"]]
        page["oversized"] = [backside_of_img(img) for img in page["oversized"]]

    return backside_pages


def make_render_page_sequence(print_dict, front_pages):
    state = as_project_state(print_dict)
    front_render_pages = [
        {
            "cards": page,
            "backside": False,
            "front_page_number": index + 1,
        }
        for index, page in enumerate(front_pages)
    ]
    if not state.backside_enabled:
        return front_render_pages

    backside_render_pages = [
        {
            "cards": page,
            "backside": True,
            "front_page_number": index + 1,
        }
        for index, page in enumerate(make_backside_pages(state, front_pages))
    ]
    if state.backside_pages_at_end:
        return front_render_pages + backside_render_pages

    return [
        page
        for page_pair in zip(front_render_pages, backside_render_pages)
        for page in page_pair
    ]


def distribute_cards_to_grid(cards, left_to_right, columns, rows):
    def get_coord(i):
        return get_grid_coords(i, columns, left_to_right)

    card_grid = [[None] * columns for i in range(rows)]

    k = 0
    for card_name, is_short_edge in cards["oversized"]:
        x, y = get_coord(k)

        # find slot that fits an oversized card
        while y + 1 >= columns or card_grid[x][y + 1] is not None:
            k = k + 1
            x, y = get_coord(k)

        card_grid[x][y] = (card_name, is_short_edge, True)
        card_grid[x][y + 1] = (None, None, None)
        k = k + 2
    del k

    i = 0
    for card_name, is_short_edge in cards["regular"]:
        x, y = get_coord(i)

        # find slot that is free for single card
        while card_grid[x][y] is not None:
            i = i + 1
            x, y = get_coord(i)

        card_grid[x][y] = (card_name, is_short_edge, False)
        i = i + 1
    del i

    return card_grid


def get_grid_coords(idx, columns, left_to_right):
    x, y = divmod(idx, columns)
    if not left_to_right:
        y = columns - y - 1
    return x, y


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
