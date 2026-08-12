import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.api.tickers as tickers_api
import app.main as main_module
import app.ml.feature_engineering as feature_engineering
import app.services.ticker_ingestion as ticker_ingestion
from app.db.schema import CREATE_FEATURES_TABLE, CREATE_OHLCV_TABLE, CREATE_TICKERS_TABLE
from app.main import app
from app.ml.training import TRAINING_TICKERS


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
        ticker_ingestion, "get_connection", lambda: sqlite3.connect(db_path)
    )
    monkeypatch.setattr(
        feature_engineering, "get_connection", lambda: sqlite3.connect(db_path)
    )
    monkeypatch.setattr(
        tickers_api, "get_connection", lambda: sqlite3.connect(db_path)
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
        test_client.db_path = db_path
        yield test_client


def test_load_endpoint_succeeds_on_first_load_and_reload(client):
    first_response = client.post("/tickers/VIB/load")
    assert first_response.status_code == 200
    assert first_response.json()["rows_loaded"] == 2

    reload_response = client.post("/tickers/VIB/load")
    assert reload_response.status_code == 200
    assert reload_response.json()["rows_loaded"] == 2


def test_startup_fails_when_model_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "MODEL_PATH", tmp_path / "missing_model.json")

    with pytest.raises(Exception):
        with TestClient(app):
            pass


def test_startup_loads_model_and_reuses_it_across_requests(client):
    assert app.state.model is not None
    loaded_model = app.state.model

    client.post("/tickers/VIB/load")
    assert app.state.model is loaded_model

    client.post("/tickers/VIB/load")
    assert app.state.model is loaded_model


def test_list_tickers_returns_exactly_training_tickers(client):
    response = client.get("/tickers")
    assert response.status_code == 200
    body = response.json()
    returned = [entry["ticker"] for entry in body["tickers"]]
    assert returned == TRAINING_TICKERS


def test_list_tickers_never_loaded_ticker_has_not_loaded_status(client):
    response = client.get("/tickers")
    body = response.json()
    entry = next(e for e in body["tickers"] if e["ticker"] == "VIB")
    assert entry["loaded"] is False
    assert entry["features_computed"] is None
    assert entry["last_loaded_at"] is None


def test_list_tickers_loaded_ticker_reflects_tickers_row(client):
    load_response = client.post("/tickers/VIB/load")
    assert load_response.status_code == 200

    response = client.get("/tickers")
    body = response.json()
    entry = next(e for e in body["tickers"] if e["ticker"] == "VIB")
    assert entry["loaded"] is True
    assert entry["features_computed"] is not None
    assert entry["last_loaded_at"] is not None


def test_list_tickers_row_with_null_features_computed_coerces_to_false(client):
    conn = sqlite3.connect(client.db_path)
    try:
        conn.execute(
            "INSERT INTO tickers (ticker, last_loaded_at, features_computed) "
            "VALUES ('VIB', '2024-01-01T00:00:00', NULL)"
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/tickers")
    body = response.json()
    entry = next(e for e in body["tickers"] if e["ticker"] == "VIB")
    assert entry["loaded"] is True
    assert entry["features_computed"] is False


def test_list_tickers_makes_no_vnstock_call_and_writes_no_rows(client, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("GET /tickers must not call vnstock")

    monkeypatch.setattr(ticker_ingestion.mkt, "equity", fail_if_called)

    response = client.get("/tickers")
    assert response.status_code == 200

    conn = sqlite3.connect(client.db_path)
    try:
        ohlcv_count = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
        tickers_count = conn.execute("SELECT COUNT(*) FROM tickers").fetchone()[0]
        features_count = conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    finally:
        conn.close()
    assert ohlcv_count == 0
    assert tickers_count == 0
    assert features_count == 0


def _insert_ohlcv_rows(db_path, ticker, num_rows):
    conn = sqlite3.connect(db_path)
    try:
        start = date(2020, 1, 1)
        rows = [
            (
                ticker,
                (start + timedelta(days=i)).isoformat(),
                10.0 + i,
                10.5 + i,
                9.5 + i,
                10.2 + i,
                1000 + i,
            )
            for i in range(num_rows)
        ]
        conn.executemany(
            "INSERT INTO ohlcv (ticker, date, open, high, low, close, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_history_returns_window_most_recent_rows_ascending_when_more_stored(client):
    _insert_ohlcv_rows(client.db_path, "VIB", tickers_api.HISTORY_WINDOW_SESSIONS + 50)

    response = client.get("/tickers/VIB/history")
    assert response.status_code == 200
    body = response.json()
    rows = body["rows"]
    assert len(rows) == tickers_api.HISTORY_WINDOW_SESSIONS
    dates = [row["date"] for row in rows]
    assert dates == sorted(dates)
    # The most recent HISTORY_WINDOW_SESSIONS rows are the last ones inserted.
    expected_start = (date(2020, 1, 1) + timedelta(days=50)).isoformat()
    assert dates[0] == expected_start


def test_history_returns_all_rows_when_fewer_than_window(client):
    _insert_ohlcv_rows(client.db_path, "VIB", 5)

    response = client.get("/tickers/VIB/history")
    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == 5
    dates = [row["date"] for row in body["rows"]]
    assert dates == sorted(dates)


def test_history_never_loaded_ticker_returns_404_with_no_side_effect(client, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("GET /history must not call vnstock or load_ticker")

    monkeypatch.setattr(ticker_ingestion.mkt, "equity", fail_if_called)

    response = client.get("/tickers/VIB/history")
    assert response.status_code == 404

    conn = sqlite3.connect(client.db_path)
    try:
        ohlcv_count = conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]
    finally:
        conn.close()
    assert ohlcv_count == 0


def test_history_rows_never_contain_indicator_or_near_gap_fields(client):
    _insert_ohlcv_rows(client.db_path, "VIB", 3)

    response = client.get("/tickers/VIB/history")
    body = response.json()
    for row in body["rows"]:
        assert set(row.keys()) == {"date", "open", "high", "low", "close", "volume"}
        assert "near_gap" not in row


def test_history_served_for_loaded_ticker_outside_training_tickers(client):
    assert "FAKE" not in TRAINING_TICKERS
    _insert_ohlcv_rows(client.db_path, "FAKE", 3)

    response = client.get("/tickers/FAKE/history")
    assert response.status_code == 200
    assert response.json()["ticker"] == "FAKE"
