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

# Caption must START the block. Case-insensitive so all-caps abbreviations
# ("FIG. 2.24", the form Robbins uses) match alongside "Figure 4.12" / "Fig 4.12".
# Anchored at block start, so inline references ("...see Fig. 2.16...") never match.
_CAPTION_RE = re.compile(
    r"^\s*(?:figure|fig\.?)\s+(\d+(?:[.\-]\d+)?[A-Za-z]?)\b", re.IGNORECASE | re.UNICODE
)
# Table captions handled the same way (rendered regions may be tables).
_TABLE_RE = re.compile(r"^\s*table\s+(\d+(?:[.\-]\d+)?)\b", re.IGNORECASE | re.UNICODE)


# f-ligatures survive PDF text extraction ("inﬂammation"); normalize them.
_LIGATURES = str.maketrans(
    {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
     "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st"}
)


def clean_caption(text: str) -> str:
    """Normalize a caption for display: fix f-ligatures, de-hyphenate soft
    line-break hyphens ('forma- tion' -> 'formation'), collapse whitespace."""
    text = text.translate(_LIGATURES)
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip()


def caption_title(caption: str | None, max_len: int = 150) -> str | None:
    """Promote a caption to a slide title: the label + its first sentence,
    verbatim and de-hyphenated. 'Table 2.10 Growth Factors' stays whole;
    'FIG. 2.24 Healing wound. (A) ...' becomes 'FIG. 2.24 Healing wound.'"""
    if not caption:
        return None
    text = clean_caption(caption)
    m = _CAPTION_RE.match(text) or _TABLE_RE.match(text)
    if m:
        head = text[: m.end()]                       # "FIG. 2.24"
        rest = text[m.end():].lstrip()               # "Healing wound. (A) ..."
        first = re.split(r"(?<=\.)\s", rest, maxsplit=1)[0] if rest else ""
        title = (head + " " + first).strip()
    else:
        title = text
    if len(title) > max_len:
        title = title[: max_len - 1].rstrip() + "…"
    return title


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
            # Tolerate a caption whose top edge dips slightly into the region's
            # bottom (common: the figure art's bbox overlaps the caption's first
            # line by a few points). Slack = half the caption's height, so a
            # bottom caption still reads as "below" while a caption bisecting the
            # figure mid-height does not (the split step handles that).
            slack = max(4.0, 0.5 * cap.bbox.height)
            if cap.bbox.y0 >= rb.y1 - slack:        # below the region
                gap = max(0.0, cap.bbox.y0 - rb.y1)
                position = "below"
            elif cap.bbox.y1 <= rb.y0 + slack:      # above the region
                gap = max(0.0, rb.y0 - cap.bbox.y1)
                position = "above"
            else:
                continue  # caption bisects the region: split step handles it
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
