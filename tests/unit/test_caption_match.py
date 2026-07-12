"""Caption detection (vs inline references) and region association."""

from pdfdeck.extraction.caption_match import (
    associate_captions,
    caption_figure_no,
    caption_title,
    clean_caption,
    find_caption_blocks,
)
from pdfdeck.models import Rect, TextBlock


def _block(text, x0=60, y0=400, x1=300, y1=430):
    return TextBlock(
        span_id="", text=text, word_count=len(text.split()),
        bbox=Rect(x0=x0, y0=y0, x1=x1, y1=y1),
    )


def test_caption_block_detected():
    cap = _block("Figure 2.16 Granulation tissue showing numerous blood vessels.")
    body = _block("The repair process begins early in inflammation.")
    found = find_caption_blocks([cap, body])
    assert found == [cap] and cap.is_caption and not body.is_caption


def test_inline_reference_not_a_caption():
    inline = _block("As shown in Figure 2.16, granulation tissue contains vessels.")
    assert find_caption_blocks([inline]) == []
    assert not inline.is_caption


def test_variants_detected():
    # "FIG." (all-caps) is the form Robbins uses -- the regression this fixes.
    for text in ("FIGURE 3.1 X.", "Fig. 4.12 Y.", "Table 2.1 Z.", "Figure 4-2 W.",
                 "FIG. 2.24 Healing wound.", "FIG 2.20 Mechanisms.", "Fig 3.1 Z."):
        assert find_caption_blocks([_block(text)]), text


def test_caption_title_first_sentence():
    cap = ("FIG. 2.24 Healing wound. (A) Granulation tissue showing numerous "
           "blood vessels and a loose matrix. (B) Trichrome stain of mature scar.")
    assert caption_title(cap) == "FIG. 2.24 Healing wound."


def test_caption_title_short_table_kept_whole():
    assert caption_title("Table 2.10 Growth Factors") == "Table 2.10 Growth Factors"


def test_caption_title_dehyphenates():
    assert caption_title("FIG. 2.20 Mechanisms of scar forma- tion.") == \
        "FIG. 2.20 Mechanisms of scar formation."


def test_caption_title_none_passthrough():
    assert caption_title(None) is None


def test_caption_title_truncates_runaway():
    cap = "FIG. 9.9 " + "x" * 300  # no sentence break
    out = caption_title(cap, max_len=150)
    assert len(out) <= 150 and out.endswith("…")


def test_clean_caption_collapses_whitespace():
    assert clean_caption("Figure  2.1\n  Repair\tprocess") == "Figure 2.1 Repair process"


def test_figure_no_extraction():
    assert caption_figure_no("Figure 2.16 Granulation tissue.") == "2.16"
    assert caption_figure_no("TABLE 3.1 Growth factors.") == "3.1"
    assert caption_figure_no("Plain body text.") is None


def test_association_prefers_below():
    region = Rect(x0=60, y0=100, x1=300, y1=380)
    below = _block("Figure 1.1 Below caption.", y0=386, y1=402)
    above = _block("Figure 1.2 Above caption.", y0=70, y1=86)
    find_caption_blocks([below, above])
    got = associate_captions([region], [above, below])
    assert got[0].caption_block is below
    assert got[0].position == "below"


def test_association_falls_back_to_above():
    region = Rect(x0=60, y0=100, x1=300, y1=380)
    above = _block("Figure 1.2 Above caption.", y0=70, y1=86)
    find_caption_blocks([above])
    got = associate_captions([region], [above])
    assert got[0].position == "above"


def test_no_cross_column_association():
    region = Rect(x0=60, y0=100, x1=300, y1=380)            # left column
    other_col = _block("Figure 9.9 Right-column caption.", x0=322, x1=560, y0=386, y1=402)
    find_caption_blocks([other_col])
    assert associate_captions([region], [other_col]) == {}   # no x-overlap


def test_one_caption_one_region_greedy():
    r1 = Rect(x0=60, y0=100, x1=300, y1=300)
    r2 = Rect(x0=60, y0=340, x1=300, y1=540)
    cap1 = _block("Figure 1.1 First.", y0=305, y1=320)
    cap2 = _block("Figure 1.2 Second.", y0=545, y1=560)
    find_caption_blocks([cap1, cap2])
    got = associate_captions([r1, r2], [cap1, cap2])
    assert got[0].caption_block is cap1
    assert got[1].caption_block is cap2


def test_distant_caption_ignored():
    region = Rect(x0=60, y0=100, x1=300, y1=200)
    far = _block("Figure 5.5 Far away.", y0=500, y1=516)
    find_caption_blocks([far])
    assert associate_captions([region], [far]) == {}
