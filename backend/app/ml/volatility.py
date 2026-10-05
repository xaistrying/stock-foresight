"""HAR-RV (Heterogeneous Autoregressive Realized Volatility) linear model.

Trains on close-to-close realized volatility using 5-, 20-, and 60-session
trailing windows. Output is forward 5-session realized volatility (Rule 1).

Finding 5 (docs/DISCUSSION_model_direction.md): linear regression on
log-volatility achieves corr ≈ 0.479, outperforming tuned XGBoost (0.471)
because log-volatility is close to linear-additive in its predictors.

Public API:
    predict_volatility_range(ticker) -> float | None
        Returns the predicted ±% range for the next 5 trading sessions,
        or None if insufficient history. Output is a percentage (Rule 2 —
        never a raw log return).
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "har_rv_model.pkl"

# Minimum sessions needed to compute all three HAR windows + target
MIN_SESSIONS = 65  # 60 for longest window + 5 for forward target


def _load_ohlcv(ticker: str) -> pd.DataFrame:
    """Load close prices for a ticker from the OHLCV table, ascending date."""
    from app.db.connection import get_connection

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT date, close FROM ohlcv WHERE ticker = ? ORDER BY date ASC",
            (ticker,),
        ).fetchall()
    finally:
        conn.close()
    return pd.DataFrame(rows, columns=["date", "close"])


def _build_har_features(closes: pd.Series) -> pd.DataFrame:
    """Compute HAR-RV features from a close price series.

    Returns a DataFrame with columns: rv5, rv20, rv60
    where rvN = trailing N-session realized volatility (std of log returns).
    Index aligns with the closes index.
    """
    log_returns = np.log(closes / closes.shift(1))

    def rolling_vol(n: int) -> pd.Series:
        return log_returns.rolling(n).std()

    return pd.DataFrame(
        {
            "rv5": rolling_vol(5),
            "rv20": rolling_vol(20),
            "rv60": rolling_vol(60),
        }
    )


def build_training_dataset(ticker: str) -> tuple[pd.DataFrame, pd.Series] | None:
    """Build (X, y) for a single ticker.

    y = forward 5-session realized volatility (Rule 1).
    X = rv5, rv20, rv60 at each session.
    Returns None if the ticker has fewer than MIN_SESSIONS rows or
    insufficient valid rows after cleaning.
    """
    df = _load_ohlcv(ticker)
    if len(df) < MIN_SESSIONS:
        return None

    # Drop zero / negative closes (stale-price / delisted artefacts)
    df = df[df["close"] > 0].copy()
    if len(df) < MIN_SESSIONS:
        return None

    features = _build_har_features(df["close"])
    log_returns = np.log(df["close"] / df["close"].shift(1))

    # Forward 5-session realized volatility as target
    target_vals: list[float | None] = []
    for i in range(len(df)):
        window = log_returns.iloc[i + 1 : i + 6]
        if len(window) < 5:
            target_vals.append(None)
        else:
            val = window.std()
            target_vals.append(float(val) if np.isfinite(val) else None)

    target = pd.Series(target_vals, index=df.index)

    combined = features.copy()
    combined["target"] = target
    combined = combined.dropna()
    # Also drop any remaining inf/-inf from extreme log-return spikes
    combined = combined.replace([np.inf, -np.inf], np.nan).dropna()

    # Remove last 5 rows where forward target cannot be computed
    combined = combined.iloc[:-5]
    if len(combined) < 10:
        return None

    X = combined[["rv5", "rv20", "rv60"]]
    # log-volatility as target (Finding 5: linear model on log-vol)
    y = np.log(combined["target"].clip(lower=1e-10))
    # Drop any remaining NaN/inf in y
    mask = np.isfinite(y)
    return X[mask], y[mask]


def predict_volatility_range(ticker: str) -> float | None:
    """Predict the ±% volatility range for the next 5 trading sessions.

    Loads har_rv_model.pkl and the ticker's latest 60 OHLCV sessions.
    Returns a positive float (percentage) or None if:
    - Model file does not exist
    - Ticker has fewer than 60 OHLCV sessions
    - Prediction fails for any reason

    Rule 2: output is a percentage, never a raw log return or log volatility.
    Rule 1: horizon is 5 trading sessions.
    """
    if not MODEL_PATH.exists():
        logger.warning("HAR-RV model not found at %s — run train_har_rv.py", MODEL_PATH)
        return None

    try:
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)

        df = _load_ohlcv(ticker)
        if len(df) < 60:
            return None

        # Use only the most recent 65 rows to compute the three rolling windows
        recent = df.tail(65)
        features = _build_har_features(recent["close"])
        latest_row = features.dropna().tail(1)
        if latest_row.empty:
            return None

        log_vol_pred = float(model.predict(latest_row[["rv5", "rv20", "rv60"]])[0])
        # Convert log-volatility back to realized volatility, then to percentage
        vol_pred = np.exp(log_vol_pred)
        range_pct = round(float(vol_pred * 100), 2)
        return max(range_pct, 0.0)

    except Exception as exc:
        logger.warning("Volatility prediction failed for %s: %s", ticker, exc)
        return None
