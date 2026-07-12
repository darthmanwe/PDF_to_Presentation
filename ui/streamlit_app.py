"""Streamlit demo UI over the pdfdeck agentic pipeline.

Upload a PDF -> watch the agent work (live per-node progress, one step per
figure verified) -> review the extracted figures with their verification
badges + the QA metrics -> download the .pptx. Business logic lives in the
graph; this streams `iter_convert` and renders. Run:

    streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import os
import tempfile

import streamlit as st

from pdfdeck.config import settings
from pdfdeck.models import VerificationStatus
from pdfdeck.pipeline import NODE_LABELS, iter_convert

st.set_page_config(page_title="pdfdeck", page_icon="\U0001F9EC", layout="wide")

_BADGE = {
    VerificationStatus.VERIFIED.value: ("verified", "✅"),
    VerificationStatus.BEST_EFFORT.value: ("best-effort", "⚠️"),
    VerificationStatus.NO_VISION.value: ("no-vision", "○"),
    VerificationStatus.UNVERIFIED.value: ("unverified", "○"),
}

st.title("pdfdeck")
st.markdown(
    "Turn a medical-textbook PDF excerpt into a student deck. Figures are "
    "**rendered and vision-verified** (not extracted as fragments); text is "
    "**summarized and fidelity-checked** against the source."
)

with st.sidebar:
    st.header("Options")
    lang = st.selectbox("Language", ["English", "Turkish"], index=0)
    lang_code = None if lang == "English" else "tr"
    no_vision = st.checkbox(
        "Skip vision verification", value=False,
        help="Deterministic figure bounds, no vision API calls (faster / cheaper).",
    )
    st.divider()
    st.caption("Configuration")
    st.write("Anthropic:", "✅ configured" if settings.anthropic_api_key else "❌ missing")
    if lang_code:
        st.write("Translator:", "✅ configured" if settings.azure_translator_key else "❌ missing")
    st.divider()
    st.caption(
        "Pipeline: ingest → detect regions → **figure agent** (render → verify "
        "→ retry) → **content agent** (plan → draft → critique) → translate → "
        "assemble."
    )

uploaded = st.file_uploader("Medical PDF excerpt (5–10 pages)", type=["pdf"])

if uploaded and st.button("Convert", type="primary"):
    if not settings.anthropic_api_key:
        st.error("ANTHROPIC_API_KEY is not set. Add it to .env and restart.")
        st.stop()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded.getvalue())
        pdf_path = tmp.name

    result = None
    fig_n = 0
    try:
        with st.status("Running the agentic pipeline…", expanded=True) as status:
            for kind, payload in iter_convert(
                pdf_path, target_language=lang_code, vision_enabled=not no_vision
            ):
                if kind == "node":
                    if payload == "process_region":
                        fig_n += 1
                        status.update(label=f"Verifying figure {fig_n} (vision agent)…")
                        status.write(f"Figure {fig_n} — crop rendered and verified")
                    else:
                        status.write(NODE_LABELS.get(payload, payload))
                else:
                    result = payload
            status.update(label="Done", state="complete", expanded=False)
    finally:
        os.unlink(pdf_path)

    if result is None:
        st.error("Conversion did not complete.")
        st.stop()

    r = result.report
    st.success(f"Built a {len(result.slides)}-slide deck with {len(result.figures)} figures.")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Slides", len(result.slides))
    c2.metric("Figures", len(result.figures))
    c3.metric("Vision calls", r.vision_calls)
    c4.metric("Best-effort", len(r.best_effort_figures))
    c5.metric("Est. cost", f"${r.cost_estimate_usd:.3f}")

    if r.garbled_pages:
        st.warning(f"Garbled pages excluded from text: {[p + 1 for p in r.garbled_pages]}")
    if r.fallback_pages:
        st.warning(f"Full-page fallback rendered for pages: {[p + 1 for p in r.fallback_pages]}")

    with open(result.output_path, "rb") as f:
        st.download_button(
            "⬇ Download .pptx", f.read(),
            file_name=os.path.basename(result.output_path),
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            type="primary",
        )

    st.subheader("Extracted figures")
    st.caption(
        "Each figure is one rendered region — the diagrams below arrive in the "
        "source PDF as hundreds of tiled image fragments."
    )
    cols = st.columns(4)
    for i, fig in enumerate(result.figures):
        with cols[i % 4]:
            if fig.image_path and os.path.exists(fig.image_path):
                st.image(fig.image_path, use_container_width=True)
            label, icon = _BADGE.get(fig.status.value, ("", ""))
            head = fig.caption.split(".")[0] if fig.caption else (fig.figure_no or "Figure")
            st.caption(f"{icon} {head[:60]} · {label}")

    with st.expander("QA report (raw)"):
        st.json(r.model_dump())
