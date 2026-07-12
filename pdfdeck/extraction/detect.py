"""Region detection composition: raw rects -> finalized Region objects.

Orchestrates the extraction primitives with provenance and column awareness:
  partition by column (2-col pages) -> cluster each partition
  -> drop margin banners -> merge genuine full-width figures back
  -> qualify (image content OR many drawings) -> absorb labels
  -> caption-split -> column-constrain -> classify -> associate captions
  -> clip above caption baseline

Provenance (image vs drawing rects) and per-column clustering are what keep
a left-column figure from bridging across the gutter into a right-column
text box (repair.pdf p8). Pure given its inputs.
"""

from __future__ import annotations

from pdfdeck.config import settings
from pdfdeck.extraction.caption_match import associate_captions
from pdfdeck.extraction.classifier import classify_region
from pdfdeck.extraction.columns import column_bounds
from pdfdeck.extraction.rects import (
    ClusterParams,
    ClusteredRegion,
    absorb_label_text,
    cluster_rects,
    constrain_to_column,
    split_regions_at_captions,
)
from pdfdeck.models import PageModel, Rect, Region


def _is_margin_banner(
    bbox: Rect, page_height: float, top_band_frac: float, bottom_band_frac: float
) -> bool:
    """Running head/foot decoration: short, lives entirely in a margin band."""
    top_band = page_height * top_band_frac
    bottom_band = page_height * (1 - bottom_band_frac)
    short = bbox.height < 60.0
    in_top = bbox.y1 <= top_band
    in_bottom = bbox.y0 >= bottom_band
    return short and (in_top or in_bottom)


def _partition_by_column(
    rects: list[Rect], split_x: float | None
) -> list[list[Rect]]:
    """Split rects into column buckets so dilation can't bridge the gutter.

    Left, right, and a full-width bucket (rects that genuinely span the
    gutter). Single-column pages return one bucket.
    """
    if split_x is None:
        return [rects]
    left: list[Rect] = []
    right: list[Rect] = []
    full: list[Rect] = []
    for r in rects:
        if r.x0 < split_x - 4 and r.x1 > split_x + 4:
            full.append(r)  # spans the gutter
        elif (r.x0 + r.x1) / 2 < split_x:
            left.append(r)
        else:
            right.append(r)
    return [b for b in (left, right, full) if b]


def _merge_full_width(
    regions: list[tuple[ClusteredRegion, int, int]],
) -> list[tuple[ClusteredRegion, int, int]]:
    """Merge column regions that together form one full-width figure.

    Two regions from different column partitions that overlap strongly in y
    and abut/overlap in x are one figure split by the partition step. Only
    image-bearing pieces merge (a text box never joins a figure). Counts are
    summed.
    """
    merged = True
    items = list(regions)
    while merged:
        merged = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (ra, ia, da), (rb, ib, db) = items[i], items[j]
                if ia == 0 or ib == 0:
                    continue  # need image content on both sides to be a figure
                a, b = ra.bbox, rb.bbox
                y_overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
                y_frac = y_overlap / min(a.height, b.height) if min(a.height, b.height) > 0 else 0
                x_gap = max(a.x0, b.x0) - min(a.x1, b.x1)
                if y_frac >= 0.5 and x_gap <= 12:
                    combined = ClusteredRegion(
                        bbox=a.union(b), source_rects=ra.source_rects + rb.source_rects
                    )
                    items[i] = (combined, ia + ib, da + db)
                    del items[j]
                    merged = True
                    break
            if merged:
                break
    return items


def detect_page_regions(
    page: PageModel,
    image_rects: list[Rect],
    drawing_rects: list[Rect],
    params: ClusterParams | None = None,
    top_band_frac: float = 0.11,
    bottom_band_frac: float = 0.06,
) -> list[Region]:
    """Detect figure regions on one page. Does not mutate `page`."""
    params = params or ClusterParams()
    page_rect = Rect(x0=0, y0=0, x1=page.width, y1=page.height)

    all_rects = image_rects + drawing_rects
    image_ids = {id(r) for r in image_rects}

    # Cluster per column partition so the gutter is never bridged.
    clustered: list[ClusteredRegion] = []
    for bucket in _partition_by_column(all_rects, page.column_split_x):
        clustered.extend(cluster_rects(bucket, page_rect, params))

    clustered = [
        c for c in clustered
        if not _is_margin_banner(c.bbox, page.height, top_band_frac, bottom_band_frac)
    ]
    if not clustered:
        return []

    # Attach per-region provenance counts, then merge genuine full-width figures.
    counted: list[tuple[ClusteredRegion, int, int]] = []
    for c in clustered:
        n_img = sum(1 for r in c.source_rects if id(r) in image_ids)
        counted.append((c, n_img, len(c.source_rects) - n_img))
    counted = _merge_full_width(counted)

    # Qualify: a figure needs image content OR enough drawings to be a real
    # diagram/table (not a shaded callout box).
    qualified = [
        c for (c, n_img, n_draw) in counted
        if n_img > 0 or n_draw >= params_min_drawings(params)
    ]
    if not qualified:
        return []
    qualified.sort(key=lambda reg: (reg.bbox.y0, reg.bbox.x0))

    qualified = absorb_label_text(qualified, page.text_blocks, params)

    caption_blocks = [b for b in page.text_blocks if b.is_caption]
    qualified = split_regions_at_captions(qualified, caption_blocks)

    bounds = column_bounds(page.text_blocks, page.column_split_x, page.width)
    constrained: list[tuple[ClusteredRegion, bool]] = []
    for reg in qualified:
        reg2, is_full_width = constrain_to_column(reg, bounds)
        constrained.append((reg2, is_full_width))

    assignments = associate_captions(
        [reg.bbox for reg, _ in constrained], caption_blocks
    )

    regions: list[Region] = []
    for idx, (reg, is_full_width) in enumerate(constrained):
        kind, confidence = classify_region(reg.source_rects, reg.bbox)
        assignment = assignments.get(idx)

        bbox = reg.bbox
        caption_text = None
        figure_no = None
        caption_bbox = None
        if assignment:
            caption_text = assignment.caption_block.text
            figure_no = assignment.figure_no
            caption_bbox = assignment.caption_block.bbox
            # Caption goes on the slide as text -- keep it out of the pixels.
            if assignment.position == "below" and caption_bbox.y0 < bbox.y1:
                bbox = Rect(
                    x0=bbox.x0, y0=bbox.y0, x1=bbox.x1,
                    y1=max(bbox.y0 + 1.0, caption_bbox.y0 - 2.0),
                )

        regions.append(
            Region(
                id=f"p{page.index}_r{idx}",
                page_index=page.index,
                bbox=bbox,
                source_rects=reg.source_rects,
                kind=kind,
                classifier_confidence=confidence,
                caption=caption_text,
                figure_no=figure_no,
                caption_bbox=caption_bbox,
                is_full_width=is_full_width,
            )
        )
    return regions


def params_min_drawings(params: ClusterParams) -> int:
    return settings.qualify_min_drawings
