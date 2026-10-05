"""Train and serialise the HAR-RV linear volatility model.

Run once from the repo root:
    python backend/scripts/train_har_rv.py

Trains a linear regression on log-volatility using all tickers that have
sufficient OHLCV history (≥ 65 sessions), pools them, and serialises the
fitted model to backend/data/models/har_rv_model.pkl.

Expected in-sample corr ≥ 0.40 (Finding 5 baseline from
docs/DISCUSSION_model_direction.md). The script prints the achieved corr
and exits non-zero if it falls below 0.35 (sanity floor).
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

# Make backend/app importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.vnstock_guard  # noqa: F401 — must install before any vnstock import

from app.db.connection import get_connection
from app.ml.volatility import MODEL_PATH, build_training_dataset

CORR_SANITY_FLOOR = 0.35


def get_all_tickers() -> list[str]:
    """Return tickers from the modelling universe (passes quality filters).

    Falls back to all OHLCV tickers if the universe table doesn't exist or
    has no qualifying rows.
    """
    conn = get_connection()
    try:
        # Prefer the quality-filtered modelling universe
        try:
            rows = conn.execute(
                """
                SELECT symbol FROM ticker_universe
                WHERE ingestion_state = 'ok'
                  AND fails_liquidity_filter = 0
                  AND below_minimum_history = 0
                ORDER BY symbol
                """
            ).fetchall()
            if rows:
                return [r[0] for r in rows]
        except Exception:
            pass
        # Fallback: all tickers in OHLCV
        rows = conn.execute(
            "SELECT DISTINCT ticker FROM ohlcv ORDER BY ticker"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def main() -> None:
    tickers = get_all_tickers()
    print(f"Found {len(tickers)} tickers in OHLCV table.")

    all_X: list[pd.DataFrame] = []
    all_y: list[pd.Series] = []

    for ticker in tickers:
        result = build_training_dataset(ticker)
        if result is None:
            continue
        X, y = result
        all_X.append(X)
        all_y.append(y)

    if not all_X:
        print("ERROR: No tickers with sufficient history. Aborting.", file=sys.stderr)
        sys.exit(1)

    X_pool = pd.concat(all_X, ignore_index=True)
    y_pool = pd.concat(all_y, ignore_index=True)
    print(f"Pooled dataset: {len(X_pool):,} rows from {len(all_X)} tickers.")

    model = LinearRegression()
    model.fit(X_pool, y_pool)

    y_pred = model.predict(X_pool)
    corr = float(np.corrcoef(y_pool, y_pred)[0, 1])
    print(f"In-sample correlation (log-volatility): {corr:.4f}")

    if corr < CORR_SANITY_FLOOR:
        print(
            f"ERROR: Corr {corr:.4f} is below sanity floor {CORR_SANITY_FLOOR}. "
            "Check data quality.",
            file=sys.stderr,
        )
        sys.exit(1)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    print(f"Model saved to {MODEL_PATH}")
    print("Done.")


if __name__ == "__main__":
    main()
