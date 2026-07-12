"""Pipeline entrypoint: convert one PDF to a deck.

Wires the injectable dependencies (vision verifier, content agent, fidelity
critic, translator, page provider) and invokes the top-level graph. Real
Claude/Azure implementations are built lazily only when not injected, so
tests pass Fakes and never touch the network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pdfdeck.config import settings
from pdfdeck.graph.build import build_pipeline
from pdfdeck.models import QAReport
from pdfdeck.pdfdoc import PageProvider
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)


@dataclass
class ConversionResult:
    output_path: str
    run_dir: str
    report: QAReport
    slides: list
    figures: list


def _finalize_cost(report: QAReport, usage_metadata: dict, run_dir: str) -> None:
    """Sum per-model token usage into the QA report and re-write the json."""
    import json
    import os

    from pdfdeck.telemetry import estimate_cost_usd

    total_in = total_out = 0
    cost = 0.0
    for model, usage in (usage_metadata or {}).items():
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        total_in += in_tok
        total_out += out_tok
        cost += estimate_cost_usd(model, in_tok, out_tok)
    report.llm_input_tokens = total_in
    report.llm_output_tokens = total_out
    report.cost_estimate_usd = round(cost, 4)
    path = os.path.join(run_dir, "qa_report.json")
    if os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)


def convert_pdf(
    pdf_path: str,
    target_language: Optional[str] = None,
    vision_enabled: bool = True,
    output_path: Optional[str] = None,
    run_dir: Optional[str] = None,
    *,
    verifier=None,
    content_agent=None,
    critic=None,
    translator=None,
    page_provider: Optional[PageProvider] = None,
) -> ConversionResult:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(pdf_path)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = run_dir or os.path.join("runs", ts)
    os.makedirs(os.path.join(run_dir, "figures"), exist_ok=True)

    # Default deck name reflects the source PDF + a timestamp (not "deck.pptx").
    if output_path is None:
        stem = os.path.splitext(os.path.basename(pdf_path))[0]
        output_path = os.path.join(run_dir, f"{stem}_{ts}.pptx")

    owns_provider = page_provider is None
    provider = page_provider or PageProvider()
    report = QAReport()
    breaker = {"failures": 0, "limit": settings.vision_circuit_breaker}

    if verifier is None:
        from pdfdeck.agents.vision_verifier import ClaudeVisionVerifier
        verifier = ClaudeVisionVerifier()
    if content_agent is None:
        from pdfdeck.agents.content_agent import ClaudeContentAgent
        content_agent = ClaudeContentAgent()
    if critic is None:
        from pdfdeck.agents.content_agent import ClaudeFidelityCritic
        critic = ClaudeFidelityCritic()
    if translator is None:
        from pdfdeck.translation.service import TranslationService
        translator = TranslationService()

    config = {
        "configurable": {
            "page_provider": provider,
            "verifier": verifier,
            "content_agent": content_agent,
            "critic": critic,
            "translator": translator,
            "breaker": breaker,
            "report": report,
        },
        "recursion_limit": settings.graph_recursion_limit,
    }
    state_in = {
        "pdf_path": pdf_path,
        "target_language": target_language,
        "run_dir": run_dir,
        "vision_enabled": vision_enabled,
        "max_retries": settings.max_figure_retries,
        "output_path": output_path,
    }

    graph = build_pipeline()
    try:
        # Capture token usage across every LLM call in the run (content agent,
        # critic, vision verifier) via contextvars -- works through
        # with_structured_output, which otherwise hides the raw usage.
        from langchain_core.callbacks import get_usage_metadata_callback

        with get_usage_metadata_callback() as usage_cb:
            final = graph.invoke(state_in, config)
        _finalize_cost(report, usage_cb.usage_metadata, run_dir)
    finally:
        if owns_provider:
            provider.close()

    return ConversionResult(
        output_path=final.get("output_path", ""),
        run_dir=run_dir,
        report=report,
        slides=final.get("slides", []),
        figures=sorted(final.get("figures", []), key=lambda f: (f.page_index, f.region_id)),
    )
