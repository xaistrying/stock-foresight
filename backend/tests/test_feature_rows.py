import sqlite3

import pytest

import app.services.feature_rows as feature_rows
from app.db.schema import CREATE_FEATURES_TABLE, CREATE_TICKERS_TABLE
from app.ml.training import FEATURE_COLUMNS


@pytest.fixture
def db_path(monkeypatch, tmp_path):
    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    conn.execute(CREATE_TICKERS_TABLE)
    conn.execute(CREATE_FEATURES_TABLE)
    conn.commit()
    conn.close()
    monkeypatch.setattr(feature_rows, "get_connection", lambda: sqlite3.connect(path))
    return path


def _insert_feature_row(db_path, ticker, date, *, indicator=1.0, near_gap=0):
    conn = sqlite3.connect(db_path)
    columns = ", ".join(["ticker", "date", "near_gap", "computed_at", *FEATURE_COLUMNS])
    marks = ", ".join("?" for _ in range(4 + len(FEATURE_COLUMNS)))
    conn.execute(
        f"INSERT INTO features ({columns}) VALUES ({marks})",
        (ticker, date, near_gap, "2026-10-07T00:00:00", *[indicator] * len(FEATURE_COLUMNS)),
    )
    conn.commit()
    conn.close()


def test_latest_row_is_the_newest_and_an_older_clean_row_is_not_substituted(db_path):
    _insert_feature_row(db_path, "VIB", "2026-10-01", indicator=1.0)
    _insert_feature_row(db_path, "VIB", "2026-10-02", indicator=None, near_gap=1)

    row = feature_rows.get_latest_features_row("VIB")

    assert row["date"] == "2026-10-02"
    assert row["near_gap"] == 1
    assert row["rsi"] is None


def test_latest_row_carries_the_indicator_columns_and_near_gap(db_path):
    _insert_feature_row(db_path, "VIB", "2026-10-01", indicator=2.5)

    row = feature_rows.get_latest_features_row("VIB")

    assert {"date", "near_gap", *FEATURE_COLUMNS} <= row.keys()
    assert row["macd_line"] == 2.5


def test_a_ticker_with_no_rows_returns_none(db_path):
    assert feature_rows.get_latest_features_row("NOPE") is None
    assert feature_rows.get_features_computed("NOPE") is None


@pytest.mark.parametrize("stored", [None, 0, 1])
def test_features_computed_is_returned_as_stored(db_path, stored):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO tickers (ticker, last_loaded_at, features_computed) VALUES ('VIB', '2026-10-01', ?)",
        (stored,),
    )
    conn.commit()
    conn.close()

    assert feature_rows.get_features_computed("VIB") == stored
