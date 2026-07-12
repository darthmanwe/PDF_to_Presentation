"""Top-level pipeline state.

The figure step fans out over regions with the Send API; the collector fields
below use `operator.add` reducers so parallel branches append instead of
clobbering each other -- the classic LangGraph map-reduce gotcha.
"""

from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from pdfdeck.models import Figure, PageModel, Region, SlideSpec


class PipelineState(TypedDict, total=False):
    # inputs
    pdf_path: str
    target_language: Optional[str]
    run_dir: str
    vision_enabled: bool
    max_retries: int

    # ingest / detect
    pdf_sha: str
    topic: str
    pages: list[PageModel]
    regions: list[Region]
    fallback_pages: list[int]

    # figure fan-out collectors (reducers required)
    figures: Annotated[list[Figure], operator.add]
    best_effort: Annotated[list[str], operator.add]
    no_vision: Annotated[list[str], operator.add]
    dropped: Annotated[list[str], operator.add]

    # content / output
    slides: list[SlideSpec]
    output_path: str
