"""Can a loaded ticker's stored data support a debate or a volatility range?

`assess_eligibility` returns every reason that applies, in a fixed order, so the
caller can show them all. `assess_eligibility_many` assesses a whole catalog in one
pass; `assess_eligibility` is its single-ticker call. Both read the database
themselves and import no API module.

Every threshold here is NEW and PROVISIONAL (openspec debate-data-guards, design
Decision 2): none implements Rules 1-6. They are module constants, to be revisited
once outcome data exists.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone

from app.db.connection import get_connection
from app.ml.feature_engineering import HARD_FLAG_BLACKOUT_SESSIONS
from app.ml.volatility import MIN_SESSIONS
from app.services.debate.news_feeds import ICT  # UTC+7: Vietnam has no DST

# Sessions of staleness tolerated: a weekend plus one slack session.
MAX_AGE_SESSIONS = 3
# Market sessions a ticker may lack from its own last MIN_SESSIONS (~3% of the window).
MAX_MISSING_SESSIONS = 2

# The four columns the Technical agent reads (technical.py), nothing more.
AGENT_INDICATORS = ("rsi", "macd_histogram", "tenkan_sen", "kijun_sen")

_PRICED_SESSIONS_NEEDED = max(MIN_SESSIONS, HARD_FLAG_BLACKOUT_SESSIONS)


def _previous_weekday(day: date) -> date:
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _weekdays_after(start: date, up_to: date) -> int:
    count, day = 0, start + timedelta(days=1)
    while day <= up_to:
        count += day.weekday() < 5
        day += timedelta(days=1)
    return count


def _age_sessions(sessions: list[str], as_of: str, now: datetime) -> int:
    """Sessions the app has stored after `as_of`, plus weekdays since the newest
    stored session up to the previous weekday (today's session is never expected).

    ponytail: a holiday inside the unrefreshed tail counts as a missing session
    (a Tet-sized closure reads stale until a refresh stores the next session).
    Upgrade path: an extra-closures list consulted here.
    """
    stored_after = len(sessions) - bisect_right(sessions, as_of)
    newest = date.fromisoformat(sessions[-1])
    tail = _weekdays_after(newest, _previous_weekday(now.astimezone(ICT).date()))
    return stored_after + tail


_SQL_CHUNK = 500  # well under SQLite's bound-variable limit


def _chunks(items: list[str]):
    for index in range(0, len(items), _SQL_CHUNK):
        yield items[index:index + _SQL_CHUNK]


def _placeholders(items: list[str]) -> str:
    return ", ".join("?" for _ in items)


def _latest_features(conn, tickers: list[str]) -> dict[str, tuple]:
    """{ticker: (as_of, *AGENT_INDICATORS)} from each ticker's newest `features` row.

    SQLite returns the bare indicator columns from the row that holds MAX(date).
    """
    found: dict[str, tuple] = {}
    for chunk in _chunks(tickers):
        for ticker, *row in conn.execute(
            f"SELECT ticker, MAX(date), {', '.join(AGENT_INDICATORS)} FROM features "
            f"WHERE ticker IN ({_placeholders(chunk)}) GROUP BY ticker",
            chunk,
        ):
            found[ticker] = tuple(row)
    return found


def _listing_statuses(conn, tickers: list[str]) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for chunk in _chunks(tickers):
        found.update(conn.execute(
            f"SELECT symbol, listing_status FROM ticker_universe "
            f"WHERE symbol IN ({_placeholders(chunk)})", chunk,
        ))
    return found


def _priced_and_flag(conn, ticker: str) -> tuple[list[str], bool]:
    """The newest `_PRICED_SESSIONS_NEEDED` priced dates (newest first) and whether
    a hard quality flag sits inside the hard-flag window."""
    priced = [
        row[0] for row in conn.execute(
            "SELECT date FROM ohlcv WHERE ticker = ? AND close > 0 "
            "ORDER BY date DESC LIMIT ?",
            (ticker, _PRICED_SESSIONS_NEEDED),
        )
    ]
    hard_flag = bool(priced) and conn.execute(
        "SELECT 1 FROM ohlcv_quality_flags WHERE ticker = ? AND flag_tier = 'hard' "
        "AND date >= ? LIMIT 1",
        (ticker, priced[:HARD_FLAG_BLACKOUT_SESSIONS][-1]),
    ).fetchone() is not None
    return priced, hard_flag


def _verdict(sessions, now, latest, status, priced, hard_flag) -> dict:
    as_of, *indicators = latest
    window = priced[:MIN_SESSIONS]
    missing = (
        bisect_right(sessions, window[0]) - bisect_left(sessions, window[-1]) - len(window)
        if window else 0
    )
    age = _age_sessions(sessions, as_of, now)
    found = {
        "delisted": status == "delisted",
        "insufficient_history": len(priced) < MIN_SESSIONS,
        "stale": age > MAX_AGE_SESSIONS,
        "near_gap": missing > MAX_MISSING_SESSIONS,
        "hard_quality_flag": hard_flag,
        "indicators_missing": any(value is None for value in indicators),
    }
    reasons = [reason for reason, applies in found.items() if applies]  # dict keeps the fixed order
    return {"eligible": not reasons, "reasons": reasons, "as_of": as_of, "age_sessions": age}


def assess_eligibility_many(tickers, now: datetime | None = None) -> dict[str, dict]:
    """{ticker: {eligible, reasons, as_of, age_sessions}} for each ticker, in order.

    One read of the distinct session dates, one grouped read of the latest features
    rows and one of the universe for the whole batch; per ticker only an indexed
    `LIMIT` read of its priced dates and a flags lookup. `now` is a tz-aware test clock.

    ponytail: the per-ticker reads are two indexed lookups each (~1 ms); for a catalog
    that outgrows that, memoise on (newest ohlcv date, now rounded to the minute).
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        return {}

    conn = get_connection()
    try:
        latest = _latest_features(conn, tickers)
        statuses = _listing_statuses(conn, list(latest))
        sessions = (
            [row[0] for row in conn.execute("SELECT DISTINCT date FROM ohlcv ORDER BY date")]
            if latest else []
        )
        results: dict[str, dict] = {}
        for ticker in tickers:
            if ticker not in latest:
                results[ticker] = {
                    "eligible": False, "reasons": ["insufficient_history"],
                    "as_of": None, "age_sessions": None,
                }
                continue
            priced, hard_flag = _priced_and_flag(conn, ticker)
            results[ticker] = _verdict(
                sessions, now, latest[ticker], statuses.get(ticker), priced, hard_flag
            )
    finally:
        conn.close()
    return results


def assess_eligibility(ticker: str, now: datetime | None = None) -> dict:
    """{eligible, reasons, as_of, age_sessions}; `now` is a tz-aware test clock.

    The single-ticker call of `assess_eligibility_many`, so the two cannot differ.
    """
    return assess_eligibility_many([ticker], now)[ticker]
