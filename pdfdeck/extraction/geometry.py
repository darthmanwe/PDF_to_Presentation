"""Coordinate transforms between PDF points and rendered-pixel space.

Conventions (asserted by tests, normalized at ingest):
- PDF space: points (1/72 inch), TOP-LEFT origin, y grows downward.
  This matches PyMuPDF's page/`get_text`/`get_image_info` coordinates.
- Pixel space: a render produced by `page.get_pixmap(clip=..., dpi=...)`,
  where pixel (0, 0) is the top-left of the CLIP rectangle.

Vision-model bbox feedback is always expressed as NORMALIZED deltas
(fractions of the current bbox size), never raw pixels — see
`apply_bbox_delta`. This avoids the DPI/clip-origin round-trip bugs that
raw pixel suggestions invite.
"""

from __future__ import annotations

from pydantic import BaseModel

from pdfdeck.models import Rect

POINTS_PER_INCH = 72.0


def scale_for_dpi(dpi: int) -> float:
    """Pixels per point at the given render DPI."""
    return dpi / POINTS_PER_INCH


def pdf_rect_to_pixel_bbox(rect: Rect, clip: Rect, dpi: int) -> tuple[int, int, int, int]:
    """Map a PDF-space rect to pixel coords within a render clipped to `clip`."""
    s = scale_for_dpi(dpi)
    return (
        int(round((rect.x0 - clip.x0) * s)),
        int(round((rect.y0 - clip.y0) * s)),
        int(round((rect.x1 - clip.x0) * s)),
        int(round((rect.y1 - clip.y0) * s)),
    )


def pixel_bbox_to_pdf_rect(
    bbox: tuple[float, float, float, float], clip: Rect, dpi: int
) -> Rect:
    """Inverse of `pdf_rect_to_pixel_bbox`."""
    s = scale_for_dpi(dpi)
    return Rect(
        x0=clip.x0 + bbox[0] / s,
        y0=clip.y0 + bbox[1] / s,
        x1=clip.x0 + bbox[2] / s,
        y1=clip.y0 + bbox[3] / s,
    )


class BboxDelta(BaseModel):
    """Normalized bbox adjustment from the vision verifier.

    Each field is a fraction of the CURRENT bbox's width/height by which
    that edge moves OUTWARD (positive = expand, negative = shrink).
    E.g. expand_left=0.10 moves x0 left by 10% of the bbox width.
    """

    expand_left: float = 0.0
    expand_top: float = 0.0
    expand_right: float = 0.0
    expand_bottom: float = 0.0


def apply_bbox_delta(bbox: Rect, delta: BboxDelta, page_rect: Rect) -> Rect:
    """Apply a normalized delta, clamped to the page bounds.

    Guarantees a valid, non-inverted rect: if a shrink would invert the box,
    the offending edges are clamped to preserve a minimal 1pt extent.
    """
    w, h = bbox.width, bbox.height
    x0 = bbox.x0 - delta.expand_left * w
    y0 = bbox.y0 - delta.expand_top * h
    x1 = bbox.x1 + delta.expand_right * w
    y1 = bbox.y1 + delta.expand_bottom * h

    # Clamp to page.
    x0 = max(page_rect.x0, x0)
    y0 = max(page_rect.y0, y0)
    x1 = min(page_rect.x1, x1)
    y1 = min(page_rect.y1, y1)

    # Prevent inversion.
    if x1 - x0 < 1.0:
        cx = (x0 + x1) / 2
        x0, x1 = cx - 0.5, cx + 0.5
    if y1 - y0 < 1.0:
        cy = (y0 + y1) / 2
        y0, y1 = cy - 0.5, cy + 0.5

    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def pad_rect(rect: Rect, frac: float, page_rect: Rect) -> Rect:
    """Expand a rect by `frac` of its size on every side, clamped to the page."""
    return apply_bbox_delta(
        rect,
        BboxDelta(
            expand_left=frac, expand_top=frac, expand_right=frac, expand_bottom=frac
        ),
        page_rect,
    )
