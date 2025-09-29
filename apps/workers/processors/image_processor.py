from __future__ import annotations

from pathlib import Path

from PIL import Image
from pytesseract import image_to_string


def ocr_image(path: Path) -> str:
    with Image.open(path) as img:
        return image_to_string(img)
