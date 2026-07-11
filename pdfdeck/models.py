"""Domain model for pdfdeck.

A single DocumentModel flows through the LangGraph pipeline:
pages -> regions (clustered figure candidates) -> figures (verified crops)
-> slide specs -> assembled deck + QA report.

All geometry uses PDF points with a TOP-LEFT origin (PyMuPDF's page
coordinate convention), normalized once at ingest.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

class Rect(BaseModel):
    """Axis-aligned rectangle in PDF points, top-left origin."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def union(self, other: "Rect") -> "Rect":
        return Rect(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1),
        )

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.x1 <= other.x0
            or other.x1 <= self.x0
            or self.y1 <= other.y0
            or other.y1 <= self.y0
        )

    def contains_point(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def rounded_key(self, ndigits: int = 1) -> tuple:
        """Stable key for caching renders/verdicts."""
        return (
            round(self.x0, ndigits),
            round(self.y0, ndigits),
            round(self.x1, ndigits),
            round(self.y1, ndigits),
        )


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------

class TextBlock(BaseModel):
    """A paragraph-level text block with a stable span ID for grounding."""

    span_id: str                     # e.g. "p3_b7"
    text: str
    bbox: Rect
    column: Optional[int] = None     # 0-based column index; None before detection
    font_size: Optional[float] = None
    word_count: int = 0
    is_caption: bool = False         # line-start "Figure N.N" caption block


# --------------------------------------------------------------------------
# Regions and figures
# --------------------------------------------------------------------------

class RegionKind(str, Enum):
    PHOTO = "photo"
    DIAGRAM = "diagram"
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"        # VLM accepted the crop
    BEST_EFFORT = "best_effort"  # retry cap hit; best crop kept, flagged
    UNVERIFIED = "unverified"    # gating skipped verification (clean photo)
    NO_VISION = "no_vision"      # vision disabled/unavailable; deterministic bbox


class Region(BaseModel):
    """A clustered figure-candidate region on a page."""

    id: str                          # e.g. "p3_r0"
    page_index: int                  # 0-based
    bbox: Rect                       # current bbox (may be refined by the agent)
    source_rects: list[Rect] = Field(default_factory=list)  # provenance tiles/paths
    kind: RegionKind = RegionKind.UNKNOWN
    classifier_confidence: float = 0.0
    caption: Optional[str] = None
    figure_no: Optional[str] = None  # "4.12"
    caption_bbox: Optional[Rect] = None
    is_full_width: bool = False
    image_path: Optional[str] = None      # deck-quality render
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    verify_notes: Optional[str] = None
    retries: int = 0


class Figure(BaseModel):
    """A finalized, rendered figure ready for slide placement."""

    region_id: str
    page_index: int
    figure_no: Optional[str] = None
    caption: Optional[str] = None
    kind: RegionKind = RegionKind.UNKNOWN
    image_path: str
    status: VerificationStatus = VerificationStatus.UNVERIFIED


# --------------------------------------------------------------------------
# Pages / document
# --------------------------------------------------------------------------

class PageModel(BaseModel):
    index: int                                  # 0-based
    width: float = 0.0                          # points
    height: float = 0.0
    markdown: str = ""                          # pymupdf4llm reading-order text
    text_blocks: list[TextBlock] = Field(default_factory=list)
    column_split_x: Optional[float] = None      # None => single column
    caption_mentions: int = 0                   # caption-style "Figure N.N" blocks
    is_garbled: bool = False
    regions: list[Region] = Field(default_factory=list)
    redetect_attempted: bool = False


# --------------------------------------------------------------------------
# Slides
# --------------------------------------------------------------------------

class SlideSpec(BaseModel):
    index: int
    title: str
    bullets: list[str] = Field(default_factory=list)
    slide_type: str = "text"                    # text | figure | title | fallback_page
    figure_ref: Optional[str] = None            # Region.id
    image_path: Optional[str] = None
    caption: Optional[str] = None
    source_span_ids: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# QA / reporting
# --------------------------------------------------------------------------

class QAReport(BaseModel):
    best_effort_figures: list[str] = Field(default_factory=list)
    no_vision_figures: list[str] = Field(default_factory=list)
    fallback_pages: list[int] = Field(default_factory=list)
    garbled_pages: list[int] = Field(default_factory=list)
    forced_accept_slides: list[int] = Field(default_factory=list)
    dropped_captions: list[str] = Field(default_factory=list)
    vision_calls: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    cost_estimate_usd: float = 0.0
    errors: list[str] = Field(default_factory=list)


class DocumentModel(BaseModel):
    pdf_path: str
    pdf_sha: str = ""
    title: str = ""
    target_language: Optional[str] = None       # None/"en" => no translation
    run_dir: str = ""                            # runs/<timestamp>/ artifact dir
    pages: list[PageModel] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    slides: list[SlideSpec] = Field(default_factory=list)
    output_path: Optional[str] = None
    report: QAReport = Field(default_factory=QAReport)
