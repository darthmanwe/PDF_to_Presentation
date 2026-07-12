"""Integration: full deterministic extraction against repair.pdf.

Real PyMuPDF parsing + clustering + classification + caption association,
asserted against the visually-calibrated oracle. Offline: no API keys, no
vision. This is the regression guard for v1's core failure -- if a future
change reintroduces fragment "figures", the sub-120px assertion fails.
"""

import json
import os

import fitz
import pytest

from pdfdeck.extraction.detect import detect_page_regions
from pdfdeck.extraction.geometry import scale_for_dpi
from pdfdeck.extraction.ingest import ingest_pdf, raw_candidate_rects
from pdfdeck.models import Rect

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
PDF = os.path.join(FIXTURES, "repair.pdf")
ORACLE = json.load(open(os.path.join(FIXTURES, "repair_oracle.json"), encoding="utf-8"))

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def detected():
    pages, sha = ingest_pdf(PDF)
    doc = fitz.open(PDF)
    result = {}
    for pm in pages:
        img_rects, draw_rects = raw_candidate_rects(doc[pm.index])
        result[pm.index] = detect_page_regions(pm, img_rects, draw_rects)
    doc.close()
    return pages, sha, result


def test_page_count(detected):
    pages, _, _ = detected
    assert len(pages) == ORACLE["total_pages"]


def test_sha_matches_oracle(detected):
    _, sha, _ = detected
    assert sha.startswith(ORACLE["pdf_sha_prefix"])


def test_region_count_per_page(detected):
    _, _, regions = detected
    for page_idx_str, spec in ORACLE["pages"].items():
        idx = int(page_idx_str)
        assert len(regions[idx]) == spec["regions"], (
            f"page {idx + 1}: expected {spec['regions']} regions, "
            f"got {len(regions[idx])}"
        )


def test_total_figures(detected):
    _, _, regions = detected
    total = sum(len(r) for r in regions.values())
    assert total == ORACLE["total_figures"]


def test_no_fragment_figures(detected):
    """THE core regression guard: no rendered figure is a sub-120px sliver.

    Measured at 300 DPI (deck quality) -- a real figure is hundreds of px on
    both edges; v1's 87x87px fragments would trip this.
    """
    _, _, regions = detected
    scale = scale_for_dpi(300)
    for idx, regs in regions.items():
        for r in regs:
            w_px = r.bbox.width * scale
            h_px = r.bbox.height * scale
            assert not (w_px < 120 and h_px < 120), (
                f"page {idx + 1} region {r.id}: {w_px:.0f}x{h_px:.0f}px fragment"
            )


def test_page3_thousands_of_tiles_one_region(detected):
    """The 8,133-tile diagram collapses to exactly one region."""
    _, _, regions = detected
    p3 = regions[2]
    assert len(p3) == 1
    assert len(p3[0].source_rects) >= ORACLE["pages"]["2"]["min_source_rects"]


def test_page2_table_caption_associated(detected):
    _, _, regions = detected
    p2 = regions[1]
    assert len(p2) == 1
    assert p2[0].figure_no == ORACLE["pages"]["1"]["figure_no"]


def test_page8_keloid_stays_in_left_column(detected):
    """The keloid figure must not bridge the gutter into the RAPID REVIEW box."""
    _, _, regions = detected
    p8 = regions[7]
    assert len(p8) == 1
    assert p8[0].bbox.x1 < ORACLE["pages"]["7"]["max_bbox_x1"]


def test_regions_have_source_provenance(detected):
    """Every region carries its constituent rects (the 2,309-tile provenance)."""
    _, _, regions = detected
    for regs in regions.values():
        for r in regs:
            assert len(r.source_rects) >= 1
