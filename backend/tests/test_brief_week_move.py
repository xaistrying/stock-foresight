"""The week just ended around an ex-date: the events in it, the board move and the move excluding the event,
and the week-1 recompute (`weekly-holdings-brief`, `add-dividend-and-ex-date-lines`)."""

from __future__ import annotations

import ast
import math

import numpy as np
import pytest

from app.ml.volatility import band_from_sigma, sigma_daily_pct_from_closes
from app.services.brief import week_move as wm
from app.services.brief.adjustment_status import AdjustmentStatus
from app.services.brief.feed_source import Event, FeedSnapshot, IssueClass

from .brief_event_rows import bars_from, d, model_with_sigma, sab_week_bars
from .test_brief_support import brief_isolation  # noqa: F401

ADJUSTED, NOT_YET, UNCLEAR = AdjustmentStatus.ADJUSTED, AdjustmentStatus.NOT_YET_ADJUSTED, AdjustmentStatus.UNCLEAR
SAB_DIVIDEND = Event("DIV", d("2026-07-28"), d("2026-07-29"), None, 3000.0, None, d("2026-05-08"), None)
ISSUE = Event("ISS", d("2026-09-22"), None, None, None, 0.2604104, d("2026-08-20"), IssueClass.STOCK_DIVIDEND)
RIGHTS = Event("ISS", d("2026-07-28"), None, None, None, 0.2, d("2026-06-01"), IssueClass.RIGHTS_OFFER)


def fetched(*events: Event) -> FeedSnapshot:
    return FeedSnapshot("fetched", events=tuple(events))


def issue_bars():
    """s = 40.00 at the sixth-last bar, c = 35.00 at the last; a stock dividend went ex on 2026-09-22."""
    window = [("2026-09-17", 40.00, 40.00), ("2026-09-18", 40.0, 39.50), ("2026-09-21", 39.5, 39.00),
              ("2026-09-22", 35.5, 35.50), ("2026-09-23", 35.4, 35.40), ("2026-09-24", 35.2, 35.00)]
    return bars_from(window, level=40.0)


# --- the events in the week --------------------------------------------------------------------------------

def test_the_week_is_the_last_five_stored_sessions():
    bars = sab_week_bars()

    assert wm.week_events((SAB_DIVIDEND,), bars.dates) == (SAB_DIVIDEND,)  # 2026-07-23 < ex 07-28 <= 07-30


def test_a_window_ending_before_the_ex_date_does_not_contain_it():
    bars = sab_week_bars()

    assert wm.week_events((SAB_DIVIDEND,), bars.dates[:-3]) == ()  # the last bar is 2026-07-27


def test_an_event_on_the_base_date_is_before_the_week():
    bars = sab_week_bars()
    earlier = Event("DIV", d("2026-07-23"), None, None, 1000.0, None, None, None)

    assert wm.week_events((earlier,), bars.dates) == ()


def test_rights_offers_are_not_week_events():
    assert wm.week_events((RIGHTS,), sab_week_bars().dates) == ()


def test_fewer_than_six_bars_give_no_week_events():
    assert wm.week_events((SAB_DIVIDEND,), sab_week_bars().dates[-5:]) == ()


# --- the board move ------------------------------------------------------------------------------------------

def test_the_measured_sab_week():
    bars = sab_week_bars()

    move = wm.board_move(SAB_DIVIDEND, bars.dates, bars.closes)

    assert move.raw_prior == 47.00  # 43.97 x 46.60 / 43.60 = 46.995, shown 47.00
    assert round(move.board_pct, 1) == -7.7 and round(move.excluding_pct, 1) == -1.3
    assert move.board_pct == pytest.approx((43.40 - 47.00) / 47.00 * 100)  # computed from the displayed figure
    assert move.base_close == 43.97 and move.last_close == 43.40 and move.adjustment_pct is None


def test_a_share_issue_week():
    bars = issue_bars()

    move = wm.board_move(ISSUE, bars.dates, bars.closes)

    assert move.raw_prior == 50.42 and round(move.board_pct, 1) == -30.6
    assert round(move.excluding_pct, 1) == -12.5 and round(move.adjustment_pct, 1) == 20.7


def test_an_event_that_is_not_a_cash_dividend_or_count_changing_issue_has_no_board_move():
    bars = sab_week_bars()

    assert wm.board_move(RIGHTS, bars.dates, bars.closes) is None


# --- the plan for the week block ------------------------------------------------------------------------------

def plan(events, statuses, feed=None, bars=None):
    bars = bars or sab_week_bars()
    return wm.week_plan(feed or fetched(*events), tuple(zip(events, statuses)), bars.dates, bars.closes)


def test_one_adjusted_event_is_the_combined_state_with_a_board_move():
    result = plan((SAB_DIVIDEND,), (ADJUSTED,))

    assert result.state == "combined" and result.board is not None and result.events[0].status is ADJUSTED


@pytest.mark.parametrize(("status", "state"), [(NOT_YET, "not_adjusted"), (UNCLEAR, "unclear")])
def test_one_event_that_is_not_adjusted_has_no_board_move(status, state):
    result = plan((SAB_DIVIDEND,), (status,))

    assert result.state == state and result.board is None


def test_two_events_list_each_status_and_have_no_board_move():
    second = Event("DIV", d("2026-07-30"), None, None, 500.0, None, None, None)

    result = plan((SAB_DIVIDEND, second), (ADJUSTED, NOT_YET))

    assert result.state == "several" and result.board is None
    assert [e.status for e in result.events] == [ADJUSTED, NOT_YET]


def test_no_event_in_the_week_after_a_fetch():
    assert plan((), ()).state == "none"
    assert plan((SAB_DIVIDEND,), (ADJUSTED,), bars=sab_week_bars()).state == "combined"


@pytest.mark.parametrize("status", ["never_fetched", "never_succeeded"])
def test_a_feed_that_was_never_fetched_is_unknown(status):
    assert plan((), (), feed=FeedSnapshot(status)).state == "unknown"


def test_no_feed_read_or_fewer_than_six_bars_give_no_plan():
    bars = sab_week_bars()

    assert wm.week_plan(None, (), bars.dates, bars.closes) is None
    assert wm.week_plan(fetched(), (), bars.dates[-5:], bars.closes[-5:]) is None


# --- the week-1 recompute --------------------------------------------------------------------------------------

def long_closes(n=70, last_move=0.011):
    rng = np.random.default_rng(3)
    closes = 20.0 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    closes[-1] = closes[-6] * math.exp(last_move)
    return closes


def one_week(closes, model, events=(), statuses=(), feed=None):
    dates = tuple(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(closes)))
    result = wm.week_plan(feed or fetched(*events), tuple(zip(events, statuses)), dates, tuple(closes))
    return wm.week_without_issue(result, dates, tuple(closes), model), dates


def test_the_recomputed_band_equals_the_public_functions_on_closes_up_to_the_sixth_last_bar():
    closes, model = long_closes(), model_with_sigma(1.0)

    week, dates = one_week(closes, model)

    expected = band_from_sigma(sigma_daily_pct_from_closes(closes[:-5], model), model)
    assert week.band_pct == pytest.approx(expected) and week.base_date == dates[-6]


def test_inside_and_outside_are_decided_in_log_space_against_the_band():
    model = model_with_sigma(1.0)  # band 1.2 x sqrt(5) x 1.0 = 2.68

    inside, _ = one_week(long_closes(last_move=0.011), model)
    outside, _ = one_week(long_closes(last_move=0.034), model)

    assert inside.inside is True and outside.inside is False and inside.suppressed is None


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        (dict(events=(SAB_DIVIDEND,), statuses=(NOT_YET,)), "not_adjusted"),
        (dict(events=(SAB_DIVIDEND,), statuses=(UNCLEAR,)), "not_adjusted"),
        (dict(events=(SAB_DIVIDEND, ISSUE), statuses=(ADJUSTED, ADJUSTED)), "several"),
        (dict(feed=FeedSnapshot("never_fetched")), "unknown"),
    ],
)
def test_the_comparison_is_suppressed_with_a_reason(kwargs, reason):
    closes = long_closes()
    dates = tuple(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(closes)))
    events = kwargs.get("events", ())
    if events:  # put the ex-dates inside the week
        events = tuple(Event(e.event_code, d(dates[-3]), None, None, e.value_per_share, e.exercise_ratio, None, e.issue_class) for e in events)
    result = wm.week_without_issue(
        wm.week_plan(kwargs.get("feed") or fetched(*events), tuple(zip(events, kwargs.get("statuses", ()))), dates, tuple(closes)),
        dates, tuple(closes), model_with_sigma(1.0),
    )

    assert result.suppressed == reason and result.inside is None and result.band_pct is not None


def test_one_adjusted_event_makes_the_comparison_on_the_move_excluding_it():
    closes = long_closes()
    dates = tuple(f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(closes)))
    event = Event("DIV", d(dates[-3]), None, None, 500.0, None, None, None)

    week = wm.week_without_issue(
        wm.week_plan(fetched(event), ((event, ADJUSTED),), dates, tuple(closes)), dates, tuple(closes), model_with_sigma(1.0),
    )

    assert week.suppressed is None and week.inside is True


def test_under_61_closes_before_the_sixth_last_bar_cannot_be_recomputed():
    week, _ = one_week(long_closes(n=65), model_with_sigma(1.0))  # 59 closes before the sixth-last bar

    assert week.band_pct is None and week.inside is None


def test_exactly_61_closes_before_the_sixth_last_bar_can_be():
    week, _ = one_week(long_closes(n=66), model_with_sigma(1.0))

    assert week.band_pct is not None


def test_a_sigma_out_of_bounds_cannot_be_recomputed():
    week, _ = one_week(long_closes(), model_with_sigma(9.0))

    assert week.band_pct is None


def test_the_module_imports_no_private_name_from_the_volatility_module_and_never_names_the_log():
    source = open(wm.__file__, encoding="utf-8").read()
    names = [
        alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom) and node.module == "app.ml.volatility"
        for alias in node.names
    ]

    assert names and not any(name.startswith("_") for name in names)
    assert "issued_log" not in source and "append" not in source


def test_the_recompute_leaves_a_temporary_issued_log_directory_untouched(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    before = sorted(state.rglob("*"))

    one_week(long_closes(), model_with_sigma(1.0))

    assert sorted(state.rglob("*")) == before == []
