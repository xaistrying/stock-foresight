import sqlite3

import pytest
from fastapi.testclient import TestClient

import app.api.predictions as predictions_module
import app.services.ticker_ingestion as ticker_ingestion_module
from app.db.schema import CREATE_FEATURES_TABLE, CREATE_OHLCV_TABLE, CREATE_TICKERS_TABLE
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
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        predictions_module, "get_connection", lambda: sqlite3.connect(db_path)
    )

    with TestClient(app) as test_client:
        yield test_client, db_path


def seed_features_row(db_path, ticker, date, near_gap):
    conn = sqlite3.connect(db_path)
    feature_values = [1.0 for _ in FEATURE_COLUMNS]
    conn.execute(
        INSERT_FEATURES_ROW,
        (ticker, date, *feature_values, 0.01, near_gap, "2024-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()


def seed_ticker_row(db_path, ticker, features_computed):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO tickers (ticker, available_since, possibly_truncated_by_tier, "
        "last_loaded_at, features_computed) VALUES (?, ?, ?, ?, ?)",
        (ticker, "2024-01-01", 0, "2024-01-01T00:00:00", features_computed),
    )
    conn.commit()
    conn.close()


def test_prediction_endpoint_returns_ok_for_clean_latest_row(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-05", near_gap=0)

    response = test_client.get("/tickers/VIB/prediction")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "predicted_log_return" in body
    assert "confidence_score" not in body
    assert "sentiment_proxy" not in body
    assert "advice_text" not in body


def test_prediction_endpoint_returns_404_when_ticker_never_loaded(client, monkeypatch):
    test_client, db_path = client

    load_ticker_spy = []
    monkeypatch.setattr(
        ticker_ingestion_module,
        "load_ticker",
        lambda ticker: load_ticker_spy.append(ticker),
    )
    mkt_spy = []
    monkeypatch.setattr(
        ticker_ingestion_module.mkt, "equity", lambda *a, **k: mkt_spy.append((a, k))
    )

    response = test_client.get("/tickers/UNKNOWN/prediction")

    assert response.status_code == 404
    assert load_ticker_spy == []
    assert mkt_spy == []


def test_prediction_endpoint_returns_5xx_when_features_computed_failed(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-05", near_gap=0)
    seed_ticker_row(db_path, "VIB", features_computed=0)

    response = test_client.get("/tickers/VIB/prediction")

    assert response.status_code >= 500
    assert response.status_code < 600


def test_prediction_endpoint_returns_ok_when_features_computed_is_null(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-05", near_gap=0)
    seed_ticker_row(db_path, "VIB", features_computed=None)

    response = test_client.get("/tickers/VIB/prediction")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_prediction_endpoint_returns_near_gap_for_near_gap_latest_row(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-05", near_gap=1)

    response = test_client.get("/tickers/VIB/prediction")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "near_gap"
    assert "predicted_log_return" not in body


def test_prediction_endpoint_does_not_walk_back_to_older_clean_row(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-01", near_gap=0)
    seed_features_row(db_path, "VIB", "2024-01-05", near_gap=1)

    response = test_client.get("/tickers/VIB/prediction")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "near_gap"
    assert "predicted_log_return" not in body


def test_prediction_endpoint_returns_near_gap_when_features_computed_is_null(client):
    test_client, db_path = client
    seed_features_row(db_path, "VIB", "2024-01-05", near_gap=1)
    seed_ticker_row(db_path, "VIB", features_computed=None)

    response = test_client.get("/tickers/VIB/prediction")

    assert response.status_code == 200
    assert response.json()["status"] == "near_gap"
