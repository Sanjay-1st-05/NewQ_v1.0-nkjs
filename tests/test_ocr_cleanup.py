"""OCR post-extraction cleanup tests (stage: OCR refinement).

The cleaner is pure text processing — no network, no Gemini. These
complement the live /api/extract-text verification already covered
against the real server.
"""

from backend.vision_service import _clean_extracted_text


def test_joins_hyphenated_word_across_line_break():
    raw = "The government announced an econom-\nic package for farmers."
    assert _clean_extracted_text(raw) == (
        "The government announced an economic package for farmers."
    )


def test_sentence_dash_is_not_joined():
    raw = "Growth is strong -\nit said. Launch of X-11 was succes-\nsful."
    cleaned = _clean_extracted_text(raw)
    assert"Growth is strong -\nit said." in cleaned
    assert "successful" in cleaned
    assert "X-11" in cleaned


def test_drops_standalone_page_numbers_and_urls():
    raw = (
        "The RBI revised the repo rate.\n"
        "Page 7\n"
        "8\n"
        "www.example-news.com\n"
        "https://follow-live-updates.in\n"
        "Inflation cooled to 4.1 percent."
    )
    cleaned = _clean_extracted_text(raw)
    assert "Page 7" not in cleaned
    assert "\n8\n" not in cleaned
    assert "www.example-news.com" not in cleaned
    assert "https://follow-live-updates.in" not in cleaned
    assert "repo rate" in cleaned
    assert "Inflation cooled" in cleaned


def test_keeps_numbers_inside_real_content():
    raw = "The state logged 412 new cases in the first week of March."
    assert _clean_extracted_text(raw) == raw


def test_collapses_blank_line_runs():
    raw = "First paragraph.\n\n\n\n\nSecond paragraph."
    cleaned = _clean_extracted_text(raw)
    assert "\n\n\n" not in cleaned
    assert "First paragraph." in cleaned
    assert "Second paragraph." in cleaned


def test_strips_bare_bullets_and_rules():
    raw = "Headline\n----\n•\nBody text continues here."
    cleaned = _clean_extracted_text(raw)
    assert "----" not in cleaned
    assert "Headline" in cleaned
    assert "Body text continues here." in cleaned


def test_empty_and_none_safe():
    assert _clean_extracted_text("") == ""
    assert _clean_extracted_text("\n\n") == ""
