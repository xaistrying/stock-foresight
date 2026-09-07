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
    last_loaded_at TEXT,
    features_computed INTEGER
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

CREATE_BACKTEST_PREDICTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS backtest_predictions (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    fold INTEGER NOT NULL,
    predicted REAL NOT NULL,
    actual REAL NOT NULL,
    hit INTEGER NOT NULL,
    PRIMARY KEY (ticker, date)
)
"""

# Universe of symbols the system knows about, as distinct from `tickers`,
# which means "something we have loaded" (design Decision 1). A universe row
# exists for symbols never fetched and for symbols whose fetch failed, so the
# two cannot be merged without breaking `tickers`' "no row means never loaded"
# semantics that `ticker-catalog` depends on.
#
# Column is `symbol` rather than `ticker` deliberately: this table is the
# authority on what a symbol *is*, while `ohlcv`/`features`/`tickers` key on
# `ticker` as the thing being loaded. See docs/DATA_DICTIONARY.md.
CREATE_TICKER_UNIVERSE_TABLE = """
CREATE TABLE IF NOT EXISTS ticker_universe (
    symbol TEXT PRIMARY KEY,
    exchange TEXT,
    exchange_is_unverified_fallback INTEGER NOT NULL DEFAULT 1,
    icb_code2 TEXT,
    listing_status TEXT NOT NULL,
    first_observed_session TEXT,
    last_observed_session TEXT,
    observed_session_count INTEGER,
    stale_close_fraction REAL,
    fails_liquidity_filter INTEGER,
    below_minimum_history INTEGER,
    ingestion_state TEXT NOT NULL DEFAULT 'pending',
    ingestion_last_error TEXT,
    ingestion_attempted_at TEXT,
    updated_at TEXT NOT NULL
)
"""

# Sidecar rather than flag columns on `ohlcv` (design Decision 4): `ohlcv` is
# upserted wholesale on every reload, so flags living there would be
# recomputed and rewritten for every row of every load. Only flagged rows
# appear here — an expected few hundred across the whole universe.
#
# One row per `(ticker, date)` holding the highest tier reached. The hard
# threshold is strictly wider than every soft threshold, so a hard-flagged row
# also satisfies its soft condition; `flag_tier = 'hard'` implies both.
# `flag_reason` separates the three things a flag can mean, which task 9.1 has
# to count separately: a price-limit breach (a missed split adjustment or bad
# print), a close that is not a valid price at all, and a resumption after a
# long halt, where the daily limit does not apply because the reference price
# was reset. Defaulted so the column can be added to an existing table.
CREATE_OHLCV_QUALITY_FLAGS_TABLE = """
CREATE TABLE IF NOT EXISTS ohlcv_quality_flags (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    flag_tier TEXT NOT NULL,
    flag_reason TEXT NOT NULL DEFAULT 'price_limit',
    log_return REAL NOT NULL,
    limit_exchange TEXT,
    limit_is_unverified_fallback INTEGER NOT NULL,
    flagged_at TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
)
"""

CREATE_OHLCV_QUALITY_FLAGS_TIER_INDEX = """
CREATE INDEX IF NOT EXISTS idx_ohlcv_quality_flags_tier
    ON ohlcv_quality_flags (flag_tier)
"""
