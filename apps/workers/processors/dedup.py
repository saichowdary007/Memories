from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from PIL import Image
from imagehash import phash
from simhash import Simhash


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_simhash(text: str) -> int:
    return Simhash(text).value


def compute_phash(image_path: Path) -> Optional[str]:
    try:
        with Image.open(image_path) as img:
            return str(phash(img))
    except Exception:
        return None


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")
