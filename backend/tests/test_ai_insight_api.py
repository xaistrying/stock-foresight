import sqlite3
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.api.insight as insight_module
from app.db.schema import CREATE_BACKTEST_PREDICTIONS_TABLE, CREATE_FEATURES_TABLE, CREATE_OHLCV_TABLE, CREATE_TICKERS_TABLE
from app.main import app
from app.ml.training import FEATURE_COLUMNS

INSERT_FEATURES_ROW = """
INSERT INTO features (ticker, date, {columns}, target, near_gap, computed_at)
VALUES (?, ?, {placeholders}, ?, ?, ?)
""".format(
    columns=", ".join(FEATURE_COLUMNS),
    placeholders=", ".join("?" for _ in FEATURE_COLUMNS),
)


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKERS_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.execute(CREATE_BACKTEST_PREDICTIONS_TABLE)
    conn.commit()
    conn.close()

    monkeypatch.setattr(insight_module, "get_connection", lambda: sqlite3.connect(db_path))
    import app.api.predictions as predictions_module
    import app.ml.backtest as backtest_module

    monkeypatch.setattr(predictions_module, "get_connection", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(backtest_module, "get_connection", lambda: sqlite3.connect(db_path))

    with TestClient(app) as test_client:
        yield test_client, db_path


def seed_features_row(db_path, ticker, feature_date, near_gap=0, feature_values=None):
    conn = sqlite3.connect(db_path)
    values = feature_values if feature_values is not None else [1.0 for _ in FEATURE_COLUMNS]
    conn.execute(
        INSERT_FEATURES_ROW,
        (ticker, feature_date, *values, 0.01, near_gap, "2024-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()


def seed_ohlcv_rows(db_path, ticker, closes, start=date(2024, 1, 1)):
    conn = sqlite3.connect(db_path)
    rows = [
        (
            ticker,
            (start + timedelta(days=i)).isoformat(),
            close,
            close + 0.5,
            close - 0.5,
            close,
            1000,
        )
        for i, close in enumerate(closes)
    ]
    conn.executemany(
        "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def seed_backtest_predictions(db_path, ticker, num_rows, hit_count):
    conn = sqlite3.connect(db_path)
    rows = [
        (
            ticker,
            (date(2024, 1, 1) + timedelta(days=i)).isoformat(),
            0,
            0.01,
            0.01,
            1 if i < hit_count else 0,
        )
        for i in range(num_rows)
    ]
    conn.executemany(
        "INSERT INTO backtest_predictions (ticker, date, fold, predicted, actual, hit) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_insight_returns_real_confidence_for_ticker_with_backtest_rows(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-05")
    seed_ohlcv_rows(db_path, "VIB", [10.0 + 0.1 * i for i in range(70)])
    seed_backtest_predictions(db_path, "VIB", 60, hit_count=45)

    response = test_client.get("/tickers/VIB/insight")

    assert response.status_code == 200
    body = response.json()
    assert body["confidence_score"] == pytest.approx(45 / 60)
    assert body["confidence_basis"] == "60-prediction backtested hit-rate."


def test_insight_returns_null_confidence_with_explanatory_basis_when_no_backtest_rows(client):
    test_client, db_path = client
    seed_features_row(db_path, "FAKE", "2024-01-05")
    seed_ohlcv_rows(db_path, "FAKE", [10.0 + 0.1 * i for i in range(70)])

    response = test_client.get("/tickers/FAKE/insight")

    assert response.status_code == 200
    body = response.json()
    assert body["confidence_score"] is None
    assert body["confidence_basis"] is not None
    assert body["confidence_basis"] != ""


def test_insight_computes_sentiment_and_advice_for_ticker_outside_training_tickers(client):
    test_client, db_path = client
    assert "FAKE" not in __import__("app.ml.training", fromlist=["TRAINING_TICKERS"]).TRAINING_TICKERS
    seed_features_row(db_path, "FAKE", "2024-01-05")
    seed_ohlcv_rows(db_path, "FAKE", [10.0 + 0.1 * i for i in range(70)])

    response = test_client.get("/tickers/FAKE/insight")

    assert response.status_code == 200
    body = response.json()
    assert body["sentiment_proxy"] in {"bullish", "bearish", "neutral"}
    assert set(body["sentiment_inputs"]) == {"RSI", "MACD", "Ichimoku position"}
    assert body["advice_text"] is not None


def test_insight_sentiment_inputs_always_name_all_three_indicators(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-05")
    seed_ohlcv_rows(db_path, "VIB", [10.0 + 0.1 * i for i in range(70)])

    response = test_client.get("/tickers/VIB/insight")

    body = response.json()
    assert "RSI" in body["sentiment_inputs"]
    assert "MACD" in body["sentiment_inputs"]
    assert "Ichimoku position" in body["sentiment_inputs"]


@pytest.mark.parametrize(
    "rsi, macd_histogram, tenkan_sen, kijun_sen",
    [
        (70.0, 0.5, 12.0, 10.0),
        (30.0, -0.5, 8.0, 10.0),
        (50.0, 0.0, 10.0, 10.0),
        (90.0, 5.0, 20.0, 5.0),
        (10.0, -5.0, 5.0, 20.0),
        (60.0, -2.0, 5.0, 5.0),
    ],
)
def test_insight_advice_text_never_contains_buy_or_sell(
    client, rsi, macd_histogram, tenkan_sen, kijun_sen
):
    test_client, db_path = client
    feature_values = []
    for col in FEATURE_COLUMNS:
        if col == "rsi":
            feature_values.append(rsi)
        elif col == "macd_histogram":
            feature_values.append(macd_histogram)
        elif col == "tenkan_sen":
            feature_values.append(tenkan_sen)
        elif col == "kijun_sen":
            feature_values.append(kijun_sen)
        else:
            feature_values.append(1.0)
    seed_features_row(db_path, "VIB", "2024-01-05", feature_values=feature_values)
    seed_ohlcv_rows(db_path, "VIB", [10.0 + ((-1) ** i) * 0.05 * i for i in range(70)])

    response = test_client.get("/tickers/VIB/insight")

    assert response.status_code == 200
    body = response.json()
    assert body["advice_text"] is not None
    assert "BUY" not in body["advice_text"].upper()
    assert "SELL" not in body["advice_text"].upper()
    assert body["advice_text"] in {"HOLD", "up", "down"}


def test_insight_returns_404_when_ticker_never_loaded(client):
    test_client, _ = client

    response = test_client.get("/tickers/UNKNOWN/insight")

    assert response.status_code == 404


def test_insight_returns_5xx_when_features_computation_failed(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-05")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO tickers (ticker, last_loaded_at, features_computed) "
        "VALUES ('VIB', '2024-01-01T00:00:00', 0)"
    )
    conn.commit()
    conn.close()

    response = test_client.get("/tickers/VIB/insight")

    assert response.status_code >= 500
    assert response.status_code < 600


def test_insight_returns_near_gap_status_with_no_advice(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-05", near_gap=1)
    seed_ohlcv_rows(db_path, "VIB", [10.0 + 0.1 * i for i in range(70)])

    response = test_client.get("/tickers/VIB/insight")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "near_gap"
    assert body["advice_text"] is None
