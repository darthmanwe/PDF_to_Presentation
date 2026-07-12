"""Content generation and fidelity critique.

Grounded summarization: the content agent plans an outline, drafts concise
bullets that cite source span IDs, and a fidelity critic verifies every
bullet is supported. Both are Protocols with Claude and Fake implementations
so the content subgraph is testable offline.
"""

from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel, Field

from pdfdeck.agents import prompts
from pdfdeck.config import settings


# --------------------------------------------------------------------------
# Structured I/O
# --------------------------------------------------------------------------

class FigureRef(BaseModel):
    region_id: str
    page_index: int
    figure_no: Optional[str] = None
    caption: Optional[str] = None
    kind: str = "figure"


class PlannedSlide(BaseModel):
    title: str = Field(description="specific slide title drawn from the source")
    kind: str = Field(description="title | content | summary")
    span_ids: list[str] = Field(default_factory=list, description="source spans this slide uses")
    figure_ref: Optional[str] = Field(default=None, description="region_id of an assigned figure, if any")


class Outline(BaseModel):
    topic: str = Field(description="chapter topic for the title slide")
    slides: list[PlannedSlide] = Field(default_factory=list)


class DraftedSlide(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)
    source_span_ids: list[str] = Field(default_factory=list)
    figure_ref: Optional[str] = None
    kind: str = "content"


class DraftBundle(BaseModel):
    slides: list[DraftedSlide] = Field(default_factory=list)


class SlideIssue(BaseModel):
    slide_index: int = Field(description="0-based index into the drafted slides")
    claim: str = Field(description="the specific unsupported/invented claim")
    detail: str = Field(default="", description="why it fails grounding")


class CritiqueReport(BaseModel):
    approved: bool = Field(description="true if every bullet is supported")
    issues: list[SlideIssue] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Protocols
# --------------------------------------------------------------------------

class ContentAgent(Protocol):
    def plan_outline(self, source_blocks: str, figures: list[FigureRef]) -> Outline: ...
    def draft_slides(self, outline: Outline, source_blocks: str) -> DraftBundle: ...
    def revise_slides(
        self, drafts: DraftBundle, issues: list[SlideIssue], source_blocks: str
    ) -> DraftBundle: ...


class FidelityCritic(Protocol):
    def critique(self, drafts: DraftBundle, source_blocks: str, history: str) -> CritiqueReport: ...


# --------------------------------------------------------------------------
# Claude implementations
# --------------------------------------------------------------------------

def _chat(model: str):
    from langchain_anthropic import ChatAnthropic

    # Only pass api_key when we actually have one; otherwise let ChatAnthropic
    # read ANTHROPIC_API_KEY from the environment (passing None fails validation).
    kwargs: dict = {"model": model, "temperature": 0, "max_tokens": 8192}
    if settings.anthropic_api_key:
        kwargs["api_key"] = settings.anthropic_api_key
    return ChatAnthropic(**kwargs)


def _figures_block(figures: list[FigureRef]) -> str:
    if not figures:
        return "(no figures available)"
    lines = []
    for f in figures:
        cap = (f.caption or "").strip()
        lines.append(f"- {f.region_id} (page {f.page_index + 1}, {f.kind})"
                     + (f": {cap}" if cap else ""))
    return "\n".join(lines)


class ClaudeContentAgent:
    def __init__(self, model: str | None = None):
        self.model = model or settings.content_model
        self._plan = _chat(self.model).with_structured_output(Outline)
        self._draft = _chat(self.model).with_structured_output(DraftBundle)
        self._revise = _chat(self.model).with_structured_output(DraftBundle)

    def plan_outline(self, source_blocks: str, figures: list[FigureRef]) -> Outline:
        from langchain_core.messages import HumanMessage, SystemMessage

        msg = (
            f"{prompts.PLAN_INSTRUCTIONS}\n\nAVAILABLE FIGURES:\n{_figures_block(figures)}"
            f"\n\nSOURCE BLOCKS:\n{source_blocks}"
        )
        return self._plan.invoke([SystemMessage(content=prompts.PLAN_SYSTEM), HumanMessage(content=msg)])

    def draft_slides(self, outline: Outline, source_blocks: str) -> DraftBundle:
        from langchain_core.messages import HumanMessage, SystemMessage

        msg = (
            f"{prompts.DRAFT_INSTRUCTIONS}\n\nOUTLINE:\n{outline.model_dump_json(indent=2)}"
            f"\n\nSOURCE BLOCKS:\n{source_blocks}"
        )
        return self._draft.invoke([SystemMessage(content=prompts.DRAFT_SYSTEM), HumanMessage(content=msg)])

    def revise_slides(
        self, drafts: DraftBundle, issues: list[SlideIssue], source_blocks: str
    ) -> DraftBundle:
        from langchain_core.messages import HumanMessage, SystemMessage

        issue_text = "\n".join(
            f"- slide {i.slide_index}: {i.claim} ({i.detail})" for i in issues
        )
        msg = (
            f"Fix these grounding issues:\n{issue_text}\n\nCURRENT SLIDES:\n"
            f"{drafts.model_dump_json(indent=2)}\n\nSOURCE BLOCKS:\n{source_blocks}"
        )
        return self._revise.invoke([SystemMessage(content=prompts.REVISE_SYSTEM), HumanMessage(content=msg)])


class ClaudeFidelityCritic:
    def __init__(self, model: str | None = None):
        self.model = model or settings.critic_model
        self._critic = _chat(self.model).with_structured_output(CritiqueReport)

    def critique(self, drafts: DraftBundle, source_blocks: str, history: str) -> CritiqueReport:
        from langchain_core.messages import HumanMessage, SystemMessage

        msg = (
            f"{prompts.CRITIC_INSTRUCTIONS}\n\nREVISION HISTORY:\n{history or '(first pass)'}"
            f"\n\nSLIDES:\n{drafts.model_dump_json(indent=2)}\n\nSOURCE BLOCKS:\n{source_blocks}"
        )
        return self._critic.invoke([SystemMessage(content=prompts.CRITIC_SYSTEM), HumanMessage(content=msg)])


# --------------------------------------------------------------------------
# Fakes for tests
# --------------------------------------------------------------------------

class FakeContentAgent:
    def __init__(self, outline: Outline, drafts: list[DraftBundle]):
        self._outline = outline
        self._drafts = list(drafts)  # index 0 = initial draft, rest = successive revisions
        self.plan_calls = 0
        self.draft_calls = 0
        self.revise_calls = 0

    def plan_outline(self, source_blocks: str, figures: list[FigureRef]) -> Outline:
        self.plan_calls += 1
        return self._outline

    def draft_slides(self, outline: Outline, source_blocks: str) -> DraftBundle:
        self.draft_calls += 1
        return self._drafts[0]

    def revise_slides(self, drafts, issues, source_blocks) -> DraftBundle:
        self.revise_calls += 1
        idx = min(self.revise_calls, len(self._drafts) - 1)
        return self._drafts[idx]


class FakeFidelityCritic:
    def __init__(self, reports: list[CritiqueReport]):
        self._reports = list(reports)
        self._i = 0
        self.calls = 0

    def critique(self, drafts, source_blocks, history) -> CritiqueReport:
        self.calls += 1
        r = self._reports[min(self._i, len(self._reports) - 1)]
        self._i += 1
        return r
