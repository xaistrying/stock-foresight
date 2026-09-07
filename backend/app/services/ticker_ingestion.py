import logging
from datetime import date, datetime, timedelta
from time import perf_counter

import pandas as pd
from dateutil.relativedelta import relativedelta
from tenacity import RetryError

from app.vnstock_guard import install as _install_vnstock_guard

_install_vnstock_guard()  # must precede any vnstock import (docs/KNOWN_ISSUES.md)

from vnstock.core.exceptions import RateLimitError  # noqa: E402
from vnstock.ui import Market  # noqa: E402

from app.db.connection import get_connection  # noqa: E402
from app.ml.feature_engineering import recompute_features_for_ticker
from app.services.ohlcv_quality_gate import (
    persist_quality_gate_result,
    run_quality_gate,
)
from app.services.ticker_universe import (
    INGESTION_STATE_FEATURES_FAILED,
    INGESTION_STATE_OK,
    record_ingestion_result,
    universe_entry,
)

logger = logging.getLogger(__name__)

mkt = Market()

UPSERT_OHLCV = """
INSERT INTO ohlcv (ticker, date, open, high, low, close, volume)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(ticker, date) DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume
"""

UPSERT_TICKER = """
INSERT INTO tickers (ticker, available_since, possibly_truncated_by_tier, last_loaded_at, features_computed)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(ticker) DO UPDATE SET
    available_since = excluded.available_since,
    possibly_truncated_by_tier = excluded.possibly_truncated_by_tier,
    last_loaded_at = excluded.last_loaded_at,
    features_computed = excluded.features_computed
"""


def _classify_load_error(exc: Exception) -> str | None:
    """Given a ValueError from vnstock's symbol validation, return the
    matching status, or None if unrecognized — caller re-raises rather
    than misclassify an unrelated error."""
    message = str(exc)
    if "Invalid symbol" in message or "characters long" in message:
        return "invalid_symbol"
    if "Không tìm thấy dữ liệu" in message:
        return "no_data"
    return None


def _stored_ohlcv(ticker: str) -> "pd.DataFrame":
    """The ticker's full stored history, which is not the same thing as what
    the last fetch returned.

    The community tier's ~8-year window slides forward, so a refetch returns
    *less* history than is already stored, and `ohlcv` rows are never
    deleted. Everything that describes the symbol's history — the quality
    gate, the observed range, the session count — must therefore read the
    stored series, or a refresh would silently narrow it: `VHM`'s
    2018-08-14 hard flag now sits before today's tier floor, and gating the
    fetched frame would delete that flag on every refresh (task 6.9), taking
    the 78-session blackout and the nulled targets with it.
    """
    conn = get_connection()
    try:
        return pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM ohlcv "
            "WHERE ticker = ? ORDER BY date ASC",
            conn,
            params=(ticker,),
        )
    finally:
        conn.close()


def _run_and_persist_quality_gate(ticker: str, df) -> dict | None:
    """Run the quality gate over a ticker's stored history and persist it.

    Called after the `ohlcv` upsert but before feature recomputation, because
    `recompute_features_for_ticker` reads the flags back out of the sidecar —
    a gate that ran afterwards would leave every load's first feature
    computation using un-neutralised data. The `ohlcv-quality-gate`
    requirement is that quality state exists when the data enters the
    database, not that a later pass reconstructs it.

    Flagged rows are persisted with their flags rather than the load being
    rejected (task 4.2), so the data stays inspectable. Returns None if the
    gate itself errored, which likewise does not fail the load: the fetched
    rows are already stored, and losing the measurement is a smaller harm
    than discarding a successful fetch.
    """
    entry = universe_entry(ticker)
    if entry is None:
        # Not in the universe: the originally-loaded 15 predate the universe
        # table (task 5.1 backfills them). The hard gate needs no exchange, so
        # it still applies; only the soft tier goes unevaluated.
        logger.info(
            "No ticker_universe row for %s; evaluating the hard gate only",
            ticker,
        )
    try:
        result = run_quality_gate(
            ticker,
            df,
            exchange=entry["exchange"] if entry else None,
            exchange_is_unverified_fallback=bool(
                entry["exchange_is_unverified_fallback"] if entry else True
            ),
        )
        persist_quality_gate_result(result)
    except Exception:
        logger.exception("Quality gate failed for %s", ticker)
        return None
    if result["hard_flag_count"] or result["soft_flag_count"]:
        logger.warning(
            "Quality gate flagged %s: %d hard, %d soft",
            ticker,
            result["hard_flag_count"],
            result["soft_flag_count"],
        )
    return result


def load_ticker(ticker: str, timings: dict | None = None) -> dict:
    """Load one ticker's full history, gate it, and recompute its features.

    `timings`, when given, is filled in with `fetch_seconds` and
    `features_seconds`. An out-parameter rather than extra response keys
    because `POST /tickers/{ticker}/load` returns this dict verbatim, and a
    batch run's stopwatch has no business in an API response. Task 6.7 needs
    the split: design Decision 7 predicts feature recomputation dominates
    fetch time at scale, and that prediction has never been measured.
    """
    end = date.today()
    fetch_started = perf_counter()
    try:
        df = mkt.equity(ticker).ohlcv(
            start="2000-01-01", end=end.isoformat(), count=5000, source="vci"
        )
    except RateLimitError:
        logger.warning("Rate limit hit while loading %s", ticker)
        return {
            "rows_loaded": 0,
            "available_since": None,
            "possibly_truncated_by_tier": None,
            "features_computed": None,
            "status": "rate_limited",
        }
    except (ValueError, RetryError) as e:
        underlying = e.last_attempt.exception() if isinstance(e, RetryError) else e
        if not isinstance(underlying, Exception):
            raise
        status = _classify_load_error(underlying)
        if status is None:
            raise
        logger.info("Load failed for %s: %s (%s)", ticker, status, underlying)
        return {
            "rows_loaded": 0,
            "available_since": None,
            "possibly_truncated_by_tier": None,
            "features_computed": None,
            "status": status,
        }

    if timings is not None:
        timings["fetch_seconds"] = perf_counter() - fetch_started

    if df.empty:
        # An empty frame is not an exception in vnstock's contract, but every
        # line below assumes at least one row — `df["time"].min()` would be
        # NaN and `date.fromisoformat` would raise `TypeError`, ending a
        # 634-symbol batch on a symbol that simply has no data.
        logger.info("Load returned no rows for %s", ticker)
        return {
            "rows_loaded": 0,
            "available_since": None,
            "possibly_truncated_by_tier": None,
            "features_computed": None,
            "status": "no_data",
        }

    df["time"] = df["time"].dt.date.astype(str)
    df = df.sort_values("time").reset_index(drop=True)
    dates = [date.fromisoformat(d) for d in df["time"]]
    gaps = [
        (prev, curr)
        for prev, curr in zip(dates, dates[1:])
        if curr - prev > timedelta(days=5)
    ]
    if gaps:
        # One line per ticker, not per gap. Vietnamese market holidays produce
        # ~13 of these a decade for every symbol, so per-gap warnings across
        # 634 symbols would be ~8,000 lines of noise burying the real errors
        # in a batch run's log.
        widest = max(gaps, key=lambda pair: pair[1] - pair[0])
        logger.info(
            "%s has %d calendar gap(s) over 5 days; widest %d days between "
            "%s and %s",
            ticker, len(gaps), (widest[1] - widest[0]).days,
            widest[0].isoformat(), widest[1].isoformat(),
        )
    available_since = df["time"].min()
    tier_floor = end - relativedelta(years=8)
    possibly_truncated_by_tier = (
        abs((date.fromisoformat(available_since) - tier_floor).days) <= 30
    )
    rows = [
        (ticker, row.time, row.open, row.high, row.low, row.close, row.volume)
        for row in df.itertuples()
    ]
    last_loaded_at = datetime.now().isoformat()
    conn = get_connection()
    try:
        conn.executemany(UPSERT_OHLCV, rows)
        conn.commit()
    finally:
        conn.close()

    # Both the gate and the observed range read the *stored* series, not the
    # frame just fetched — see `_stored_ohlcv` for why the two differ and what
    # gating the fetch would destroy.
    stored = _stored_ohlcv(ticker)
    gate = _run_and_persist_quality_gate(ticker, stored)

    features_started = perf_counter()
    try:
        recompute_features_for_ticker(ticker)
        features_computed = True
    except Exception:
        logger.exception("Feature recomputation failed for %s", ticker)
        features_computed = False
    if timings is not None:
        timings["features_seconds"] = perf_counter() - features_started

    # Observed range and session count are populated by ingestion, never by
    # universe construction — the listing carries no dates. They are what
    # point-in-time reconstruction reads (design Decision 2) and what the
    # minimum-history threshold is later chosen against (task 7.1).
    #
    # A delisted symbol whose last session is years old is recorded exactly
    # like any other: `last_observed_session` is simply old. Nothing here
    # compares it against today, so the absence of recent sessions is not an
    # error (`ticker-data-ingestion`: delisted symbols load through the
    # normal path).
    #
    # Written *after* feature recomputation, and only as `ok` if that
    # succeeded: `ingestion_state` doubles as the batch runner's resume point,
    # so marking a symbol done whose features failed would make a resumed run
    # skip precisely the symbols that need another attempt.
    record_ingestion_result(
        ticker,
        first_observed_session=stored["date"].min(),
        last_observed_session=stored["date"].max(),
        observed_session_count=len(stored),
        ingestion_state=(
            INGESTION_STATE_OK if features_computed else INGESTION_STATE_FEATURES_FAILED
        ),
        ingestion_last_error=None if features_computed else "features_failed",
    )

    conn = get_connection()
    try:
        conn.execute(
            UPSERT_TICKER,
            (
                ticker,
                available_since,
                int(possibly_truncated_by_tier),
                last_loaded_at,
                int(features_computed),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "rows_loaded": len(rows),
        "available_since": available_since,
        "possibly_truncated_by_tier": possibly_truncated_by_tier,
        "features_computed": features_computed,
        "status": "ok",
        # Reported alongside the load rather than requiring a follow-up query,
        # so a batch run (task group 6) can separate fetch failures from
        # quality outcomes without re-reading the sidecar. None only if the
        # gate itself errored — the load still stands.
        "hard_flag_count": gate["hard_flag_count"] if gate else None,
        "soft_flag_count": gate["soft_flag_count"] if gate else None,
        "stale_close_fraction": gate["stale_close_fraction"] if gate else None,
        # Passed through from the gate rather than recompared against the
        # threshold downstream, so a batch summary cannot disagree with what
        # the gate itself persisted.
        "fails_liquidity_filter": gate["fails_liquidity_filter"] if gate else None,
    }
