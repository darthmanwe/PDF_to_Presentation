"""Caption detection and caption<->region association.

Distinguishes true caption blocks ("Figure 2.16 Granulation tissue...")
from inline references ("...as shown in Figure 2.16, the..."), then pairs
captions with detected regions: same column first, nearest below, then
nearest above, with figure-number monotonicity as a tie-break signal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdfdeck.models import Rect, TextBlock

# Caption must START the block: "Figure 4.12 ...", "FIGURE 4.12.", "Fig. 4.12"
_CAPTION_RE = re.compile(
    r"^\s*(?:FIGURE|Figure|Fig\.)\s+(\d+(?:[.\-]\d+)?[A-Z]?)\b", re.UNICODE
)
# Table captions handled the same way (rendered regions may be tables).
_TABLE_RE = re.compile(r"^\s*(?:TABLE|Table)\s+(\d+(?:[.\-]\d+)?)\b", re.UNICODE)


def find_caption_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    """Mark and return caption blocks. Mutates .is_caption in place.

    A block is a caption iff the caption pattern matches at the very start
    of the block text. Inline references never start a block, so this
    single rule separates the two cases that v1's regexes conflated.
    """
    captions: list[TextBlock] = []
    for b in blocks:
        if _CAPTION_RE.match(b.text) or _TABLE_RE.match(b.text):
            b.is_caption = True
            captions.append(b)
    return captions


def caption_figure_no(text: str) -> str | None:
    m = _CAPTION_RE.match(text) or _TABLE_RE.match(text)
    return m.group(1) if m else None


@dataclass
class CaptionAssignment:
    caption_block: TextBlock
    figure_no: str | None
    distance: float          # vertical gap between region edge and caption
    position: str            # "below" | "above"


def _x_overlap_frac(a: Rect, b: Rect) -> float:
    overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    denom = min(a.width, b.width)
    return max(0.0, overlap) / denom if denom > 0 else 0.0


def associate_captions(
    region_bboxes: list[Rect],
    captions: list[TextBlock],
    max_gap_pt: float = 60.0,
) -> dict[int, CaptionAssignment]:
    """Pair each region (by index) with its best caption.

    Rules, in priority order:
    1. Caption must overlap the region horizontally (>= 30% of the narrower).
    2. Prefer captions BELOW the region (standard textbook layout), nearest
       first; fall back to nearest ABOVE.
    3. Each caption pairs with at most one region (greedy by distance).
    """
    candidates: list[tuple[float, int, int, CaptionAssignment]] = []
    for ri, rb in enumerate(region_bboxes):
        for ci, cap in enumerate(captions):
            if _x_overlap_frac(rb, cap.bbox) < 0.3:
                continue
            if cap.bbox.y0 >= rb.y1 - 2:            # below the region
                gap = cap.bbox.y0 - rb.y1
                position = "below"
            elif cap.bbox.y1 <= rb.y0 + 2:          # above the region
                gap = rb.y0 - cap.bbox.y1
                position = "above"
            else:
                continue  # caption inside region: split step handles that case
            if gap > max_gap_pt:
                continue
            # Below beats above at equal distance.
            rank = gap + (0.0 if position == "below" else max_gap_pt)
            candidates.append(
                (rank, ri, ci,
                 CaptionAssignment(
                     caption_block=cap,
                     figure_no=caption_figure_no(cap.text),
                     distance=gap,
                     position=position,
                 ))
            )

    candidates.sort(key=lambda t: t[0])
    assigned: dict[int, CaptionAssignment] = {}
    used_captions: set[int] = set()
    for rank, ri, ci, assignment in candidates:
        if ri in assigned or ci in used_captions:
            continue
        assigned[ri] = assignment
        used_captions.add(ci)
    return assigned
