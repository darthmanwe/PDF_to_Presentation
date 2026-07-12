"""Figure Agent loop: every verdict route, driven by a scripted fake verifier.

Real PyMuPDF rendering (offline, from the repair.pdf fixture); the vision
model is faked, so no network and no API key. Exercises accept / adjust->cap
/ reject / split / vision-outage / gating-skip.
"""

import os

import pytest

from pdfdeck.agents.vision_verifier import (
    BboxDelta,
    FakeVisionVerifier,
    Verdict,
    VerificationResult,
    VisionUnavailable,
)
from pdfdeck.graph.figure_runner import run_figure_agent
from pdfdeck.models import QAReport, Rect, Region, RegionKind, VerificationStatus
from pdfdeck.pdfdoc import PageProvider

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
PDF = os.path.join(FIXTURES, "repair.pdf")


def _region(kind=RegionKind.DIAGRAM, confidence=0.9, caption=None, page_index=5):
    # A modest real region on page 6 (a photo area); bbox kept small for speed.
    return Region(
        id="p5_r0",
        page_index=page_index,
        bbox=Rect(x0=60, y0=540, x1=300, y1=700),
        source_rects=[Rect(x0=60, y0=540, x1=300, y1=700)],
        kind=kind,
        classifier_confidence=confidence,
        caption=caption,
    )


def _run(script, tmp_path, region=None, vision_enabled=True):
    provider = PageProvider()
    qa = QAReport()
    verifier = FakeVisionVerifier(script)
    figs = run_figure_agent(
        [region or _region()],
        pdf_path=PDF,
        run_dir=str(tmp_path),
        verifier=verifier,
        page_provider=provider,
        qa_report=qa,
        vision_enabled=vision_enabled,
    )
    provider.close()
    return figs, qa, verifier


def _r(verdict, **kw):
    return VerificationResult(verdict=verdict, reason="test", **kw)


def test_accept_first_try(tmp_path):
    figs, qa, v = _run([_r(Verdict.ACCEPT)], tmp_path)
    assert len(figs) == 1
    assert figs[0].status == VerificationStatus.VERIFIED
    assert v.calls == 1
    assert os.path.exists(figs[0].image_path)


def test_adjust_to_cap_is_best_effort(tmp_path):
    figs, qa, v = _run([_r(Verdict.ADJUST, bbox_delta=BboxDelta(expand_top=0.1))], tmp_path)
    assert len(figs) == 1
    assert figs[0].status == VerificationStatus.BEST_EFFORT
    # render a0 -> verify, a1 -> verify, a2 -> verify (cap=2): 3 calls.
    assert v.calls == 3
    assert figs[0].region_id in qa.best_effort_figures


def test_adjust_then_accept(tmp_path):
    figs, qa, v = _run(
        [_r(Verdict.ADJUST, bbox_delta=BboxDelta(expand_left=0.05)), _r(Verdict.ACCEPT)],
        tmp_path,
    )
    assert len(figs) == 1
    assert figs[0].status == VerificationStatus.VERIFIED
    assert v.calls == 2


def test_reject_drops_figure(tmp_path):
    region = _region(caption="Figure 9.9 A shaded review box.")
    figs, qa, v = _run([_r(Verdict.REJECT)], tmp_path, region=region)
    assert figs == []
    assert qa.dropped_captions  # caption recorded


def test_split_produces_two_figures(tmp_path):
    figs, qa, v = _run(
        [_r(Verdict.SPLIT, split_at=0.5), _r(Verdict.ACCEPT), _r(Verdict.ACCEPT)],
        tmp_path,
    )
    assert len(figs) == 2
    assert all(f.status == VerificationStatus.VERIFIED for f in figs)
    assert {f.region_id for f in figs} == {"p5_r0_t", "p5_r0_b"}


def test_vision_outage_is_no_vision(tmp_path):
    figs, qa, v = _run([VisionUnavailable("api down")], tmp_path)
    assert len(figs) == 1
    assert figs[0].status == VerificationStatus.NO_VISION
    assert figs[0].region_id in qa.no_vision_figures


def test_gating_skips_confident_captioned_photo(tmp_path):
    region = _region(kind=RegionKind.PHOTO, confidence=0.9, caption="Figure 2.1 A photo.")
    figs, qa, v = _run([_r(Verdict.ACCEPT)], tmp_path, region=region)
    assert len(figs) == 1
    assert figs[0].status == VerificationStatus.UNVERIFIED
    assert v.calls == 0  # verifier never called


def test_no_vision_mode_skips_calls(tmp_path):
    figs, qa, v = _run([_r(Verdict.ACCEPT)], tmp_path, vision_enabled=False)
    assert len(figs) == 1
    assert figs[0].status == VerificationStatus.NO_VISION
    assert v.calls == 0
