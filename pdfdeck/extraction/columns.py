"""Column detection and reading-order correction for 2-column layouts.

v1 fed `page.get_text()` (raw character-stream order) to the LLM, which
interleaves columns on textbook pages. Here text blocks are assigned to
columns by x-position and sorted (column, y) so downstream consumers see
human reading order.
"""

from __future__ import annotations

from pdfdeck.models import TextBlock


def detect_column_split(
    blocks: list[TextBlock],
    page_width: float,
    min_side_frac: float = 0.20,
) -> float | None:
    """Return the x of the gutter between two columns, or None if single-column.

    Whitespace-corridor method: project the x-intervals of COLUMN-WIDTH body
    blocks onto the x-axis and find the widest x-band in the central region
    that no such block covers. That band is the gutter. Full-width blocks
    (headings, wide captions) are excluded from the projection so they don't
    paper over the corridor — the failure mode of the old max/min approach,
    which a single wide block on p8 (A4) collapsed.
    """
    body = [b for b in blocks if b.word_count >= 3]
    if len(body) < 6:
        return None

    # Column-width blocks only: a full-width element crosses the gutter and
    # must not hide it.
    col_blocks = [b for b in body if b.bbox.width < 0.55 * page_width]
    if len(col_blocks) < 4:
        return None

    center_lo = page_width * 0.30
    center_hi = page_width * 0.70
    step = 2.0

    def covered(x: float) -> bool:
        return any(b.bbox.x0 - 1 <= x <= b.bbox.x1 + 1 for b in col_blocks)

    runs: list[tuple[float, float]] = []
    start: float | None = None
    x = center_lo
    while x <= center_hi:
        if not covered(x):
            if start is None:
                start = x
        elif start is not None:
            runs.append((start, x))
            start = None
        x += step
    if start is not None:
        runs.append((start, center_hi))
    if not runs:
        return None

    lo, hi = max(runs, key=lambda r: r[1] - r[0])
    if hi - lo < 6:  # corridor too narrow => single column
        return None
    split = (lo + hi) / 2

    left_count = sum(1 for b in col_blocks if b.bbox.x1 <= split + 2)
    right_count = sum(1 for b in col_blocks if b.bbox.x0 >= split - 2)
    if min(left_count, right_count) < min_side_frac * len(col_blocks):
        return None
    return split


def assign_columns(blocks: list[TextBlock], split_x: float | None) -> None:
    """Set .column on each block in place. Full-width blocks get column 0."""
    for b in blocks:
        if split_x is None:
            b.column = 0
        elif b.bbox.x1 <= split_x + 2:
            b.column = 0
        elif b.bbox.x0 >= split_x - 2:
            b.column = 1
        else:
            b.column = 0  # straddles the gutter: treat as full-width/left


def order_reading(blocks: list[TextBlock]) -> list[TextBlock]:
    """Sort blocks into reading order: column-major, top-to-bottom."""
    return sorted(blocks, key=lambda b: (b.column or 0, b.bbox.y0, b.bbox.x0))


def column_bounds(
    blocks: list[TextBlock], split_x: float | None, page_width: float
) -> list[tuple[float, float]]:
    """(x_lo, x_hi) extents per column, for region column-constraining."""
    if split_x is None:
        return [(0.0, page_width)]
    return [(0.0, split_x), (split_x, page_width)]
