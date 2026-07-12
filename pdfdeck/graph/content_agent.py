"""The Content Agent: a LangGraph subgraph for grounded summarization.

Agentic loop #2: plan -> draft -> critique -> (revise -> critique)* -> done.
The critic combines a DETERMINISTIC span-citation check (a bullet may only
cite spans that exist) with an LLM entailment check (is each bullet actually
supported?). Bounded by a revision cap; on cap it accepts with flags rather
than looping forever.

    plan --> draft --> critique --> route --+--> approve/cap --> finalize
                          ^                  |
                          +---- revise <-----+--- issues (revisions < cap)
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from pdfdeck.agents.content_agent import (
    CritiqueReport,
    DraftBundle,
    FigureRef,
    Outline,
    SlideIssue,
)
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)


class ContentState(TypedDict, total=False):
    source_blocks: str
    valid_span_ids: list[str]
    figures: list[FigureRef]
    outline: Outline
    drafts: DraftBundle
    critique: CritiqueReport
    history: str
    revisions: int
    max_revisions: int
    forced_accept: bool


def validate_citations(drafts: DraftBundle, valid_span_ids: set[str]) -> list[SlideIssue]:
    """Deterministic guard: a slide may only cite spans that exist."""
    issues: list[SlideIssue] = []
    for i, s in enumerate(drafts.slides):
        for sid in s.source_span_ids:
            if sid not in valid_span_ids:
                issues.append(
                    SlideIssue(slide_index=i, claim=f"cites nonexistent span {sid}",
                               detail="span id not present in source")
                )
    return issues


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return (config or {}).get("configurable", {})


def _plan_node(state: ContentState, config: RunnableConfig) -> dict:
    agent = _cfg(config)["agent"]
    outline = agent.plan_outline(state["source_blocks"], state["figures"])
    return {"outline": outline}


def _draft_node(state: ContentState, config: RunnableConfig) -> dict:
    agent = _cfg(config)["agent"]
    drafts = agent.draft_slides(state["outline"], state["source_blocks"])
    return {"drafts": drafts}


def _critique_node(state: ContentState, config: RunnableConfig) -> dict:
    critic = _cfg(config)["critic"]
    valid = set(state.get("valid_span_ids", []))
    det_issues = validate_citations(state["drafts"], valid)

    report = critic.critique(state["drafts"], state["source_blocks"], state.get("history", ""))
    merged = list(report.issues) + det_issues
    approved = report.approved and not det_issues
    history = state.get("history", "")
    history += f"\nrev {state.get('revisions', 0)}: " + (
        "approved" if approved else f"{len(merged)} issue(s)"
    )
    return {"critique": CritiqueReport(approved=approved, issues=merged), "history": history}


def _route(state: ContentState) -> str:
    critique = state.get("critique")
    if critique and critique.approved:
        return "finalize"
    if state.get("revisions", 0) < state.get("max_revisions", 2):
        return "revise"
    return "finalize"  # cap -> accept with flags


def _revise_node(state: ContentState, config: RunnableConfig) -> dict:
    agent = _cfg(config)["agent"]
    revised = agent.revise_slides(
        state["drafts"], state["critique"].issues, state["source_blocks"]
    )
    return {"drafts": revised, "revisions": state.get("revisions", 0) + 1}


def _finalize_node(state: ContentState) -> dict:
    critique = state.get("critique")
    forced = bool(critique and not critique.approved)
    if forced:
        log.warning("content accepted with %d unresolved grounding issue(s)",
                    len(critique.issues))
    return {"forced_accept": forced}


def build_content_subgraph():
    g = StateGraph(ContentState)
    g.add_node("plan", _plan_node)
    g.add_node("draft", _draft_node)
    g.add_node("critique", _critique_node)
    g.add_node("revise", _revise_node)
    g.add_node("finalize", _finalize_node)

    g.add_edge(START, "plan")
    g.add_edge("plan", "draft")
    g.add_edge("draft", "critique")
    g.add_conditional_edges("critique", _route, {"revise": "revise", "finalize": "finalize"})
    g.add_edge("revise", "critique")
    g.add_edge("finalize", END)
    return g.compile()
