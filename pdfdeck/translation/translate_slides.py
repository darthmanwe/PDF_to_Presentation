"""Translate the human-visible text of a SlideSpec deck in one batch.

Flattens every title / bullet / caption into a single ordered list, sends it
through the batching TranslationService, and maps the results back to their
slots. Figure image paths and structural fields are untouched.
"""

from __future__ import annotations

from typing import Protocol

from pdfdeck.models import SlideSpec


class Translator(Protocol):
    def translate_batch(self, texts: list[str], target: str, source: str = "en") -> list[str]: ...


def _collect(slides: list[SlideSpec]) -> tuple[list[str], list[tuple]]:
    """Return (texts, addresses) where each address locates a text back in the deck."""
    texts: list[str] = []
    addrs: list[tuple] = []
    for si, s in enumerate(slides):
        if s.title:
            texts.append(s.title)
            addrs.append(("title", si))
        for bi, b in enumerate(s.bullets):
            texts.append(b)
            addrs.append(("bullet", si, bi))
        if s.caption:
            texts.append(s.caption)
            addrs.append(("caption", si))
    return texts, addrs


def translate_slides(
    slides: list[SlideSpec], target: str, service: Translator
) -> list[SlideSpec]:
    """Return a translated copy of the deck. `target` None/'en' is a no-op."""
    if not target or target == "en":
        return slides

    texts, addrs = _collect(slides)
    if not texts:
        return slides
    translated = service.translate_batch(texts, target)

    out = [s.model_copy(deep=True) for s in slides]
    for value, addr in zip(translated, addrs):
        if addr[0] == "title":
            out[addr[1]].title = value
        elif addr[0] == "bullet":
            out[addr[1]].bullets[addr[2]] = value
        elif addr[0] == "caption":
            out[addr[1]].caption = value
    return out
