"""Can a loaded ticker's stored data support a debate or a volatility range?

`assess_eligibility` returns every reason that applies, in a fixed order, so the
caller can show them all. It reads the database itself and imports no API module.

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


def assess_eligibility(ticker: str, now: datetime | None = None) -> dict:
    """{eligible, reasons, as_of, age_sessions}; `now` is a tz-aware test clock."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    conn = get_connection()
    try:
        as_of = conn.execute(
            "SELECT MAX(date) FROM features WHERE ticker = ?", (ticker,)
        ).fetchone()[0]
        if as_of is None:
            return {
                "eligible": False, "reasons": ["insufficient_history"],
                "as_of": None, "age_sessions": None,
            }

        indicators = conn.execute(
            f"SELECT {', '.join(AGENT_INDICATORS)} FROM features WHERE ticker = ? AND date = ?",
            (ticker, as_of),
        ).fetchone()
        status = conn.execute(
            "SELECT listing_status FROM ticker_universe WHERE symbol = ?", (ticker,)
        ).fetchone()
        priced = [
            row[0] for row in conn.execute(
                "SELECT date FROM ohlcv WHERE ticker = ? AND close > 0 "
                "ORDER BY date DESC LIMIT ?",
                (ticker, _PRICED_SESSIONS_NEEDED),
            )
        ]  # newest first
        # ponytail: full scan of idx_ohlcv_date per call (~0.05 s on 1M rows). Add a
        # short-lived cache if /range or the debate log call this in bulk.
        sessions = [row[0] for row in conn.execute("SELECT DISTINCT date FROM ohlcv ORDER BY date")]
        window = priced[:MIN_SESSIONS]
        missing = (
            bisect_right(sessions, window[0]) - bisect_left(sessions, window[-1]) - len(window)
            if window else 0
        )
        hard_flag = bool(priced) and conn.execute(
            "SELECT 1 FROM ohlcv_quality_flags WHERE ticker = ? AND flag_tier = 'hard' "
            "AND date >= ? LIMIT 1",
            (ticker, priced[:HARD_FLAG_BLACKOUT_SESSIONS][-1]),
        ).fetchone() is not None
    finally:
        conn.close()

    age = _age_sessions(sessions, as_of, now)
    found = {
        "delisted": status is not None and status[0] == "delisted",
        "insufficient_history": len(priced) < MIN_SESSIONS,
        "stale": age > MAX_AGE_SESSIONS,
        "near_gap": missing > MAX_MISSING_SESSIONS,
        "hard_quality_flag": hard_flag,
        "indicators_missing": any(value is None for value in indicators),
    }
    reasons = [reason for reason, applies in found.items() if applies]  # dict keeps the fixed order
    return {"eligible": not reasons, "reasons": reasons, "as_of": as_of, "age_sessions": age}
