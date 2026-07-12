"""Coordinate-transform round-trips and bbox-delta application."""

from pdfdeck.extraction.geometry import (
    BboxDelta,
    apply_bbox_delta,
    pad_rect,
    pdf_rect_to_pixel_bbox,
    pixel_bbox_to_pdf_rect,
)
from pdfdeck.models import Rect

PAGE = Rect(x0=0, y0=0, x1=612, y1=792)  # US Letter in points


def test_pixel_roundtrip_within_epsilon():
    rect = Rect(x0=72.3, y0=100.7, x1=310.2, y1=402.9)
    clip = Rect(x0=50, y0=80, x1=400, y1=500)
    px = pdf_rect_to_pixel_bbox(rect, clip, dpi=300)
    back = pixel_bbox_to_pdf_rect(px, clip, dpi=300)
    # 300 DPI => 1px = 0.24pt; rounding error must stay below one pixel.
    for a, b in [(rect.x0, back.x0), (rect.y0, back.y0), (rect.x1, back.x1), (rect.y1, back.y1)]:
        assert abs(a - b) < 0.25


def test_delta_expands_all_edges():
    box = Rect(x0=100, y0=100, x1=200, y1=300)
    out = apply_bbox_delta(
        box,
        BboxDelta(expand_left=0.1, expand_top=0.05, expand_right=0.2, expand_bottom=0.0),
        PAGE,
    )
    assert out.x0 == 100 - 0.1 * 100
    assert out.y0 == 100 - 0.05 * 200
    assert out.x1 == 200 + 0.2 * 100
    assert out.y1 == 300


def test_delta_clamps_to_page():
    box = Rect(x0=5, y0=5, x1=600, y1=780)
    out = apply_bbox_delta(
        box, BboxDelta(expand_left=1.0, expand_top=1.0, expand_right=1.0, expand_bottom=1.0), PAGE
    )
    assert out.x0 == 0 and out.y0 == 0
    assert out.x1 == 612 and out.y1 == 792


def test_delta_never_inverts():
    box = Rect(x0=100, y0=100, x1=110, y1=110)
    out = apply_bbox_delta(
        box,
        BboxDelta(expand_left=-3.0, expand_right=-3.0, expand_top=-3.0, expand_bottom=-3.0),
        PAGE,
    )
    assert out.x1 > out.x0 and out.y1 > out.y0


def test_pad_rect_symmetric():
    box = Rect(x0=100, y0=100, x1=200, y1=200)
    out = pad_rect(box, 0.10, PAGE)
    assert out.x0 == 90 and out.y0 == 90 and out.x1 == 210 and out.y1 == 210
