"""The Figure Agent: a LangGraph subgraph that verifies and refines one
figure crop through a bounded render -> verify -> adjust loop.

This is agentic loop #1 and the project's headline: a deterministic clusterer
proposes a bbox; the agent RENDERS it, LOOKS at the result with a vision
model, and if the crop is cut off or captures a neighbor it moves the box and
re-renders -- up to a cap. A pipeline cannot self-correct; this loop can.

Control flow (conditional edges):

    render ---> verify ---> route ---+--> accept/reject/no_vision --> finalize
      ^                              |
      +----- apply_delta <-----------+--- adjust (retries < cap)

`split` and the retry cap are terminal into finalize (the driver in
figure_runner.py handles split spawning and best-effort flagging).
"""

from __future__ import annotations

import os
from typing import Any, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from pdfdeck.agents.vision_verifier import Verdict, VerificationResult, VisionUnavailable
from pdfdeck.extraction.geometry import apply_bbox_delta
from pdfdeck.models import Rect, VerificationStatus
from pdfdeck.rendering.page_render import render_region, render_verify_image
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)


class FigureAgentState(TypedDict, total=False):
    pdf_path: str
    page_index: int
    region_id: str
    bbox: Rect
    page_rect: Rect
    caption: Optional[str]
    figure_no: Optional[str]
    kind: str
    run_dir: str
    needs_verification: bool
    vision_enabled: bool
    max_retries: int
    retries: int
    image_path: Optional[str]
    status: str
    verdict: Optional[str]
    split_at: Optional[float]
    notes: Optional[str]


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return (config or {}).get("configurable", {})


def _render_node(state: FigureAgentState, config: RunnableConfig) -> dict:
    provider = _cfg(config)["page_provider"]
    page = provider.page(state["pdf_path"], state["page_index"])
    attempt = state.get("retries", 0)
    out = os.path.join(
        state["run_dir"], "figures", f"{state['region_id']}_a{attempt}.png"
    )
    render_region(page, state["bbox"], out)
    return {"image_path": out}


def _verify_node(state: FigureAgentState, config: RunnableConfig) -> dict:
    cfg = _cfg(config)
    # Gating: confident captioned photos and the --no-vision mode skip the call.
    if not state.get("needs_verification", True):
        return {"status": VerificationStatus.UNVERIFIED.value, "verdict": Verdict.ACCEPT.value}
    if not state.get("vision_enabled", True) or not cfg.get("vision_enabled", True):
        return {"status": VerificationStatus.NO_VISION.value, "verdict": Verdict.ACCEPT.value}

    verifier = cfg["verifier"]
    provider = cfg["page_provider"]
    breaker = cfg.get("circuit_breaker")  # optional mutable {"failures": int, "limit": int}
    page = provider.page(state["pdf_path"], state["page_index"])

    verify_img = os.path.join(
        state["run_dir"], "figures",
        f"{state['region_id']}_a{state.get('retries', 0)}_verify.png",
    )
    render_verify_image(page, state["bbox"], verify_img)

    try:
        result: VerificationResult = verifier.verify(
            verify_img, state.get("caption"), state.get("kind", "")
        )
    except VisionUnavailable as exc:
        log.warning("vision unavailable for %s: %s", state["region_id"], exc)
        if breaker is not None:
            breaker["failures"] = breaker.get("failures", 0) + 1
            if breaker["failures"] >= breaker.get("limit", 3):
                cfg["vision_enabled"] = False  # trip the breaker for the rest of the run
        return {"status": VerificationStatus.NO_VISION.value, "verdict": Verdict.ACCEPT.value,
                "notes": f"vision unavailable: {exc}"}

    if breaker is not None:
        breaker["failures"] = 0  # reset run of failures on success

    update: dict = {"verdict": result.verdict.value, "notes": result.reason}
    if result.verdict == Verdict.ACCEPT:
        update["status"] = VerificationStatus.VERIFIED.value
    elif result.verdict == Verdict.REJECT:
        update["status"] = "rejected"
    elif result.verdict == Verdict.SPLIT:
        update["status"] = "split"
        update["split_at"] = result.split_at
    elif result.verdict == Verdict.ADJUST:
        update["status"] = "adjusting"
        update["_delta"] = result.bbox_delta  # consumed by apply_delta
    return update


def _route(state: FigureAgentState) -> str:
    verdict = state.get("verdict")
    if verdict == Verdict.ADJUST.value:
        if state.get("retries", 0) < state.get("max_retries", 2):
            return "apply_delta"
        return "finalize"  # cap hit -> best-effort (set in finalize)
    return "finalize"  # accept / reject / split / no_vision


def _apply_delta_node(state: FigureAgentState) -> dict:
    delta = state.get("_delta")
    if delta is None:
        return {"retries": state.get("retries", 0) + 1}
    new_bbox = apply_bbox_delta(state["bbox"], delta, state["page_rect"])
    return {"bbox": new_bbox, "retries": state.get("retries", 0) + 1, "_delta": None}


def _finalize_node(state: FigureAgentState) -> dict:
    # If we exhausted retries while still 'adjusting', keep the best crop.
    if state.get("verdict") == Verdict.ADJUST.value and state.get("status") == "adjusting":
        return {"status": VerificationStatus.BEST_EFFORT.value}
    return {}


def build_figure_subgraph():
    g = StateGraph(FigureAgentState)
    g.add_node("render", _render_node)
    g.add_node("verify", _verify_node)
    g.add_node("apply_delta", _apply_delta_node)
    g.add_node("finalize", _finalize_node)

    g.add_edge(START, "render")
    g.add_edge("render", "verify")
    g.add_conditional_edges("verify", _route, {"apply_delta": "apply_delta", "finalize": "finalize"})
    g.add_edge("apply_delta", "render")
    g.add_edge("finalize", END)
    return g.compile()
