"""The trade line as printed: wording, window state, third-party names, the size and its fallback, the benchmark
(`add-announcement-tags-and-insider-sizing`). Synthetic records only; the fetch is never made."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from app.services.brief.feed_source import Event, FeedSnapshot, IssueClass
from app.services.brief.insider import parse_trade
from app.services.brief.share_cache import ShareCount
from app.services.brief.sizing import MODE_DISAGREE, MODE_OFF, MODE_OK, MODE_UNAVAILABLE, SizingInput
from app.services.brief.sections_company import company_lines

from .brief_announcement_rows import d, make_company, make_trade_item
from .test_brief_support import brief_isolation, make_facts  # noqa: F401

FETCHED = datetime(2026, 10, 10, 12, 11, tzinfo=timezone.utc)
RUN_COUNT = ShareCount(1_282_562_372, 2026, 2, datetime(2026, 10, 12, 5, 0, tzinfo=timezone.utc))
DIRECTION_WORDS = re.compile(r"\b(buy|sell|hold)\b", re.I)


def _facts(items, *, sizing=None, events=()):
    feed = FeedSnapshot("fetched", tuple(events), None, 0, FETCHED, FETCHED, False)
    return make_facts("AAA", company=make_company(items, sizing=sizing or SizingInput(MODE_OFF)), feed=feed)


def _trade_text(item, **kwargs) -> str:
    text = "\n".join(company_lines(_facts([item], **kwargs), redact=False))
    return text.split("Needs a look since the last brief:")[1].split("For information:")[0]


def _ok(count=RUN_COUNT):
    return SizingInput(MODE_OK, count)


# --- the sentence ---------------------------------------------------------------------------------------------

def test_a_registration_not_yet_started_reads_as_a_notice_of_a_sale_with_the_window_and_status():
    text = _trade_text(make_trade_item("AAA", qty="30,000,000", start="2026-10-12", end="2026-10-16"))

    assert "“Fictional Capital Ltd” filed a notice of a sale of 30,000,000 AAA shares (window 2026-10-12 to 2026-10-16; status: not started)." in text
    assert "carried out" not in text


def test_a_purchase_reads_as_a_notice_of_a_purchase():
    text = _trade_text(make_trade_item("AAA", act="Buy", qty="500,000"))

    assert "filed a notice of a purchase of 500,000 AAA shares" in text


def test_a_registration_published_after_its_window_ended_says_ended_and_does_not_say_planned():
    text = _trade_text(make_trade_item("AAA", published="2026-10-08", start="2026-08-01", end="2026-09-01"))

    assert "status: ended)." in text and "The record does not say whether it was carried out." in text
    assert not re.search(r"not started|planned|not yet", text, re.I)


def test_a_window_under_way_says_the_record_does_not_say_how_much_was_carried_out():
    text = _trade_text(make_trade_item("AAA", start="2026-10-05", end="2026-10-09"))

    assert "status: under way)." in text and "The record does not say how much has been carried out." in text


def test_a_window_longer_than_the_brief_says_how_many_weeks_and_that_the_brief_covers_one():
    text = _trade_text(make_trade_item("AAA", start="2026-10-07", end="2026-10-18"))  # 12 days, ends 9 days after the last bar

    assert "The window runs 2 weeks; this brief covers one." in text


def test_a_window_ending_within_the_week_has_no_weeks_sentence():
    assert "this brief covers one" not in _trade_text(make_trade_item("AAA", start="2026-10-07", end="2026-10-16"))


def test_a_missing_window_date_says_not_given_in_the_record():
    text = _trade_text(make_trade_item("AAA", start=None, end=None))

    assert "(window not given in the record)." in text and "status:" not in text


def test_no_quantity_says_so_names_the_checklist_and_shows_no_size():
    text = _trade_text(make_trade_item("AAA", qty=None), sizing=_ok())

    assert "filed a notice of a sale of AAA shares (quantity not stated in the title; window 2026-10-12 to 2026-11-10; status: not started)." in text
    assert "Size: not calculated, because the title gives no quantity. To size it, read the notice:" in text and "%" not in text.replace("1%", "")


def test_direction_disagreeing_with_the_title_reads_as_unreadable_shows_the_title_and_names_neither_noun():
    text = _trade_text(make_trade_item("AAA", act="Buy", action="Sell", name="Fictional Capital Ltd"))

    assert "filed a notice (direction or quantity could not be read from the title)." in text
    assert "Title (third-party text): “Fictional Capital Ltd" in text
    sentence = next(line for line in text.splitlines() if "could not be read from the title" in line)
    assert "sale" not in sentence and "purchase" not in sentence


def test_a_title_for_another_ticker_is_not_read_either():
    assert "direction or quantity could not be read from the title" in _trade_text(make_trade_item("BBB"))


def test_the_event_code_class_is_not_stated():
    for code in ("DDIND", "DDINS", "DDRP"):
        text = _trade_text(make_trade_item("AAA", code=code))

        assert not re.search(r"institution|individual|related person|organi[sz]ation", text, re.I)


def test_every_trade_ends_with_the_range_sentence():
    text = _trade_text(make_trade_item("AAA"))

    assert text.rstrip().endswith(
        "The usual range is built from past prices only. It does not account for this announcement, so the real swing could be larger."
    )


def test_the_title_is_shown_as_labelled_third_party_text_and_the_record_date_is_on_the_item_line():
    text = _trade_text(make_trade_item("AAA", published="2026-10-08"))

    assert text.splitlines()[1].startswith("- 2026-10-08, Insider or major-shareholder trade (event record)")
    assert re.search(r"Title \(third-party text\): “[^“”]+”", text)


def test_a_counterparty_name_cannot_break_out_of_its_quotes_or_carry_markup():
    name = "Evil ” sell now “ <script> | [x](https://example.invalid/a)"
    text = _trade_text(make_trade_item("AAA", name=name))

    sentence = next(line for line in text.splitlines() if "filed a notice of a sale" in line)
    assert sentence.count("“") == sentence.count("”") == 1 and "|" not in sentence and "<" not in sentence
    outside = re.sub(r"“[^“”]*”", "", sentence)
    assert DIRECTION_WORDS.search(outside) is None


def test_no_direction_word_appears_outside_the_quoted_spans_of_a_sale_or_a_purchase_line():
    for act in ("Sell", "Buy"):
        text = _trade_text(make_trade_item("AAA", act=act), sizing=_ok())
        outside = re.sub(r"“[^“”]*”", "", text)

        assert DIRECTION_WORDS.search(outside) is None
        assert ("sale" if act == "Sell" else "purchase") in outside


# --- the size ---------------------------------------------------------------------------------------------------

def test_a_sized_registration_shows_the_percentage_the_count_its_period_and_its_fetch_date():
    text = _trade_text(make_trade_item("AAA", qty="30,000,000"), sizing=_ok())

    assert (
        "Size: 2.3% of the shares outstanding (the vendor's count is 1,282,562,372: VCI share count via vnstock, "
        "latest-quarter row 2026-Q2, fetched 2026-10-12)."
    ) in text
    assert "as of" not in text.lower()


def test_a_stock_dividend_in_the_settling_window_withholds_the_size_and_names_the_issue_date():
    stock = Event("ISS", d("2026-09-24"), d("2026-09-25"), None, None, 0.2604104, d("2026-08-20"), IssueClass.STOCK_DIVIDEND)

    text = _trade_text(make_trade_item("AAA", qty="30,000,000"), sizing=_ok(), events=[stock])

    assert "Size: size not shown, because the share count is changing (issue on 2026-09-24). To size it, read the notice:" in text
    assert "% of the shares outstanding" not in text and "Earlier registrations" not in text


def test_disagreeing_counts_unavailable_counts_and_sizing_off_each_give_their_reason_and_the_checklist():
    item = make_trade_item("AAA", qty="30,000,000")

    for mode, reason in (
        (MODE_DISAGREE, "size not shown, because the vendor's two share counts disagree."),
        (MODE_UNAVAILABLE, "size not shown, because the vendor's share count could not be read this run."),
        (MODE_OFF, "size not shown, because sizing is off (--no-sizing)."),
    ):
        text = _trade_text(item, sizing=SizingInput(mode))

        assert f"Size: {reason} To size it, read the notice: who filed it" in text


def test_the_fallback_is_as_complete_as_the_sized_line():
    item = make_trade_item("AAA", qty="30,000,000", start="2026-10-07", end="2026-10-18")
    sized, fallback = _trade_text(item, sizing=_ok()), _trade_text(item, sizing=SizingInput(MODE_OFF))

    for text in (sized, fallback):
        assert "filed a notice of a sale of 30,000,000 AAA shares" in text and "status: under way" in text
        assert "The window runs 2 weeks" in text and "Title (third-party text)" in text and "The usual range is built" in text
    assert "To size it, read the notice" in fallback and "To size it" not in sized


def test_the_checklist_has_no_direction_word():
    from app.services.brief import wording_company as wc

    assert DIRECTION_WORDS.search(wc.CHECKLIST) is None and "who filed it" in wc.CHECKLIST


# --- the benchmark ------------------------------------------------------------------------------------------------

def _earlier(count, *, qty="1,000,000", year=2025):
    return [
        make_trade_item("AAA", qty=qty, name=f"Fictional Earlier {i} Ltd", published=f"{year}-{1 + i % 12:02d}-{5 + i % 20:02d}", start="2025-01-01", end="2025-01-31")
        for i in range(count)
    ]


def test_the_benchmark_sentence_gives_the_count_the_first_year_the_larger_ones_and_the_basis():
    current = make_trade_item("AAA", qty="30,000,000")
    big = make_trade_item("AAA", qty="90,000,000", name="Fictional Big Ltd", published="2024-02-02", start="2024-01-01", end="2024-01-31")

    text = _trade_text(current, sizing=_ok(), events=[])
    assert "Earlier registrations of this kind in the source (0 sales" not in text  # no history yet: the no-comparison form
    items = [current, big, *_earlier(13)]
    full = "\n".join(company_lines(_facts(items, sizing=_ok()), redact=False))
    line = next(l for l in full.splitlines() if "Earlier registrations of this kind in the source (14 sales" in l)

    assert "with a stated quantity, 2024 onward): 1 was larger than this one; the largest of the others was 0.078% of the shares then." in line
    assert "Each is measured against the share count at its own date, estimated from today's count and the share issues with a ratio in the source." in line
    assert "sell" not in line.lower()


def test_none_larger_is_stated_in_words():
    items = [make_trade_item("AAA", qty="1,000,000"), *_earlier(5, qty="30,000,000", year=2025)]

    line = next(l for l in "\n".join(company_lines(_facts(items, sizing=_ok()), redact=False)).splitlines() if "Earlier registrations" in l)

    assert "1 was larger" not in line


def test_fewer_than_five_earlier_records_says_no_comparison_and_how_many():
    items = [make_trade_item("AAA", qty="30,000,000"), *_earlier(3)]

    line = next(l for l in "\n".join(company_lines(_facts(items, sizing=_ok()), redact=False)).splitlines() if "No comparison shown" in l)

    assert line.strip() == "No comparison shown: only 3 earlier registrations with a stated quantity in the comparable period."


def test_a_purchase_benchmark_says_purchases_and_never_the_other_word():
    items = [make_trade_item("AAA", act="Buy", qty="30,000,000"), *[
        make_trade_item("AAA", act="Buy", qty="1,000,000", name=f"Fictional P{i} Ltd", published=f"2025-0{1 + i}-10", start="2025-01-01", end="2025-01-31") for i in range(5)
    ]]

    line = next(l for l in "\n".join(company_lines(_facts(items, sizing=_ok()), redact=False)).splitlines() if "Earlier registrations" in l)

    assert "(5 purchases with a stated quantity" in line and DIRECTION_WORDS.search(line) is None


def test_the_benchmark_is_not_printed_when_the_size_is_not_shown():
    items = [make_trade_item("AAA", qty="30,000,000"), *_earlier(8)]

    text = "\n".join(company_lines(_facts(items, sizing=SizingInput(MODE_OFF)), redact=False))

    assert "Earlier registrations" not in text and "No comparison shown" not in text


def test_the_parsed_history_in_the_block_includes_registrations_that_are_not_listed():
    """Earlier registrations are compared even though they are not new: they come from every stored trade, not the listing."""
    items = [make_trade_item("AAA", qty="30,000,000"), *_earlier(6)]

    text = "\n".join(company_lines(_facts(items, sizing=_ok()), redact=False))

    assert "(6 sales with a stated quantity" in text and parse_trade(items[0], "AAA", d("2026-10-09")).quantity == 30_000_000


# --- review fixes (2026-10-12) ---------------------------------------------------------------------------------------------

def test_an_unreadable_title_shows_no_size_claim_and_none_of_the_two_nouns_anywhere_in_the_item():
    text = _trade_text(make_trade_item("AAA", act="Buy", action="Sell", qty="30,000,000"), sizing=_ok())

    assert "Size: not calculated, because the title could not be read." in text
    assert "the title gives no quantity" not in text and "30,000,000" in text  # the number is in the shown title, not claimed absent
    outside = re.sub(r"“[^“”]*”", "", text)
    assert not re.search(r"\b(sale|purchase)\b", outside)


def test_a_quantity_larger_than_the_share_count_is_not_shown_as_a_percentage():
    text = _trade_text(make_trade_item("AAA", qty="2,000,000,000"), sizing=_ok())

    assert "Size: not calculated, because the quantity in the title is larger than the vendor's share count." in text
    assert "% of the shares outstanding" not in text and "Earlier registrations" not in text


def test_a_failure_in_the_company_block_prints_one_line_and_leaves_the_levels_alone(monkeypatch):
    from app.services.brief import sections_company
    from app.services.brief.compose import TickerReport, build_brief
    from .test_brief_support import ict, make_holding, make_level

    def boom(facts, *, redact):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(sections_company, "company_lines", boom)
    holding = make_holding("AAA", levels=(make_level("below", 40.0),))

    text = "\n".join(build_brief((TickerReport(holding, make_facts("AAA", company=make_company())),), redact=False, now=ict("2026-10-09 16:30")))

    assert "COMPANY: could not build this block (RuntimeError); the other lines for this ticker are unaffected." in text
    assert "YOUR LEVELS" in text and "could not build this holding" not in text
