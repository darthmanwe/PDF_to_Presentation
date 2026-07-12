# pdfdeck

Turn a medical-textbook PDF excerpt (5–10 pages) into a student presentation deck: the chapter's **figures extracted cleanly** and interleaved with **grounded, fidelity-checked text slides**, optionally translated to Turkish.

Built as an **agentic system** in LangGraph on Anthropic Claude. It's a top-to-bottom rebuild of an earlier prompt-chain that fragmented diagrams into hundreds of unusable slivers.

## The problem it solves

A schematic diagram in a PDF has no single extractable image — it's vector paths + text labels + many small raster tiles. Naively extracting embedded image objects shatters it. On the test document (`tests/fixtures/repair.pdf`, a Robbins *Tissue Repair* chapter), one figure is delivered as **2,309 tiles**.

| approach | figures produced | fragments |
|---|---|---|
| extract embedded image objects (old) | **3,214 image objects** | **3,123 sub-120px fragments (97%)** |
| **pdfdeck** (render clustered regions) | **8 clean figures** | **0** |

pdfdeck **renders page regions** instead of extracting objects — compositing every tile/path in a region into one flat image — and a vision agent verifies each crop.

## Architecture

```
ingest -> detect regions -> [Send fan-out] -> Figure Agent -> gather
       -> Content Agent -> translate -> assemble (.pptx) -> QA report
```

Two genuinely agentic loops (LangGraph subgraphs with conditional edges); everything else is deterministic.

- **Figure Agent** — cluster tile/drawing placement rects (mask + dilation + connected-components), render the region, then *look at the crop with Claude vision* and **retry with an adjusted bbox** if it's cut off or captures a neighbor. Bounded; falls back to best-effort / no-vision gracefully.
- **Content Agent** — plan → draft → **fidelity critic** → revise. Every bullet cites source span IDs; a hybrid critic (deterministic citation check + LLM entailment) rejects unsupported or invented claims. No fabricated fallbacks — failures are flagged, never faked.

Full rationale and code walkthrough: `../Supporting_Files/DECISIONS_AND_CODE_WALKTHROUGH.md`.

## Install

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows; use source .venv/bin/activate elsewhere
pip install -e ".[dev,ui]"
cp .env.example .env                                 # then fill in ANTHROPIC_API_KEY (+ Azure Translator for --lang tr)
```

## Use

```bash
pdfdeck run excerpt.pdf --lang tr           # convert + translate to Turkish
pdfdeck run excerpt.pdf --no-vision         # deterministic figures, no vision API calls
pdfdeck calibrate excerpt.pdf               # render candidate figure regions for inspection
streamlit run ui/streamlit_app.py           # browser UI
```

Output lands in `runs/<timestamp>/`: `deck.pptx`, the rendered `figures/`, and `qa_report.json` (verification statuses, dropped/flagged figures, cost).

## Test

```bash
pytest                      # 77 offline tests (no API key): unit + integration + e2e-with-fakes
pytest -m vision            # opt-in live smoke test (needs ANTHROPIC_API_KEY)
python evals/judge.py figures tests/fixtures/repair.pdf   # the v1-vs-v2 extraction metric
```

The whole pipeline runs offline against injected Fakes, so tests need no network. `test_no_fragment_figures` is the permanent guard against the fragmentation failure returning.

## Configuration

All tunables live in `pdfdeck/config.py` (model IDs per role, render DPI, clustering dilation radius, loop caps). Models default to `claude-opus-4-8`; the high-volume vision verification can be routed to `claude-haiku-4-5` / `claude-sonnet-5` as a cost lever.

## Stack

LangGraph · langchain-anthropic (Claude) · PyMuPDF + pymupdf4llm · scipy/numpy (clustering) · python-pptx · Azure Translator · Typer · Streamlit · pytest.
