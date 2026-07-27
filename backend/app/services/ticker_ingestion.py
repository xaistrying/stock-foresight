import logging
from datetime import date, datetime, timedelta

from vnstock.core.exceptions import RateLimitError
from vnstock.ui import Market

from app.db.connection import get_connection

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
INSERT INTO tickers (ticker, available_since, possibly_truncated_by_tier, last_loaded_at)
VALUES (?, ?, ?, ?)
ON CONFLICT(ticker) DO UPDATE SET
    available_since = excluded.available_since,
    possibly_truncated_by_tier = excluded.possibly_truncated_by_tier,
    last_loaded_at = excluded.last_loaded_at
"""


def load_ticker(ticker: str) -> dict:
    end = date.today()
    try:
        df = mkt.equity(ticker).ohlcv(
            start="2000-01-01", end=end.isoformat(), count=5000, source="vci"
        )
    except RateLimitError:
        return {"rows_loaded": 0, "available_since": None, "possibly_truncated_by_tier": None}

    df["time"] = df["time"].dt.date.astype(str)
    df = df.sort_values("time").reset_index(drop=True)

    dates = [date.fromisoformat(d) for d in df["time"]]
    for prev, curr in zip(dates, dates[1:]):
        if curr - prev > timedelta(days=5):
            logger.warning(
                "Gap of %s days detected for %s between %s and %s",
                (curr - prev).days, ticker, prev.isoformat(), curr.isoformat(),
            )

    available_since = df["time"].min()
    tier_floor = end - timedelta(days=365 * 8)
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
        conn.execute(
            UPSERT_TICKER,
            (ticker, available_since, int(possibly_truncated_by_tier), last_loaded_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "rows_loaded": len(rows),
        "available_since": available_since,
        "possibly_truncated_by_tier": possibly_truncated_by_tier,
    }
