import sqlite3
from pathlib import Path

from app.db.schema import (
    CREATE_BACKTEST_PREDICTIONS_TABLE,
    CREATE_FEATURES_TABLE,
    CREATE_OHLCV_TABLE,
    CREATE_TICKERS_TABLE,
)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "app.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_tickers_features_computed(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tickers)")}
    if "features_computed" not in columns:
        conn.execute("ALTER TABLE tickers ADD COLUMN features_computed INTEGER")


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(CREATE_OHLCV_TABLE)
        conn.execute(CREATE_TICKERS_TABLE)
        conn.execute(CREATE_FEATURES_TABLE)
        conn.execute(CREATE_BACKTEST_PREDICTIONS_TABLE)
        _migrate_tickers_features_computed(conn)
        conn.commit()
    finally:
        conn.close()
