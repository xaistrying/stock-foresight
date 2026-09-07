from fastapi import APIRouter, HTTPException

from app.db.connection import get_connection
from app.ml.backtest import (
    SINGLE_TICKER_BACKTEST_MIN_ROWS,
    load_single_ticker_features,
    persist_backtest_predictions,
    run_single_ticker_backtest,
)
from app.ml.training import TRAINING_TICKERS, filter_clean_labeled
from app.services.ticker_ingestion import load_ticker
from app.services.ticker_universe import INGESTION_STATE_OK

router = APIRouter()

# Fixed trailing window for GET /tickers/{ticker}/history (design.md
# Decision 2). Not a query parameter in v1 — see design.md for rationale.
# Widened from 300 to 750 (~3 years) post-ship, 2026-08-12 — the original
# window read as too little visible chart history in real use.
HISTORY_WINDOW_SESSIONS = 750


@router.post("/tickers/{ticker}/load")
def load_ticker_endpoint(ticker: str):
    return load_ticker(ticker)


CATALOG_UNIVERSE_ROWS = """
SELECT symbol, exchange, icb_code2, listing_status
  FROM ticker_universe
 WHERE ingestion_state = ?
   AND COALESCE(fails_liquidity_filter, 0) = 0
   AND COALESCE(below_minimum_history, 0) = 0
 ORDER BY symbol
"""


def _catalog_entry(symbol: str, universe_row: tuple | None, load_row: tuple | None) -> dict:
    """One `GET /tickers` entry.

    Universe fields are null when the symbol has no universe row, rather than
    omitted — a client should not have to distinguish "field missing" from
    "value unknown" (`ticker-catalog`: null where the universe has no value).
    """
    _, exchange, industry_code, listing_status = universe_row or (None, None, None, None)
    features_computed = load_row[1] if load_row else None
    return {
        "ticker": symbol,
        # The model was trained and backtested on these
        # (`docs/MODEL_CARD.md`); every other entry is a ticker the system
        # merely knows about. These two sets are no longer identical, which
        # is the whole point of the catalog no longer being TRAINING_TICKERS.
        "in_training_set": symbol in TRAINING_TICKERS,
        "exchange": exchange,
        "industry_code": industry_code,
        "listing_status": listing_status,
        "loaded": load_row is not None,
        # A `tickers` row always sets this to 0/1 on write
        # (ticker_ingestion.load_ticker); NULL here would only be
        # pre-migration legacy data, which the migration's own backfill
        # already closes. Coerce defensively to False rather than surfacing
        # `null` for a ticker that IS loaded — `null` is reserved for "no row
        # at all".
        "features_computed": (
            bool(features_computed) if features_computed is not None else False
        )
        if load_row is not None
        else None,
        "last_loaded_at": load_row[2] if load_row else None,
    }


@router.get("/tickers")
def list_tickers_endpoint():
    """The ticker catalog, derived from the universe rather than from
    `TRAINING_TICKERS` (`ticker-catalog` MODIFIED requirement).

    Reads only: the universe, the `tickers` table, and the
    `TRAINING_TICKERS` constant. No `load_ticker`, no `vnstock` call, and no
    write — hundreds of never-loaded symbols in the universe must not turn a
    catalog request into an ingestion run.

    Every `TRAINING_TICKERS` member appears whether or not it passes the
    universe's default filters. Deliberate deviation from a literal reading
    of "tickers that pass the default filters": the model was trained on
    those nine, so the dashboard has to be able to show and predict them.
    Dropping one because a re-tuned liquidity threshold (task 7.2) crossed
    its measured value would leave the UI silently inconsistent with the
    model it serves. None of the nine fails a filter today — `SAB` at 0.103
    and `VIB` at 0.116 are the closest to the 0.15 cutoff — so this is a
    guard, not a current exception.
    """
    conn = get_connection()
    try:
        universe_rows = conn.execute(
            CATALOG_UNIVERSE_ROWS, (INGESTION_STATE_OK,)
        ).fetchall()
        training_rows = conn.execute(
            "SELECT symbol, exchange, icb_code2, listing_status "
            "FROM ticker_universe WHERE symbol IN ({})".format(
                ", ".join("?" for _ in TRAINING_TICKERS)
            ),
            tuple(TRAINING_TICKERS),
        ).fetchall()
        load_rows = conn.execute(
            "SELECT ticker, features_computed, last_loaded_at FROM tickers"
        ).fetchall()
    finally:
        conn.close()

    universe_by_symbol = {row[0]: row for row in universe_rows}
    universe_by_symbol.update({row[0]: row for row in training_rows})
    load_by_symbol = {row[0]: row for row in load_rows}

    # Training tickers first, in their declared order, so the dashboard's
    # fixed watchlist keeps the order it has always rendered in; then the
    # rest of the universe alphabetically.
    ordered = list(TRAINING_TICKERS) + [
        row[0] for row in universe_rows if row[0] not in set(TRAINING_TICKERS)
    ]
    tickers = [
        _catalog_entry(
            symbol, universe_by_symbol.get(symbol), load_by_symbol.get(symbol)
        )
        for symbol in ordered
    ]
    return {"tickers": tickers}


@router.get("/tickers/{ticker}/history")
def ticker_history_endpoint(ticker: str):
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT date, open, high, low, close, volume
            FROM (
                SELECT date, open, high, low, close, volume
                FROM ohlcv
                WHERE ticker = ?
                ORDER BY date DESC
                LIMIT ?
            )
            ORDER BY date ASC
            """,
            (ticker, HISTORY_WINDOW_SESSIONS),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail="Ticker not found")

    return {
        "ticker": ticker,
        "rows": [
            {
                "date": date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
            for date, open_, high, low, close, volume in rows
        ],
    }


@router.post("/tickers/{ticker}/backtest")
def backtest_ticker_endpoint(ticker: str):
    """Single-ticker walk-forward backtest (design.md Decision 12 / tasks.md
    5.1-5.3), for the "Backtest this ticker" action on a ticker outside
    `TRAINING_TICKERS` whose Confidence is `N/A`. Gated on
    `SINGLE_TICKER_BACKTEST_MIN_ROWS` clean+labeled feature rows — below
    that, returns `409` rather than attempting a backtest that would
    produce an empty or degenerate fold.
    """
    full_df = load_single_ticker_features(ticker)
    clean_df = filter_clean_labeled(full_df)

    if len(clean_df) < SINGLE_TICKER_BACKTEST_MIN_ROWS:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Not enough clean, labeled price history to backtest '{ticker}' yet "
                f"— needs at least {SINGLE_TICKER_BACKTEST_MIN_ROWS} clean+labeled rows, "
                f"has {len(clean_df)}."
            ),
        )

    results = run_single_ticker_backtest(full_df, clean_df)
    persist_backtest_predictions(results)

    return {
        "ticker": ticker,
        "rows_backtested": len(results),
        "folds": sorted(results["fold"].unique().tolist()),
    }
