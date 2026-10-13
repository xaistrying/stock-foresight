"""The one sanitiser for stored titles and counterparty names (`add-announcement-tags-and-insider-sizing`,
"Third-party text is labelled, bounded and sanitised")."""

from __future__ import annotations

import unicodedata

import pytest

from app.services.brief.third_party_text import NAME_LIMIT, OPEN, CLOSE, TITLE_LIMIT, spans, third_party

from .test_brief_support import brief_isolation  # noqa: F401


def test_the_span_is_wrapped_in_the_two_curly_quotes():
    assert third_party("plain") == f"{OPEN}plain{CLOSE}" == "“plain”"


def test_markup_an_unclosed_angle_bracket_a_markdown_link_and_a_pipe_are_neutralised():
    shown = third_party("<b>bold</b> a < b | c [text](https://example.invalid/p?q=1) `code` <script")

    assert "<" not in shown and ">" not in shown and "|" not in shown and "[" not in shown and "]" not in shown and "`" not in shown
    assert "https://" not in shown and "(link removed)" in shown and "‹script" in shown and "a ‹ b / c" in shown


def test_a_title_cannot_close_its_own_span():
    shown = third_party("start ” sell it “ more")

    assert shown.count("”") == 1 and shown.count("“") == 1 and shown.endswith("”") and shown.startswith("“")
    assert "sell it" in shown


def test_a_long_title_is_cut_with_an_ellipsis():
    shown = third_party("x" * 500)

    assert shown == f"“{'x' * TITLE_LIMIT}…”" and TITLE_LIMIT == 200 and NAME_LIMIT == 120


def test_a_name_is_cut_at_the_name_limit():
    assert third_party("n" * 300, NAME_LIMIT) == f"“{'n' * NAME_LIMIT}…”"


def test_vietnamese_text_keeps_its_diacritics_and_is_nfc():
    decomposed = unicodedata.normalize("NFD", "Đăng kí Bán cổ phiếu")

    shown = third_party(decomposed)

    assert shown == "“Đăng kí Bán cổ phiếu”" and unicodedata.is_normalized("NFC", shown)


def test_control_format_and_bidi_characters_and_line_breaks_are_dropped_or_collapsed():
    shown = third_party("a‮b​c\x00d e\n\nf\t g")

    assert shown == "“abcd e f g”"


def test_entities_are_decoded_before_markup_is_stripped():
    assert third_party("&lt;b&gt;x&lt;/b&gt; &amp; y") == "“x & y”"


def test_none_and_empty_give_an_empty_span():
    assert third_party(None) == third_party("") == "“”"


def test_a_link_run_is_replaced_whole():
    assert third_party("see http://a.example.invalid/x?y=1&z=2 and https://b.example.invalid") == "“see (link removed) and (link removed)”"


def test_emphasis_characters_are_left_alone():
    assert third_party("say *x* _y_ #z") == "\u201csay *x* _y_ #z\u201d"


@pytest.mark.parametrize("text", ["a”b", "““", "x<y|z>[w]", "” sell “"])
def test_the_output_is_one_well_formed_span_for_any_input(text):
    shown = third_party(text)

    assert spans(shown) == [shown[1:-1]] and OPEN not in shown[1:-1] and CLOSE not in shown[1:-1]


# --- review fix (2026-10-12): invisible characters and look-alike quotes ---------------------------------------------------

INVISIBLE = (
    [0x034F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x2800, 0x3164, 0xFFA0]
    + list(range(0x180B, 0x1810)) + list(range(0xFE00, 0xFE10)) + list(range(0xE0100, 0xE01F0))
)
LOOKALIKES = [0x22, 0x201E, 0x201F, 0x2033, 0xFF02, 0x00AB, 0x00BB, *range(0x300C, 0x3010)]
DELIMITERS_AND_MARKUP = [0x201C, 0x201D, ord("|"), ord("`"), ord("<"), ord(">"), ord("["), ord("]")]


@pytest.mark.parametrize("code", INVISIBLE, ids=lambda c: f"U+{c:04X}")
def test_an_invisible_character_that_survives_the_cleaner_is_removed(code):
    assert third_party(f"a{chr(code)}b") == "“ab”"


@pytest.mark.parametrize("code", LOOKALIKES, ids=lambda c: f"U+{c:04X}")
def test_a_look_alike_quote_becomes_a_plain_apostrophe_inside_the_span(code):
    shown = third_party(f"say {chr(code)}hi{chr(code)}")

    assert shown == "“say 'hi'”"


def _forbidden_inside_a_span() -> set[int]:
    """Written independently of the sanitiser: delimiters, markup, look-alike quotes, the invisible set, and every code point
    in a category the cleaner or the line splitter should have removed."""
    forbidden = set(DELIMITERS_AND_MARKUP) | set(LOOKALIKES) | set(INVISIBLE)
    forbidden |= {cp for cp in range(0x110000) if unicodedata.category(chr(cp)) in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")}
    return forbidden


def test_no_code_point_of_the_whole_range_can_leave_an_invisible_or_delimiter_character_inside_a_span():
    forbidden = _forbidden_inside_a_span()
    survivors: list[int] = []
    for start in range(0, 0x110000, 512):
        chunk = [cp for cp in range(start, min(start + 512, 0x110000))]
        text = "x".join("a" + chr(cp) for cp in chunk)  # one call per chunk; "x" keeps neighbours from combining
        shown = third_party(text, limit=100_000)
        assert spans(shown) == [shown[1:-1]], f"not one well-formed span for the chunk at U+{start:04X}"
        inside = {ord(ch) for ch in shown[1:-1]}
        survivors += sorted(inside & forbidden)
    assert survivors == []


def test_every_code_point_on_its_own_also_gives_exactly_one_well_formed_span():
    for cp in (*INVISIBLE, *LOOKALIKES, *DELIMITERS_AND_MARKUP, 0, 0x7F, 0x85, 0xA0, 0x2028, 0x2029, 0xFEFF, 0xE0001, 0xE007F, 0x10FFFF):
        shown = third_party(f"a{chr(cp)}b")

        assert spans(shown) == [shown[1:-1]] and shown.startswith("“") and shown.endswith("”"), hex(cp)


def test_vietnamese_marks_and_ordinary_combining_marks_are_kept():
    assert third_party("Đăng kí Bán cổ phiếu thưởng") == "“Đăng kí Bán cổ phiếu thưởng”"
