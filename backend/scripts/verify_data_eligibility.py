"""
Reproduces the figures `debate-data-guards` relies on (design.md Context,
tasks 1.1 / 1.2), from `backend/data/app.db` opened read-only.

It deliberately does NOT call `app.services.data_eligibility`: it recomputes
every reason from the raw tables with pandas, so task 8.2 can compare the two
independent implementations over all loaded tickers.

Prints:
- loaded tickers by `last_loaded_at` date;
- per-ticker `age_sessions` (design Decision 1) as a histogram;
- weekday non-sessions since 2025-06 from the stored calendar;
- tickers per eligibility reason, and how many pass ignoring age;
- listed tickers missing >= 6 / >= 1 market session in their last 65;
- the stored `near_gap` flip (rows 26..77 sessions after a holiday gap).

With `--compare` it then runs `assess_eligibility` over every loaded ticker and
lists any ticker where its reasons or age differ from the recomputation above
(task 8.2); the exit code is non-zero on any difference.

DATABASE-DEPENDENT. Writes nothing. Run from the project root:
    backend/.venv/bin/python backend/scripts/verify_data_eligibility.py [--compare]
"""

import sqlite3
import sys
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ml.feature_engineering import HARD_FLAG_BLACKOUT_SESSIONS  # noqa: E402
from app.ml.volatility import MIN_SESSIONS  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"
VIETNAM = timezone(timedelta(hours=7))
MAX_AGE_SESSIONS = 3
MAX_MISSING_SESSIONS = 2
CALENDAR_START = date(2025, 6, 1)
REVIEW_FLAG_DAYS = 120  # the review's window; ours is HARD_FLAG_BLACKOUT_SESSIONS sessions
FLIP_TICKER, FLIP_GAP_REOPEN = "ACB", "2026-02-23"
REASONS = (
    "delisted", "insufficient_history", "stale", "near_gap",
    "hard_quality_flag", "indicators_missing",
)
INDICATORS = ["rsi", "macd_histogram", "tenkan_sen", "kijun_sen"]


def previous_weekday(day: date) -> date:
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def weekdays_between(after: date, up_to: date) -> list[date]:
    days, day = [], after + timedelta(days=1)
    while day <= up_to:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def compare_with_service(tickers, reasons_by_ticker, ages) -> list[str]:
    """Differences between this script's recomputation and `assess_eligibility`."""
    from app.services import data_eligibility

    # The service opens its own connections: make them read-only like this script's.
    data_eligibility.get_connection = lambda: sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    now = datetime.now(VIETNAM)
    differences = []
    for ticker in tickers:
        result = data_eligibility.assess_eligibility(ticker, now=now)
        if result["reasons"] != reasons_by_ticker[ticker] or result["age_sessions"] != ages[ticker]:
            differences.append(
                f"{ticker}: service {result['reasons']} age {result['age_sessions']}"
                f" vs script {reasons_by_ticker[ticker]} age {ages[ticker]}"
            )
    print(f"\n== --compare: assess_eligibility vs this script over {len(list(tickers))} tickers ==")
    print(f"  differences: {len(differences)}")
    for line in differences[:20]:
        print("  " + line)
    return differences


def main() -> None:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    loaded = pd.read_sql("SELECT ticker, last_loaded_at FROM tickers", conn)
    universe = pd.read_sql("SELECT symbol, listing_status FROM ticker_universe", conn)
    ohlcv = pd.read_sql("SELECT ticker, date, close FROM ohlcv", conn)
    flags = pd.read_sql(
        "SELECT ticker, date FROM ohlcv_quality_flags WHERE flag_tier = 'hard'", conn
    )
    features = pd.read_sql(
        f"SELECT f.ticker, f.date, f.near_gap, {', '.join('f.' + c for c in INDICATORS)} FROM features f "
        "JOIN (SELECT ticker, MAX(date) AS d FROM features GROUP BY ticker) m "
        "ON m.ticker = f.ticker AND m.d = f.date",
        conn,
    )

    sessions = sorted(ohlcv["date"].unique())
    newest = date.fromisoformat(sessions[-1])
    today = datetime.now(VIETNAM).date()
    tail = len(weekdays_between(newest, previous_weekday(today)))
    print(f"Newest stored session {newest}; Vietnam today {today}; wall-clock tail {tail}\n")

    print("== loaded tickers by last_loaded_at date ==")
    by_day = loaded["last_loaded_at"].str[:10].value_counts().sort_index(ascending=False)
    for day, count in by_day.items():
        print(f"  {day}: {count}")

    stored = set(sessions)
    non_sessions = [
        d for d in weekdays_between(CALENDAR_START - timedelta(days=1), newest)
        if d.isoformat() not in stored
    ]
    print(f"\n== weekday non-sessions since {CALENDAR_START:%Y-%m} ({len(non_sessions)}) ==")
    print("  " + ", ".join(d.isoformat() for d in non_sessions))

    status = dict(zip(universe["symbol"], universe["listing_status"]))
    as_of = dict(zip(features["ticker"], features["date"]))
    indicators_null = {
        row.ticker: any(pd.isna(getattr(row, c)) for c in INDICATORS)
        for row in features.itertuples()
    }
    hard_dates = flags.groupby("ticker")["date"].apply(list).to_dict()
    priced = ohlcv[ohlcv["close"] > 0].sort_values("date").groupby("ticker")["date"].apply(list)

    reasons_by_ticker: dict[str, list[str]] = {}
    ages: dict[str, int] = {}
    missing_by_ticker: dict[str, int] = {}
    for ticker in loaded["ticker"]:
        dates = priced.get(ticker, [])
        window = dates[-MIN_SESSIONS:]
        missing = 0
        if window:
            span = bisect_right(sessions, window[-1]) - bisect_left(sessions, window[0])
            missing = span - len(window)
        missing_by_ticker[ticker] = missing

        ages[ticker] = len(sessions) - bisect_right(sessions, as_of[ticker]) + tail
        boundary = dates[-HARD_FLAG_BLACKOUT_SESSIONS:][0] if dates else None
        found = {
            "delisted": status.get(ticker) == "delisted",
            "insufficient_history": len(dates) < MIN_SESSIONS,
            "stale": ages[ticker] > MAX_AGE_SESSIONS,
            "near_gap": missing > MAX_MISSING_SESSIONS,
            "hard_quality_flag": boundary is not None
            and any(d >= boundary for d in hard_dates.get(ticker, [])),
            "indicators_missing": indicators_null[ticker],
        }
        reasons_by_ticker[ticker] = [r for r in REASONS if found[r]]

    print("\n== age_sessions histogram (design Decision 1) ==")
    for age, count in sorted(Counter(ages.values()).items()):
        print(f"  {age:>3}: {count}")

    counts = Counter(r for reasons in reasons_by_ticker.values() for r in reasons)
    ignoring_age = sum(1 for rs in reasons_by_ticker.values() if not set(rs) - {"stale"})
    print(f"\n== reasons across {len(loaded)} loaded tickers (a ticker can have several) ==")
    for reason in REASONS:
        print(f"  {reason:<22}{counts[reason]}")
    print(f"  passing ignoring age   {ignoring_age}")
    print(f"  passing now            {sum(1 for rs in reasons_by_ticker.values() if not rs)}")

    listed = [t for t in loaded["ticker"] if status.get(t) == "listed"]
    print(f"\n== {len(listed)} listed tickers: market sessions missing from the last {MIN_SESSIONS} ==")
    print(f"  >= 6: {sum(missing_by_ticker[t] >= 6 for t in listed)}")
    print(f"  >= 1: {sum(missing_by_ticker[t] >= 1 for t in listed)}")

    differences = compare_with_service(loaded["ticker"], reasons_by_ticker, ages) if "--compare" in sys.argv else None
    stale_only = sum(1 for rs in reasons_by_ticker.values() if rs == ["stale"])
    recent_hard = sum(
        1 for t in loaded["ticker"]
        if any(
            date.fromisoformat(as_of[t]) - timedelta(days=REVIEW_FLAG_DAYS)
            <= date.fromisoformat(d) <= date.fromisoformat(as_of[t])
            for d in hard_dates.get(t, [])
        )
    )
    print(f"\n== review figures (2026-10-06 post-pivot review) ==")
    print(f"  loaded on the modal date      : {by_day.max()} of {len(loaded)}  (review: 596)")
    print(f"  latest features row near_gap=1: {int(features['near_gap'].sum())}  (review: 199)")
    print(f"  hard flag within {REVIEW_FLAG_DAYS} days of own as_of: {recent_hard}  (review: 49)")
    print(f"  stale only (refresh fixes)    : {stale_only}")

    gap_rows = pd.read_sql(
        "SELECT date, near_gap FROM features WHERE ticker = ? ORDER BY date",
        conn, params=(FLIP_TICKER,),
    )
    positions = gap_rows["date"].tolist()
    if FLIP_GAP_REOPEN in positions:
        origin = positions.index(FLIP_GAP_REOPEN)
        flagged = [i - origin for i, v in enumerate(gap_rows["near_gap"]) if v and i > origin]
        run = [k for k in flagged if k <= 80]
        print(f"\n== stored near_gap after {FLIP_TICKER}'s {FLIP_GAP_REOPEN} reopening ==")
        print(f"  offsets flagged (<= 80): {min(run)}..{max(run)}" if run else "  none flagged")
    if differences:
        sys.exit(1)


if __name__ == "__main__":
    main()
