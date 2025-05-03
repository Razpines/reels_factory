"""Utility helpers for ID generation and text cleaning."""
from __future__ import annotations

import hashlib
import re
from typing import Iterable, Mapping


def apply_patterns(text: str, patterns: Iterable[Mapping[str, str]]) -> str:
    """Apply a list of regex replacement patterns."""
    for pattern in patterns:
        text = re.sub(pattern["pattern"], pattern["replacement"], text, flags=re.IGNORECASE)
    return text


def reel_id_from_title(title: str) -> str:
    """Deterministic, filesystem-safe reel id derived from a title."""
    digest = hashlib.sha256(title.encode("utf-8")).hexdigest()
    return digest[:10].upper()
