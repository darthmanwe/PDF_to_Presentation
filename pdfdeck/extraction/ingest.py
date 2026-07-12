"""PDF ingestion: pages -> text blocks (span IDs), columns, captions, raw rects.

Deterministic and offline. Produces the PageModel list that region detection
and the content agent consume. Reading-order text comes from pymupdf4llm
(markdown, column-aware); block-level bboxes come from get_text("dict").
Span IDs are assigned AFTER reading-order sorting so p3_b0, p3_b1, ...
follow human reading order — the content agent cites these IDs.
"""

from __future__ import annotations

import hashlib
from statistics import median

import fitz  # PyMuPDF
import pymupdf4llm

from pdfdeck.extraction.caption_match import find_caption_blocks
from pdfdeck.extraction.columns import assign_columns, detect_column_split, order_reading
from pdfdeck.extraction.garbled import is_garbled
from pdfdeck.models import PageModel, Rect, TextBlock
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _blocks_from_page(page: fitz.Page, page_index: int) -> list[TextBlock]:
    """Paragraph-level text blocks with bbox, font size, and word count."""
    raw = page.get_text("dict")
    blocks: list[TextBlock] = []
    for blk in raw.get("blocks", []):
        if blk.get("type") != 0:  # text blocks only
            continue
        lines = blk.get("lines", [])
        text = " ".join(
            "".join(span.get("text", "") for span in line.get("spans", []))
            for line in lines
        ).strip()
        if not text:
            continue
        sizes = [
            span.get("size", 0.0)
            for line in lines
            for span in line.get("spans", [])
            if span.get("size")
        ]
        bb = blk.get("bbox", (0, 0, 0, 0))
        blocks.append(
            TextBlock(
                span_id="",  # assigned after reading-order sort
                text=text,
                bbox=Rect(x0=bb[0], y0=bb[1], x1=bb[2], y1=bb[3]),
                font_size=median(sizes) if sizes else None,
                word_count=len(text.split()),
            )
        )
    return blocks


def raw_candidate_rects(page: fitz.Page) -> tuple[list[Rect], list[Rect]]:
    """Return (image_rects, drawing_rects) — placement rects, provenance kept.

    Provenance matters downstream: a region with image content is a real
    figure; a drawings-only region qualifies only if it has MANY drawings (a
    real vector diagram or a table), not a handful (a shaded callout box).
    Images alone miss vector arrows/labels; drawings alone miss raster tiles;
    the union feeds clustering (noise filtered there).
    """
    image_rects: list[Rect] = []
    for info in page.get_image_info():
        bb = info.get("bbox")
        if bb:
            image_rects.append(Rect(x0=bb[0], y0=bb[1], x1=bb[2], y1=bb[3]))
    drawing_rects: list[Rect] = []
    try:
        for path in page.get_drawings():
            r = path.get("rect")
            if r is not None:
                drawing_rects.append(Rect(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1))
    except Exception as exc:  # very complex pages can trip get_drawings
        log.warning("get_drawings failed on page %d: %s", page.number, exc)
    return image_rects, drawing_rects


def ingest_pdf(pdf_path: str) -> tuple[list[PageModel], str]:
    """Build PageModels (text, columns, captions, garble flags) + doc sha.

    Region detection is a separate step (detect.py) so calibration and the
    graph can re-run it with different parameters without re-ingesting.
    """
    doc = fitz.open(pdf_path)
    try:
        md_chunks = pymupdf4llm.to_markdown(doc, page_chunks=True)
    except Exception as exc:
        log.warning("pymupdf4llm failed (%s); falling back to plain text", exc)
        md_chunks = None

    pages: list[PageModel] = []
    for i, page in enumerate(doc):
        blocks = _blocks_from_page(page, i)

        split_x = detect_column_split(blocks, page.rect.width)
        assign_columns(blocks, split_x)
        ordered = order_reading(blocks)
        for n, b in enumerate(ordered):
            b.span_id = f"p{i}_b{n}"

        captions = find_caption_blocks(ordered)

        if md_chunks is not None and i < len(md_chunks):
            markdown = md_chunks[i].get("text", "")
        else:
            markdown = "\n\n".join(b.text for b in ordered)

        pages.append(
            PageModel(
                index=i,
                width=page.rect.width,
                height=page.rect.height,
                markdown=markdown,
                text_blocks=ordered,
                column_split_x=split_x,
                caption_mentions=len(captions),
                is_garbled=is_garbled(markdown),
            )
        )
    doc.close()
    return pages, sha256_file(pdf_path)
