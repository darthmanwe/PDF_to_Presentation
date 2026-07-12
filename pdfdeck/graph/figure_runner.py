"""Driver around the Figure Agent subgraph.

`process_region` runs the verify->retry subgraph for ONE region (spawning
split children), returning finalized figures + QA flags. It is called both by
the sequential `run_figure_agent` (used in tests) and by the top-level
graph's Send fan-out, so the agentic loop is defined once.
"""

from __future__ import annotations

from pdfdeck.agents.vision_verifier import VisionVerifier
from pdfdeck.config import settings
from pdfdeck.extraction.classifier import needs_vision_verification
from pdfdeck.graph.figure_agent import build_figure_subgraph
from pdfdeck.models import (
    Figure,
    QAReport,
    Rect,
    Region,
    RegionKind,
    VerificationStatus,
)
from pdfdeck.pdfdoc import PageProvider
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)

_MAX_SPLIT_DEPTH = 1
_SUBGRAPH = build_figure_subgraph()  # compiled once; stateless


def _split_bbox(bbox: Rect, split_at: float) -> tuple[Rect, Rect]:
    y = bbox.y0 + max(0.05, min(0.95, split_at)) * bbox.height
    top = Rect(x0=bbox.x0, y0=bbox.y0, x1=bbox.x1, y1=y)
    bottom = Rect(x0=bbox.x0, y0=y, x1=bbox.x1, y1=bbox.y1)
    return top, bottom


def process_region(
    region: Region,
    pdf_path: str,
    run_dir: str,
    verifier: VisionVerifier,
    page_provider: PageProvider,
    page_rect: Rect,
    vision_enabled: bool,
    max_retries: int,
    breaker: dict,
) -> dict:
    """Run the subgraph for one region. Returns figures + QA-flag lists."""
    config = {
        "configurable": {
            "page_provider": page_provider,
            "verifier": verifier,
            "circuit_breaker": breaker,
            "vision_enabled": vision_enabled,
        },
        "recursion_limit": settings.graph_recursion_limit,
    }
    figures: list[Figure] = []
    best_effort: list[str] = []
    no_vision: list[str] = []
    dropped: list[str] = []

    queue: list[tuple[Rect, str, int]] = [(region.bbox, "", 0)]
    while queue:
        bbox, suffix, depth = queue.pop(0)
        rid = region.id + suffix
        needs = needs_vision_verification(
            region.kind, region.classifier_confidence, region.caption is not None
        )
        state_in = {
            "pdf_path": pdf_path,
            "page_index": region.page_index,
            "region_id": rid,
            "bbox": bbox,
            "page_rect": page_rect,
            "caption": region.caption,
            "figure_no": region.figure_no,
            "kind": region.kind.value,
            "run_dir": run_dir,
            "needs_verification": needs,
            "vision_enabled": vision_enabled,
            "max_retries": max_retries,
            "retries": 0,
        }
        out = _SUBGRAPH.invoke(state_in, config)
        status = out.get("status")

        if status == "rejected":
            log.info("figure %s rejected: %s", rid, out.get("notes"))
            if region.caption:
                dropped.append(region.caption[:80])
            continue

        if status == "split" and depth < _MAX_SPLIT_DEPTH and out.get("split_at"):
            top, bottom = _split_bbox(bbox, out["split_at"])
            queue.append((top, f"{suffix}_t", depth + 1))
            queue.append((bottom, f"{suffix}_b", depth + 1))
            continue

        vstatus = {
            VerificationStatus.VERIFIED.value: VerificationStatus.VERIFIED,
            VerificationStatus.BEST_EFFORT.value: VerificationStatus.BEST_EFFORT,
            VerificationStatus.NO_VISION.value: VerificationStatus.NO_VISION,
            VerificationStatus.UNVERIFIED.value: VerificationStatus.UNVERIFIED,
        }.get(status, VerificationStatus.BEST_EFFORT)

        if vstatus == VerificationStatus.BEST_EFFORT:
            best_effort.append(rid)
        elif vstatus == VerificationStatus.NO_VISION:
            no_vision.append(rid)

        figures.append(
            Figure(
                region_id=rid,
                page_index=region.page_index,
                figure_no=region.figure_no,
                caption=region.caption,
                kind=region.kind if isinstance(region.kind, RegionKind) else RegionKind(region.kind),
                image_path=out["image_path"],
                status=vstatus,
            )
        )
    return {"figures": figures, "best_effort": best_effort, "no_vision": no_vision, "dropped": dropped}


def run_figure_agent(
    regions: list[Region],
    pdf_path: str,
    run_dir: str,
    verifier: VisionVerifier,
    page_provider: PageProvider,
    qa_report: QAReport,
    vision_enabled: bool = True,
    max_retries: int | None = None,
) -> list[Figure]:
    """Sequential driver: process every region, merge QA flags. Used in tests."""
    max_retries = settings.max_figure_retries if max_retries is None else max_retries
    breaker = {"failures": 0, "limit": settings.vision_circuit_breaker}
    page = page_provider.page(pdf_path, regions[0].page_index) if regions else None
    page_rect = Rect(x0=0, y0=0, x1=page.rect.width, y1=page.rect.height) if page else None

    figures: list[Figure] = []
    for region in regions:
        r = process_region(region, pdf_path, run_dir, verifier, page_provider,
                            page_rect, vision_enabled, max_retries, breaker)
        figures.extend(r["figures"])
        qa_report.best_effort_figures.extend(r["best_effort"])
        qa_report.no_vision_figures.extend(r["no_vision"])
        qa_report.dropped_captions.extend(r["dropped"])
    qa_report.vision_calls = getattr(verifier, "calls", qa_report.vision_calls)
    figures.sort(key=lambda f: (f.page_index, f.region_id))
    return figures
