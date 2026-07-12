"""Garbled-text detection.

Some PDFs extract as CID artifacts, replacement characters, or symbol soup
(bad ToUnicode maps). Feeding that to the content agent produces garbage
slides; such pages are excluded from content input and flagged in the QA
report instead.
"""

from __future__ import annotations

import re

_CID_RE = re.compile(r"\(cid:\d+\)")
_WORD_RE = re.compile(r"[A-Za-zÀ-ɏ]{2,}")


def is_garbled(text: str, min_chars: int = 200) -> bool:
    """Heuristic: True if the page text is unusable for content generation.

    Signals (any one trips the flag):
    - replacement characters (U+FFFD) above 1% of characters
    - '(cid:NNN)' artifacts above 0.5% incidence by character mass
    - alphabetic-word coverage below 30% of the text mass
    Short texts (< min_chars) are never flagged — not enough evidence.
    """
    if len(text) < min_chars:
        return False

    n = len(text)
    replacement_ratio = text.count("�") / n
    if replacement_ratio > 0.01:
        return True

    cid_mass = sum(len(m.group(0)) for m in _CID_RE.finditer(text))
    if cid_mass / n > 0.005:
        return True

    word_mass = sum(len(m.group(0)) for m in _WORD_RE.finditer(text))
    if word_mass / n < 0.30:
        return True

    return False
