"""Content Agent loop: critic routing, span validation, figure conservation."""

import pytest

from pdfdeck.agents.content_agent import (
    CritiqueReport,
    DraftBundle,
    DraftedSlide,
    FakeContentAgent,
    FakeFidelityCritic,
    Outline,
    PlannedSlide,
    SlideIssue,
)
from pdfdeck.graph.content_agent import build_content_subgraph, validate_citations
from pdfdeck.graph.content_runner import run_content_agent
from pdfdeck.models import (
    Figure,
    PageModel,
    QAReport,
    Rect,
    RegionKind,
    TextBlock,
    VerificationStatus,
)


def _page(index, blocks):
    tbs = [
        TextBlock(span_id=f"p{index}_b{i}", text=t, word_count=len(t.split()),
                  bbox=Rect(x0=0, y0=i * 20, x1=100, y1=i * 20 + 15))
        for i, t in enumerate(blocks)
    ]
    return PageModel(index=index, width=600, height=800, text_blocks=tbs,
                     markdown="\n".join(blocks))


def _figure(rid, page_index, fig_no=None, caption=None, status=VerificationStatus.VERIFIED):
    return Figure(region_id=rid, page_index=page_index, figure_no=fig_no,
                  caption=caption, kind=RegionKind.DIAGRAM, image_path=f"/tmp/{rid}.png",
                  status=status)


def _outline(fig_refs=()):
    slides = [
        PlannedSlide(title="Tissue Repair", kind="title"),
        PlannedSlide(title="Granulation Tissue", kind="content",
                     span_ids=["p0_b0"], figure_ref=fig_refs[0] if fig_refs else None),
    ]
    return Outline(topic="Tissue Repair", slides=slides)


def _draft(span_ids=("p0_b0",), figure_ref=None):
    return DraftBundle(slides=[
        DraftedSlide(title="Granulation Tissue",
                     bullets=["New capillaries and fibroblasts appear by days 3-5."],
                     source_span_ids=list(span_ids), figure_ref=figure_ref, kind="content")
    ])


PAGES = [_page(0, ["Granulation tissue forms by days 3-5 with new capillaries.",
                   "Fibroblasts deposit collagen."])]


def _run(agent, critic, figures, max_revisions=2):
    qa = QAReport()
    slides = run_content_agent(PAGES, figures, agent, critic, qa, max_revisions=max_revisions)
    return slides, qa


# --- span validation (deterministic) --------------------------------------

def test_valid_citation_passes():
    issues = validate_citations(_draft(("p0_b0",)), {"p0_b0", "p0_b1"})
    assert issues == []


def test_nonexistent_span_flagged():
    issues = validate_citations(_draft(("p9_b9",)), {"p0_b0"})
    assert len(issues) == 1
    assert "p9_b9" in issues[0].claim


# --- critic routing --------------------------------------------------------

def test_approve_first_pass():
    agent = FakeContentAgent(_outline(), [_draft()])
    critic = FakeFidelityCritic([CritiqueReport(approved=True)])
    slides, qa = _run(agent, critic, [])
    assert critic.calls == 1 and agent.revise_calls == 0
    assert qa.forced_accept_slides == []
    # title + 1 content slide
    assert [s.slide_type for s in slides] == ["title", "text"]


def test_reject_twice_then_approve():
    agent = FakeContentAgent(_outline(), [_draft(), _draft(), _draft()])
    critic = FakeFidelityCritic([
        CritiqueReport(approved=False, issues=[SlideIssue(slide_index=0, claim="x")]),
        CritiqueReport(approved=False, issues=[SlideIssue(slide_index=0, claim="y")]),
        CritiqueReport(approved=True),
    ])
    slides, qa = _run(agent, critic, [])
    assert agent.revise_calls == 2
    assert critic.calls == 3
    assert qa.forced_accept_slides == []


def test_reject_forever_forces_accept_with_flag():
    agent = FakeContentAgent(_outline(), [_draft(), _draft(), _draft()])
    critic = FakeFidelityCritic([
        CritiqueReport(approved=False, issues=[SlideIssue(slide_index=0, claim="bad")])
    ])
    slides, qa = _run(agent, critic, [], max_revisions=2)
    # 2 revisions then forced accept
    assert agent.revise_calls == 2
    content = [s for s in slides if s.slide_type == "text"]
    assert any("critic_forced_accept" in s.flags for s in content)
    assert qa.forced_accept_slides


# --- figure conservation ---------------------------------------------------

def test_assigned_figure_interleaved():
    fig = _figure("p0_r0", 0, fig_no="2.1", caption="Figure 2.1 Repair.")
    agent = FakeContentAgent(_outline(("p0_r0",)), [_draft(figure_ref="p0_r0")])
    critic = FakeFidelityCritic([CritiqueReport(approved=True)])
    slides, qa = _run(agent, critic, [fig])
    types = [s.slide_type for s in slides]
    assert types == ["title", "text", "figure"]
    fig_slide = slides[2]
    assert fig_slide.figure_ref == "p0_r0"
    assert fig_slide.image_path == "/tmp/p0_r0.png"


def test_unassigned_figures_appended_never_dropped():
    figs = [_figure("p0_r0", 0), _figure("p3_r0", 3, caption="Figure 4.2")]
    # outline assigns neither
    agent = FakeContentAgent(_outline(), [_draft()])
    critic = FakeFidelityCritic([CritiqueReport(approved=True)])
    slides, qa = _run(agent, critic, figs)
    fig_refs = {s.figure_ref for s in slides if s.slide_type == "figure"}
    assert fig_refs == {"p0_r0", "p3_r0"}  # both present, none dropped


def test_best_effort_figure_flagged_on_slide():
    fig = _figure("p0_r0", 0, status=VerificationStatus.BEST_EFFORT)
    agent = FakeContentAgent(_outline(("p0_r0",)), [_draft(figure_ref="p0_r0")])
    critic = FakeFidelityCritic([CritiqueReport(approved=True)])
    slides, qa = _run(agent, critic, [fig])
    fig_slide = next(s for s in slides if s.slide_type == "figure")
    assert "best_effort" in fig_slide.flags


# --- topic robustness (a model may omit the required-looking field) --------

def test_outline_tolerates_missing_topic():
    # A fallback model once returned slides but no topic; that must not crash.
    o = Outline(slides=[PlannedSlide(title="Intro", kind="title")])
    assert o.topic == ""


def test_missing_topic_uses_fallback_topic():
    agent = FakeContentAgent(
        Outline(slides=[PlannedSlide(title="Intro", kind="title")]), [_draft()]
    )
    critic = FakeFidelityCritic([CritiqueReport(approved=True)])
    qa = QAReport()
    slides = run_content_agent(PAGES, [], agent, critic, qa, fallback_topic="Repair Chapter")
    title = next(s for s in slides if s.slide_type == "title")
    assert title.title == "Repair Chapter"  # fell back to the PDF-derived topic


def test_garbled_page_excluded_from_source():
    from pdfdeck.graph.content_runner import build_source_blocks
    good = _page(0, ["Clean readable text about repair."])
    bad = _page(1, ["gibberish"])
    bad.is_garbled = True
    text, span_ids = build_source_blocks([good, bad])
    assert "p0_b0" in span_ids
    assert not any(s.startswith("p1_") for s in span_ids)
