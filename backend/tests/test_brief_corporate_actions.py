"""Pure rules over feed events: the dividend list, completeness, count-changing issues, pending and scheduled
events, the 7-calendar-day window and the shifted range (`weekly-holdings-brief`, `add-dividend-and-ex-date-lines`)."""

from __future__ import annotations

import ast
import math
from datetime import timedelta

import pytest

from app.services.brief import corporate_actions as ca
from app.services.brief.feed_source import Event, IssueClass, read_events

from .brief_event_rows import BONUS, STOCK_DIV, d, iss_row, load_feed
from .test_brief_support import brief_isolation  # noqa: F401

LAST_BAR = d("2026-10-09")


def event(code="DIV", ex=None, vnd=None, ratio=None, published=None, record=None, payout=None, klass=None) -> Event:
    return Event(
        event_code=code, exright_date=d(ex) if ex else None, record_date=d(record) if record else None,
        payout_date=d(payout) if payout else None, value_per_share=vnd, exercise_ratio=ratio,
        published_at=d(published) if published else None, issue_class=klass,
    )


def stored(ticker: str) -> tuple[Event, ...]:
    load_feed()
    return read_events(ticker).events


def issue(klass, ex, ratio, published="2026-01-01") -> Event:
    return event("ISS", ex=ex, ratio=ratio, published=published, klass=klass)


# --- the dividend list --------------------------------------------------------------------------------

def test_the_dividend_list_since_a_purchase_gives_the_three_stored_dividends():
    events = stored("SAB")

    listed = ca.dividends_since(events, d("2025-06-10"), LAST_BAR)

    assert [(e.value_per_share, e.exright_date.isoformat()) for e in listed] == [
        (3000.0, "2025-06-30"), (2000.0, "2026-01-12"), (3000.0, "2026-07-28"),
    ]


def test_a_purchase_on_the_ex_date_excludes_that_dividend():
    events = (event(ex="2026-07-28", vnd=3000.0),)

    assert ca.dividends_since(events, d("2026-07-28"), LAST_BAR) == ()
    assert len(ca.dividends_since(events, d("2026-07-27"), LAST_BAR)) == 1


def test_an_ex_date_after_the_last_bar_is_not_listed():
    assert ca.dividends_since((event(ex="2026-10-14", vnd=2000.0),), d("2025-01-01"), LAST_BAR) == ()


def test_a_repeated_dividend_is_listed_once_and_two_amounts_on_one_ex_date_stay_two():
    repeat = (event(ex="2026-07-28", vnd=3000.0, published="2026-05-08"), event(ex="2026-07-28", vnd=3000.0, published="2026-05-09"))
    distinct = (event(ex="2026-07-28", vnd=3000.0), event(ex="2026-07-28", vnd=500.0))

    assert len(ca.cash_dividends(repeat)) == 1
    assert len(ca.cash_dividends(distinct)) == 2


@pytest.mark.parametrize("vnd", [None, 0.0, -5.0, math.nan, math.inf])
def test_a_dividend_without_a_positive_finite_amount_or_an_ex_date_is_not_a_cash_dividend(vnd):
    assert ca.cash_dividends((event(ex="2026-07-28", vnd=vnd), event(ex=None, vnd=3000.0))) == ()


def test_only_the_div_code_is_a_cash_dividend():
    assert ca.cash_dividends((event("AGME", ex="2026-07-28", vnd=3000.0),)) == ()


# --- completeness -------------------------------------------------------------------------------------

def test_completeness_at_the_horizon():
    oldest = d("2022-07-19")

    on = ca.completeness(oldest, d("2022-11-16"))
    before = ca.completeness(oldest, d("2022-11-15"))

    assert on.complete and on.horizon == d("2022-11-16")
    assert not before.complete and before.horizon == d("2022-11-16") and before.oldest == oldest


def test_a_long_history_is_complete():
    assert ca.completeness(d("2017-05-15"), d("2025-06-10")).complete


def test_the_oldest_event_of_any_code_sets_the_horizon():
    vpb = stored("VPB")
    oldest = read_events("VPB").oldest_event_date

    assert oldest == d("2022-07-19")  # an issue, older than the oldest dividend (2023-10-20)
    assert min(e.published_at for e in ca.cash_dividends(vpb)) == d("2023-10-20")
    assert not ca.completeness(oldest, d("2022-11-15")).complete


def test_nothing_stored_is_never_complete():
    assert not ca.completeness(None, d("2025-06-10")).complete


def test_the_lag_constant_is_120_days():
    assert ca.MAX_LAG_DAYS == 120 and ca.WINDOW_CALENDAR_DAYS == 7 and ca.PENDING_ANNOUNCEMENT_DAYS == 365


# --- count-changing issues ----------------------------------------------------------------------------

def _all_issue_events() -> dict[str, tuple[Event, ...]]:
    load_feed()
    return {t: read_events(t).events for t in ("SAB", "VPB", "FPT", "KBC", "SSI", "VCB")}


def test_count_changing_issues_are_exactly_the_bonus_and_stock_dividend_rows_with_an_ex_date_and_a_ratio():
    by_ticker = _all_issue_events()

    found = {t: [(e.issue_class.name, e.exright_date.isoformat(), e.exercise_ratio) for e in ca.count_changing_issues(evs)] for t, evs in by_ticker.items()}

    assert found["SAB"] == [("BONUS", "2023-09-14", 1.0)]
    assert found["VPB"] == [("BONUS", "2022-09-28", 0.5), ("STOCK_DIVIDEND", "2026-09-24", 0.2604104)]
    assert found["FPT"] == [("BONUS", "2025-07-21", 0.15), ("BONUS", "2026-09-21", 0.1)]
    assert found["KBC"] == [] and found["SSI"] == [] and found["VCB"] == []  # placement, rights offer, undated bonuses


def test_the_employee_issue_with_an_ex_date_and_the_undated_placement_are_not_count_changing():
    fpt = _all_issue_events()["FPT"]

    assert any(e.issue_class is IssueClass.EMPLOYEE and e.exright_date for e in fpt)
    assert all(e.issue_class is not IssueClass.EMPLOYEE for e in ca.count_changing_issues(fpt))


@pytest.mark.parametrize("ratio", [None, 0.0, -0.1, math.nan])
def test_a_bonus_without_a_positive_ratio_is_not_count_changing(ratio):
    assert ca.count_changing_issues((issue(IssueClass.BONUS, "2026-09-21", ratio),)) == ()


def test_a_repeated_issue_is_returned_once():
    twice = (issue(IssueClass.BONUS, "2026-09-21", 0.1, "2026-08-01"), issue(IssueClass.BONUS, "2026-09-21", 0.1, "2026-08-02"))

    assert len(ca.count_changing_issues(twice)) == 1


def test_share_issues_between_gives_the_cumulative_factor():
    vpb = stored("VPB")

    result = ca.share_issues_between(vpb, d("2022-01-01"), LAST_BAR)

    assert len(result.issues) == 2
    assert result.factor == pytest.approx(1.5 * 1.2604104)


def test_share_issues_between_respects_both_bounds_and_an_empty_range_has_factor_one():
    vpb = stored("VPB")

    only_last = ca.share_issues_between(vpb, d("2022-09-28"), LAST_BAR)
    none = ca.share_issues_between(vpb, d("2026-09-24"), LAST_BAR)

    assert [e.exright_date.isoformat() for e in only_last.issues] == ["2026-09-24"]
    assert none.issues == () and none.factor == 1.0


def test_the_helper_documents_that_its_factor_is_calculated_and_must_be_labelled():
    assert "calculated, check with your broker" in ca.share_issues_between.__doc__


# --- pending announcements and rights offers ------------------------------------------------------------

def test_a_recent_undated_bonus_is_pending_and_older_ones_are_counted_not_shown():
    vcb = _all_issue_events()["VCB"]

    pending = ca.pending_issues(vcb, LAST_BAR)

    assert [(e.published_at.isoformat(), e.exercise_ratio) for e in pending] == [("2026-04-28", 0.1279)]
    assert ca.older_undated_count(vcb, LAST_BAR) == 2
    assert ca.count_changing_issues(vcb) == ()


def test_pending_and_older_boundaries_at_365_days():
    on = issue(IssueClass.BONUS, None, 0.1, published=(LAST_BAR - timedelta(days=365)).isoformat())
    past = issue(IssueClass.BONUS, None, 0.1, published=(LAST_BAR - timedelta(days=366)).isoformat())

    assert ca.pending_issues((on, past), LAST_BAR) == (on,)
    assert ca.older_undated_count((on, past), LAST_BAR) == 1


def test_an_undated_bonus_with_no_announcement_date_is_counted_as_older_not_dropped():
    no_date = issue(IssueClass.BONUS, None, 0.1, published=None)

    assert ca.older_undated_count((no_date,), LAST_BAR) == 1 and ca.pending_issues((no_date,), LAST_BAR) == ()


def test_nothing_older_counts_zero():
    assert ca.older_undated_count((issue(IssueClass.BONUS, None, 0.1, "2026-04-28"),), LAST_BAR) == 0


def test_a_row_with_an_ex_date_is_never_pending_or_counted_as_older():
    dated = (issue(IssueClass.BONUS, "2026-11-02", 0.1, "2019-04-26"),)

    assert ca.pending_issues(dated, LAST_BAR) == () and ca.older_undated_count(dated, LAST_BAR) == 0


def test_a_bonus_that_later_gained_an_ex_date_is_a_dated_issue_not_pending():
    load_feed({"VCB": [iss_row("VCB", BONUS, 2, published="2019-04-26", ex=None, ratio=0.5)]})
    load_feed({"VCB": [iss_row("VCB", BONUS, 2, published="2019-04-26", ex="2019-06-03", ratio=0.5)]})

    events = read_events("VCB").events

    assert len(events) == 1 and ca.older_undated_count(events, LAST_BAR) == 0
    assert len(ca.count_changing_issues(events)) == 1


def test_a_stock_dividend_without_an_ex_date_is_pending_like_a_bonus():
    pending = ca.pending_issues((issue(IssueClass.STOCK_DIVIDEND, None, 0.2, "2026-06-01"),), LAST_BAR)

    assert len(pending) == 1


def test_a_rights_offer_is_listed_between_dates_scheduled_and_in_the_window_but_never_in_the_factor():
    ssi = _all_issue_events()["SSI"]

    since = ca.rights_offers_between(ssi, d("2025-11-01"), LAST_BAR)
    after = ca.rights_offers_between(ssi, d("2025-12-08"), LAST_BAR)
    assert [e.exright_date.isoformat() for e in since] == ["2025-12-08"] and after == ()
    assert ca.share_issues_between(ssi, d("2025-01-01"), LAST_BAR).factor == 1.0

    offer = issue(IssueClass.RIGHTS_OFFER, "2026-10-14", 0.2)
    assert ca.scheduled_events((offer,), LAST_BAR) == (offer,)
    assert ca.events_in_window((offer,), LAST_BAR) == (offer,)


# --- the window ----------------------------------------------------------------------------------------

@pytest.mark.parametrize(("ex", "inside"), [("2026-10-09", False), ("2026-10-10", True), ("2026-10-16", True), ("2026-10-17", False)])
def test_window_membership_at_7_and_8_calendar_days(ex, inside):
    found = ca.events_in_window((event(ex=ex, vnd=2000.0),), LAST_BAR)

    assert bool(found) is inside


def test_an_ex_date_just_beyond_the_window_is_scheduled_with_its_exact_date():
    beyond = event(ex="2026-10-18", vnd=2000.0)  # 9 calendar days

    assert ca.events_in_window((beyond,), LAST_BAR) == () and ca.scheduled_events((beyond,), LAST_BAR) == (beyond,)


def test_the_window_holds_dividends_count_changing_issues_and_rights_offers_only():
    bonus = issue(IssueClass.BONUS, "2026-10-14", 0.1)
    placement = issue(IssueClass.PRIVATE_PLACEMENT, "2026-10-14", 0.3)
    undated = issue(IssueClass.BONUS, None, 0.1)

    assert ca.events_in_window((bonus, placement, undated), LAST_BAR) == (bonus,)


def test_scheduled_events_are_everything_dated_after_the_last_bar_ascending():
    later, sooner = event(ex="2026-12-01", vnd=1000.0), event(ex="2026-10-14", vnd=2000.0, record="2026-10-15")

    assert ca.scheduled_events((later, sooner, event(ex="2026-10-09", vnd=3000.0)), LAST_BAR) == (sooner, later)


# --- the shifted range ---------------------------------------------------------------------------------

def test_the_range_shifts_down_by_the_dividend_in_thousand_vnd():
    assert ca.shifted_range(45.69, 48.30, 3000.0) == (42.69, 45.30)
    assert ca.shifted_range(41.74, 44.06, 2000.0) == (39.74, 42.06)


def test_a_shift_that_reaches_zero_is_not_shown():
    assert ca.shifted_range(2.5, 3.5, 3000.0) is None


def test_the_window_range_is_shifted_only_for_exactly_one_cash_dividend():
    one = (event(ex="2026-10-14", vnd=2000.0),)
    two = (*one, event(ex="2026-10-15", vnd=500.0))
    mixed = (*one, issue(IssueClass.BONUS, "2026-10-15", 0.1))

    assert ca.window_range(41.74, 44.06, one) == (39.74, 42.06)
    assert ca.window_range(41.74, 44.06, two) is None and ca.window_range(41.74, 44.06, mixed) is None
    assert ca.window_range(41.74, 44.06, ()) is None


# --- events between two dates (level notes, the week, the re-adjusted note) -------------------------------

def test_events_between_are_dividends_and_count_changing_issues_after_the_first_date_up_to_the_last():
    events = (
        event(ex="2026-07-28", vnd=3000.0), issue(IssueClass.BONUS, "2026-09-21", 0.1),
        issue(IssueClass.RIGHTS_OFFER, "2026-09-22", 0.2), issue(IssueClass.EMPLOYEE, "2026-09-23", 0.01),
    )

    assert [e.exright_date.isoformat() for e in ca.events_between(events, d("2026-07-15"), LAST_BAR)] == ["2026-07-28", "2026-09-21"]


@pytest.mark.parametrize(("entered", "expected"), [("2026-07-27", 1), ("2026-07-28", 0), ("2026-08-01", 0)])
def test_a_level_entered_before_on_and_after_the_ex_date(entered, expected):
    events = (event(ex="2026-07-28", vnd=3000.0),)

    assert len(ca.events_between(events, d(entered), LAST_BAR)) == expected


# --- structure ---------------------------------------------------------------------------------------------

def test_the_module_imports_the_feed_adapter_only_for_type_checking():
    import app.services.brief.corporate_actions as module

    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    top_level = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]

    assert not any("feed_source" in (getattr(n, "module", "") or "") for n in top_level)
    assert "TYPE_CHECKING" in open(module.__file__, encoding="utf-8").read()


def test_nothing_is_mutated():
    events = (event(ex="2026-07-28", vnd=3000.0), event(ex="2026-01-12", vnd=2000.0))
    before = tuple(events)

    ca.cash_dividends(events), ca.scheduled_events(events, LAST_BAR), ca.dividends_since(events, d("2025-01-01"), LAST_BAR)

    assert events == before
