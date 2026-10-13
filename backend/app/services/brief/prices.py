"""Stored opens for the bars the brief already reads, through a read-only connection.

`app.ml.volatility.read_recent_closes` returns dates and closes only. Later sections (for example a
share issue's ex-date) need opens too; this is a brief-local, read-only query beside it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.db import connection


def read_opens(ticker: str, dates: Sequence[str]) -> tuple[float, ...]:
    """The stored open for each of `dates` (ascending), nan where a bar has none."""
    if not dates:
        return ()
    conn = connection.open_readonly(connection.DB_PATH)  # the path is read at call time so a test can redirect it
    try:
        rows = conn.execute(
            "SELECT date, open FROM ohlcv WHERE ticker = ? AND date >= ? AND date <= ?",
            (ticker, dates[0], dates[-1]),
        ).fetchall()
    finally:
        conn.close()
    by_date = {row[0]: float(row[1]) for row in rows if row[1] is not None}
    return tuple(by_date.get(day, math.nan) for day in dates)
