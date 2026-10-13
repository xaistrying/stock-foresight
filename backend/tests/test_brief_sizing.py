"""The size line's withhold rule and the benchmark (`add-announcement-tags-and-insider-sizing`, "A size is shown only when
the share count is safe ..." and "The size carries a benchmark with its stated basis, or none")."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.brief import sizing
from app.services.brief.feed_source import Event, IssueClass
from app.services.brief.insider import parse_trade
from app.services.brief.share_cache import ShareCount
from app.services.brief.sizing import (
    BENCHMARK_MIN_RECORDS, CHANGING, DISAGREE, MODE_DISAGREE, MODE_OFF, MODE_OK, MODE_UNAVAILABLE, NO_QUANTITY, OFF, SETTLING_DAYS,
    SHOWN, UNAVAILABLE, SizingInput, changing_issue_date, fmt_percent, size_for,
)

from .brief_announcement_rows import d, make_trade_item
from .test_brief_support import brief_isolation  # noqa: F401

RUN = d("2026-10-12")
COUNT = 1_282_562_372


def _count(fetched: str = "2026-10-12", *, count: int = COUNT) -> ShareCount:
    return ShareCount(count, 2026, 2, datetime.fromisoformat(fetched + "T05:00:00").replace(tzinfo=timezone.utc))


def _ok(fetched: str = "2026-10-12", *, count: int = COUNT) -> SizingInput:
    return SizingInput(MODE_OK, _count(fetched, count=count))


def _issue(issue_class, ratio, *, ex=None, record=None, published="2026-09-01") -> Event:
    return Event("ISS", d(ex) if ex else None, d(record) if record else None, None, None, ratio, d(published), issue_class)


def _trade(qty="30,000,000", *, act="Sell", published="2026-10-08", name="Fictional Capital Ltd"):
    return parse_trade(make_trade_item("AAA", name=name, act=act, qty=qty, published=published), "AAA", RUN)


def _size(trade, sizing_input, events=(), history=()):
    return size_for(trade, sizing_input, tuple(events), RUN, tuple(history) or (trade,))


# --- the size -----------------------------------------------------------------------------------------

def test_a_sized_registration_shows_two_significant_figures_with_the_count():
    got = _size(_trade("30,000,000"), _ok())

    assert got.state == SHOWN and fmt_percent(got.percent) == "2.3" and got.count.count == COUNT


@pytest.mark.parametrize(("value", "text"), [(2.339, "2.3"), (0.0164, "0.016"), (150.0, "150"), (12.0, "12"), (0.000016, "0.000016"), (100.0, "100"), (9.96, "10")])
def test_percent_has_at_most_two_significant_figures_and_no_exponent(value, text):
    assert fmt_percent(value) == text


def test_no_quantity_gives_no_size_whatever_the_count():
    assert _size(_trade(None), _ok()).state == NO_QUANTITY


def test_sizing_off_and_an_unavailable_count_give_their_own_states():
    assert _size(_trade(), SizingInput(MODE_OFF)).state == OFF
    assert _size(_trade(), SizingInput(MODE_UNAVAILABLE)).state == UNAVAILABLE


# --- the withhold rule ----------------------------------------------------------------------------------

def test_a_stock_dividend_inside_the_settling_window_withholds_even_when_the_counts_agree():
    stock = _issue(IssueClass.STOCK_DIVIDEND, 0.26, ex="2026-09-24")  # 18 days before the run

    got = _size(_trade(), _ok(), [stock])

    assert got.state == CHANGING and got.issue_on == d("2026-09-24") and got.percent is None and got.benchmark is None


def test_the_same_issue_31_days_before_with_a_later_cached_fetch_is_shown():
    stock = _issue(IssueClass.STOCK_DIVIDEND, 0.26, ex="2026-09-11")

    assert _size(_trade(), _ok("2026-09-12"), [stock]).state == SHOWN
    assert d("2026-09-11") < RUN - timedelta(days=SETTLING_DAYS)


def test_the_settling_window_is_thirty_days_and_inclusive_of_the_thirtieth_day():
    assert SETTLING_DAYS == 30
    assert changing_issue_date([_issue(IssueClass.BONUS, 0.5, ex="2026-09-12")], d("2026-10-12"), RUN) == d("2026-09-12")  # 30 days
    assert changing_issue_date([_issue(IssueClass.BONUS, 0.5, ex="2026-09-11")], d("2026-10-12"), RUN) is None  # 31 days


def test_a_bonus_after_the_cached_fetch_withholds():
    bonus = _issue(IssueClass.BONUS, 0.128, ex="2026-10-10")  # the cache is 4 days old: fetched 2026-10-08

    got = _size(_trade(), _ok("2026-10-08"), [bonus])

    assert got.state == CHANGING and got.issue_on == d("2026-10-10")


def test_a_future_ex_date_counts_as_after_the_fetch():
    assert _size(_trade(), _ok(), [_issue(IssueClass.BONUS, 0.1, ex="2026-11-20")]).state == CHANGING


def test_an_old_issue_before_the_cached_fetch_and_outside_the_window_does_not_withhold():
    assert _size(_trade(), _ok("2026-10-01"), [_issue(IssueClass.BONUS, 0.5, ex="2026-08-01")]).state == SHOWN


def test_an_employee_issue_of_point_four_percent_is_ignored():
    employee = _issue(IssueClass.EMPLOYEE, 0.004, ex="2026-10-07")  # 5 days before the run

    assert _size(_trade(), _ok(), [employee]).state == SHOWN


def test_an_employee_issue_with_a_missing_or_zero_ratio_is_ignored_but_not_a_placement():
    assert _size(_trade(), _ok(), [_issue(IssueClass.EMPLOYEE, None, ex="2026-10-07"), _issue(IssueClass.EMPLOYEE, 0.0, ex="2026-10-07")]).state == SHOWN
    assert _size(_trade(), _ok(), [_issue(IssueClass.OTHER, None, ex="2026-10-07")]).state == CHANGING


def test_a_private_placement_of_six_percent_with_no_ex_date_names_the_publication_date():
    placement = _issue(IssueClass.PRIVATE_PLACEMENT, 0.06, published="2026-10-02")  # 10 days before

    got = _size(_trade(), _ok(), [placement])

    assert got.state == CHANGING and got.issue_on == d("2026-10-02")


def test_a_placement_stored_with_ratio_zero_has_an_unknown_size_and_withholds():
    assert _size(_trade(), _ok(), [_issue(IssueClass.PRIVATE_PLACEMENT, 0.0, ex="2026-10-02")]).state == CHANGING


def test_a_rights_offer_of_twenty_percent_withholds():
    assert _size(_trade(), _ok(), [_issue(IssueClass.RIGHTS_OFFER, 0.2, ex="2026-10-08")]).state == CHANGING


def test_a_small_non_employee_issue_does_not_withhold():
    assert _size(_trade(), _ok(), [_issue(IssueClass.BONUS, 0.004, ex="2026-10-08")]).state == SHOWN


def test_the_record_date_then_the_publication_date_stand_in_for_a_missing_ex_date():
    on_record = _issue(IssueClass.PRIVATE_PLACEMENT, 0.06, record="2026-10-03", published="2025-01-01")

    assert _size(_trade(), _ok(), [on_record]).issue_on == d("2026-10-03")


def test_additional_listings_a_quarter_end_and_cash_dividends_do_not_withhold():
    listing = Event("AIS", None, None, None, None, None, d("2026-10-05"), None)
    cash = Event("DIV", d("2026-10-05"), None, None, 1000.0, None, d("2026-09-20"), None)

    assert _size(_trade(), _ok(), [listing, cash]).state == SHOWN


def test_disagreeing_counts_with_no_issue_say_so():
    assert _size(_trade(), SizingInput(MODE_DISAGREE)).state == DISAGREE


def test_disagreeing_counts_with_an_issue_in_the_window_name_the_issue():
    got = _size(_trade(), SizingInput(MODE_DISAGREE), [_issue(IssueClass.STOCK_DIVIDEND, 0.26, ex="2026-09-24")])

    assert got.state == CHANGING and got.issue_on == d("2026-09-24")


# --- the benchmark -----------------------------------------------------------------------------------------

def _history(current, quantities, *, act="Sell", year=2025):
    """Earlier trades of the same ticker, one per quantity, published on distinct days before `current`."""
    trades = [
        _trade(str(q), act=act, published=f"{year}-{1 + i % 12:02d}-{10 + i % 15:02d}", name=f"Fictional {i} Ltd")
        for i, q in enumerate(quantities)
    ]
    return trades


def test_the_benchmark_counts_larger_ones_against_the_count_at_their_own_date():
    count = 1_000_000_000
    current = _trade("30,000,000")  # 3.0%
    bonus = _issue(IssueClass.BONUS, 1.0, ex="2023-09-14")
    # one record before the 100% bonus: 25,000,000 shares against 500,000,000 then (5.0%), so larger than 3.0%
    old = parse_trade(make_trade_item("AAA", qty="25,000,000", published="2023-01-10", name="Fictional Old Ltd"), "AAA", RUN)
    others = _history(current, [10_000_000, 12_000_000, 8_000_000, 20_000_000, 5_000_000, 9_000_000, 11_000_000, 7_000_000, 6_000_000, 4_000_000, 3_000_000, 2_000_000, 1_000_000])
    history = (current, old, *others)

    got = size_for(current, SizingInput(MODE_OK, _count(count=count)), (bonus,), RUN, history)

    assert got.state == SHOWN and got.benchmark.shown and got.benchmark.compared == 14
    assert got.benchmark.larger == 1 and got.benchmark.first_year == 2023
    assert fmt_percent(got.benchmark.largest_other_pct) == "2" and BENCHMARK_MIN_RECORDS == 5


def test_a_none_larger_benchmark_gives_the_largest_overall():
    current = _trade("50,000,000")
    others = _history(current, [10_000_000, 9_000_000, 8_000_000, 7_000_000, 6_000_000])

    got = size_for(current, _ok(count=1_000_000_000), (), RUN, (current, *others))

    assert got.benchmark.larger == 0 and fmt_percent(got.benchmark.largest_other_pct) == "1"


def test_when_every_earlier_record_is_larger_there_is_no_largest_of_the_others():
    current = _trade("1,000,000")
    others = _history(current, [10_000_000] * 5)

    got = size_for(current, _ok(count=1_000_000_000), (), RUN, (current, *others))

    assert got.benchmark.larger == 5 and got.benchmark.largest_other_pct is None


def test_fewer_than_five_comparable_records_is_no_comparison():
    current = _trade()
    others = _history(current, [1_000_000, 2_000_000, 3_000_000])

    got = size_for(current, _ok(), (), RUN, (current, *others))

    assert got.benchmark == sizing.Benchmark(compared=3, shown=False)


def test_a_placement_truncates_the_history_to_the_records_after_it():
    current = _trade()
    placement = _issue(IssueClass.PRIVATE_PLACEMENT, 0.06, ex="2025-06-01")
    before = _history(current, [1_000_000] * 8, year=2024)
    after = [parse_trade(make_trade_item("AAA", qty="2,000,000", published="2025-08-15", name="Fictional After Ltd"), "AAA", RUN)]

    got = size_for(current, _ok(), (placement,), RUN, (current, *before, *after))

    assert not got.benchmark.shown and got.benchmark.compared == 1


def test_a_bonus_with_an_ex_date_does_not_truncate_but_one_without_does():
    current = _trade()
    records = _history(current, [1_000_000] * 6, year=2024)
    dated = _issue(IssueClass.BONUS, 0.5, ex="2024-12-31")
    undated = _issue(IssueClass.BONUS, 0.5, ex=None, published="2025-06-01")

    assert size_for(current, _ok(), (dated,), RUN, (current, *records)).benchmark.shown
    assert not size_for(current, _ok(), (undated,), RUN, (current, *records)).benchmark.shown


def test_small_employee_issues_are_ignored_by_the_period():
    current = _trade()
    records = _history(current, [1_000_000] * 6, year=2024)
    employee = _issue(IssueClass.EMPLOYEE, 0.003, ex="2025-03-01")

    assert size_for(current, _ok(), (employee,), RUN, (current, *records)).benchmark.shown


def test_the_current_record_is_not_in_its_own_comparison_set():
    current = _trade()
    others = _history(current, [1_000_000] * 5)

    with_current = size_for(current, _ok(), (), RUN, (current, *others)).benchmark
    without = size_for(current, _ok(), (), RUN, tuple(others)).benchmark

    assert with_current == without and with_current.compared == 5


def test_only_the_same_direction_published_earlier_and_stating_a_quantity_are_compared():
    current = _trade(published="2026-10-08")
    mix = [
        *_history(current, [1_000_000] * 5),  # the five that count
        *_history(current, [1_000_000] * 3, act="Buy"),  # the other direction
        parse_trade(make_trade_item("AAA", qty=None, published="2025-01-01", name="Fictional NoQty Ltd"), "AAA", RUN),  # no quantity
        parse_trade(make_trade_item("AAA", qty="1,000,000", published="2026-10-08", name="Fictional Same Day Ltd"), "AAA", RUN),  # same day, not earlier
        parse_trade(make_trade_item("AAA", qty="1,000,000", published="2026-10-09", name="Fictional Later Ltd"), "AAA", RUN),  # later
    ]

    assert size_for(current, _ok(), (), RUN, (current, *mix)).benchmark.compared == 5


def test_a_purchase_is_compared_with_purchases():
    current = _trade("30,000,000", act="Buy")
    sells = _history(current, [1_000_000] * 6)

    assert not size_for(current, _ok(), (), RUN, (current, *sells)).benchmark.shown


def test_no_size_means_no_benchmark():
    current = _trade()
    stock = _issue(IssueClass.STOCK_DIVIDEND, 0.26, ex="2026-09-24")

    assert size_for(current, _ok(), (stock,), RUN, (current, *_history(current, [1_000_000] * 8))).benchmark is None
    assert size_for(current, SizingInput(MODE_OFF), (), RUN, (current,)).benchmark is None


def test_same_day_duplicate_filers_are_all_kept_apart_by_identity():
    current = _trade(name="Fictional Current Ltd")
    twins = [
        parse_trade(make_trade_item("AAA", qty="1,000,000", published="2025-05-05", name=f"Fictional Twin {i} Ltd"), "AAA", RUN) for i in range(6)
    ]

    assert size_for(current, _ok(), (), RUN, (current, *twins)).benchmark.compared == 6
