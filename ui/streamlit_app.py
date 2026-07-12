"""Thin Streamlit shell over the pdfdeck pipeline.

Business logic lives in the graph; this is upload -> run -> download only.
Run with:  streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import os
import tempfile

import streamlit as st

from pdfdeck.config import settings
from pdfdeck.pipeline import convert_pdf

st.set_page_config(page_title="pdfdeck", page_icon="\U0001F4CA", layout="centered")
st.title("PDF excerpt -> presentation deck")
st.caption("Agentic: figures are rendered and verified; text is summarized and fidelity-checked.")

with st.sidebar:
    st.header("Options")
    lang = st.selectbox("Language", ["English", "Turkish"], index=0)
    lang_code = None if lang == "English" else "tr"
    no_vision = st.checkbox("Skip vision verification (faster, deterministic)", value=False)
    st.markdown("---")
    st.write("Anthropic key:", "configured" if settings.anthropic_api_key else "MISSING")
    if lang_code:
        st.write("Translator:", "configured" if settings.azure_translator_key else "MISSING")

uploaded = st.file_uploader("Upload a medical PDF excerpt (5-10 pages)", type=["pdf"])

if uploaded and st.button("Convert", type="primary"):
    if not settings.anthropic_api_key:
        st.error("ANTHROPIC_API_KEY is not set. Add it to your .env and restart.")
        st.stop()
    with st.spinner("Extracting figures, verifying crops, drafting grounded slides..."):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.getvalue())
            pdf_path = tmp.name
        try:
            result = convert_pdf(pdf_path, target_language=lang_code, vision_enabled=not no_vision)
        finally:
            os.unlink(pdf_path)

    st.success(f"Done: {len(result.slides)} slides, {len(result.figures)} figures.")
    r = result.report
    st.info(
        f"vision_calls={r.vision_calls} | best_effort={len(r.best_effort_figures)} | "
        f"no_vision={len(r.no_vision_figures)} | fallback_pages={len(r.fallback_pages)} | "
        f"est_cost=${r.cost_estimate_usd:.4f}"
    )
    if r.garbled_pages:
        st.warning(f"Garbled pages excluded from text: {[p + 1 for p in r.garbled_pages]}")
    with open(result.output_path, "rb") as f:
        st.download_button(
            "Download .pptx", f.read(), file_name="presentation.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
