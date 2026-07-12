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

    run_dir = run_dir or os.path.join("runs", datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(os.path.join(run_dir, "figures"), exist_ok=True)

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
        final = graph.invoke(state_in, config)
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
