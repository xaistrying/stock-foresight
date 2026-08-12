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

router = APIRouter()

# Fixed trailing window for GET /tickers/{ticker}/history (design.md
# Decision 2). Not a query parameter in v1 — see design.md for rationale.
# Widened from 300 to 750 (~3 years) post-ship, 2026-08-12 — the original
# window read as too little visible chart history in real use.
HISTORY_WINDOW_SESSIONS = 750


@router.post("/tickers/{ticker}/load")
def load_ticker_endpoint(ticker: str):
    return load_ticker(ticker)


@router.get("/tickers")
def list_tickers_endpoint():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT ticker, features_computed, last_loaded_at FROM tickers"
        ).fetchall()
    finally:
        conn.close()
    status_by_ticker = {row[0]: row for row in rows}

    tickers = []
    for ticker in TRAINING_TICKERS:
        row = status_by_ticker.get(ticker)
        if row is None:
            tickers.append(
                {
                    "ticker": ticker,
                    "loaded": False,
                    "features_computed": None,
                    "last_loaded_at": None,
                }
            )
        else:
            _, features_computed, last_loaded_at = row
            tickers.append(
                {
                    "ticker": ticker,
                    "loaded": True,
                    # A `tickers` row always sets this to 0/1 on write
                    # (ticker_ingestion.load_ticker); NULL here would only
                    # be pre-migration legacy data, which the migration's
                    # own backfill already closes. Coerce defensively to
                    # False rather than surfacing `null` for a ticker that
                    # IS loaded — `null` is reserved for "no row at all".
                    "features_computed": bool(features_computed)
                    if features_computed is not None
                    else False,
                    "last_loaded_at": last_loaded_at,
                }
            )
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
