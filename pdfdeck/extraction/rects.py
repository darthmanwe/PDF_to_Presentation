"""Figure-region detection: cluster tile/path placement rects into regions.

THE core fix for v1's fragmentation failure. A tiled diagram (e.g. 2,309
image XObjects on one page of repair.pdf) has no single extractable image —
but the tiles' PLACEMENT rectangles collectively cover the figure's area.
We cluster those rects and later render each clustered region as one flat
raster.

Algorithm (deliberately NOT pairwise distance-threshold clustering):
1. Filter noise rects (page-background images, thin rules, specks).
2. Rasterize surviving rects into a low-res binary occupancy mask.
3. Binary-dilate the mask (radius = the gap size we're willing to bridge).
4. Connected-components label the mask; each component -> one region bbox
   (the union of the ORIGINAL rects assigned to that component, so the
   bbox is exact, not mask-quantized).
5. Absorb small nearby text blocks (panel labels "A", axis text) into the
   region — but never paragraph-sized blocks.
6. Split any region that a caption block bisects (a caption BETWEEN two
   image clusters means they are two figures, not one).

O(mask pixels), one intuitive hyperparameter (dilation radius in points).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from pdfdeck.config import settings
from pdfdeck.models import Rect, TextBlock


@dataclass
class ClusterParams:
    """Tunables for one clustering pass (loosened on the re-detect retry)."""

    mask_px_per_pt: float = settings.mask_px_per_pt
    dilation_radius_pt: float = settings.dilation_radius_pt
    max_rect_page_frac: float = settings.max_rect_page_frac
    rule_max_height_pt: float = settings.rule_max_height_pt
    rule_min_aspect: float = settings.rule_min_aspect
    min_region_area_pt2: float = settings.min_region_area_pt2
    label_text_max_words: int = settings.label_text_max_words

    def loosened(self) -> "ClusterParams":
        """Retry parameters for pages with captions but zero detected regions."""
        return ClusterParams(
            mask_px_per_pt=self.mask_px_per_pt,
            dilation_radius_pt=self.dilation_radius_pt * 1.8,
            max_rect_page_frac=min(0.95, self.max_rect_page_frac + 0.1),
            rule_max_height_pt=self.rule_max_height_pt,
            rule_min_aspect=self.rule_min_aspect,
            min_region_area_pt2=self.min_region_area_pt2 / 4,
            label_text_max_words=self.label_text_max_words,
        )


@dataclass
class ClusteredRegion:
    """One detected figure-candidate region (pre-caption, pre-verification)."""

    bbox: Rect
    source_rects: list[Rect]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def filter_candidate_rects(
    rects: list[Rect], page_rect: Rect, params: ClusterParams
) -> list[Rect]:
    """Drop rects that would poison the mask.

    - page-background images / watermarks (cover most of the page)
    - thin full-width rules and near-zero-area stroke paths (would bridge
      unrelated figures vertically stacked in a column)
    - degenerate/inverted rects
    """
    page_area = page_rect.area
    kept: list[Rect] = []
    for r in rects:
        w, h = r.width, r.height
        if w <= 0 or h <= 0:
            continue
        if r.area > params.max_rect_page_frac * page_area:
            continue  # background image / watermark
        short, long_ = min(w, h), max(w, h)
        if short < params.rule_max_height_pt and long_ / max(short, 0.1) > params.rule_min_aspect:
            continue  # separator rule (horizontal or vertical)
        if r.area < 1.0:
            continue  # zero-ish stroke path
        kept.append(r)
    return kept


# ---------------------------------------------------------------------------
# Core clustering
# ---------------------------------------------------------------------------

def cluster_rects(
    rects: list[Rect],
    page_rect: Rect,
    params: ClusterParams | None = None,
) -> list[ClusteredRegion]:
    """Cluster candidate rects into figure regions via mask + dilation + CC."""
    params = params or ClusterParams()
    candidates = filter_candidate_rects(rects, page_rect, params)
    if not candidates:
        return []

    s = params.mask_px_per_pt
    mask_w = max(1, int(math.ceil(page_rect.width * s)))
    mask_h = max(1, int(math.ceil(page_rect.height * s)))
    mask = np.zeros((mask_h, mask_w), dtype=bool)

    def to_mask_coords(r: Rect) -> tuple[int, int, int, int]:
        x0 = max(0, int((r.x0 - page_rect.x0) * s))
        y0 = max(0, int((r.y0 - page_rect.y0) * s))
        x1 = min(mask_w, int(math.ceil((r.x1 - page_rect.x0) * s)))
        y1 = min(mask_h, int(math.ceil((r.y1 - page_rect.y0) * s)))
        return x0, y0, x1, y1

    for r in candidates:
        x0, y0, x1, y1 = to_mask_coords(r)
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = True

    # Dilate: bridge gaps up to dilation_radius_pt.
    radius_px = max(1, int(round(params.dilation_radius_pt * s)))
    structure = np.ones((2 * radius_px + 1, 2 * radius_px + 1), dtype=bool)
    dilated = ndimage.binary_dilation(mask, structure=structure)

    # Label connected components.
    labels, n_components = ndimage.label(dilated)
    if n_components == 0:
        return []

    # Assign each ORIGINAL rect to the component under its center, and build
    # exact bboxes from rect unions (not mask-quantized component extents).
    groups: dict[int, list[Rect]] = {}
    for r in candidates:
        cx = (r.x0 + r.x1) / 2
        cy = (r.y0 + r.y1) / 2
        mx = min(mask_w - 1, max(0, int((cx - page_rect.x0) * s)))
        my = min(mask_h - 1, max(0, int((cy - page_rect.y0) * s)))
        label = int(labels[my, mx])
        if label == 0:
            # Center fell just outside its dilated blob (rounding) — probe the
            # rect's own mask area instead.
            x0, y0, x1, y1 = to_mask_coords(r)
            patch = labels[y0:y1, x0:x1]
            nonzero = patch[patch > 0]
            label = int(nonzero[0]) if nonzero.size else 0
        if label > 0:
            groups.setdefault(label, []).append(r)

    regions: list[ClusteredRegion] = []
    for label, members in groups.items():
        bbox = members[0]
        for m in members[1:]:
            bbox = bbox.union(m)
        if bbox.area < params.min_region_area_pt2:
            continue  # speck
        regions.append(ClusteredRegion(bbox=bbox, source_rects=members))

    regions.sort(key=lambda reg: (reg.bbox.y0, reg.bbox.x0))
    return regions


# ---------------------------------------------------------------------------
# Post-processing: label absorption and caption-aware splitting
# ---------------------------------------------------------------------------

def absorb_label_text(
    regions: list[ClusteredRegion],
    text_blocks: list[TextBlock],
    params: ClusterParams | None = None,
    reach_pt: float = 6.0,
) -> list[ClusteredRegion]:
    """Grow each region to include SMALL text blocks touching/near it.

    Diagram labels (panel letters, axis text, arrow annotations) are text
    blocks, not drawings — without this step they'd be clipped off the
    render. Paragraph blocks are never absorbed (word_count guard), so body
    text can't drag a region across the column.
    """
    params = params or ClusterParams()
    out: list[ClusteredRegion] = []
    for reg in regions:
        bbox = reg.bbox
        grown = True
        # Iterate: absorbing one label can bring another into reach.
        while grown:
            grown = False
            probe = Rect(
                x0=bbox.x0 - reach_pt, y0=bbox.y0 - reach_pt,
                x1=bbox.x1 + reach_pt, y1=bbox.y1 + reach_pt,
            )
            for tb in text_blocks:
                if tb.is_caption or tb.word_count > params.label_text_max_words:
                    continue
                if probe.intersects(tb.bbox):
                    new_bbox = bbox.union(tb.bbox)
                    if new_bbox != bbox:
                        bbox = new_bbox
                        grown = True
        out.append(ClusteredRegion(bbox=bbox, source_rects=reg.source_rects))
    return out


def split_regions_at_captions(
    regions: list[ClusteredRegion],
    caption_blocks: list[TextBlock],
) -> list[ClusteredRegion]:
    """Split any region that a caption block horizontally bisects.

    A caption BETWEEN two image clusters (vertically) means the cluster pass
    wrongly merged two figures (repair.pdf p6). A caption BELOW all content
    (p7 multi-panel) does not trigger a split. Source rects are reassigned
    by center-y; a side with no rects is dropped.
    """
    out: list[ClusteredRegion] = []
    for reg in regions:
        pieces = [reg]
        for cap in caption_blocks:
            next_pieces: list[ClusteredRegion] = []
            for piece in pieces:
                b = piece.bbox
                cap_cy = (cap.bbox.y0 + cap.bbox.y1) / 2
                x_overlap = min(b.x1, cap.bbox.x1) - max(b.x0, cap.bbox.x0)
                # Caption strictly inside the region's vertical span (with a
                # margin so bottom-edge captions don't split), overlapping in x.
                margin = cap.bbox.height
                bisects = (
                    x_overlap > 0.5 * cap.bbox.width
                    and b.y0 + margin < cap_cy < b.y1 - margin
                )
                if not bisects:
                    next_pieces.append(piece)
                    continue
                above = [r for r in piece.source_rects if (r.y0 + r.y1) / 2 < cap_cy]
                below = [r for r in piece.source_rects if (r.y0 + r.y1) / 2 >= cap_cy]
                if not above or not below:
                    next_pieces.append(piece)  # nothing on one side: no split
                    continue
                for side in (above, below):
                    bbox = side[0]
                    for m in side[1:]:
                        bbox = bbox.union(m)
                    next_pieces.append(ClusteredRegion(bbox=bbox, source_rects=side))
            pieces = next_pieces
        out.extend(pieces)
    out.sort(key=lambda reg: (reg.bbox.y0, reg.bbox.x0))
    return out


def constrain_to_column(
    region: ClusteredRegion,
    column_bounds: list[tuple[float, float]],
    full_width_col_frac: float = settings.full_width_col_frac,
) -> tuple[ClusteredRegion, bool]:
    """Clip a region to its column unless it is a full-width figure.

    Returns (region, is_full_width). Multi-column pages only; single-column
    pages pass through untouched.
    """
    if len(column_bounds) < 2:
        return region, False
    col_width = max(hi - lo for lo, hi in column_bounds)
    if region.bbox.width > full_width_col_frac * col_width:
        return region, True  # spans columns; leave as-is

    # Pick the column with the greatest x-overlap.
    def overlap(lo: float, hi: float) -> float:
        return max(0.0, min(region.bbox.x1, hi) - max(region.bbox.x0, lo))

    lo, hi = max(column_bounds, key=lambda b: overlap(*b))
    clipped = Rect(
        x0=max(region.bbox.x0, lo - 2.0),
        y0=region.bbox.y0,
        x1=min(region.bbox.x1, hi + 2.0),
        y1=region.bbox.y1,
    )
    return ClusteredRegion(bbox=clipped, source_rects=region.source_rects), False
