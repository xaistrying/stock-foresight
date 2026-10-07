"""Readers for a ticker's latest `features` row and its `features_computed` flag.

Used by the debate endpoint and the Technical agent. They return what is stored:
no walk-back to an older clean row, no repair of a failed feature computation.
"""

from app.db.connection import get_connection
from app.ml.training import FEATURE_COLUMNS

FEATURES_COMPUTED_FOR_TICKER = """
SELECT features_computed
FROM tickers
WHERE ticker = ?
"""

LATEST_FEATURES_ROW = """
SELECT date, near_gap, {columns}
FROM features
WHERE ticker = ?
ORDER BY date DESC
LIMIT 1
""".format(columns=", ".join(FEATURE_COLUMNS))


def get_features_computed(ticker: str) -> int | None:
    conn = get_connection()
    try:
        cursor = conn.execute(FEATURES_COMPUTED_FOR_TICKER, (ticker,))
        row = cursor.fetchone()
        return row[0] if row is not None else None
    finally:
        conn.close()


def get_latest_features_row(ticker: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.execute(LATEST_FEATURES_ROW, (ticker,))
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))
    finally:
        conn.close()
