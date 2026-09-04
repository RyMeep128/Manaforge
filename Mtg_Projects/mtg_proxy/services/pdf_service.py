from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable

import pdf

from models import ProjectState, as_project_state


@dataclass
class PDFGenerationResult:
    state: ProjectState
    pdf_path: str
    pages: object
    backside_pdf_path: str | None = None
    backside_pages: object | None = None


def generate_pdf(
    project_like,
    size,
    pdf_path,
    print_fn: Callable[[str], None],
) -> PDFGenerationResult:
    state = as_project_state(project_like)
    separate_backs = state.backside_enabled and state.backside_separate_file
    pages = pdf.generate(
        state, size, pdf_path, print_fn,
        page_side="front" if separate_backs else "both",
    )
    backside_pdf_path = None
    backside_pages = None
    if separate_backs:
        stem, extension = os.path.splitext(pdf_path)
        backside_pdf_path = f"{stem}_backs{extension or '.pdf'}"
        backside_pages = pdf.generate(
            state, size, backside_pdf_path, print_fn, page_side="back"
        )
    return PDFGenerationResult(
        state=state,
        pdf_path=pdf_path,
        pages=pages,
        backside_pdf_path=backside_pdf_path,
        backside_pages=backside_pages,
    )
