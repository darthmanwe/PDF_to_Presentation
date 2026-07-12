"""Region and page rendering.

`render_region` produces the deck-quality PNG (300 DPI): PyMuPDF composites
vector paths, text labels, and every raster tile inside the clip into ONE
flat image — this is the fix for v1's fragmentation.

`render_verify_image` produces what the vision verifier sees: the region
plus ~10% surrounding context, with the actual crop bbox drawn as a red
rectangle, downscaled to control image-token cost. The model judges the
BOUNDARY (is anything cut off / wrongly included), which a bare crop cannot
reveal.
"""

from __future__ import annotations

import os

import fitz
from PIL import Image, ImageDraw

from pdfdeck.config import settings
from pdfdeck.extraction.geometry import pad_rect, pdf_rect_to_pixel_bbox
from pdfdeck.models import Rect
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)


def _page_rect(page: fitz.Page) -> Rect:
    return Rect(x0=0, y0=0, x1=page.rect.width, y1=page.rect.height)


def render_region(
    page: fitz.Page,
    bbox: Rect,
    out_path: str,
    dpi: int = settings.render_dpi,
) -> str:
    """Clip-render `bbox` to a PNG at `dpi`. Returns out_path."""
    clip = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    pix = page.get_pixmap(clip=clip, dpi=dpi)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pix.save(out_path)
    return out_path


def render_full_page(
    page: fitz.Page, out_path: str, dpi: int = settings.fallback_page_dpi
) -> str:
    """Full-page render for the no-regions-found fallback slide."""
    pix = page.get_pixmap(dpi=dpi)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pix.save(out_path)
    return out_path


def render_verify_image(
    page: fitz.Page,
    bbox: Rect,
    out_path: str,
    padding_frac: float = settings.verify_padding_frac,
    max_long_edge: int = settings.verify_max_long_edge,
) -> str:
    """Render bbox + context, draw the bbox outline, downscale. Returns path."""
    page_rect = _page_rect(page)
    padded = pad_rect(bbox, padding_frac, page_rect)

    # Render the padded area at a DPI that keeps the long edge near the cap,
    # rather than rendering huge and shrinking (faster, less memory).
    long_edge_pt = max(padded.width, padded.height)
    dpi = max(72, min(300, int(max_long_edge / long_edge_pt * 72)))
    clip = fitz.Rect(padded.x0, padded.y0, padded.x1, padded.y1)
    pix = page.get_pixmap(clip=clip, dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    # Draw the actual crop bbox in the padded render's pixel space.
    px = pdf_rect_to_pixel_bbox(bbox, padded, dpi)
    draw = ImageDraw.Draw(img)
    width = max(2, int(img.width / 300))
    draw.rectangle(px, outline=(255, 0, 0), width=width)

    if max(img.size) > max_long_edge:
        img.thumbnail((max_long_edge, max_long_edge), Image.LANCZOS)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "PNG")
    return out_path
