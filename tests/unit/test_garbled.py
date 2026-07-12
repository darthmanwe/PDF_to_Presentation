"""Garbled-text heuristic."""

from pdfdeck.extraction.garbled import is_garbled

CLEAN = (
    "Repair by connective tissue deposition consists of sequential processes "
    "that follow tissue injury: angiogenesis, formation of granulation tissue, "
    "and deposition of extracellular matrix. " * 5
)


def test_clean_text_passes():
    assert not is_garbled(CLEAN)


def test_replacement_chars_flagged():
    garbage = ("word ��� " * 80)
    assert is_garbled(garbage)


def test_cid_artifacts_flagged():
    garbage = ("(cid:1024)(cid:88) some words here " * 30)
    assert is_garbled(garbage)


def test_symbol_soup_flagged():
    garbage = ("@#$% ^&*() 12345 ~~ || " * 40)
    assert is_garbled(garbage)


def test_short_text_never_flagged():
    assert not is_garbled("���")
