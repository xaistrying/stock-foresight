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

CREATE_FEATURES_TABLE = """
CREATE TABLE IF NOT EXISTS features (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    tenkan_sen REAL,
    kijun_sen REAL,
    senkou_span_a REAL,
    senkou_span_b REAL,
    chikou_signal REAL,
    rsi REAL,
    macd_line REAL,
    macd_signal REAL,
    macd_histogram REAL,
    bb_upper REAL,
    bb_middle REAL,
    bb_lower REAL,
    atr REAL,
    obv REAL,
    target REAL,
    near_gap INTEGER NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
)
"""
