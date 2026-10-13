"""The re-read triggers line with the announcement counts appended (`add-announcement-tags-and-insider-sizing`,
"The re-read triggers line carries the announcement counts as further entries"). The base line's own format, banned-word
check and judgement list are run over it unchanged."""

from __future__ import annotations

import re

import pytest

from app.services.brief import wording
from app.services.brief import wording_company as wc
from app.services.brief.compose import TRIGGER_COUNTERS, TickerReport, build_brief
from app.services.brief.feed_source import IssueClass
from app.services.brief.wording import TriggerCount, TRIGGERS_FORMAT, judgement_words_in

from .brief_announcement_rows import health, make_company, make_issue_item, make_trade_item
from .test_brief_support import brief_isolation, ict, make_facts, make_holding, make_level  # noqa: F401

NOW = ict("2026-10-09 16:30")
BASE = "Re-read triggers this run: your levels reached: 0"
TRADES = wc.TRIGGER_TRADES_LABEL
ISSUES = wc.TRIGGER_ISSUES_LABEL


def _report(ticker="AAA", items=(), **company):
    return TickerReport(make_holding(ticker), make_facts(ticker, company=make_company(items, **company)))


def _line(*reports, redact=False) -> str:
    lines = build_brief(tuple(reports), redact=redact, now=NOW)
    return next((l for l in lines if l.startswith(wording.TRIGGERS_PREFIX)), "")


def test_one_registered_trade_and_no_capital_change_and_no_level_reached():
    line = _line(_report(items=[make_trade_item("AAA", published="2026-10-08")]))

    assert line == f"{BASE}; {TRADES}: 1; {ISSUES}: 0."
    assert line == (
        "Re-read triggers this run: your levels reached: 0; registered sales or purchases by a major shareholder or "
        "insider since the last brief: 1; share issues or capital changes since the last brief: 0."
    )


def test_both_counts_are_printed_at_zero():
    assert _line(_report()) == f"{BASE}; {TRADES}: 0; {ISSUES}: 0."


def test_counts_run_across_all_holdings():
    line = _line(
        _report("AAA", [make_trade_item("AAA"), make_trade_item("AAA", name="Fictional Two Ltd")]),
        _report("BBB", [make_trade_item("BBB"), make_issue_item(IssueClass.BONUS, 0.1, ex="2026-10-20")]),
    )

    assert f"{TRADES}: 3; {ISSUES}: 1" in line


def test_a_trade_listed_again_only_for_its_open_window_is_not_counted():
    reopened = make_trade_item("AAA", published="2026-09-28", start="2026-10-01", end="2026-10-20")

    assert f"{TRADES}: 0" in _line(_report(items=[reopened]))


def test_small_issues_and_additional_listings_are_not_counted():
    items = [
        make_issue_item(IssueClass.EMPLOYEE, 0.002), make_issue_item(IssueClass.BONUS, 0.004),
        make_issue_item(IssueClass.OTHER, None, code="AIS"),
    ]

    assert f"{ISSUES}: 0" in _line(_report(items=items))


def test_a_trade_that_is_not_new_is_not_counted_even_when_it_is_not_relisted():
    assert f"{TRADES}: 0" in _line(_report(items=[make_trade_item("AAA", published="2026-09-10", start="2026-09-11", end="2026-09-20")]))


def test_one_of_two_holdings_not_checked_adds_a_last_entry_and_no_parenthetical():
    line = _line(_report("AAA"), _report("BBB", news=health("never_fetched"), events=health("never_fetched")))

    assert line.endswith(f"{ISSUES}: 0; {wc.TRIGGER_UNCHECKED_LABEL}: 1.") and "(" not in line


def test_all_checked_has_no_not_checked_entry():
    assert wc.TRIGGER_UNCHECKED_LABEL not in _line(_report("AAA"), _report("BBB"))


def test_a_holding_with_only_one_kind_fetched_counts_as_checked():
    assert wc.TRIGGER_UNCHECKED_LABEL not in _line(_report("AAA", news=health("never_fetched")))


def test_the_base_entry_comes_first_and_keeps_its_own_unchecked_levels_note():
    holding = make_holding("AAA", levels=(make_level("below", 40.0),))
    report = TickerReport(holding, make_facts("AAA", close=None, last_bar=None, status="no_prices", week=None, band_pct=None, band_lo=None, band_hi=None, range_coverage=None, calibrated=None))

    line = _line(report)

    assert line == "Re-read triggers this run: your levels reached: 0 (1 level could not be checked: no stored close)."  # no announcement facts: no entries


def test_the_rendered_line_matches_the_base_pattern_and_has_none_of_the_banned_words():
    for reports in (
        (_report(items=[make_trade_item("AAA")]),),
        (_report("AAA"), _report("BBB", news=health("never_fetched"), events=health("never_fetched"))),
    ):
        line = _line(*reports)

        assert TRIGGERS_FORMAT.match(line) and judgement_words_in(line) == []
        assert not re.search(r"\b(buy|sell|hold)\b", line, re.I)


@pytest.mark.parametrize("label", [wc.TRIGGER_TRADES_LABEL, wc.TRIGGER_ISSUES_LABEL, wc.TRIGGER_UNCHECKED_LABEL])
def test_each_label_passes_the_base_checks_run_over_it(label):
    """The base line's own label format and whole-word, case-insensitive banned-word check, so a later change to
    its list (recommend, consider, ...) is picked up without editing this test."""
    TriggerCount(label, 0)  # the label format is validated by the base dataclass
    assert re.fullmatch(r"[a-z' -]+", label) and judgement_words_in(label) == []
    assert wording.triggers_line((TriggerCount(label, 3),)).endswith(f"{label}: 3.")
    assert not re.search(r"\b(buy|sell|hold)\b", label, re.I)


def test_the_judgement_check_would_catch_a_banned_word_in_a_label():
    assert judgement_words_in("registered sales you should act on") == ["should", "act"]


def test_the_redacted_copy_has_no_triggers_line_and_no_announcement_count():
    reports = (_report(items=[make_trade_item("AAA")]),)

    text = "\n".join(build_brief(reports, redact=True, now=NOW))

    assert "Re-read triggers" not in text and TRADES not in text and ISSUES not in text


def test_the_counters_registry_has_the_base_counter_first_and_ends_with_the_optional_one():
    assert TRIGGER_COUNTERS[0].__name__ == "level_trigger_count"
    assert [c.__name__ for c in TRIGGER_COUNTERS[1:]] == ["trades_trigger_count", "issues_trigger_count", "unchecked_trigger_count"]


def test_a_counter_returning_none_is_skipped_and_the_others_still_print():
    lines = build_brief((_report(),), redact=False, now=NOW, trigger_counters=(TRIGGER_COUNTERS[0], lambda reports: None))

    assert next(l for l in lines if l.startswith(wording.TRIGGERS_PREFIX)) == f"{BASE}."


# --- review fixes (2026-10-12): a 0 must not read as "none" when the events were not looked at -----------------------------

def test_a_holding_whose_events_were_never_fetched_counts_as_not_checked_even_if_its_news_were_fetched():
    line = _line(_report("AAA"), _report("BBB", events=health("never_fetched")))

    assert line.endswith(f"{wc.TRIGGER_UNCHECKED_LABEL}: 1.")


def test_a_holding_with_no_announcement_facts_counts_as_not_checked_while_another_holding_was_read():
    no_bar = TickerReport(make_holding("BBB"), make_facts("BBB", last_bar=None, close=None, status="no_prices", week=None, band_pct=None, band_lo=None, band_hi=None, range_coverage=None, calibrated=None))

    line = _line(_report("AAA"), no_bar)

    assert line.endswith(f"{wc.TRIGGER_UNCHECKED_LABEL}: 1.")


def test_no_announcement_entries_at_all_when_no_holding_was_read():
    assert wc.TRIGGER_UNCHECKED_LABEL not in _line(TickerReport(make_holding("AAA"), make_facts("AAA")))
