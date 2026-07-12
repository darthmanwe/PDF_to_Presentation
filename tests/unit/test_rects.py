"""Clustering: the 2,309-tiles-to-1-region behavior and its guard rails."""

import random

from pdfdeck.extraction.rects import (
    ClusterParams,
    absorb_label_text,
    cluster_rects,
    constrain_to_column,
    split_regions_at_captions,
)
from pdfdeck.models import Rect, TextBlock

PAGE = Rect(x0=0, y0=0, x1=612, y1=792)
PARAMS = ClusterParams()


def _tile_grid(x0, y0, x1, y1, nx, ny, jitter=0.0):
    """Synthetic tiled diagram: nx*ny abutting tiles filling the envelope."""
    rng = random.Random(42)
    tiles = []
    w, h = (x1 - x0) / nx, (y1 - y0) / ny
    for i in range(nx):
        for j in range(ny):
            jx = rng.uniform(-jitter, jitter)
            jy = rng.uniform(-jitter, jitter)
            tiles.append(
                Rect(
                    x0=x0 + i * w + jx, y0=y0 + j * h + jy,
                    x1=x0 + (i + 1) * w + jx, y1=y0 + (j + 1) * h + jy,
                )
            )
    return tiles


def test_page3_scenario_thousands_of_tiles_one_region():
    """The repair.pdf p3 case: ~2.3k tiny tiles in one figure envelope."""
    tiles = _tile_grid(60, 80, 540, 420, nx=48, ny=48, jitter=0.3)  # 2304 tiles
    regions = cluster_rects(tiles, PAGE, PARAMS)
    assert len(regions) == 1
    assert len(regions[0].source_rects) == 2304
    b = regions[0].bbox
    assert abs(b.x0 - 60) < 2 and abs(b.y1 - 420) < 2


def test_two_separated_figures_stay_separate():
    top = _tile_grid(60, 80, 300, 250, nx=6, ny=6)
    bottom = _tile_grid(60, 400, 300, 570, nx=6, ny=6)  # 150pt gap >> dilation
    regions = cluster_rects(top + bottom, PAGE, PARAMS)
    assert len(regions) == 2


def test_thin_strips_merge_into_parent():
    """36x136-style strips (repair.pdf p5) join the adjacent block."""
    block = _tile_grid(60, 80, 200, 216, nx=4, ny=4)
    strips = [Rect(x0=204, y0=80 + i * 34, x1=216, y1=80 + (i + 1) * 34) for i in range(4)]
    regions = cluster_rects(block + strips, PAGE, PARAMS)
    assert len(regions) == 1
    assert len(regions[0].source_rects) == 20


def test_page_background_rect_filtered():
    background = Rect(x0=0, y0=0, x1=612, y1=792)
    figure = _tile_grid(60, 80, 300, 250, nx=4, ny=4)
    regions = cluster_rects([background] + figure, PAGE, PARAMS)
    assert len(regions) == 1
    assert all(r.area < 0.5 * PAGE.area for r in regions[0].source_rects)


def test_full_width_rule_does_not_bridge_figures():
    """A 1.5pt-high horizontal rule between two figures must not merge them."""
    top = _tile_grid(60, 80, 300, 200, nx=4, ny=4)
    bottom = _tile_grid(60, 260, 300, 380, nx=4, ny=4)
    rule = Rect(x0=40, y0=228, x1=572, y1=229.5)
    regions = cluster_rects(top + [rule] + bottom, PAGE, ClusterParams(dilation_radius_pt=20.0))
    # With a large radius the two figures merge on their own (40pt gap < 2x20);
    # so use the default radius where the 60pt gap keeps them apart, and check
    # the rule doesn't bridge it.
    regions = cluster_rects(top + [rule] + bottom, PAGE, PARAMS)
    assert len(regions) == 2


def test_specks_discarded():
    speck = [Rect(x0=100, y0=100, x1=104, y1=104)]
    assert cluster_rects(speck, PAGE, PARAMS) == []


def test_caption_between_figures_splits_region():
    """repair.pdf p6: two stacked photos + caption between => split into 2."""
    top = _tile_grid(60, 80, 300, 240, nx=2, ny=2)
    bottom = _tile_grid(60, 300, 300, 460, nx=2, ny=2)
    # Force-merge them with a generous radius (gap 60pt, radius 35 bridges it).
    merged = cluster_rects(top + bottom, PAGE, ClusterParams(dilation_radius_pt=35.0))
    assert len(merged) == 1  # precondition: wrongly merged

    caption = TextBlock(
        span_id="p5_b9",
        text="Figure 3.1 Top figure caption sits between the two photos.",
        bbox=Rect(x0=60, y0=262, x1=300, y1=280),
        word_count=10,
        is_caption=True,
    )
    split = split_regions_at_captions(merged, [caption])
    assert len(split) == 2
    assert split[0].bbox.y1 <= 262 + 1
    assert split[1].bbox.y0 >= 280 - 1


def test_caption_below_all_panels_does_not_split():
    """repair.pdf p7: multi-panel figure, caption BELOW everything => 1 region."""
    panels = _tile_grid(60, 80, 540, 420, nx=3, ny=2)
    merged = cluster_rects(panels, PAGE, ClusterParams(dilation_radius_pt=35.0))
    caption = TextBlock(
        span_id="p6_b9",
        text="Figure 4.2 Multi-panel figure with sub-panels A-F.",
        bbox=Rect(x0=60, y0=430, x1=540, y1=448),
        word_count=8,
        is_caption=True,
    )
    split = split_regions_at_captions(merged, [caption])
    assert len(split) == len(merged) == 1


def test_absorb_small_label_but_not_paragraph():
    figure = cluster_rects(_tile_grid(100, 100, 300, 300, nx=4, ny=4), PAGE, PARAMS)
    label = TextBlock(
        span_id="p0_b1", text="A", word_count=1,
        bbox=Rect(x0=302, y0=102, x1=312, y1=114),
    )
    paragraph = TextBlock(
        span_id="p0_b2",
        text="This is a long body paragraph that must never be absorbed " * 3,
        word_count=33,
        bbox=Rect(x0=302, y0=150, x1=560, y1=290),
    )
    out = absorb_label_text(figure, [label, paragraph], PARAMS)
    assert out[0].bbox.x1 >= 312          # label absorbed
    assert out[0].bbox.x1 < 400           # paragraph NOT absorbed


def test_column_constraint_and_full_width_exception():
    cols = [(0.0, 300.0), (312.0, 612.0)]
    narrow = cluster_rects(_tile_grid(60, 80, 290, 250, nx=3, ny=3), PAGE, PARAMS)[0]
    constrained, full = constrain_to_column(narrow, cols)
    assert not full
    assert constrained.bbox.x1 <= 302

    wide = cluster_rects(_tile_grid(60, 80, 560, 250, nx=6, ny=3), PAGE, PARAMS)[0]
    constrained, full = constrain_to_column(wide, cols)
    assert full
    assert constrained.bbox.x1 > 500  # untouched
