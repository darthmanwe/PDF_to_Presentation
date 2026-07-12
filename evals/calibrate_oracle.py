"""One-time oracle calibration: detect regions on repair.pdf, render each
candidate to runs/calibration/, and print the per-page summary.

After visual confirmation of the renders, the verified truth is frozen into
tests/fixtures/repair_oracle.json, which the integration suite asserts
against. Tests then encode INSPECTED reality, not assumptions.

Usage:  python evals/calibrate_oracle.py [pdf_path]
"""

from __future__ import annotations

import json
import os
import sys

import fitz

from pdfdeck.extraction.detect import detect_page_regions
from pdfdeck.extraction.ingest import ingest_pdf, raw_candidate_rects
from pdfdeck.extraction.rects import ClusterParams
from pdfdeck.rendering.page_render import render_region

PDF = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/repair.pdf"
OUT = "runs/calibration"


def main() -> None:
    pages, sha = ingest_pdf(PDF)
    doc = fitz.open(PDF)
    os.makedirs(OUT, exist_ok=True)

    summary: dict[str, dict] = {}
    print(f"{PDF}  sha={sha[:12]}")
    print(f"{'page':>4} {'regions':>7} {'kind':<26} caption")
    for pm in pages:
        image_rects, drawing_rects = raw_candidate_rects(doc[pm.index])
        regions = detect_page_regions(pm, image_rects, drawing_rects, ClusterParams())
        page_entry = {"regions": len(regions), "detail": []}
        for reg in regions:
            out_png = f"{OUT}/p{pm.index + 1}_{reg.id}_{reg.kind.value}.png"
            render_region(doc[pm.index], reg.bbox, out_png, dpi=150)
            cap = (reg.caption or "")[:60]
            print(
                f"{pm.index + 1:>4} {'':>7} {reg.id + ' ' + reg.kind.value:<26} "
                f"[{len(reg.source_rects):>4} rects] {cap}"
            )
            page_entry["detail"].append(
                {
                    "id": reg.id,
                    "kind": reg.kind.value,
                    "source_rects": len(reg.source_rects),
                    "figure_no": reg.figure_no,
                    "caption_head": cap,
                    "bbox": [round(reg.bbox.x0), round(reg.bbox.y0),
                             round(reg.bbox.x1), round(reg.bbox.y1)],
                    "full_width": reg.is_full_width,
                }
            )
        print(f"{pm.index + 1:>4} {len(regions):>7}   (captions on page: {pm.caption_mentions}, "
              f"cols: {'2' if pm.column_split_x else '1'}, garbled: {pm.is_garbled})")
        summary[str(pm.index + 1)] = page_entry

    with open(f"{OUT}/summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nrenders + summary.json written to {OUT}/")


if __name__ == "__main__":
    main()
