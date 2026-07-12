"""Central configuration for pdfdeck.

All tunables live here: API keys (from .env / environment), per-role model IDs,
rendering DPI, clustering thresholds, and agent loop caps.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- API credentials -------------------------------------------------
    anthropic_api_key: str = ""
    azure_translator_key: str = ""
    azure_translator_endpoint: str = ""
    azure_translator_region: str = ""

    # --- Model IDs (per agent role; swappable cost levers) ---------------
    vision_model: str = "claude-opus-4-8"   # figure crop verification
    content_model: str = "claude-opus-4-8"  # outline + slide drafting
    critic_model: str = "claude-opus-4-8"   # fidelity critique

    # --- Rendering --------------------------------------------------------
    render_dpi: int = 300          # deck-quality region renders
    fallback_page_dpi: int = 150   # full-page fallback slide renders
    verify_max_long_edge: int = 1400  # downscale cap for VLM verify images
    verify_padding_frac: float = 0.10  # context padding around bbox in verify image

    # --- Region detection (extraction/rects.py) ---------------------------
    mask_px_per_pt: float = 2.0        # occupancy-mask resolution
    dilation_radius_pt: float = 9.0    # gap (in points) bridged when clustering
    max_rect_page_frac: float = 0.80   # drop rects covering more of the page
    rule_max_height_pt: float = 3.0    # thin-rule filter: max height
    rule_min_aspect: float = 20.0      # thin-rule filter: min width/height ratio
    min_region_area_pt2: float = 900.0  # discard specks (< ~30x30pt regions)
    label_text_max_words: int = 6      # text blocks absorbable into a region
    full_width_col_frac: float = 1.2   # region wider than this x column width => full-width
    qualify_min_drawings: int = 10     # drawings-only region needs >= this many to be a figure

    # --- Classification ----------------------------------------------------
    photo_max_rects: int = 8       # <= this many source rects can still be a photo
    diagram_min_rects: int = 12    # >= this many tiles => diagram

    # --- Agent loop caps ----------------------------------------------------
    max_figure_retries: int = 2
    max_content_revisions: int = 2
    vision_circuit_breaker: int = 3   # consecutive vision failures before disabling
    max_vision_concurrency: int = 4
    graph_recursion_limit: int = 100

    # --- Feature flags -------------------------------------------------------
    vision_enabled: bool = True


settings = Settings()
