import numpy as np
import pandas as pd
import xgboost as xgb
from fastapi import APIRouter, HTTPException, Request

from app.api.predictions import get_features_computed, get_latest_features_row
from app.db.connection import get_connection
from app.ml.backtest import ROLLING_HIT_RATE_WINDOW, compute_rolling_hit_rate
from app.ml.training import FEATURE_COLUMNS

router = APIRouter()

# Rule 3 / design.md Decision 13: Advice compares the predicted move against
# this fraction of the ticker's own trailing volatility — provisional per
# CLAUDE.md's domain rules, not a fixed absolute threshold.
ADVICE_VOLATILITY_COEFFICIENT = 0.5
ADVICE_VOLATILITY_WINDOW = 60


def _load_recent_closes(ticker: str, limit: int) -> pd.Series:
    """Most recent `limit` closes for `ticker`, ascending by date — the
    input `rolling_std(returns, 60 sessions)` (Rule 3) is computed from.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT close FROM (
                SELECT close, date FROM ohlcv WHERE ticker = ?
                ORDER BY date DESC LIMIT ?
            )
            ORDER BY date ASC
            """,
            (ticker, limit),
        ).fetchall()
    finally:
        conn.close()
    return pd.Series([row[0] for row in rows], dtype="float64")


def _compute_sentiment(row: dict) -> tuple[str, list[str]]:
    """Technical-proxy Sentiment (Rule 5) from the latest feature row's RSI,
    MACD, and Ichimoku (Tenkan/Kijun) position — never real news/NLP
    sentiment. Returns (label, inputs-used).
    """
    inputs = ["RSI", "MACD", "Ichimoku position"]
    bullish_votes = 0
    bearish_votes = 0

    rsi = row.get("rsi")
    if rsi is not None:
        if rsi >= 55:
            bullish_votes += 1
        elif rsi <= 45:
            bearish_votes += 1

    macd_histogram = row.get("macd_histogram")
    if macd_histogram is not None:
        if macd_histogram > 0:
            bullish_votes += 1
        elif macd_histogram < 0:
            bearish_votes += 1

    tenkan = row.get("tenkan_sen")
    kijun = row.get("kijun_sen")
    if tenkan is not None and kijun is not None:
        if tenkan > kijun:
            bullish_votes += 1
        elif tenkan < kijun:
            bearish_votes += 1

    if bullish_votes > bearish_votes:
        label = "bullish"
    elif bearish_votes > bullish_votes:
        label = "bearish"
    else:
        label = "neutral"

    return label, inputs


def _compute_advice(predicted_log_return: float, closes: pd.Series) -> str:
    """Volatility-relative Advice (Rule 3): compares the predicted move
    against `ADVICE_VOLATILITY_COEFFICIENT x rolling_std(returns,
    ADVICE_VOLATILITY_WINDOW)` computed on the ticker's own OHLCV closes.
    Maps to directional wording only — never "BUY"/"SELL" (Rule 6).
    """
    returns = closes.pct_change().dropna()
    if len(returns) < 2:
        return "HOLD"

    threshold = ADVICE_VOLATILITY_COEFFICIENT * returns.std()
    if not np.isfinite(threshold) or threshold == 0:
        return "HOLD"

    predicted_move = np.exp(predicted_log_return) - 1
    if predicted_move > threshold:
        return "up"
    if predicted_move < -threshold:
        return "down"
    return "HOLD"


@router.get("/tickers/{ticker}/insight")
def get_insight(ticker: str, request: Request):
    if get_features_computed(ticker) == 0:
        raise HTTPException(status_code=503, detail="Feature computation failed for this ticker")

    row = get_latest_features_row(ticker)
    if row is None:
        raise HTTPException(status_code=404, detail="Ticker has not been loaded")

    confidence_score = compute_rolling_hit_rate(ticker)
    confidence_basis = (
        f"{ROLLING_HIT_RATE_WINDOW}-prediction backtested hit-rate."
        if confidence_score is not None
        else "No backtested predictions for this ticker yet — needs more price "
        "history to backtest."
    )

    if row["near_gap"]:
        sentiment_proxy, sentiment_inputs = _compute_sentiment(row)
        return {
            "ticker": ticker,
            "as_of": row["date"],
            "status": "near_gap",
            "confidence_score": confidence_score,
            "confidence_basis": confidence_basis,
            "sentiment_proxy": sentiment_proxy,
            "sentiment_inputs": sentiment_inputs,
            "advice_text": None,
            "note": "A data gap prevents a current prediction, so Advice is unavailable.",
        }

    feature_matrix = pd.DataFrame([{col: row[col] for col in FEATURE_COLUMNS}])
    model: xgb.Booster = request.app.state.model
    predicted_log_return = float(model.predict(xgb.DMatrix(feature_matrix))[0])

    sentiment_proxy, sentiment_inputs = _compute_sentiment(row)
    closes = _load_recent_closes(ticker, ADVICE_VOLATILITY_WINDOW + 1)
    advice_text = _compute_advice(predicted_log_return, closes)

    return {
        "ticker": ticker,
        "as_of": row["date"],
        "status": "ok",
        "confidence_score": confidence_score,
        "confidence_basis": confidence_basis,
        "sentiment_proxy": sentiment_proxy,
        "sentiment_inputs": sentiment_inputs,
        "advice_text": advice_text,
        "note": None,
    }
