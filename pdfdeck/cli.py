"""pdfdeck command line.

    pdfdeck run INPUT.pdf --lang tr
    pdfdeck run INPUT.pdf --no-vision          # deterministic, no API calls to vision
    pdfdeck calibrate INPUT.pdf                 # render candidate regions for inspection
"""

from __future__ import annotations

import typer

from pdfdeck.telemetry import get_logger

app = typer.Typer(add_completion=False, help="Medical PDF excerpt -> presentation deck.")
log = get_logger(__name__)


@app.command()
def run(
    pdf: str = typer.Argument(..., help="Input PDF path"),
    lang: str = typer.Option("en", "--lang", help="Target language (en = no translation, tr = Turkish)"),
    no_vision: bool = typer.Option(False, "--no-vision", help="Skip vision verification (deterministic)"),
    out: str = typer.Option(None, "--out", help="Output .pptx path (default: runs/<ts>/deck.pptx)"),
):
    """Convert a PDF excerpt into a presentation deck."""
    from pdfdeck.pipeline import convert_pdf

    result = convert_pdf(
        pdf,
        target_language=None if lang == "en" else lang,
        vision_enabled=not no_vision,
        output_path=out,
    )
    typer.echo(f"\nDeck:   {result.output_path}")
    typer.echo(f"Run:    {result.run_dir}")
    typer.echo(f"Slides: {len(result.slides)}  Figures: {len(result.figures)}")
    r = result.report
    typer.echo(
        f"QA:     vision_calls={r.vision_calls} best_effort={len(r.best_effort_figures)} "
        f"no_vision={len(r.no_vision_figures)} fallback_pages={len(r.fallback_pages)} "
        f"cost=${r.cost_estimate_usd:.4f}"
    )


@app.command()
def calibrate(pdf: str = typer.Argument("tests/fixtures/repair.pdf")):
    """Render candidate figure regions to runs/calibration/ for visual review."""
    import runpy
    import sys

    sys.argv = ["calibrate_oracle.py", pdf]
    runpy.run_path("evals/calibrate_oracle.py", run_name="__main__")


if __name__ == "__main__":
    app()
