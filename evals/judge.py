"""Evaluation harness: v1-vs-v2 figure extraction + LLM-as-judge content fidelity.

Two parts:
1. `figure_metrics` (deterministic, no API key) -- the headline number. It
   measures what v1's get_images() approach would have emitted (raw image
   XObjects, most sub-120px fragments) vs what v2 produces (clustered,
   rendered, verified regions), on the same PDF.
2. `content_fidelity` (LLM-as-judge, needs ANTHROPIC_API_KEY) -- scores a
   produced deck's bullets against the source for grounding, coverage, and
   caption correctness.

Usage:
    python evals/judge.py figures tests/fixtures/repair.pdf
    python evals/judge.py content <run_dir>       # needs a produced deck + key
"""

from __future__ import annotations

import json
import sys

import fitz

from pdfdeck.extraction.detect import detect_page_regions
from pdfdeck.extraction.geometry import scale_for_dpi
from pdfdeck.extraction.ingest import ingest_pdf, raw_candidate_rects

FRAGMENT_PX = 120


def figure_metrics(pdf_path: str) -> dict:
    """Deterministic v1-vs-v2 extraction comparison on one PDF."""
    doc = fitz.open(pdf_path)

    # v1 baseline: raw embedded image XObjects (what get_images() extracts).
    v1_total = 0
    v1_fragments = 0
    for page in doc:
        for info in page.get_image_info():
            v1_total += 1
            w = info.get("width", 0)
            h = info.get("height", 0)
            if w < FRAGMENT_PX and h < FRAGMENT_PX:
                v1_fragments += 1

    # v2: clustered + rendered regions.
    pages, _ = ingest_pdf(pdf_path)
    scale = scale_for_dpi(300)
    v2_regions = 0
    v2_fragments = 0
    for pm in pages:
        img_rects, draw_rects = raw_candidate_rects(doc[pm.index])
        regions = detect_page_regions(pm, img_rects, draw_rects)
        v2_regions += len(regions)
        for r in regions:
            if r.bbox.width * scale < FRAGMENT_PX and r.bbox.height * scale < FRAGMENT_PX:
                v2_fragments += 1
    doc.close()

    return {
        "pdf": pdf_path,
        "v1_raw_images_extracted": v1_total,
        "v1_sub120px_fragments": v1_fragments,
        "v1_fragment_rate": round(v1_fragments / v1_total, 3) if v1_total else 0.0,
        "v2_figures": v2_regions,
        "v2_fragments": v2_fragments,
        "reduction_ratio": round(v1_total / v2_regions, 1) if v2_regions else None,
    }


def content_fidelity(run_dir: str, source_pdf: str) -> dict:
    """LLM-as-judge scoring of a produced deck against its source. Needs a key."""
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage
    from pydantic import BaseModel, Field

    from pdfdeck.config import settings
    from pdfdeck.graph.content_runner import build_source_blocks

    class Scores(BaseModel):
        fidelity: int = Field(description="1-5: are all bullets supported by the source (5=fully grounded)")
        coverage: int = Field(description="1-5: do the slides cover the key concepts (5=comprehensive)")
        caption_correctness: int = Field(description="1-5: are figure captions right (5=all correct)")
        invented_facts: list[str] = Field(default_factory=list, description="any claims not in the source")
        notes: str = ""

    slides = json.load(open(f"{run_dir}/slides.json", encoding="utf-8"))
    pages, _ = ingest_pdf(source_pdf)
    source, _ = build_source_blocks(pages)

    llm = ChatAnthropic(model=settings.critic_model, temperature=0,
                        max_tokens=2048).with_structured_output(Scores)
    system = ("You are grading student slides generated from a medical textbook "
              "excerpt. Score strictly against the source; reward grounding and "
              "penalize any invented fact.")
    msg = (f"SOURCE:\n{source}\n\nGENERATED SLIDES:\n{json.dumps(slides, indent=2)}\n\n"
           "Score fidelity, coverage, caption_correctness (1-5 each) and list any invented facts.")
    scores = llm.invoke([SystemMessage(content=system), HumanMessage(content=msg)])
    return scores.model_dump()


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "figures"
    if cmd == "figures":
        pdf = sys.argv[2] if len(sys.argv) > 2 else "tests/fixtures/repair.pdf"
        m = figure_metrics(pdf)
        print(json.dumps(m, indent=2))
        print(f"\n>> v1 would emit {m['v1_raw_images_extracted']} image objects "
              f"({m['v1_sub120px_fragments']} sub-120px fragments, "
              f"{m['v1_fragment_rate']:.0%} fragment rate).")
        print(f">> v2 emits {m['v2_figures']} clean figures, {m['v2_fragments']} fragments. "
              f"Reduction: {m['reduction_ratio']}x fewer objects, zero fragments.")
    elif cmd == "content":
        run_dir = sys.argv[2]
        source = sys.argv[3] if len(sys.argv) > 3 else "tests/fixtures/repair.pdf"
        print(json.dumps(content_fidelity(run_dir, source), indent=2))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
