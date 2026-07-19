"""Pipeline entrypoint: convert one PDF to a deck.

Wires the injectable dependencies (vision verifier, content agent, fidelity
critic, translator, page provider) and runs the top-level graph. Real
Claude/Azure implementations are built lazily only when not injected, so
tests pass Fakes and never touch the network.

Two entrypoints share the same setup:
- `convert_pdf`    -- one blocking call, returns the result (CLI, tests).
- `iter_convert`   -- a generator yielding ("node", name) progress events and
                       a final ("done", result), for the streaming UI.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Optional

from pdfdeck.config import settings
from pdfdeck.graph.build import build_pipeline
from pdfdeck.models import QAReport
from pdfdeck.pdfdoc import PageProvider
from pdfdeck.telemetry import estimate_cost_usd, get_logger

log = get_logger(__name__)

# Reducer-annotated state keys (see graph/state.py): accumulate across the
# figure fan-out rather than overwrite when reconstructing state from a stream.
_REDUCER_KEYS = {"figures", "best_effort", "no_vision", "dropped"}

# Friendly labels for streaming progress in the UI.
NODE_LABELS = {
    "ingest": "Reading PDF and extracting text",
    "detect": "Detecting figure regions",
    "process_region": "Verifying a figure crop (vision agent)",
    "gather": "Collecting figures",
    "content": "Drafting grounded slides (plan -> draft -> critique)",
    "translate": "Translating",
    "assemble": "Building the presentation",
    "qa": "Finalizing and writing the QA report",
    "emit_extra": "Translating and building the extra-language deck",
}


@dataclass
class ConversionResult:
    output_path: str
    run_dir: str
    report: QAReport
    slides: list = field(default_factory=list)
    figures: list = field(default_factory=list)
    # lang code -> pptx path for extra language variants (translation-only cost).
    extra_outputs: dict = field(default_factory=dict)


@dataclass
class _Run:
    graph: object
    state_in: dict
    config: dict
    report: QAReport
    provider: PageProvider
    owns_provider: bool
    run_dir: str


def _finalize_cost(report: QAReport, usage_metadata: dict, run_dir: str) -> None:
    """Sum per-model token usage into the QA report and re-write the json."""
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


def _prepare(
    pdf_path, target_language, vision_enabled, output_path, run_dir,
    verifier, content_agent, critic, translator, page_provider,
) -> _Run:
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
    return _Run(build_pipeline(), state_in, config, report, provider, owns_provider, run_dir)


def _result(run: _Run, state: dict) -> ConversionResult:
    return ConversionResult(
        output_path=state.get("output_path", ""),
        run_dir=run.run_dir,
        report=run.report,
        slides=state.get("slides", []),
        figures=sorted(state.get("figures", []), key=lambda f: (f.page_index, f.region_id)),
    )


def _emit_extra_languages(
    run: _Run, english_slides: list, languages, primary_output: str, topic: str
) -> dict:
    """Assemble one extra deck per language from the already-finalized English
    slides. Reuses the rendered figures on disk and pays only Azure Translator
    cost -- the expensive vision + content stages ran exactly once."""
    from pdfdeck.pptx.builder import DeckBuilder
    from pdfdeck.translation.translate_slides import translate_slides

    translator = run.config["configurable"].get("translator")
    if translator is not None and hasattr(translator, "is_configured") \
            and not translator.is_configured():
        log.warning("extra languages requested but translator not configured; skipping")
        return {}

    base, ext = os.path.splitext(primary_output)
    outputs: dict = {}
    for lang in languages:
        if not lang or lang == "en":
            continue
        slides = translate_slides(english_slides, lang, translator)
        out = f"{base}_{lang}{ext}"
        DeckBuilder().build(slides, out, subtitle=topic)
        outputs[lang] = out
        log.info("extra-language deck (%s): %s", lang, out)
    return outputs


def convert_pdf(
    pdf_path: str,
    target_language: Optional[str] = None,
    vision_enabled: bool = True,
    output_path: Optional[str] = None,
    run_dir: Optional[str] = None,
    extra_languages: Optional[list] = None,
    *,
    verifier=None,
    content_agent=None,
    critic=None,
    translator=None,
    page_provider: Optional[PageProvider] = None,
) -> ConversionResult:
    """Convert a PDF into a deck. `extra_languages` emits additional translated
    decks from the same English content (translation-only cost) -- run this with
    an English primary (`target_language=None`) to get e.g. English + Turkish
    without paying for the vision + content stages twice."""
    run = _prepare(pdf_path, target_language, vision_enabled, output_path, run_dir,
                   verifier, content_agent, critic, translator, page_provider)
    try:
        from langchain_core.callbacks import get_usage_metadata_callback

        with get_usage_metadata_callback() as usage_cb:
            final = run.graph.invoke(run.state_in, run.config)
        _finalize_cost(run.report, usage_cb.usage_metadata, run.run_dir)
        result = _result(run, final)
        if extra_languages:
            if target_language not in (None, "en"):
                log.warning(
                    "extra_languages translates from the primary-language deck "
                    "(%s), not English; run English-primary for clean variants",
                    target_language,
                )
            result.extra_outputs = _emit_extra_languages(
                run, result.slides, extra_languages,
                result.output_path, final.get("topic", "Medical Education"),
            )
    finally:
        if run.owns_provider:
            run.provider.close()
    return result


def iter_convert(
    pdf_path: str,
    target_language: Optional[str] = None,
    vision_enabled: bool = True,
    output_path: Optional[str] = None,
    run_dir: Optional[str] = None,
    extra_languages: Optional[list] = None,
    *,
    verifier=None,
    content_agent=None,
    critic=None,
    translator=None,
    page_provider: Optional[PageProvider] = None,
) -> Iterator[tuple]:
    """Stream the pipeline. Yields ('node', name) per graph step, then
    ('done', ConversionResult). Reconstructs final state from the update
    stream, honoring the fan-out reducers.

    `extra_languages` mirrors `convert_pdf`: after the primary deck is built it
    emits one translated sibling deck per language (translation-only cost),
    reusing the already-rendered figures. Run English-primary
    (`target_language=None`) for clean variants."""
    run = _prepare(pdf_path, target_language, vision_enabled, output_path, run_dir,
                   verifier, content_agent, critic, translator, page_provider)
    acc = dict(run.state_in)
    try:
        from langchain_core.callbacks import get_usage_metadata_callback

        with get_usage_metadata_callback() as usage_cb:
            for update in run.graph.stream(run.state_in, run.config, stream_mode="updates"):
                for node, delta in update.items():
                    for k, v in (delta or {}).items():
                        if k in _REDUCER_KEYS:
                            acc[k] = acc.get(k, []) + list(v)
                        else:
                            acc[k] = v
                    yield ("node", node)
        _finalize_cost(run.report, usage_cb.usage_metadata, run.run_dir)
    finally:
        if run.owns_provider:
            run.provider.close()

    result = _result(run, acc)
    if extra_languages:
        if target_language not in (None, "en"):
            log.warning(
                "extra_languages translates from the primary-language deck "
                "(%s), not English; run English-primary for clean variants",
                target_language,
            )
        yield ("node", "emit_extra")
        result.extra_outputs = _emit_extra_languages(
            run, result.slides, extra_languages,
            result.output_path, acc.get("topic", "Medical Education"),
        )
    yield ("done", result)
