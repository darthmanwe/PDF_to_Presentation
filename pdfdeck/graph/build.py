"""The top-level pipeline graph.

ingest -> detect -> [Send fan-out -> process_region] -> gather
       -> content -> translate -> assemble -> qa_report

All agents (vision verifier, content agent, fidelity critic, translator) and
the page provider are injected via the run config's `configurable`, so the
whole pipeline runs offline against Fakes in tests and against Claude + Azure
in production. The figure step uses the Send API with reducer collectors
(state.py) for map-reduce over regions.
"""

from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from pdfdeck.config import settings
from pdfdeck.extraction.detect import detect_page_regions
from pdfdeck.extraction.ingest import ingest_pdf, raw_candidate_rects
from pdfdeck.extraction.rects import ClusterParams
from pdfdeck.graph.content_runner import run_content_agent
from pdfdeck.graph.figure_runner import process_region
from pdfdeck.graph.state import PipelineState
from pdfdeck.models import Figure, QAReport, Rect, RegionKind, VerificationStatus
from pdfdeck.pptx.builder import DeckBuilder
from pdfdeck.rendering.page_render import render_full_page
from pdfdeck.telemetry import estimate_cost_usd, get_logger
from pdfdeck.translation.translate_slides import translate_slides

log = get_logger(__name__)


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return (config or {}).get("configurable", {})


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------

def _ingest(state: PipelineState, config: RunnableConfig) -> dict:
    pages, sha = ingest_pdf(state["pdf_path"])
    topic = os.path.splitext(os.path.basename(state["pdf_path"]))[0].replace("_", " ").title()
    log.info("ingested %d pages (sha %s)", len(pages), sha[:12])
    return {"pages": pages, "pdf_sha": sha, "topic": topic}


def _detect(state: PipelineState, config: RunnableConfig) -> dict:
    provider = _cfg(config)["page_provider"]
    pdf_path = state["pdf_path"]
    all_regions = []
    fallback_pages = []
    for pm in state["pages"]:
        page = provider.page(pdf_path, pm.index)
        img_rects, draw_rects = raw_candidate_rects(page)
        regions = detect_page_regions(pm, img_rects, draw_rects)
        if not regions and pm.caption_mentions > 0:
            # A page that references figures but yielded none: re-detect looser.
            regions = detect_page_regions(
                pm, img_rects, draw_rects, ClusterParams().loosened()
            )
            if not regions:
                fallback_pages.append(pm.index)  # render the whole page as a slide
        all_regions.extend(regions)
    log.info("detected %d figure regions (%d fallback pages)",
             len(all_regions), len(fallback_pages))
    return {"regions": all_regions, "fallback_pages": fallback_pages}


def _fan_out(state: PipelineState):
    """Conditional edge: one Send per region, or skip to gather if none."""
    regions = state.get("regions", [])
    if not regions:
        return "gather"
    return [
        Send("process_region", {
            "region": r,
            "pdf_path": state["pdf_path"],
            "run_dir": state["run_dir"],
            "vision_enabled": state.get("vision_enabled", True),
            "max_retries": state.get("max_retries", settings.max_figure_retries),
        })
        for r in regions
    ]


def _process_region_node(payload: dict, config: RunnableConfig) -> dict:
    cfg = _cfg(config)
    provider = cfg["page_provider"]
    region = payload["region"]
    page = provider.page(payload["pdf_path"], region.page_index)
    page_rect = Rect(x0=0, y0=0, x1=page.rect.width, y1=page.rect.height)
    result = process_region(
        region,
        pdf_path=payload["pdf_path"],
        run_dir=payload["run_dir"],
        verifier=cfg["verifier"],
        page_provider=provider,
        page_rect=page_rect,
        vision_enabled=payload.get("vision_enabled", True),
        max_retries=payload.get("max_retries", settings.max_figure_retries),
        breaker=cfg["breaker"],
    )
    return result  # figures/best_effort/no_vision/dropped merge via reducers


def _gather(state: PipelineState, config: RunnableConfig) -> dict:
    """Join point: add full-page fallback figures for pages with no regions."""
    provider = _cfg(config)["page_provider"]
    extra: list[Figure] = []
    for pidx in state.get("fallback_pages", []):
        page = provider.page(state["pdf_path"], pidx)
        out = os.path.join(state["run_dir"], "figures", f"p{pidx}_fullpage.png")
        render_full_page(page, out)
        extra.append(Figure(
            region_id=f"p{pidx}_fullpage", page_index=pidx, kind=RegionKind.UNKNOWN,
            image_path=out, status=VerificationStatus.NO_VISION,
            caption=f"Page {pidx + 1} (figure region not isolated)",
        ))
    return {"figures": extra} if extra else {}


def _content(state: PipelineState, config: RunnableConfig) -> dict:
    cfg = _cfg(config)
    report: QAReport = cfg["report"]
    figures = sorted(state.get("figures", []), key=lambda f: (f.page_index, f.region_id))
    slides = run_content_agent(
        state["pages"], figures, cfg["content_agent"], cfg["critic"], report,
        fallback_topic=state.get("topic", ""),
    )
    return {"slides": slides}


def _translate(state: PipelineState, config: RunnableConfig) -> dict:
    target = state.get("target_language")
    translator = _cfg(config).get("translator")
    if not target or target == "en" or translator is None:
        return {}
    if hasattr(translator, "is_configured") and not translator.is_configured():
        log.warning("translation requested but translator not configured; skipping")
        return {}
    log.info("translating deck to %s", target)
    return {"slides": translate_slides(state["slides"], target, translator)}


def _assemble(state: PipelineState, config: RunnableConfig) -> dict:
    out = state.get("output_path") or os.path.join(state["run_dir"], "deck.pptx")
    DeckBuilder().build(state["slides"], out, subtitle=state.get("topic", "Medical Education"))
    return {"output_path": out}


def _qa(state: PipelineState, config: RunnableConfig) -> dict:
    cfg = _cfg(config)
    report: QAReport = cfg["report"]
    report.best_effort_figures = list(state.get("best_effort", []))
    report.no_vision_figures = list(state.get("no_vision", []))
    report.dropped_captions = list(state.get("dropped", []))
    report.fallback_pages = list(state.get("fallback_pages", []))
    report.garbled_pages = [p.index for p in state["pages"] if p.is_garbled]
    verifier = cfg.get("verifier")
    report.vision_calls = getattr(verifier, "calls", report.vision_calls)
    report.cost_estimate_usd = estimate_cost_usd(
        settings.vision_model, report.llm_input_tokens, report.llm_output_tokens
    )
    path = os.path.join(state["run_dir"], "qa_report.json")
    os.makedirs(state["run_dir"], exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2)
    log.info("QA report: %d figures, best_effort=%d no_vision=%d dropped=%d fallback=%d",
             len(state.get("figures", [])), len(report.best_effort_figures),
             len(report.no_vision_figures), len(report.dropped_captions),
             len(report.fallback_pages))
    return {}


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------

def build_pipeline():
    g = StateGraph(PipelineState)
    g.add_node("ingest", _ingest)
    g.add_node("detect", _detect)
    g.add_node("process_region", _process_region_node)
    g.add_node("gather", _gather)
    g.add_node("content", _content)
    g.add_node("translate", _translate)
    g.add_node("assemble", _assemble)
    g.add_node("qa", _qa)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "detect")
    g.add_conditional_edges("detect", _fan_out, ["process_region", "gather"])
    g.add_edge("process_region", "gather")
    g.add_edge("gather", "content")
    g.add_edge("content", "translate")
    g.add_edge("translate", "assemble")
    g.add_edge("assemble", "qa")
    g.add_edge("qa", END)
    return g.compile()
