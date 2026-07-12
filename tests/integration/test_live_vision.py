"""Opt-in live smoke tests against the real Anthropic API.

Run explicitly:  pytest -m vision
Skipped by default (pyproject addopts = -m 'not vision') and skipped if no
ANTHROPIC_API_KEY is set. These are smoke checks that the real Claude wiring
works end to end -- not asserted heavily, since model output varies.
"""

import os

import pytest

from pdfdeck.config import settings

pytestmark = pytest.mark.vision

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
PDF = os.path.join(FIXTURES, "repair.pdf")

_NO_KEY = not (settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(_NO_KEY, reason="ANTHROPIC_API_KEY not set")
def test_vision_verifier_returns_a_verdict():
    """Render one real figure crop and confirm the live verifier returns a verdict."""
    import fitz

    from pdfdeck.agents.vision_verifier import ClaudeVisionVerifier, Verdict
    from pdfdeck.extraction.detect import detect_page_regions
    from pdfdeck.extraction.ingest import ingest_pdf, raw_candidate_rects
    from pdfdeck.rendering.page_render import render_verify_image

    pages, _ = ingest_pdf(PDF)
    doc = fitz.open(PDF)
    # Page 3: the 8,133-tile diagram -- the hardest crop to judge.
    pm = pages[2]
    img_rects, draw_rects = raw_candidate_rects(doc[2])
    regions = detect_page_regions(pm, img_rects, draw_rects)
    assert regions
    tmp = os.path.join("runs", "live_smoke", "verify.png")
    render_verify_image(doc[2], regions[0].bbox, tmp)

    result = ClaudeVisionVerifier().verify(tmp, regions[0].caption, regions[0].kind.value)
    assert isinstance(result.verdict, Verdict)
    doc.close()


@pytest.mark.skipif(_NO_KEY, reason="ANTHROPIC_API_KEY not set")
def test_full_live_conversion():
    """Full pipeline with real Claude agents (deterministic figures for speed)."""
    from pdfdeck.pipeline import convert_pdf

    result = convert_pdf(PDF, target_language=None, vision_enabled=False,
                         run_dir=os.path.join("runs", "live_smoke_full"))
    assert os.path.exists(result.output_path)
    assert len(result.figures) == 8
    text_slides = [s for s in result.slides if s.slide_type == "text"]
    assert text_slides and all(s.bullets for s in text_slides)
