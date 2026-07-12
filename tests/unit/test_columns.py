"""Column detection and reading order."""

import random

from pdfdeck.extraction.columns import (
    assign_columns,
    column_bounds,
    detect_column_split,
    order_reading,
)
from pdfdeck.models import Rect, TextBlock

PAGE_W = 612.0


def _block(x0, y0, x1, y1, text="lorem ipsum dolor sit amet consectetur"):
    return TextBlock(
        span_id="", text=text, word_count=len(text.split()),
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
    )


def _two_column_page():
    """Blocks alternating columns, delivered in scrambled stream order."""
    left = [_block(50, 80 + i * 90, 290, 150 + i * 90) for i in range(6)]
    right = [_block(322, 80 + i * 90, 562, 150 + i * 90) for i in range(6)]
    blocks = left + right
    random.Random(7).shuffle(blocks)
    return blocks, left, right


def test_two_column_split_detected():
    blocks, _, _ = _two_column_page()
    split = detect_column_split(blocks, PAGE_W)
    assert split is not None
    assert 290 < split < 322


def test_single_column_returns_none():
    blocks = [_block(72, 80 + i * 90, 540, 150 + i * 90) for i in range(6)]
    assert detect_column_split(blocks, PAGE_W) is None


def test_too_few_blocks_no_crash():
    assert detect_column_split([_block(50, 80, 290, 150)], PAGE_W) is None
    assert detect_column_split([], PAGE_W) is None


def test_reading_order_column_major():
    blocks, left, right = _two_column_page()
    split = detect_column_split(blocks, PAGE_W)
    assign_columns(blocks, split)
    ordered = order_reading(blocks)
    # All left-column blocks first (top to bottom), then all right-column.
    assert [b.bbox.x0 for b in ordered[:6]] == [50.0] * 6
    assert [b.bbox.y0 for b in ordered[:6]] == sorted(b.bbox.y0 for b in left)
    assert [b.bbox.x0 for b in ordered[6:]] == [322.0] * 6
    assert [b.bbox.y0 for b in ordered[6:]] == sorted(b.bbox.y0 for b in right)


def test_column_bounds():
    assert column_bounds([], None, PAGE_W) == [(0.0, PAGE_W)]
    bounds = column_bounds([], 306.0, PAGE_W)
    assert bounds == [(0.0, 306.0), (306.0, PAGE_W)]
