"""Photo-vs-diagram classification of detected regions.

IMPORTANT DESIGN RULE: classification NEVER gates rendering. Every region
gets rendered regardless of its label. The kind only:
- styles/labels the resulting slide, and
- decides whether to SPEND a vision-verification call (diagrams and
  ambiguous regions get verified; clean single-raster photos skip).
A misclassification is therefore cosmetic, not fatal.
"""

from __future__ import annotations

from pdfdeck.config import settings
from pdfdeck.models import Rect, RegionKind


def classify_region(
    source_rects: list[Rect],
    bbox: Rect,
    photo_max_rects: int = settings.photo_max_rects,
    diagram_min_rects: int = settings.diagram_min_rects,
) -> tuple[RegionKind, float]:
    """Classify from structural evidence: (kind, confidence 0..1).

    Signals:
    - Tile count: hundreds/thousands of small rects => tiled diagram.
      One or a few large rects => photo(s).
    - Fill ratio: photos' rects cover ~all of their bbox; diagrams
      (vector art + scattered tiles) leave whitespace.
    - Median rect area: tiny tiles => diagram.
    """
    n = len(source_rects)
    if n == 0:
        return RegionKind.UNKNOWN, 0.0

    areas = sorted(r.area for r in source_rects)
    median_area = areas[n // 2]
    covered = sum(areas)  # overestimates on overlap; fine as a signal
    fill_ratio = min(1.0, covered / bbox.area) if bbox.area > 0 else 0.0

    if n >= diagram_min_rects:
        # Many pieces. Almost certainly a tiled/composited diagram.
        conf = min(1.0, 0.6 + n / 100.0)
        return RegionKind.DIAGRAM, conf

    if n <= photo_max_rects:
        # Few pieces. Large, high-fill rects => photo (or photo panel group).
        if median_area > 10_000 and fill_ratio > 0.55:
            return RegionKind.PHOTO, 0.85
        if median_area > 4_000 and fill_ratio > 0.4:
            return RegionKind.PHOTO, 0.6
        # Few small/sparse pieces: probably a small vector diagram.
        return RegionKind.DIAGRAM, 0.5

    return RegionKind.UNKNOWN, 0.3


def needs_vision_verification(
    kind: RegionKind, confidence: float, has_caption: bool
) -> bool:
    """Vision-call gating: verify everything except confident, captioned photos."""
    if kind == RegionKind.PHOTO and confidence >= 0.8 and has_caption:
        return False
    return True
