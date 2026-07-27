CREATE_OHLCV_TABLE = """
CREATE TABLE IF NOT EXISTS ohlcv (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    PRIMARY KEY (ticker, date)
)
"""

CREATE_TICKERS_TABLE = """
CREATE TABLE IF NOT EXISTS tickers (
    ticker TEXT PRIMARY KEY,
    available_since TEXT,
    possibly_truncated_by_tier INTEGER,
    last_loaded_at TEXT
)
"""
