"""Driver around the Figure Agent subgraph.

Invokes `build_figure_subgraph()` once per region, threads a shared vision
circuit-breaker and page provider through the run config, spawns split
children, and turns finalized states into `Figure` records while updating the
QA report. This is the unit the top-level graph fans out over.
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


def _split_bbox(bbox: Rect, split_at: float) -> tuple[Rect, Rect]:
    y = bbox.y0 + max(0.05, min(0.95, split_at)) * bbox.height
    top = Rect(x0=bbox.x0, y0=bbox.y0, x1=bbox.x1, y1=y)
    bottom = Rect(x0=bbox.x0, y0=y, x1=bbox.x1, y1=bbox.y1)
    return top, bottom


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
    """Verify/refine every region; return the finalized figures."""
    subgraph = build_figure_subgraph()
    breaker = {"failures": 0, "limit": settings.vision_circuit_breaker}
    config = {
        "configurable": {
            "page_provider": page_provider,
            "verifier": verifier,
            "circuit_breaker": breaker,
            "vision_enabled": vision_enabled,
        },
        "recursion_limit": settings.graph_recursion_limit,
    }
    max_retries = settings.max_figure_retries if max_retries is None else max_retries

    page = page_provider.page(pdf_path, regions[0].page_index) if regions else None
    page_rect = (
        Rect(x0=0, y0=0, x1=page.rect.width, y1=page.rect.height) if page else None
    )

    figures: list[Figure] = []
    # (region, bbox, suffix, depth)
    queue: list[tuple[Region, Rect, str, int]] = [(r, r.bbox, "", 0) for r in regions]

    while queue:
        region, bbox, suffix, depth = queue.pop(0)
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
        out = subgraph.invoke(state_in, config)
        status = out.get("status")
        qa_report.vision_calls = getattr(verifier, "calls", qa_report.vision_calls)

        if status == "rejected":
            log.info("figure %s rejected by verifier: %s", rid, out.get("notes"))
            if region.caption:
                qa_report.dropped_captions.append(region.caption[:80])
            continue

        if status == "split" and depth < _MAX_SPLIT_DEPTH and out.get("split_at"):
            top, bottom = _split_bbox(bbox, out["split_at"])
            queue.append((region, top, f"{suffix}_t", depth + 1))
            queue.append((region, bottom, f"{suffix}_b", depth + 1))
            continue

        # Map terminal statuses -> a persisted VerificationStatus.
        vstatus = {
            VerificationStatus.VERIFIED.value: VerificationStatus.VERIFIED,
            VerificationStatus.BEST_EFFORT.value: VerificationStatus.BEST_EFFORT,
            VerificationStatus.NO_VISION.value: VerificationStatus.NO_VISION,
            VerificationStatus.UNVERIFIED.value: VerificationStatus.UNVERIFIED,
        }.get(status, VerificationStatus.BEST_EFFORT)

        if vstatus == VerificationStatus.BEST_EFFORT:
            qa_report.best_effort_figures.append(rid)
        elif vstatus == VerificationStatus.NO_VISION:
            qa_report.no_vision_figures.append(rid)

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

    figures.sort(key=lambda f: (f.page_index, f.region_id))
    return figures
