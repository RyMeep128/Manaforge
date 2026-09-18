"""Raster, individual-card, and ZIP exports using the shared PDF renderer."""
from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from PyQt6 import QtCore, QtGui
from PyQt6.QtPdf import QPdfDocument

from constants import page_sizes
from models import as_project_state
import runtime_images
from services import pdf_service


def _safe(value):
    return re.sub(r'[^A-Za-z0-9._-]+', '-', str(value)).strip('-._') or 'card'


def _save_pdf_result(result):
    result.pages.save()
    if result.backside_pages is not None:
        result.backside_pages.save()


def _rasterize(pdf_path, output_dir, prefix, *, image_format='PNG', dpi=300,
               quality=90, transparent=False):
    document = QPdfDocument(None)
    error = document.load(str(pdf_path))
    if error != QPdfDocument.Error.None_:
        raise ValueError(f'Could not load generated export ({error.name}).')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = image_format.lower()
    paths = []
    try:
        for index in range(document.pageCount()):
            points = document.pagePointSize(index)
            pixels = QtCore.QSize(
                max(1, round(points.width() * dpi / 72)),
                max(1, round(points.height() * dpi / 72)))
            rendered = document.render(index, pixels)
            if rendered.isNull():
                raise OSError(f'Could not rasterize sheet {index + 1}.')
            if not transparent:
                background = QtGui.QImage(
                    rendered.size(), QtGui.QImage.Format.Format_RGB32)
                background.fill(QtCore.Qt.GlobalColor.white)
                painter = QtGui.QPainter(background)
                painter.drawImage(0, 0, rendered)
                painter.end()
                rendered = background
            path = output_dir / f'{prefix}_{index + 1:03d}.{suffix}'
            if not rendered.save(str(path), image_format, quality):
                raise OSError(f'Could not save {path.name}.')
            paths.append(str(path))
    finally:
        document.close()
    return paths


def export_sheets(project_like, output_dir, print_fn=lambda _text: None, *,
                  image_format='PNG', dpi=300, quality=90,
                  transparent=False):
    state = as_project_state(project_like)
    image_format = image_format.upper()
    if image_format not in ('PNG', 'JPEG'):
        raise ValueError('Sheet format must be PNG or JPEG.')
    if not 72 <= int(dpi) <= 1200:
        raise ValueError('Sheet DPI must be between 72 and 1200.')
    if not 1 <= int(quality) <= 100:
        raise ValueError('JPEG quality must be between 1 and 100.')
    with tempfile.TemporaryDirectory(prefix='manaforge-export-') as temp:
        pdf_path = os.path.join(temp, 'sheets.pdf')
        result = pdf_service.generate_pdf(
            state, page_sizes[state.pagesize], pdf_path, print_fn)
        _save_pdf_result(result)
        paths = _rasterize(
            result.pdf_path, output_dir, 'sheet', image_format=image_format,
            dpi=dpi, quality=quality, transparent=transparent)
        if result.backside_pdf_path:
            paths.extend(_rasterize(
                result.backside_pdf_path, output_dir, 'back_sheet',
                image_format=image_format, dpi=dpi, quality=quality,
                transparent=transparent))
    return paths


def export_individual_cards(project_like, output_dir, *, image_format='PNG',
                            quality=95):
    state = as_project_state(project_like)
    image_format = image_format.upper()
    if image_format not in ('PNG', 'JPEG'):
        raise ValueError('Card format must be PNG or JPEG.')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    names = []
    for front in state.cards:
        if state.get_card_count(front) <= 0 or front.startswith('__'):
            continue
        entry = state.get_card_entry(front)
        if entry is not None and entry.do_not_print:
            continue
        names.append((front, 'front'))
        if state.backside_enabled:
            back = state.backsides.get(front) or state.backside_default
            if back:
                names.append((back, 'back'))
    seen = set()
    for name, side in names:
        key = (name, side)
        if key in seen:
            continue
        seen.add(key)
        source = runtime_images.get_processed_path(state, name)
        if not source or not os.path.exists(source):
            raise OSError(f'Prepared image is unavailable: {name}')
        image = QtGui.QImage(source)
        if image.isNull():
            raise OSError(f'Could not load prepared image: {name}')
        path = output / f'{_safe(Path(name).stem)}_{side}.{image_format.lower()}'
        if not image.save(str(path), image_format, quality):
            raise OSError(f'Could not save {path.name}.')
        paths.append(str(path))
    return paths


def export_zip(project_like, zip_path, print_fn=lambda _text: None, *, dpi=300):
    state = as_project_state(project_like)
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='manaforge-package-') as temp:
        root = Path(temp)
        sheets = export_sheets(state, root / 'sheets', print_fn, dpi=dpi)
        cards = export_individual_cards(state, root / 'cards')
        manifest = {
            'version': 1,
            'project': state.to_persisted_dict(),
            'sheet_files': [str(Path(path).relative_to(root)).replace('\\', '/') for path in sheets],
            'card_files': [str(Path(path).relative_to(root)).replace('\\', '/') for path in cards],
            'dpi': int(dpi),
        }
        (root / 'manifest.json').write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob('*')):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    return str(zip_path)
