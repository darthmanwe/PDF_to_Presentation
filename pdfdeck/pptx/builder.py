"""SlideSpec -> PowerPoint (.pptx).

Deterministic assembly. Fixes two v1 bugs by construction:
- a fresh Presentation() per call (v1 cached one builder in Streamlit session
  state, so a second conversion appended to the first deck), and
- aspect-ratio-preserving image placement (v1 forced width AND height, so
  every figure was stretched to a fixed box).
"""

from __future__ import annotations

import os

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from pdfdeck.models import SlideSpec
from pdfdeck.telemetry import get_logger

log = get_logger(__name__)

# 16:9 canvas.
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
_GRAY = RGBColor(0x59, 0x59, 0x59)
_BLACK = RGBColor(0x00, 0x00, 0x00)


def _fit(img_w: int, img_h: int, box_w: float, box_h: float) -> tuple[float, float]:
    """Scale (img_w, img_h) to fit inside (box_w, box_h) preserving aspect."""
    if img_w <= 0 or img_h <= 0:
        return box_w, box_h
    scale = min(box_w / img_w, box_h / img_h)
    return img_w * scale, img_h * scale


class DeckBuilder:
    def build(
        self, slides: list[SlideSpec], output_path: str, subtitle: str = "Medical Education"
    ) -> str:
        prs = Presentation()
        prs.slide_width = SLIDE_W
        prs.slide_height = SLIDE_H
        self._blank = prs.slide_layouts[6]  # fully blank layout; we place shapes manually

        for spec in slides:
            if spec.slide_type == "title":
                self._title_slide(prs, spec, subtitle)
            elif spec.slide_type in ("figure", "fallback_page"):
                self._figure_slide(prs, spec)
            else:
                self._text_slide(prs, spec)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        prs.save(output_path)
        log.info("deck saved: %s (%d slides)", output_path, len(prs.slides))
        return output_path

    # -- slide kinds --------------------------------------------------------

    def _title_slide(self, prs, spec: SlideSpec, subtitle: str) -> None:
        slide = prs.slides.add_slide(self._blank)
        box = slide.shapes.add_textbox(Inches(1), Inches(2.6), Inches(11.33), Inches(1.6))
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = spec.title or "Medical Presentation"
        p.alignment = PP_ALIGN.CENTER
        p.font.size = Pt(40)
        p.font.bold = True
        p.font.color.rgb = _BLACK
        sub = slide.shapes.add_textbox(Inches(1), Inches(4.3), Inches(11.33), Inches(0.8))
        sp = sub.text_frame.paragraphs[0]
        sp.text = subtitle
        sp.alignment = PP_ALIGN.CENTER
        sp.font.size = Pt(20)
        sp.font.italic = True
        sp.font.color.rgb = _GRAY

    def _text_slide(self, prs, spec: SlideSpec) -> None:
        slide = prs.slides.add_slide(self._blank)
        self._add_title(slide, spec.title)
        body = slide.shapes.add_textbox(Inches(0.7), Inches(1.5), Inches(12.0), Inches(5.4))
        tf = body.text_frame
        tf.word_wrap = True
        bullets = spec.bullets or ["(no content)"]
        for i, bullet in enumerate(bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = "• " + bullet
            p.font.size = Pt(18)
            p.font.color.rgb = _BLACK
            p.space_after = Pt(10)

    def _figure_slide(self, prs, spec: SlideSpec) -> None:
        slide = prs.slides.add_slide(self._blank)
        self._add_title(slide, spec.title)

        box_w, box_h = Inches(11.5), Inches(4.7)
        top = Inches(1.5)
        if spec.image_path and os.path.exists(spec.image_path):
            with Image.open(spec.image_path) as im:
                iw, ih = im.size
            disp_w, disp_h = _fit(iw, ih, box_w, box_h)
            left = (SLIDE_W - disp_w) / 2
            slide.shapes.add_picture(spec.image_path, left, top, width=int(disp_w), height=int(disp_h))
            caption_top = top + int(disp_h) + Inches(0.15)
        else:
            log.warning("figure slide %s has no image at %s", spec.figure_ref, spec.image_path)
            caption_top = top

        if spec.caption:
            cap = slide.shapes.add_textbox(Inches(0.9), caption_top, Inches(11.5), Inches(1.0))
            ctf = cap.text_frame
            ctf.word_wrap = True
            cp = ctf.paragraphs[0]
            cp.text = spec.caption
            cp.font.size = Pt(11)
            cp.font.italic = True
            cp.font.color.rgb = _GRAY
            cp.alignment = PP_ALIGN.CENTER

    # -- helpers ------------------------------------------------------------

    def _add_title(self, slide, title: str) -> None:
        box = slide.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(12.1), Inches(1.0))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = title or "Slide"
        p.font.size = Pt(28)
        p.font.bold = True
        p.font.color.rgb = _BLACK
