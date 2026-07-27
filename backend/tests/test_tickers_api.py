import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.services.ticker_ingestion as ticker_ingestion
from app.db.schema import CREATE_OHLCV_TABLE, CREATE_TICKERS_TABLE
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKERS_TABLE)
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        ticker_ingestion, "get_connection", lambda: sqlite3.connect(db_path)
    )

    df = pd.DataFrame(
        {
            "time": pd.to_datetime(["2024-01-02 07:00:00", "2024-01-03 07:00:00"]),
            "open": [10.0, 11.0],
            "high": [10.5, 11.5],
            "low": [9.5, 10.5],
            "close": [10.2, 11.2],
            "volume": [1000, 1100],
        }
    )

    class FakeEquity:
        def ohlcv(self, **kwargs):
            return df.copy()

    monkeypatch.setattr(ticker_ingestion.mkt, "equity", lambda ticker: FakeEquity())

    with TestClient(app) as test_client:
        yield test_client


def test_load_endpoint_succeeds_on_first_load_and_reload(client):
    first_response = client.post("/tickers/VIB/load")
    assert first_response.status_code == 200
    assert first_response.json()["rows_loaded"] == 2

    reload_response = client.post("/tickers/VIB/load")
    assert reload_response.status_code == 200
    assert reload_response.json()["rows_loaded"] == 2
