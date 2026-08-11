import sqlite3
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import app.api.tickers as tickers_api
import app.ml.backtest as backtest_module
from app.db.schema import CREATE_BACKTEST_PREDICTIONS_TABLE, CREATE_FEATURES_TABLE, CREATE_OHLCV_TABLE, CREATE_TICKERS_TABLE
from app.main import app
from app.ml.backtest import SINGLE_TICKER_BACKTEST_MIN_ROWS, compute_rolling_hit_rate
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

    monkeypatch.setattr(tickers_api, "get_connection", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(backtest_module, "get_connection", lambda: sqlite3.connect(db_path))

    with TestClient(app) as test_client:
        test_client.db_path = db_path
        yield test_client


def seed_features_rows(db_path, ticker, num_rows, near_gap_every=None, start=date(2020, 1, 1)):
    """Seed `num_rows` clean+labeled (near_gap=0, target not null) feature
    rows, plus an interspersed near_gap row every `near_gap_every`-th
    position when given — matching the realistic "gaps between clean rows"
    shape the empirical threshold (SINGLE_TICKER_BACKTEST_MIN_ROWS) was
    checked against, rather than an artificially gap-free sequence.
    Feature/target values vary per row (not constant) so a real model can
    be trained without degenerate all-identical inputs.
    """
    conn = sqlite3.connect(db_path)
    day = start
    clean_written = 0
    row_index = 0
    while clean_written < num_rows:
        is_gap = near_gap_every is not None and (row_index + 1) % near_gap_every == 0
        values = [1.0 + 0.01 * row_index + 0.1 * (i % 3) for i in range(len(FEATURE_COLUMNS))]
        target = None if is_gap else 0.001 * ((-1) ** row_index) * (row_index % 7 + 1)
        conn.execute(
            INSERT_FEATURES_ROW,
            (ticker, day.isoformat(), *values, target, 1 if is_gap else 0, "2024-01-01T00:00:00"),
        )
        day += timedelta(days=1)
        row_index += 1
        if not is_gap:
            clean_written += 1
    conn.commit()
    conn.close()


def test_backtest_below_threshold_returns_409_without_attempting_backtest(client):
    seed_features_rows(client.db_path, "FAKE", SINGLE_TICKER_BACKTEST_MIN_ROWS - 1)

    response = client.post("/tickers/FAKE/backtest")

    assert response.status_code == 409
    conn = sqlite3.connect(client.db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM backtest_predictions WHERE ticker = 'FAKE'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 0


def test_backtest_at_or_above_threshold_persists_rows_and_unlocks_hit_rate(client):
    seed_features_rows(
        client.db_path, "FAKE", SINGLE_TICKER_BACKTEST_MIN_ROWS, near_gap_every=10
    )

    assert compute_rolling_hit_rate("FAKE") is None

    response = client.post("/tickers/FAKE/backtest")

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "FAKE"
    assert body["rows_backtested"] > 0

    conn = sqlite3.connect(client.db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM backtest_predictions WHERE ticker = 'FAKE'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == body["rows_backtested"]

    assert compute_rolling_hit_rate("FAKE") is not None


def test_backtest_gate_reads_only_clean_labeled_rows(client):
    # Rows below the near_gap=0/target-not-null filter must not count
    # toward the threshold, even if the raw row count clears it.
    seed_features_rows(
        client.db_path,
        "FAKE",
        SINGLE_TICKER_BACKTEST_MIN_ROWS - 1,
        near_gap_every=2,
    )

    response = client.post("/tickers/FAKE/backtest")

    assert response.status_code == 409
