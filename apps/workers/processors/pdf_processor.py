from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from pdf2image import convert_from_path
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer
from pytesseract import image_to_string


@dataclass
class PDFPageContent:
    page_index: int
    text: str


def extract_pdf_pages(path: Path) -> List[PDFPageContent]:
    pages: List[PDFPageContent] = []
    for index, layout in enumerate(extract_pages(path)):
        text_parts: List[str] = []
        for element in layout:
            if isinstance(element, LTTextContainer):
                text_parts.append(element.get_text())
        text = "".join(text_parts).strip()
        if not text:
            images = convert_from_path(str(path), first_page=index + 1, last_page=index + 1)
            if images:
                text = image_to_string(images[0])
        pages.append(PDFPageContent(page_index=index, text=text))
    return pages
