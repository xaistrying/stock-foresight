import pandas as pd
import xgboost as xgb
from fastapi import APIRouter, HTTPException, Request

from app.db.connection import get_connection
from app.ml.training import FEATURE_COLUMNS

router = APIRouter()

FEATURES_COMPUTED_FOR_TICKER = """
SELECT features_computed
FROM tickers
WHERE ticker = ?
"""

LATEST_FEATURES_ROW = """
SELECT date, near_gap, {columns}
FROM features
WHERE ticker = ?
ORDER BY date DESC
LIMIT 1
""".format(columns=", ".join(FEATURE_COLUMNS))


def get_features_computed(ticker: str) -> int | None:
    conn = get_connection()
    try:
        cursor = conn.execute(FEATURES_COMPUTED_FOR_TICKER, (ticker,))
        row = cursor.fetchone()
        return row[0] if row is not None else None
    finally:
        conn.close()


def get_latest_features_row(ticker: str) -> dict | None:
    conn = get_connection()
    try:
        cursor = conn.execute(LATEST_FEATURES_ROW, (ticker,))
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))
    finally:
        conn.close()


@router.get("/tickers/{ticker}/prediction")
def get_prediction(ticker: str, request: Request):
    if get_features_computed(ticker) == 0:
        raise HTTPException(status_code=503, detail="Feature computation failed for this ticker")

    row = get_latest_features_row(ticker)
    if row is None:
        raise HTTPException(status_code=404, detail="Ticker has not been loaded")

    if row["near_gap"]:
        return {
            "ticker": ticker,
            "as_of": row["date"],
            "status": "near_gap",
        }

    feature_matrix = pd.DataFrame([{col: row[col] for col in FEATURE_COLUMNS}])
    model: xgb.Booster = request.app.state.model
    predicted_log_return = float(model.predict(xgb.DMatrix(feature_matrix))[0])

    return {
        "ticker": ticker,
        "as_of": row["date"],
        "status": "ok",
        "predicted_log_return": predicted_log_return,
    }
