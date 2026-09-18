"""Shared print/export readiness checks."""
from __future__ import annotations

from dataclasses import dataclass

from constants import low_dpi_warning_threshold
from models import as_project_state
import runtime_images
from services import layout_service, quality_service


@dataclass(frozen=True)
class PreflightIssue:
    code: str
    summary: str
    details: tuple[str, ...] = ()
    blocking: bool = False
    card_names: tuple[str, ...] = ()


def analyze(project_like, img_dict, placements, columns, rows):
    state = as_project_state(project_like)
    issues = []
    occupancy = layout_service.occupancy(placements, columns, rows)
    underfilled = [page for page in occupancy if page['filled'] < page['capacity']]
    if underfilled:
        issues.append(PreflightIssue(
            'occupancy', f'{len(underfilled)} under-filled sheet(s)',
            tuple(layout_service.occupancy_label(page) for page in underfilled)))

    card_names = sorted({placement['name'] for placement in placements})
    low_resolution = []
    low_resolution_names = []
    missing_art = []
    clipping = []
    missing_backs = []
    card_service = None
    if state.backside_enabled:
        from mtg_core import get_default_card_service
        card_service = get_default_card_service()
    for name in card_names:
        preview = runtime_images.ensure_preview_entry(state, img_dict, name)
        if preview is None:
            missing_art.append(name)
            continue
        dpi = preview.get('effective_dpi')
        if dpi is not None and float(dpi) < low_dpi_warning_threshold:
            low_resolution.append(f'{name} ({round(float(dpi))} DPI)')
            low_resolution_names.append(name)
        if float(state.bleed_edge) > 0 and not preview.get('uncropped'):
            clipping.append(name)
        if state.backside_enabled:
            if quality_service.missing_back(
                    state, img_dict, name, card_service,
                    ensure_preview=runtime_images.ensure_preview_entry):
                missing_backs.append(name)

    if low_resolution:
        issues.append(PreflightIssue(
            'low_resolution', f'{len(low_resolution)} low-resolution card(s)',
            tuple(low_resolution), card_names=tuple(low_resolution_names)))
    if missing_backs:
        issues.append(PreflightIssue(
            'missing_back', f'{len(missing_backs)} card(s) have no printable back',
            tuple(missing_backs), card_names=tuple(missing_backs)))
    if clipping:
        issues.append(PreflightIssue(
            'clipping', f'{len(clipping)} card(s) may clip configured bleed',
            tuple(clipping), card_names=tuple(clipping)))
    if missing_art:
        issues.append(PreflightIssue(
            'missing_art', f'{len(missing_art)} card image(s) are unavailable',
            tuple(missing_art), blocking=True, card_names=tuple(missing_art)))
    return issues


def invalid_layout_issue(error):
    return PreflightIssue('invalid_layout', 'The selected sheet cannot render this layout',
                          (str(error),), blocking=True)
