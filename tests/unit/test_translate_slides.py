"""Slide translation: flatten -> translate -> map back, structure preserved."""

from pdfdeck.models import SlideSpec
from pdfdeck.translation.translate_slides import translate_slides


class _FakeService:
    def __init__(self):
        self.batches = []

    def translate_batch(self, texts, target, source="en"):
        self.batches.append(list(texts))
        return [f"<{target}>{t}" for t in texts]


def _deck():
    return [
        SlideSpec(index=0, title="Tissue Repair", slide_type="title"),
        SlideSpec(index=1, title="Granulation", slide_type="text",
                  bullets=["Capillaries appear.", "Fibroblasts deposit collagen."]),
        SlideSpec(index=2, title="Figure 2.1", slide_type="figure",
                  figure_ref="p0_r0", image_path="/tmp/x.png", caption="Figure 2.1 Repair."),
    ]


def test_english_is_noop():
    deck = _deck()
    svc = _FakeService()
    out = translate_slides(deck, "en", svc)
    assert out is deck
    assert svc.batches == []


def test_all_visible_text_translated_in_one_batch():
    svc = _FakeService()
    out = translate_slides(_deck(), "tr", svc)
    # one batch: 3 titles + 2 bullets + 1 caption = 6 items
    assert len(svc.batches) == 1
    assert len(svc.batches[0]) == 6
    assert out[0].title == "<tr>Tissue Repair"
    assert out[1].bullets == ["<tr>Capillaries appear.", "<tr>Fibroblasts deposit collagen."]
    assert out[2].caption == "<tr>Figure 2.1 Repair."


def test_structure_and_images_preserved():
    out = translate_slides(_deck(), "tr", _FakeService())
    assert [s.slide_type for s in out] == ["title", "text", "figure"]
    assert out[2].image_path == "/tmp/x.png"      # untouched
    assert out[2].figure_ref == "p0_r0"


def test_original_deck_not_mutated():
    deck = _deck()
    translate_slides(deck, "tr", _FakeService())
    assert deck[1].bullets == ["Capillaries appear.", "Fibroblasts deposit collagen."]
