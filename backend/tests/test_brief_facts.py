"""facts.py: everything derived from prices and the model, for every range status, end to end over a
temporary database and model artifact (tasks 6.3 and 6.4)."""

from __future__ import annotations

import dataclasses
import logging
import math

import pytest

from app.services import range as range_service
from app.services.brief.facts import MarketFacts, gather_market_facts, with_staleness
from app.services.brief.refresh import RefreshOutcome

from .test_brief_support import (  # noqa: F401
    brief_env, brief_isolation, ict, make_closes, make_facts, make_issued_entry, make_log, sessions_ending,
)

AFTER_CLOSE = ict("2026-10-09 16:30")
EMPTY_LOG = make_log()


def _gather(ticker, **kwargs):
    kwargs.setdefault("refresh", None)
    kwargs.setdefault("log", EMPTY_LOG)
    kwargs.setdefault("now", AFTER_CLOSE)
    return gather_market_facts(ticker, **kwargs)


def test_ok_gives_the_band_the_vnd_edges_and_the_coverage(brief_env):
    dates = brief_env.add_ticker("AAA", make_closes(400))

    facts = _gather("AAA")

    result = range_service.compute_range("AAA")
    assert facts.status == "ok" and facts.calibrated is True
    assert facts.last_bar == dates[-1] and facts.close == pytest.approx(make_closes(400)[-1])
    assert facts.band_pct == result.range_5s_pct and facts.range_coverage == 0.68
    assert facts.band_lo == pytest.approx(facts.close * math.exp(-facts.band_pct / 100))
    assert facts.band_hi == pytest.approx(facts.close * math.exp(facts.band_pct / 100))
    assert facts.model_version == "har-rv-test-0001"
    assert facts.error_class is None and facts.reasons == ()


@pytest.mark.parametrize(
    ("last", "inside"),
    [(100.0, True), (104.9, True), (95.2, True), (105.2, False), (94.7, False), (130.0, False), (70.0, False)],
)
def test_the_inside_outside_verdict_agrees_with_the_printed_edges(brief_env, last, inside):
    """Last week's issued range was close 100, band 5: the edges are 100 x exp(-/+0.05) = 95.12 and 105.13."""
    closes = [float(c) for c in make_closes(394)] + [100.0, 101.0, 99.0, 100.5, 99.5, last]
    dates = brief_env.add_ticker("AAA", closes)
    band = 5.0
    entry = make_issued_entry(
        as_of=dates[-6], close=100.0, band_pct=band, band_lo=100.0 * math.exp(-band / 100), band_hi=100.0 * math.exp(band / 100),
    )

    facts = _gather("AAA", log=make_log(entry))

    assert (entry.band_lo <= last <= entry.band_hi) is inside
    assert facts.week.kind == "band" and facts.week.inside is inside


def test_uncalibrated_has_a_band_but_no_coverage(brief_env):
    brief_env.add_ticker("OUT", make_closes(400, seed=2))

    facts = _gather("OUT")

    assert facts.status == "uncalibrated" and facts.calibrated is False
    assert facts.band_pct and facts.band_lo and facts.range_coverage is None


@pytest.mark.parametrize(
    "reasons", [["delisted"], ["insufficient_history"], ["stale"], ["near_gap"], ["hard_quality_flag"], ["stale", "near_gap"]],
)
def test_ineligible_carries_every_reason_and_keeps_the_close(brief_env, reasons):
    brief_env.add_ticker("AAA", make_closes(400))
    brief_env.eligibility["AAA"] = reasons

    facts = _gather("AAA")

    assert facts.status == "ineligible" and facts.reasons == tuple(reasons)
    assert facts.close is not None and facts.band_pct is None and facts.band_lo is None


def test_too_few_closes_is_ineligible_for_insufficient_history(brief_env):
    brief_env.add_ticker("SHORT", make_closes(50, seed=3))

    facts = _gather("SHORT")

    assert facts.status == "ineligible" and facts.reasons == ("insufficient_history",)


def test_model_unavailable(brief_env):
    brief_env.add_ticker("AAA", make_closes(400))
    brief_env.model_path.unlink()

    facts = _gather("AAA")

    assert facts.status == "model_unavailable" and facts.model_version is None and facts.close is not None


def test_range_out_of_bounds_has_no_band_and_no_sigma(brief_env):
    import numpy as np

    brief_env.add_ticker("WILD", np.concatenate([make_closes(340), make_closes(60, noise=0.2, seed=4)]))

    facts = _gather("WILD")

    assert facts.status == "range_out_of_bounds" and facts.band_pct is None
    assert not any("sigma" in name for name in (f.name for f in dataclasses.fields(MarketFacts)))
    assert "sigma" not in repr(facts)


def test_a_ticker_with_no_rows_has_no_prices(brief_env):
    facts = _gather("NONE")

    assert facts.status == "no_prices" and facts.close is None and facts.last_bar is None and facts.week is None


def test_any_other_exception_becomes_an_error_and_is_logged(brief_env, caplog):
    brief_env.add_ticker("AAA", make_closes(400))

    def broken(ticker):
        raise KeyError("boom")

    with caplog.at_level(logging.ERROR):
        facts = _gather("AAA", range_fn=broken)

    assert facts.status == "error" and facts.error_class == "KeyError"
    assert facts.close is not None  # the stored close is still shown
    assert any("AAA" in record.getMessage() for record in caplog.records)


def test_an_exception_while_reading_closes_is_an_error_without_a_close(brief_env, caplog):
    def broken(ticker):
        raise RuntimeError("db gone")

    with caplog.at_level(logging.ERROR):
        facts = _gather("AAA", closes_fn=broken)

    assert facts.status == "error" and facts.error_class == "RuntimeError" and facts.close is None


def test_ticker_not_loaded_from_the_range_service_is_no_prices(brief_env):
    brief_env.add_ticker("AAA", make_closes(400))

    def not_loaded(ticker):
        raise range_service.TickerNotLoaded(ticker)

    assert _gather("AAA", range_fn=not_loaded).status == "no_prices"


def test_the_refresh_outcome_is_carried(brief_env):
    brief_env.add_ticker("AAA", make_closes(400))

    ok = _gather("AAA", refresh=RefreshOutcome("AAA", "ok", "ok"))
    failed = _gather("AAA", refresh=RefreshOutcome("AAA", "failed", "RuntimeError"))
    skipped = _gather("AAA")

    assert (ok.refresh, failed.refresh, skipped.refresh) == ("ok", "failed", "skipped")
    assert failed.refresh_detail == "RuntimeError"


def test_a_bar_dated_today_before_the_close_is_provisional(brief_env):
    brief_env.add_ticker("AAA", make_closes(400))

    assert _gather("AAA", now=ict("2026-10-09 11:00")).provisional is True
    assert _gather("AAA", now=ict("2026-10-09 16:00")).provisional is False


def test_a_stale_holding_is_not_provisional(brief_env):
    dates = brief_env.add_ticker("AAA", make_closes(400), sessions_ending("2026-10-07", 400))

    assert _gather("AAA", now=ict("2026-10-09 11:00")).provisional is False
    assert dates[-1] == "2026-10-07"


def test_the_week_and_the_readjusted_note_come_from_the_log(brief_env):
    closes = list(make_closes(400))
    dates = brief_env.add_ticker("AAA", closes)
    entry = make_issued_entry(as_of=dates[-6], close=closes[-6] + 3.0)

    facts = _gather("AAA", log=make_log(entry))

    assert facts.week.kind == "band"
    assert facts.readjusted is not None and facts.readjusted.date == dates[-6]


def test_a_week_needs_six_closes(brief_env):
    brief_env.add_ticker("TINY", make_closes(5, seed=9))

    assert _gather("TINY").week is None


def test_staleness_is_set_from_the_whole_set_of_holdings():
    base = dict(
        ticker="X", refresh="ok", refresh_detail="ok", close=1.0, provisional=False, status="ok", reasons=(),
        band_pct=None, band_lo=None, band_hi=None, range_coverage=None, calibrated=None, model_version=None,
        week=None, readjusted=None, error_class=None,
    )
    fresh = MarketFacts(last_bar="2026-10-09", **base)
    behind = MarketFacts(last_bar="2026-10-07", **{**base, "ticker": "Y"})
    empty = MarketFacts(last_bar=None, **{**base, "ticker": "Z", "close": None, "status": "no_prices"})

    result = with_staleness((fresh, behind, empty), AFTER_CLOSE)

    assert [f.stale_reasons for f in result] == [(), ("behind_newest",), ()]
    assert fresh.stale_reasons == ()  # the originals are untouched


def test_the_price_history_and_the_model_travel_with_the_facts(brief_env):
    closes = [float(c) for c in make_closes(400)]
    dates = brief_env.add_ticker("AAA", closes)

    facts = _gather("AAA")

    assert facts.dates[-1] == dates[-1] and len(facts.dates) == len(facts.closes) == len(facts.opens)
    assert facts.closes[-1] == pytest.approx(closes[-1]) and facts.opens[-1] == pytest.approx(closes[-1])  # open = close in the fixture
    assert facts.model is not None and facts.model.model_version == "har-rv-test-0001"


def test_the_new_fields_have_defaults_so_later_changes_never_break_a_constructor():
    facts = make_facts()

    assert facts.dates == () and facts.opens == () and facts.closes == () and facts.model is None


def test_opens_are_read_without_creating_a_missing_database(tmp_path):
    from app.db import connection
    from app.services.brief.prices import read_opens

    assert not connection.DB_PATH.exists()

    import sqlite3

    with pytest.raises(sqlite3.OperationalError):  # the caller (gather) degrades this to no opens
        read_opens("AAA", ["2026-10-08", "2026-10-09"])
    assert not connection.DB_PATH.exists()


def test_a_failed_opens_read_degrades_to_no_opens_not_to_a_failed_holding(brief_env):
    brief_env.add_ticker("AAA", make_closes(400))

    def broken(ticker, dates):
        raise RuntimeError("no db")

    facts = _gather("AAA", opens_fn=broken)

    assert facts.status == "ok" and facts.opens == ()


def test_missing_opens_are_nan(brief_env):
    from app.services.brief.prices import read_opens

    dates = brief_env.add_ticker("AAA", make_closes(10))

    opens = read_opens("AAA", [*dates, "2099-01-01"])

    assert math.isnan(opens[-1]) and opens[0] == pytest.approx(make_closes(10)[0])


def test_the_opens_connection_is_read_only(brief_env):
    import sqlite3

    from app.db import connection

    brief_env.add_ticker("AAA", make_closes(10))
    conn = connection.open_readonly(connection.DB_PATH)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM ohlcv")
    conn.close()


def test_a_model_that_cannot_load_is_model_unavailable(brief_env):
    brief_env.add_ticker("AAA", make_closes(400))

    def broken():
        raise OSError("disk")

    facts = _gather("AAA", model_fn=broken)

    assert facts.status == "model_unavailable" and facts.band_pct is None and facts.close is not None


def test_ticker_not_loaded_clears_the_prices_so_no_close_sits_beside_no_stored_prices(brief_env):
    brief_env.add_ticker("AAA", make_closes(400))

    def not_loaded(ticker):
        raise range_service.TickerNotLoaded(ticker)

    facts = _gather("AAA", range_fn=not_loaded)

    assert facts.status == "no_prices" and facts.close is None and facts.last_bar is None
    assert facts.dates == () and facts.week is None and facts.readjusted is None
