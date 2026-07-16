"""Vision verification of rendered figure crops.

The judgment half of the Figure Agent: given a crop (rendered with context
padding and its bbox drawn as a red rectangle), decide whether the box holds
exactly one complete figure. This is where an LLM earns its place -- a
deterministic clusterer cannot tell that an arrow is cut off or that a
neighboring figure crept in.

`VisionVerifier` is a Protocol so the graph is testable without the network:
`ClaudeVisionVerifier` calls Anthropic; `FakeVisionVerifier` replays scripts.
"""

from __future__ import annotations

import base64
from enum import Enum
from typing import Optional, Protocol

from pydantic import BaseModel, Field

from pdfdeck.config import settings
from pdfdeck.extraction.geometry import BboxDelta
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)


class Verdict(str, Enum):
    ACCEPT = "accept"   # box holds exactly one complete figure
    ADJUST = "adjust"   # figure cut off / extra content -> apply bbox_delta, retry
    SPLIT = "split"     # box holds TWO figures -> split at split_at, reprocess
    REJECT = "reject"   # not a figure at all (text box, artifact) -> drop


class VerificationResult(BaseModel):
    """Structured verdict returned by the vision model."""

    verdict: Verdict = Field(description="accept | adjust | split | reject")
    reason: str = Field(description="one concise sentence explaining the verdict")
    bbox_delta: Optional[BboxDelta] = Field(
        default=None,
        description="for 'adjust': how far to move each edge outward, as a "
        "fraction of the current box size (positive expands, negative shrinks)",
    )
    split_at: Optional[float] = Field(
        default=None,
        description="for 'split': vertical split position as a fraction (0..1) "
        "of the box height, top to bottom",
    )
    confidence: float = Field(default=1.0, description="0..1 confidence in the verdict")


class VisionUnavailable(RuntimeError):
    """Raised when the vision backend cannot be reached / fails hard."""


class VisionVerifier(Protocol):
    def verify(
        self, image_path: str, expected_caption: Optional[str], kind: str
    ) -> VerificationResult: ...


_SYSTEM = (
    "You are a meticulous layout checker for a medical-textbook figure "
    "extraction pipeline. You are shown a rendered crop from a PDF page. A RED "
    "rectangle marks the region the pipeline intends to save as one figure; "
    "there is extra page context OUTSIDE the rectangle so you can see whether "
    "anything is cut off. Judge ONLY what is inside the red rectangle."
)

_PROMPT = (
    "Does the RED rectangle contain exactly ONE complete figure (a photo, "
    "micrograph, diagram, or table), with nothing important cut off at its "
    "edges and no neighboring figure, caption, page header, or body-text "
    "paragraph included?\n\n"
    "Reply with a verdict:\n"
    "- accept: exactly one complete figure, cleanly bounded.\n"
    "- adjust: it IS one figure but the box is slightly wrong (part cut off, "
    "or a strip of caption/adjacent text included). Provide bbox_delta to move "
    "the offending edges (fractions of the current box; positive = expand "
    "outward, negative = shrink inward). Keep deltas small (<= 0.3).\n"
    "- split: the box contains TWO separate figures stacked vertically. "
    "Provide split_at (fraction of box height where they divide).\n"
    "- reject: the box is NOT a figure (e.g. a shaded text/callout box, a page "
    "header, or blank).\n"
)


class ClaudeVisionVerifier:
    """Anthropic-backed verifier via langchain-anthropic structured output."""

    def __init__(self, model: str | None = None):
        from pdfdeck.agents.llm import structured_llm

        self.model = model or settings.vision_model
        # Retries + model fallback on overload are handled inside structured_llm.
        self._llm = structured_llm(VerificationResult, self.model, max_tokens=1024)
        self.calls = 0

    def verify(
        self, image_path: str, expected_caption: Optional[str], kind: str
    ) -> VerificationResult:
        from langchain_core.messages import HumanMessage, SystemMessage

        self.calls += 1

        with open(image_path, "rb") as f:
            b64 = base64.standard_b64encode(f.read()).decode("ascii")

        text = _PROMPT
        if expected_caption:
            text += f"\nThe pipeline associated this caption: {expected_caption!r}."
        if kind:
            text += f"\nThe deterministic classifier labeled it: {kind}."

        content = [
            {"type": "text", "text": text},
            {"type": "image", "source_type": "base64", "mime_type": "image/png", "data": b64},
        ]
        try:
            result = self._llm.invoke(
                [SystemMessage(content=_SYSTEM), HumanMessage(content=content)]
            )
        except Exception as exc:  # network / API / parse failure
            raise VisionUnavailable(str(exc)) from exc
        return result


class FakeVisionVerifier:
    """Scripted verifier for tests. Yields results in order; repeats the last."""

    def __init__(self, script: list[VerificationResult | Exception]):
        self._script = list(script)
        self._i = 0
        self.calls = 0

    def verify(
        self, image_path: str, expected_caption: Optional[str], kind: str
    ) -> VerificationResult:
        self.calls += 1
        item = self._script[min(self._i, len(self._script) - 1)]
        self._i += 1
        if isinstance(item, Exception):
            raise item
        return item
