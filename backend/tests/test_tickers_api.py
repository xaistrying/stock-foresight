import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.api.tickers as tickers_api
import app.main as main_module
import app.ml.feature_engineering as feature_engineering
import app.services.ohlcv_quality_gate as ohlcv_quality_gate
import app.services.ticker_ingestion as ticker_ingestion
import app.services.ticker_universe as ticker_universe
from app.db.schema import (
    CREATE_FEATURES_TABLE,
    CREATE_OHLCV_QUALITY_FLAGS_TABLE,
    CREATE_OHLCV_TABLE,
    CREATE_TICKER_UNIVERSE_TABLE,
    CREATE_TICKERS_TABLE,
)
from app.main import app
from app.ml.training import TRAINING_TICKERS


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKERS_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.execute(CREATE_OHLCV_QUALITY_FLAGS_TABLE)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    conn.commit()
    conn.close()

    # A load now also touches the quality-gate sidecar and the universe, each
    # through its own module-level `get_connection`.
    for module in (
        ticker_ingestion,
        feature_engineering,
        tickers_api,
        ohlcv_quality_gate,
        ticker_universe,
    ):
        monkeypatch.setattr(
            module, "get_connection", lambda: sqlite3.connect(db_path)
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


def _seed_universe(db_path, rows):
    """Universe rows as `(symbol, listing_status, ingestion_state, exchange,
    icb_code2, fails_liquidity, below_minimum_history)`."""
    conn = sqlite3.connect(db_path)
    try:
        for row in rows:
            conn.execute(
                "INSERT INTO ticker_universe (symbol, listing_status, "
                "ingestion_state, exchange, icb_code2, fails_liquidity_filter, "
                "below_minimum_history, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, '2026-09-07T00:00:00')",
                row,
            )
        conn.commit()
    finally:
        conn.close()


def test_list_tickers_derives_from_the_universe_not_training_tickers(client):
    """`ticker-catalog` MODIFIED: the catalog is universe-derived, so a
    symbol nobody trained on appears, and the two sets are no longer the
    same list."""
    _seed_universe(
        client.db_path,
        [
            ("AAA", "listed", "ok", "HSX", "2300", 0, 0),
            ("ZZZ", "delisted", "ok", None, None, 0, 0),
        ],
    )

    response = client.get("/tickers")

    assert response.status_code == 200
    returned = [entry["ticker"] for entry in response.json()["tickers"]]
    # Training tickers first in declared order — the dashboard's fixed
    # watchlist renders in response order — then the rest alphabetically.
    assert returned == TRAINING_TICKERS + ["AAA", "ZZZ"]


def test_list_tickers_marks_training_membership_exactly(client):
    _seed_universe(client.db_path, [("AAA", "listed", "ok", "HSX", "2300", 0, 0)])

    body = client.get("/tickers").json()

    flagged = {e["ticker"] for e in body["tickers"] if e["in_training_set"]}
    assert flagged == set(TRAINING_TICKERS)


def test_list_tickers_carries_universe_metadata_with_null_not_omitted(client):
    _seed_universe(
        client.db_path,
        [
            ("AAA", "listed", "ok", "HSX", "2300", 0, 0),
            ("NOICB", "listed", "ok", "HSX", None, 0, 0),
        ],
    )

    entries = {e["ticker"]: e for e in client.get("/tickers").json()["tickers"]}

    assert entries["AAA"]["exchange"] == "HSX"
    assert entries["AAA"]["industry_code"] == "2300"
    assert entries["AAA"]["listing_status"] == "listed"
    # Null, not absent — a client should not have to tell "field missing"
    # from "value unknown".
    assert entries["NOICB"]["industry_code"] is None
    assert "industry_code" in entries["NOICB"]


def test_list_tickers_distinguishes_delisted_entries(client):
    _seed_universe(
        client.db_path,
        [
            ("LIVE", "listed", "ok", "HSX", "2300", 0, 0),
            ("DEAD", "delisted", "ok", None, None, 0, 0),
        ],
    )

    entries = {e["ticker"]: e for e in client.get("/tickers").json()["tickers"]}

    assert entries["DEAD"]["listing_status"] == "delisted"
    assert entries["LIVE"]["listing_status"] == "listed"


def test_list_tickers_applies_the_universe_default_filters(client):
    """Task 8.1: the endpoint serves the *filtered* universe, or it would
    hand a frontend built for nine every illiquid and too-short symbol in
    the set."""
    _seed_universe(
        client.db_path,
        [
            ("CLEAN", "listed", "ok", "HSX", "2300", 0, 0),
            ("ILLIQUID", "listed", "ok", "HSX", "2300", 1, 0),
            ("SHORT", "listed", "ok", "HSX", "2300", 0, 1),
            ("PENDING", "listed", "pending", "HSX", "2300", 0, 0),
        ],
    )

    returned = [e["ticker"] for e in client.get("/tickers").json()["tickers"]]

    assert "CLEAN" in returned
    for excluded in ("ILLIQUID", "SHORT", "PENDING"):
        assert excluded not in returned


def test_list_tickers_keeps_a_training_ticker_that_fails_a_filter(client):
    """The model was trained on those nine, so the dashboard must be able to
    show and predict them. Dropping one because a re-tuned liquidity
    threshold (task 7.2) crossed its measured value would leave the UI
    silently inconsistent with the model it serves."""
    _seed_universe(
        client.db_path, [("VIB", "listed", "ok", "HSX", "8300", 1, 1)]
    )

    entries = {e["ticker"]: e for e in client.get("/tickers").json()["tickers"]}

    assert "VIB" in entries
    assert entries["VIB"]["in_training_set"] is True
    assert entries["VIB"]["exchange"] == "HSX"


def test_list_tickers_includes_a_training_ticker_absent_from_the_universe(client):
    """Universe construction could not place it, or has not run. The
    watchlist still needs its nine chips, with the universe fields null
    rather than the entry missing."""
    body = client.get("/tickers").json()

    entries = {e["ticker"]: e for e in body["tickers"]}
    assert set(TRAINING_TICKERS) <= set(entries)
    assert entries["VIB"]["exchange"] is None
    assert entries["VIB"]["listing_status"] is None


def test_list_tickers_serves_a_universe_sized_catalog_without_fetching(
    client, monkeypatch
):
    """Task 8.3: hundreds of never-loaded symbols must not turn a catalog
    request into an ingestion run."""
    monkeypatch.setattr(
        ticker_ingestion.mkt,
        "equity",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("GET /tickers must not fetch")
        ),
    )
    _seed_universe(
        client.db_path,
        [(f"S{i:03d}", "listed", "ok", "HSX", "2300", 0, 0) for i in range(600)],
    )

    body = client.get("/tickers").json()

    assert len(body["tickers"]) == 600 + len(TRAINING_TICKERS)
    assert all(entry["loaded"] is False for entry in body["tickers"])


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
