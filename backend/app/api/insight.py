import numpy as np
import pandas as pd
import xgboost as xgb
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.predictions import get_features_computed, get_latest_features_row
from app.db.connection import get_connection
from app.ml.backtest import ROLLING_HIT_RATE_WINDOW, compute_rolling_hit_rate
from app.ml.training import FEATURE_COLUMNS
from app.services.ohlcv_quality_gate import (
    hard_flagged_dates,
    neutralise_hard_flagged_returns as _neutralise,
)

router = APIRouter()

# Rule 3 / design.md Decision 13: Advice compares the predicted move against
# this fraction of the ticker's own trailing volatility — provisional per
# CLAUDE.md's domain rules, not a fixed absolute threshold.
ADVICE_VOLATILITY_COEFFICIENT = 0.5
ADVICE_VOLATILITY_WINDOW = 60


def _load_recent_closes(ticker: str, limit: int) -> pd.DataFrame:
    """Most recent `limit` sessions for `ticker`, ascending by date — the
    input `rolling_std(returns, 60 sessions)` (Rule 3) is computed from.

    Returns `date` alongside `close` so the quality gate's hard-flagged
    sessions can be identified; a single spurious return inside the window
    would otherwise dominate `returns.std()` and so the Advice threshold.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT date, close FROM (
                SELECT close, date FROM ohlcv WHERE ticker = ?
                ORDER BY date DESC LIMIT ?
            )
            ORDER BY date ASC
            """,
            (ticker, limit),
        ).fetchall()
    finally:
        conn.close()
    return pd.DataFrame(
        {
            "date": [str(row[0]) for row in rows],
            "close": pd.Series([row[1] for row in rows], dtype="float64"),
        }
    )


def _load_hard_flagged(ticker: str) -> set[str]:
    """Hard-flagged sessions for `ticker`, read through this module's own
    `get_connection` so it follows wherever that has been pointed."""
    conn = get_connection()
    try:
        return hard_flagged_dates(ticker, conn)
    finally:
        conn.close()


def _compute_sentiment(row: dict) -> tuple[str | None, list[str]]:
    """Technical-proxy Sentiment (Rule 5) from the latest feature row's RSI,
    MACD, and Ichimoku (Tenkan/Kijun) position — never real news/NLP
    sentiment. Returns (label, inputs-actually-used).

    `inputs` names only the indicators that were present, and the label is
    None when none of them were. A fixed list would claim a basis the row
    does not have: a blacked-out or warm-up row has every indicator null, so
    each guard below skips and the votes stay tied — which would otherwise
    render as a confident "neutral" Technical Signal derived from nothing,
    indistinguishable from a real reading.
    """
    inputs: list[str] = []
    bullish_votes = 0
    bearish_votes = 0

    rsi = row.get("rsi")
    if rsi is not None:
        inputs.append("RSI")
        if rsi >= 55:
            bullish_votes += 1
        elif rsi <= 45:
            bearish_votes += 1

    macd_histogram = row.get("macd_histogram")
    if macd_histogram is not None:
        inputs.append("MACD")
        if macd_histogram > 0:
            bullish_votes += 1
        elif macd_histogram < 0:
            bearish_votes += 1

    tenkan = row.get("tenkan_sen")
    kijun = row.get("kijun_sen")
    if tenkan is not None and kijun is not None:
        inputs.append("Ichimoku position")
        if tenkan > kijun:
            bullish_votes += 1
        elif tenkan < kijun:
            bearish_votes += 1

    if not inputs:
        return None, []

    if bullish_votes > bearish_votes:
        label = "bullish"
    elif bearish_votes > bullish_votes:
        label = "bearish"
    else:
        label = "neutral"

    return label, inputs


def _compute_advice(
    predicted_log_return: float,
    recent: pd.DataFrame,
    hard_flagged: set[str] | None = None,
) -> str:
    """Volatility-relative Advice (Rule 3): compares the predicted move
    against `ADVICE_VOLATILITY_COEFFICIENT x rolling_std(returns,
    ADVICE_VOLATILITY_WINDOW)` computed on the ticker's own OHLCV closes.
    Maps to directional wording only — never "BUY"/"SELL" (Rule 6).

    Rule 3's volatility-relative design and its provisional `0.5` coefficient
    are unchanged. Returns at sessions the `ohlcv-quality-gate` hard-flagged
    are dropped before the standard deviation is taken: `VHM`'s 2018-08-14
    step, for instance, is a ~50% single-session move that would inflate a
    60-session standard deviation roughly tenfold and push every prediction
    in that window to "HOLD".
    """
    returns = _neutralise(
        recent["date"], recent["close"].pct_change(), hard_flagged or set()
    ).dropna()
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

    # Deprecation headers — this endpoint is superseded by POST /tickers/{ticker}/debate
    _DEPRECATION_HEADERS = {
        "Deprecation": "true",
        "Link": '</tickers/{ticker}/debate>; rel="successor-version"',
    }

    confidence_score = compute_rolling_hit_rate(ticker)
    confidence_basis = (
        f"{ROLLING_HIT_RATE_WINDOW}-prediction backtested hit-rate."
        if confidence_score is not None
        else "No backtested predictions for this ticker yet — needs more price "
        "history to backtest."
    )

    if row["near_gap"]:
        sentiment_proxy, sentiment_inputs = _compute_sentiment(row)
        return JSONResponse(
            content={
                "ticker": ticker,
                "as_of": row["date"],
                "status": "near_gap",
                "confidence_score": confidence_score,
                "confidence_basis": confidence_basis,
                "sentiment_proxy": sentiment_proxy,
                "sentiment_inputs": sentiment_inputs,
                "advice_text": None,
                "note": "A data gap prevents a current prediction, so Advice is unavailable.",
                "deprecated": True,
            },
            headers=_DEPRECATION_HEADERS,
        )

    if any(row[column] is None for column in FEATURE_COLUMNS):
        sentiment_proxy, sentiment_inputs = _compute_sentiment(row)
        return JSONResponse(
            content={
                "ticker": ticker,
                "as_of": row["date"],
                "status": "indicators_unavailable",
                "confidence_score": confidence_score,
                "confidence_basis": confidence_basis,
                "sentiment_proxy": sentiment_proxy,
                "sentiment_inputs": sentiment_inputs,
                "advice_text": None,
                "note": "A data-quality flag on recent sessions prevents a current "
                "prediction, so Advice is unavailable.",
                "deprecated": True,
            },
            headers=_DEPRECATION_HEADERS,
        )

    feature_matrix = pd.DataFrame([{col: row[col] for col in FEATURE_COLUMNS}])
    model: xgb.Booster = request.app.state.model
    predicted_log_return = float(model.predict(xgb.DMatrix(feature_matrix))[0])

    sentiment_proxy, sentiment_inputs = _compute_sentiment(row)
    recent = _load_recent_closes(ticker, ADVICE_VOLATILITY_WINDOW + 1)
    advice_text = _compute_advice(
        predicted_log_return, recent, _load_hard_flagged(ticker)
    )

    return JSONResponse(
        content={
            "ticker": ticker,
            "as_of": row["date"],
            "status": "ok",
            "confidence_score": confidence_score,
            "confidence_basis": confidence_basis,
            "sentiment_proxy": sentiment_proxy,
            "sentiment_inputs": sentiment_inputs,
            "advice_text": advice_text,
            "note": None,
            "deprecated": True,
        },
        headers=_DEPRECATION_HEADERS,
    )
