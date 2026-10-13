"""compose.py: the ordered sections, the top of the brief, the provisional warning, the triggers line,
the redacted path (tasks 7.2a, 7.3, 8.3)."""

from __future__ import annotations

import re
from datetime import date

import pytest

from app.services.brief import compose, sections_holding, wording
from app.services.brief.compose import TICKER_SECTIONS, TickerReport, build_brief
from app.services.brief.wording import TriggerCount

from .test_brief_support import brief_isolation, ict, make_facts, make_holding, make_level, make_week  # noqa: F401

AFTER_CLOSE = ict("2026-10-09 16:30")
BEFORE_CLOSE = ict("2026-10-09 11:00")


def _report(ticker="AAA", close=42.90, levels=(), **fact_fields) -> TickerReport:
    return TickerReport(make_holding(ticker, levels=levels), make_facts(ticker, close=close, **fact_fields))


def _brief(reports, *, redact=False, now=AFTER_CLOSE, **kwargs):
    return build_brief(tuple(reports), redact=redact, now=now, **kwargs)


def _text(lines):
    return "\n".join(lines)


# --- the order of the first lines ---------------------------------------------------------------------

def test_the_first_lines_in_order_for_a_run_after_the_close():
    lines = _brief([_report()])

    assert lines[0].startswith("WEEKLY CHECK") and "the 5 sessions after 2026-10-09" in lines[0]
    assert lines[1] == "Re-read triggers this run: your levels reached: 0."
    assert lines[2] == "Prices refreshed this run. Last bar for every holding is 2026-10-09."
    assert lines[3] == wording.UNITS_LINE
    assert lines[4] == wording.HEADER_SENTENCE


def test_a_provisional_run_puts_the_warning_second():
    lines = _brief([_report(provisional=True)], now=BEFORE_CLOSE)

    assert lines[1] == wording.PROVISIONAL_WARNING
    assert lines[2].startswith("Re-read triggers this run")
    assert lines[3].startswith("Prices refreshed")


def test_the_provisional_mark_is_in_the_position_close_line():
    text = _text(_brief([_report(provisional=True)], now=BEFORE_CLOSE))

    assert "Close 42.90 (2026-10-09, provisional)" in text


def test_a_run_after_the_close_shows_neither_warning_nor_mark():
    text = _text(_brief([_report(provisional=False)]))

    assert "provisional" not in text.lower().replace("(that range was issued from a provisional bar)", "")


def test_the_week_sentence_marks_a_provisional_issue():
    week = make_week(prior_provisional=True)

    assert wording.PROVISIONAL_ISSUE_NOTE in _text(_brief([_report(week=week)]))


def test_the_title_has_no_weekday_period():
    title = _brief([_report()])[0]

    assert not re.search(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)", title)


def test_the_brief_ends_with_the_footer_and_the_disclaimer_last():
    lines = _brief([_report()])

    assert lines[-1] == wording.BRIEF_DISCLAIMER and lines[-2] == wording.FOOTER


def test_no_announcement_dividend_company_or_net_line_exists_for_facts_without_a_feed_state():
    """`add-dividend-and-ex-date-lines` adds the DIVIDENDS block only for facts that carry a feed state (see
    `test_brief_sections_dividends.py`), and `add-announcement-tags-and-insider-sizing` the COMPANY block only for facts that
    carry announcements; these facts carry neither, so the brief has no block of either kind. The footer, which now names
    registered trades, is the one line allowed to say so."""
    lines = _brief([_report(), _report("BBB")])
    body = _text([line for line in lines if line != wording.FOOTER])

    assert not re.search(r"announcement|insider|net line", body, re.I)
    assert not re.search(r"^(DIVIDENDS|COMPANY)\b", body, re.M)


# --- the triggers line ------------------------------------------------------------------------------

def _level(comparator, price):
    return make_level(comparator, price, date(2026, 10, 2), "own words")


def test_the_count_is_across_holdings_reached_only():
    reports = [
        _report("AAA", close=40.0, levels=(_level("below", 41.0),)),  # reached
        _report("BBB", close=40.0, levels=(_level("below", 41.0),)),  # reached
        _report("CCC", close=40.0, levels=(_level("below", 30.0),)),  # not reached
    ]

    assert _brief(reports)[1] == "Re-read triggers this run: your levels reached: 2."


def test_none_set_counts_zero():
    assert _brief([_report(), _report("BBB")])[1] == "Re-read triggers this run: your levels reached: 0."


def test_levels_that_could_not_be_checked_are_counted_with_the_reason():
    reports = [
        _report("AAA", levels=(_level("below", 41.0),)),
        _report("BBB", close=None, last_bar=None, status="no_prices", levels=(_level("below", 1.0), _level("above", 2.0))),
    ]

    line = _brief(reports)[1]

    assert line == (
        "Re-read triggers this run: your levels reached: 0 (2 levels could not be checked: no stored close)."
    )
    assert wording.TRIGGERS_FORMAT.match(line)


def test_the_count_comes_from_the_checks_not_from_the_rendered_text(monkeypatch):
    monkeypatch.setattr(sections_holding, "levels_lines", lambda checks, close: ("REACHED. REACHED. REACHED.",))
    reports = [_report(close=40.0, levels=(_level("below", 41.0),))]

    assert _brief(reports)[1].endswith("your levels reached: 1.")


def test_a_later_change_adds_a_count_by_appending_to_the_registry():
    def insider_counter(reports):
        return TriggerCount("registered insider trades", 3)

    lines = _brief([_report()], trigger_counters=compose.TRIGGER_COUNTERS + (insider_counter,))

    assert lines[1] == "Re-read triggers this run: your levels reached: 0; registered insider trades: 3."


def test_the_registry_holds_the_levels_counter_first():
    assert compose.TRIGGER_COUNTERS[0] is compose.level_trigger_count


# --- the section list ------------------------------------------------------------------------------

def test_a_dummy_section_is_added_without_touching_any_other_section():
    def dummy(report, redact):
        return (f"DUMMY {report.facts.ticker} redact={redact}",)

    full = _brief([_report()], sections=TICKER_SECTIONS + (dummy,))
    redacted = _brief([_report()], redact=True, sections=TICKER_SECTIONS + (dummy,))

    assert "DUMMY AAA redact=False" in full and "DUMMY AAA redact=True" in redacted
    at = full.index("DUMMY AAA redact=False")
    assert full[at - 1] == "" and full[:at - 1] + full[at + 1:] == _brief([_report()])  # a blank line and the dummy


def test_the_default_order_of_the_ticker_sections():
    lines = _brief([_report(levels=(_level("below", 41.0),))])

    positions = [
        next(i for i, line in enumerate(lines) if line.startswith(marker))
        for marker in ("--- AAA", "Close 42.90", "THE WEEK JUST ENDED", "NEXT 5 TRADING DAYS", "YOUR LEVELS")
    ]
    assert positions == sorted(positions)


def test_holdings_listed_appears_only_with_two_holdings():
    assert not any(l.startswith("HOLDINGS LISTED") for l in _brief([_report()]))
    two = _brief([_report("AAA"), _report("BBB")])
    assert any(l.startswith("HOLDINGS LISTED (2)") for l in two)


def test_the_footer_names_a_registered_trade_a_share_issue_and_the_investors_levels():
    assert wording.FOOTER == _brief([_report()])[-2]
    assert wording.FOOTER == (
        "These would make a re-read worthwhile: a registered sale or purchase by a major shareholder or insider, a share issue "
        "or capital change, or one of your levels appearing or being reached. Other new announcements are listed for "
        "information. Re-run this brief to refresh."
    )
    assert not re.search(r"\b(buy|sell|hold)\b", wording.FOOTER, re.I)


def test_staleness_across_the_holdings_is_set_by_the_brief():
    reports = [_report("AAA"), _report("BBB", last_bar="2026-10-07")]

    text = _text(_brief(reports))

    assert "WARNING: last bar 2026-10-07 is behind the other holdings'" in text


# --- the redacted path -----------------------------------------------------------------------------

def _redacted(reports, **kwargs):
    return _brief(reports, redact=True, **kwargs)


def test_the_redacted_copy_has_its_notice_and_ticker_only_headers():
    lines = _redacted([_report(levels=(_level("below", 41.0),))])

    assert wording.REDACTED_NOTICE in lines
    assert "--- AAA ---" in lines
    assert not any("shares" in l and "cost" in l for l in lines)


def test_the_redacted_copy_has_no_triggers_line_and_no_holdings_block():
    lines = _redacted([_report("AAA", close=40.0, levels=(_level("below", 41.0),)), _report("BBB")])

    text = _text(lines)
    assert "Re-read triggers" not in text and "HOLDINGS LISTED" not in text and "levels reached" not in text


def test_the_redacted_levels_line_is_the_same_with_and_without_levels():
    lines = _redacted([_report("AAA", levels=(_level("below", 41.0),)), _report("BBB")])

    levels_lines = [l for l in lines if l.startswith("YOUR LEVELS")]
    assert levels_lines == [f"YOUR LEVELS: {wording.REDACTED_LEVELS_LINE}"] * 2


def test_the_redacted_copy_keeps_the_provisional_warning_and_mark():
    lines = _redacted([_report(provisional=True)], now=BEFORE_CLOSE)

    assert wording.PROVISIONAL_WARNING == lines[1]
    assert "Close 42.90 (2026-10-09, provisional)" in lines


def test_redacted_output_for_a_ticker_is_identical_with_and_without_levels():
    with_levels = _redacted([_report(levels=(_level("below", 41.0), _level("above", 50.0)))])
    without = _redacted([_report()])

    assert with_levels == without


def test_the_redacted_path_never_calls_the_holding_sections(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a holdings section ran in the redacted copy")

    for name in ("ticker_header", "position_lines", "range_amount_lines", "readjusted_levels_lines", "levels_lines", "holdings_listed_lines"):
        monkeypatch.setattr(sections_holding, name, boom)

    assert _redacted([_report(levels=(_level("below", 41.0),)), _report("BBB")])  # does not raise


def test_the_redacted_copy_keeps_the_disclaimer_and_footer():
    lines = _redacted([_report()])

    assert lines[-1] == wording.BRIEF_DISCLAIMER and lines[-2] == wording.FOOTER


# --- the section order does not depend on an index --------------------------------------------------------

def test_a_section_marked_joins_next_sits_directly_above_the_next_one():
    @compose.joins_next
    def banner(report, redact):
        return ("BANNER",)

    def after(report, redact):
        return ("AFTER",)

    lines = _brief([_report()], sections=(banner, after))

    at = lines.index("BANNER")
    assert lines[at + 1] == "AFTER" and lines[at - 1] == ""


def test_a_section_that_returns_nothing_leaves_no_stray_blank_line():
    def nothing(report, redact):
        return ()

    with_empty = _brief([_report()], sections=(nothing, *TICKER_SECTIONS, nothing))

    assert with_empty == _brief([_report()])


def test_the_header_still_joins_the_next_section_when_sections_are_reordered():
    lines = _brief([_report()], sections=(TICKER_SECTIONS[0], TICKER_SECTIONS[2]))

    at = next(i for i, l in enumerate(lines) if l.startswith("--- AAA"))
    assert lines[at + 1].startswith("THE WEEK JUST ENDED")


# --- redaction omits everything read from the log -------------------------------------------------------

@pytest.mark.parametrize(
    "week",
    [
        make_week(kind="first", band_pct=None, band_lo=None, band_hi=None, inside=None),
        make_week(kind="no_match", latest_on_file="2026-09-25", band_pct=None, band_lo=None, band_hi=None, inside=None),
        make_week(kind="no_band", prior_status="ineligible", band_pct=None, band_lo=None, band_hi=None, inside=None),
        make_week(prior_provisional=True),
    ],
    ids=["first", "no_match", "no_band", "band"],
)
def test_the_redacted_copy_has_no_log_derived_week_text(week):
    redacted = _text(_redacted([_report(week=week)]))
    full = _text(_brief([_report(week=week)]))

    for fragment in ("first brief", "Last week's range", "no range was issued", "last week's brief gave no range", "issued from a provisional"):
        assert fragment not in redacted
    assert "THE WEEK JUST ENDED" in redacted and "Move:" in redacted  # the market part stays
    assert wording.WEEK_COMPARE_LIMIT not in redacted and wording.WEEK_COMPARE_LIMIT in full


# --- fail-closed behaviours ------------------------------------------------------------------------------

def test_a_failing_holding_prints_a_visible_block_and_the_others_are_built(monkeypatch):
    real = compose.market_sections.next_five_lines

    def selective(facts):
        if facts.ticker == "BBB":
            raise ZeroDivisionError("boom")
        return real(facts)

    monkeypatch.setattr(compose.market_sections, "next_five_lines", selective)

    text = _text(_brief([_report("AAA"), _report("BBB"), _report("CCC")]))

    assert "could not build this holding: ZeroDivisionError" in text
    assert text.count("NEXT 5 TRADING DAYS") == 2 and "--- CCC " in text


def test_a_model_at_another_coverage_fails_closed_for_any_caller():
    from app.services.brief.wording import DisclaimerCoverageMismatch

    with pytest.raises(DisclaimerCoverageMismatch):
        _brief([_report(range_coverage=0.80)])


def test_a_model_object_at_another_coverage_fails_closed(monkeypatch):
    from types import SimpleNamespace

    from app.services.brief.wording import DisclaimerCoverageMismatch

    with pytest.raises(DisclaimerCoverageMismatch):
        _brief([_report(model=SimpleNamespace(range_coverage=0.8))])


def test_a_transaction_word_in_tool_text_fails_closed_naming_only_the_line(monkeypatch):
    monkeypatch.setattr(wording, "FOOTER", "Please sell now.")

    with pytest.raises(compose.BriefTextGuardError) as caught:
        _brief([_report()])

    assert "line" in str(caught.value) and "sell" not in str(caught.value).lower()


@pytest.mark.parametrize("word", ["Confidence", "Market Sentiment", "ｂｕｙ", "ho\u200bld"])
def test_the_final_scan_sees_lookalikes(monkeypatch, word):
    monkeypatch.setattr(wording, "UNITS_LINE", f"Prices are per share; {word}.")

    with pytest.raises(compose.BriefTextGuardError):
        _brief([_report()])


def test_the_investors_own_words_pass_the_final_scan():
    level = make_level("below", 41.0, date(2026, 10, 2), "Sell 300 if it falls; buy back and hold")

    lines = _brief([_report(close=40.0, levels=(level,))])

    assert any("Sell 300 if it falls; buy back and hold" in l for l in lines)


def test_a_judgement_word_in_the_triggers_line_fails_closed():
    def bad_counter(reports):
        return TriggerCount("needs attention", 1)

    with pytest.raises(ValueError, match="judgement"):
        _brief([_report()], trigger_counters=(bad_counter,))
