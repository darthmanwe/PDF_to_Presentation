"""Driver around the Content Agent subgraph.

Builds the span-tagged source text, runs the plan->draft->critique loop, then
DETERMINISTICALLY assembles SlideSpecs -- enforcing the figure-conservation
invariant: every figure lands on exactly one slide (assigned by the outline,
or appended at the end), never dropped.
"""

from __future__ import annotations

from pdfdeck.agents.content_agent import (
    ContentAgent,
    FidelityCritic,
    FigureRef,
)
from pdfdeck.extraction.caption_match import caption_title, clean_caption
from pdfdeck.config import settings
from pdfdeck.graph.content_agent import build_content_subgraph
from pdfdeck.models import Figure, PageModel, QAReport, SlideSpec
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)


def build_source_blocks(pages: list[PageModel]) -> tuple[str, list[str]]:
    """Span-tagged source text (garbled pages excluded). Returns (text, span_ids)."""
    lines: list[str] = []
    span_ids: list[str] = []
    for pm in pages:
        if pm.is_garbled:
            continue
        for b in pm.text_blocks:
            if b.text.strip():
                lines.append(f"[{b.span_id}] {b.text}")
                span_ids.append(b.span_id)
    return "\n".join(lines), span_ids


def _figure_slide(idx: int, fig: Figure) -> SlideSpec:
    # The caption (verbatim, de-hyphenated) becomes the slide title; it is also
    # preserved as the subtitle beneath the figure. Falls back to the figure
    # number, then a generic label, when no caption was detected.
    title = caption_title(fig.caption)
    if not title:
        title = f"Figure {fig.figure_no}" if fig.figure_no else "Figure"
    return SlideSpec(
        index=idx,
        title=title,
        slide_type="figure",
        figure_ref=fig.region_id,
        image_path=fig.image_path,
        caption=clean_caption(fig.caption) if fig.caption else None,
        flags=[] if fig.status.value in ("verified", "unverified") else [fig.status.value],
    )


def run_content_agent(
    pages: list[PageModel],
    figures: list[Figure],
    agent: ContentAgent,
    critic: FidelityCritic,
    qa_report: QAReport,
    max_revisions: int | None = None,
    fallback_topic: str = "",
) -> list[SlideSpec]:
    """Generate grounded slides and interleave figures (conservation enforced)."""
    source_blocks, span_ids = build_source_blocks(pages)
    figure_refs = [
        FigureRef(region_id=f.region_id, page_index=f.page_index,
                  figure_no=f.figure_no, caption=f.caption, kind=f.kind.value)
        for f in figures
    ]
    figures_by_id = {f.region_id: f for f in figures}

    subgraph = build_content_subgraph()
    config = {
        "configurable": {"agent": agent, "critic": critic},
        "recursion_limit": settings.graph_recursion_limit,
    }
    state_in = {
        "source_blocks": source_blocks,
        "valid_span_ids": span_ids,
        "figures": figure_refs,
        "history": "",
        "revisions": 0,
        "max_revisions": settings.max_content_revisions if max_revisions is None else max_revisions,
    }
    out = subgraph.invoke(state_in, config)

    drafts = out["drafts"]
    outline_topic = out["outline"].topic if out.get("outline") else ""
    topic = outline_topic or fallback_topic or "Medical Presentation"
    forced_flag = ["critic_forced_accept"] if out.get("forced_accept") else []

    slides: list[SlideSpec] = []
    idx = 0
    # Title slide.
    slides.append(SlideSpec(index=idx, title=topic, slide_type="title"))
    idx += 1

    assigned: set[str] = set()
    for d in drafts.slides:
        if d.kind == "title":
            continue  # topic slide already emitted
        slides.append(
            SlideSpec(index=idx, title=d.title, bullets=d.bullets, slide_type="text",
                      source_span_ids=d.source_span_ids, flags=list(forced_flag))
        )
        idx += 1
        # Interleave the figure this slide illustrates, right after it.
        if d.figure_ref and d.figure_ref in figures_by_id and d.figure_ref not in assigned:
            slides.append(_figure_slide(idx, figures_by_id[d.figure_ref]))
            idx += 1
            assigned.add(d.figure_ref)

    # Conservation: any figure the outline didn't place goes at the end.
    for f in figures:
        if f.region_id not in assigned:
            slides.append(_figure_slide(idx, f))
            idx += 1
            assigned.add(f.region_id)

    if forced_flag:
        qa_report.forced_accept_slides.extend(
            s.index for s in slides if "critic_forced_accept" in s.flags
        )

    assert assigned == set(figures_by_id), "figure-conservation invariant violated"
    return slides
