"""The adjustment status of an ex-date from the stored bars, with no vendor call (`weekly-holdings-brief`:
"Adjustment status is checked from the stored bars at run time, not assumed")."""

from __future__ import annotations

import socket

import pytest

from app.services.brief.adjustment_status import UNCLEAR_GAP_SIGMAS, AdjustmentStatus, adjustment_status
from app.services.brief.feed_source import Event, IssueClass

from .brief_event_rows import bars_from, d, model_with_sigma, raw_history_bars, sab_week_bars, small_dividend_bars, stock_bars
from .test_brief_support import brief_isolation  # noqa: F401

ADJUSTED, NOT_YET, UNCLEAR = AdjustmentStatus.ADJUSTED, AdjustmentStatus.NOT_YET_ADJUSTED, AdjustmentStatus.UNCLEAR


def cash(ex: str, vnd: float) -> Event:
    return Event("DIV", d(ex), None, None, vnd, None, None, None)


def issue(ex: str, ratio: float, klass=IssueClass.BONUS) -> Event:
    return Event("ISS", d(ex), None, None, None, ratio, None, klass)


def status(event: Event, bars, sigma: float = 1.0) -> AdjustmentStatus:
    return adjustment_status(event, bars.dates, bars.opens, bars.closes, model_with_sigma(sigma))


def test_adjusted_history_for_the_measured_sab_dividend():
    assert status(cash("2026-07-28", 3000.0), sab_week_bars()) is ADJUSTED


def test_raw_history_is_not_yet_adjusted():
    assert status(cash("2026-07-28", 3000.0), raw_history_bars()) is NOT_YET


@pytest.mark.parametrize(("open_price", "expected"), [(27.30, NOT_YET), (29.80, ADJUSTED)])
def test_a_stock_issue_both_ways(open_price, expected):
    assert status(issue("2026-09-21", 0.10), stock_bars(open_price)) is expected


def test_a_small_dividend_is_unclear_at_a_sigma_of_one_and_a_half_percent():
    bars = small_dividend_bars()

    assert status(cash("2026-07-28", 500.0), bars, sigma=1.5) is UNCLEAR  # expected gap -2.2% is within 2 sigmas (3.0%)
    assert status(cash("2026-07-28", 500.0), bars, sigma=0.8) is ADJUSTED  # decided at 0.8: 2 sigmas is 1.6%


def test_the_floor_is_relative_to_the_ticker_not_a_fixed_percent():
    bars = small_dividend_bars()  # expected gap about -2.2%

    unclear = status(cash("2026-07-28", 500.0), bars, sigma=1.5)
    decided = status(cash("2026-07-28", 500.0), bars, sigma=0.8)

    assert (unclear, decided) == (UNCLEAR, ADJUSTED) and UNCLEAR_GAP_SIGMAS == 2.0


def test_a_gap_at_or_below_half_the_expected_gap_is_not_yet_adjusted_and_above_it_adjusted():
    # previous close 100.00, a 4,000 VND dividend (4.00 in thousand VND): expected gap -4%, half is -2%
    def at(open_price):
        return bars_from([("2026-07-27", 100.0, 100.0), ("2026-07-28", open_price, open_price)], level=100.0)

    event = cash("2026-07-28", 4000.0)

    assert status(event, at(98.0)) is NOT_YET  # exactly half
    assert status(event, at(97.9)) is NOT_YET
    assert status(event, at(98.1)) is ADJUSTED


def test_a_missing_ex_bar_or_previous_bar_is_unclear():
    bars = sab_week_bars()

    assert status(cash("2026-07-31", 3000.0), bars) is UNCLEAR  # no bar for that date
    assert status(cash("2025-01-02", 3000.0), bars) is UNCLEAR  # before the stored window
    assert adjustment_status(cash("2026-07-28", 3000.0), bars.dates[-1:], bars.opens[-1:], bars.closes[-1:], model_with_sigma(1.0)) is UNCLEAR


def test_a_bar_with_no_positive_open_or_close_is_unclear():
    bars = sab_week_bars()
    opens = list(bars.opens)
    opens[bars.dates.index("2026-07-28")] = float("nan")

    assert adjustment_status(cash("2026-07-28", 3000.0), bars.dates, tuple(opens), bars.closes, model_with_sigma(1.0)) is UNCLEAR


def test_fewer_than_61_closes_before_the_ex_date_is_unclear():
    short = bars_from([("2026-07-27", 46.60, 46.60), ("2026-07-28", 43.60, 43.40)], history=40, level=46.6)

    assert status(cash("2026-07-28", 3000.0), short) is UNCLEAR


def test_only_cash_dividends_and_count_changing_issues_are_classified():
    bars = stock_bars(27.30)

    assert status(issue("2026-09-21", 0.2, IssueClass.RIGHTS_OFFER), bars) is UNCLEAR
    assert status(issue("2026-09-21", 0.2, IssueClass.PRIVATE_PLACEMENT), bars) is UNCLEAR
    assert status(Event("AGME", d("2026-09-21"), None, None, None, None, None, None), bars) is UNCLEAR


def test_no_network_call_is_made(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a network call was attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)

    assert status(cash("2026-07-28", 3000.0), sab_week_bars()) is ADJUSTED


def test_the_inputs_are_not_modified():
    bars = sab_week_bars()
    before = (bars.dates, bars.opens, bars.closes)

    status(cash("2026-07-28", 3000.0), bars)

    assert (bars.dates, bars.opens, bars.closes) == before


def test_the_module_states_that_only_an_upper_bound_of_the_lag_is_known():
    import app.services.brief.adjustment_status as module

    assert "upper bound" in module.__doc__ and "no lower bound" in module.__doc__
