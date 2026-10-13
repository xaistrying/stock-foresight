"""refresh.py and timing.py: the vendor refresh that may fail, and staleness / provisional bars
(spec: "Every held ticker is refreshed before computing, and a failed refresh degrades")."""

from __future__ import annotations

import pytest

from app.services import bulk_ingestion
from app.services.brief import refresh as refresh_mod
from app.services.brief.refresh import RefreshOutcome, refresh_tickers
from app.services.brief.timing import PROVISIONAL_BEFORE, STALE_AFTER_CALENDAR_DAYS, provisional_bar, stale_reasons

from .test_brief_support import brief_isolation, fake_loader_factory, ict  # noqa: F401

RATE_LIMIT = "Rate limit exceeded. Process terminated."


def _states(outcomes):
    return [(o.ticker, o.state) for o in outcomes]


def test_all_ok():
    loader = fake_loader_factory()

    outcomes = refresh_tickers(("AAA", "BBB"), loader=loader, sleep=lambda s: None)

    assert _states(outcomes) == [("AAA", "ok"), ("BBB", "ok")] and loader.calls == ["AAA", "BBB"]


@pytest.mark.parametrize("status", ["rate_limited", "no_data", "invalid_symbol"])
def test_a_returned_status_other_than_ok_is_failed(status):
    loader = fake_loader_factory({"AAA": status})

    (outcome,) = refresh_tickers(("AAA",), loader=loader, sleep=lambda s: None)

    assert outcome == RefreshOutcome("AAA", "failed", status)


def test_a_rate_limit_exit_fails_that_ticker_and_skips_the_rest():
    loader = fake_loader_factory({"BBB": SystemExit(RATE_LIMIT)})

    outcomes = refresh_tickers(("AAA", "BBB", "CCC"), loader=loader, sleep=lambda s: None)

    assert _states(outcomes) == [("AAA", "ok"), ("BBB", "failed"), ("CCC", "not_attempted")]
    assert loader.calls == ["AAA", "BBB"]  # the third is never called
    assert "earlier in this run" in outcomes[2].detail


def test_a_genuine_exit_propagates():
    loader = fake_loader_factory({"AAA": SystemExit("interpreter is going down")})

    with pytest.raises(SystemExit, match="going down"):
        refresh_tickers(("AAA", "BBB"), loader=loader, sleep=lambda s: None)


def test_a_runtime_error_fails_one_ticker_only_and_keeps_just_the_class_name():
    loader = fake_loader_factory({"BBB": RuntimeError("secret detail 12345")})

    outcomes = refresh_tickers(("AAA", "BBB", "CCC"), loader=loader, sleep=lambda s: None)

    assert _states(outcomes) == [("AAA", "ok"), ("BBB", "failed"), ("CCC", "ok")]
    assert outcomes[1].detail == "RuntimeError"


def test_calls_are_spaced_at_the_bulk_ingestion_rate():
    sleeps = []

    refresh_tickers(("AAA", "BBB", "CCC"), loader=fake_loader_factory(), sleep=sleeps.append)

    assert sleeps == [60 / bulk_ingestion.DEFAULT_SYMBOLS_PER_MINUTE] * 2  # none before the first


def test_the_rate_constant_and_the_decision_function_are_the_bulk_ingestion_ones():
    assert refresh_mod._is_rate_limit_exit is bulk_ingestion._is_rate_limit_exit
    assert refresh_mod.DEFAULT_SYMBOLS_PER_MINUTE == bulk_ingestion.DEFAULT_SYMBOLS_PER_MINUTE


@pytest.mark.parametrize(
    "message", [RATE_LIMIT, "RATE LIMIT hit", "interpreter is going down", "", None, 3, "limit rate"],
)
def test_the_wrappers_decision_equals_is_rate_limit_exit(message):
    exit_request = SystemExit(message)
    loader = fake_loader_factory({"AAA": exit_request})

    if bulk_ingestion._is_rate_limit_exit(exit_request):
        (outcome,) = refresh_tickers(("AAA",), loader=loader, sleep=lambda s: None)
        assert outcome.state == "failed"
    else:
        with pytest.raises(SystemExit):
            refresh_tickers(("AAA",), loader=loader, sleep=lambda s: None)


def test_an_empty_ticker_list_calls_nothing():
    loader = fake_loader_factory()

    assert refresh_tickers((), loader=loader, sleep=lambda s: None) == ()
    assert loader.calls == []


def test_the_default_loader_is_looked_up_at_call_time():
    """The isolation fixture replaces `load_ticker`; a forgotten injection must fail, not reach the vendor."""
    with pytest.raises(pytest.fail.Exception):
        refresh_tickers(("AAA",), sleep=lambda s: None)


# --- task 4.3: provisional bars and staleness ----------------------------------------------------

def test_a_bar_dated_today_before_the_close_is_provisional():
    assert provisional_bar("2026-10-09", ict("2026-10-09 11:00")) is True
    assert provisional_bar("2026-10-09", ict("2026-10-09 15:14")) is True


def test_a_bar_dated_today_at_or_after_1515_is_final():
    assert PROVISIONAL_BEFORE.hour == 15 and PROVISIONAL_BEFORE.minute == 15
    assert provisional_bar("2026-10-09", ict("2026-10-09 15:15")) is False
    assert provisional_bar("2026-10-09", ict("2026-10-09 16:00")) is False


def test_an_older_bar_is_never_provisional():
    assert provisional_bar("2026-10-08", ict("2026-10-09 11:00")) is False
    assert provisional_bar(None, ict("2026-10-09 11:00")) is False


def test_the_clock_is_read_as_vietnam_time_whatever_its_zone():
    from datetime import datetime, timezone

    just_after_midnight_utc_is_morning_ict = datetime(2026, 10, 9, 4, 0, tzinfo=timezone.utc)  # 11:00 ICT
    assert provisional_bar("2026-10-09", just_after_midnight_utc_is_morning_ict) is True
    late_utc_is_next_day_ict = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)  # 01:00 ICT on the 10th
    assert provisional_bar("2026-10-09", late_utc_is_next_day_ict) is False


def test_a_holding_behind_the_newest_bar_is_stale():
    assert stale_reasons("2026-10-07", "2026-10-09", ict("2026-10-09 16:00")) == ("behind_newest",)


def test_a_bar_more_than_five_calendar_days_old_is_stale():
    assert STALE_AFTER_CALENDAR_DAYS == 5
    assert stale_reasons("2026-10-04", "2026-10-04", ict("2026-10-10 16:00")) == ("old",)
    assert stale_reasons("2026-10-05", "2026-10-05", ict("2026-10-10 16:00")) == ()  # exactly 5 days


def test_both_reasons_can_apply():
    assert stale_reasons("2026-09-20", "2026-10-09", ict("2026-10-12 16:00")) == ("behind_newest", "old")


def test_no_bar_has_no_staleness():
    assert stale_reasons(None, "2026-10-09", ict("2026-10-09 16:00")) == ()


def test_the_current_bar_is_not_stale():
    assert stale_reasons("2026-10-09", "2026-10-09", ict("2026-10-09 16:00")) == ()
