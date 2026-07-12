"""Photo/diagram classification and vision-call gating."""

from pdfdeck.extraction.classifier import classify_region, needs_vision_verification
from pdfdeck.models import Rect, RegionKind


def _tiles(n, size=8.0, per_row=40):
    return [
        Rect(
            x0=(i % per_row) * size, y0=(i // per_row) * size,
            x1=(i % per_row + 1) * size, y1=(i // per_row + 1) * size,
        )
        for i in range(n)
    ]


def test_many_tiles_is_diagram():
    tiles = _tiles(147)
    bbox = tiles[0]
    for t in tiles[1:]:
        bbox = bbox.union(t)
    kind, conf = classify_region(tiles, bbox)
    assert kind == RegionKind.DIAGRAM
    assert conf > 0.6


def test_two_large_rects_is_photo():
    rects = [Rect(x0=0, y0=0, x1=250, y1=180), Rect(x0=260, y0=0, x1=510, y1=180)]
    bbox = rects[0].union(rects[1])
    kind, conf = classify_region(rects, bbox)
    assert kind == RegionKind.PHOTO
    assert conf >= 0.6


def test_single_photo():
    rects = [Rect(x0=0, y0=0, x1=360, y1=250)]
    kind, conf = classify_region(rects, rects[0])
    assert kind == RegionKind.PHOTO


def test_few_sparse_pieces_leans_diagram():
    rects = [
        Rect(x0=0, y0=0, x1=30, y1=20),
        Rect(x0=200, y0=150, x1=240, y1=170),
        Rect(x0=400, y0=300, x1=430, y1=330),
    ]
    bbox = Rect(x0=0, y0=0, x1=430, y1=330)
    kind, _ = classify_region(rects, bbox)
    assert kind == RegionKind.DIAGRAM


def test_empty_is_unknown():
    kind, conf = classify_region([], Rect(x0=0, y0=0, x1=10, y1=10))
    assert kind == RegionKind.UNKNOWN and conf == 0.0


def test_gating():
    # Confident captioned photo skips the vision call...
    assert not needs_vision_verification(RegionKind.PHOTO, 0.85, has_caption=True)
    # ...everything else gets verified.
    assert needs_vision_verification(RegionKind.PHOTO, 0.85, has_caption=False)
    assert needs_vision_verification(RegionKind.PHOTO, 0.6, has_caption=True)
    assert needs_vision_verification(RegionKind.DIAGRAM, 0.99, has_caption=True)
    assert needs_vision_verification(RegionKind.UNKNOWN, 0.3, has_caption=False)
