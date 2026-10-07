import sqlite3
from pathlib import Path

from app.db.schema import (
    CREATE_FEATURES_TABLE,
    CREATE_OHLCV_DATE_INDEX,
    CREATE_OHLCV_QUALITY_FLAGS_TABLE,
    CREATE_OHLCV_QUALITY_FLAGS_TIER_INDEX,
    CREATE_OHLCV_TABLE,
    CREATE_TICKER_UNIVERSE_TABLE,
    CREATE_TICKERS_TABLE,
)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "app.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_readonly(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Connection that cannot write (mode=ro), for analysis and training scripts."""
    return sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)  # as_uri quotes # ? %


def _migrate_tickers_features_computed(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tickers)")}
    if "features_computed" not in columns:
        conn.execute("ALTER TABLE tickers ADD COLUMN features_computed INTEGER")


def _migrate_quality_flags_reason(conn: sqlite3.Connection) -> None:
    """Add `flag_reason` to a sidecar created before it existed.

    Existing rows are all price-limit breaches — the only kind the gate could
    record at the time — so the column's default describes them correctly.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ohlcv_quality_flags)")}
    if "flag_reason" not in columns:
        conn.execute(
            "ALTER TABLE ohlcv_quality_flags "
            "ADD COLUMN flag_reason TEXT NOT NULL DEFAULT 'price_limit'"
        )


def init_db() -> None:
    conn = get_connection()
    try:
        conn.execute(CREATE_OHLCV_TABLE)
        conn.execute(CREATE_OHLCV_DATE_INDEX)
        conn.execute(CREATE_TICKERS_TABLE)
        conn.execute(CREATE_FEATURES_TABLE)
        conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
        conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
        conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TIER_INDEX)
        _migrate_tickers_features_computed(conn)
        _migrate_quality_flags_reason(conn)
        conn.commit()
    finally:
        conn.close()
