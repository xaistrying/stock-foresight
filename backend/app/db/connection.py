import sqlite3
from pathlib import Path

from app.db.schema import CREATE_OHLCV_TABLE, CREATE_TICKERS_TABLE

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "app.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(CREATE_OHLCV_TABLE)
        conn.execute(CREATE_TICKERS_TABLE)
        conn.commit()
    finally:
        conn.close()
