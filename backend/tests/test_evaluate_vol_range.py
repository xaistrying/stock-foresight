"""Tests for backend/scripts/evaluate_vol_range.py (calibrate-volatility-range, task 1)."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.db.schema import CREATE_OHLCV_TABLE, CREATE_TICKER_UNIVERSE_TABLE

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import evaluate_vol_range as ev  # noqa: E402

SQRT5 = math.sqrt(5)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_db(path: Path, n_rows: int = 800) -> None:
    """Three tickers: two in the modelling universe (one delisted), one outside it."""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2022-01-03", periods=n_rows).strftime("%Y-%m-%d")
    conn = sqlite3.connect(path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    universe = [
        ("AAA", "listed", 0),
        ("BBB", "delisted", 0),
        ("CCC", "listed", 1),  # fails the liquidity filter: outside the universe
    ]
    for symbol, status, fails in universe:
        closes = 20 * np.exp(np.cumsum(rng.normal(0, 0.015, n_rows)))
        conn.executemany(
            "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(symbol, d, c, c, c, c, 1000) for d, c in zip(dates, closes)],
        )
        conn.execute(
            "INSERT INTO ticker_universe (symbol, listing_status, fails_liquidity_filter, "
            "below_minimum_history, ingestion_state, updated_at) VALUES (?, ?, ?, 0, 'ok', 'x')",
            (symbol, status, fails),
        )
    conn.commit()
    conn.close()


def _make_model(path: Path, range_k: float = 1.2) -> None:
    path.write_text(json.dumps({
        "schema_version": 1, "model_version": "v", "trained_at": "t", "data_through": "d",
        "features": ["rv5", "rv20", "rv60"], "intercept": -4.9,
        "coef": {"rv5": 9.0, "rv20": 13.0, "rv60": 14.0}, "target": "x", "range_k": range_k,
        "range_coverage": 0.68, "universe": {"criteria": "c", "n_tickers": 2, "symbols": ["AAA", "BBB"]},
        "n_rows": 1, "validation": {},
    }))


def test_coverage_returns_known_share_at_each_multiplier():
    # Arrange: sigma 1.0 everywhere, so the band at multiplier m is m
    windows = pd.DataFrame(
        {
            "sigma": [1.0] * 10,
            "abs_r5_pct": [0.5, 0.9, 1.0, 1.5, 2.0, 2.3, 2.5, 3.0, 3.5, 4.0],
        }
    )
    range_k = 1.2

    # Act / Assert
    assert ev.coverage(windows, 1.0) == pytest.approx(0.3)
    assert ev.coverage(windows, SQRT5) == pytest.approx(0.5)  # band 2.236
    assert ev.coverage(windows, range_k * SQRT5) == pytest.approx(0.7)  # band 2.683


def test_coverage_of_no_windows_is_nan():
    empty = pd.DataFrame({"sigma": [], "abs_r5_pct": []})
    assert math.isnan(ev.coverage(empty, 1.0))


def test_connection_is_read_only(tmp_path):
    db = tmp_path / "app.db"
    _make_db(db)

    conn = ev.open_readonly(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0] > 0
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO ohlcv VALUES ('ZZZ', '2030-01-01', 1, 1, 1, 1, 1)")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM ohlcv")
    finally:
        conn.close()


def test_run_leaves_database_and_model_files_byte_identical(tmp_path):
    db, model = tmp_path / "app.db", tmp_path / "har_rv_model.json"
    _make_db(db)
    _make_model(model)
    before = (_sha(db), _sha(model))

    report = ev.run(db, model)

    assert (_sha(db), _sha(model)) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app.db", "har_rv_model.json"]
    assert report["n_windows"] > 0


def test_run_reports_every_requested_breakdown(tmp_path):
    db, model = tmp_path / "app.db", tmp_path / "har_rv_model.json"
    _make_db(db)
    _make_model(model)

    report = ev.run(db, model)

    assert set(report) >= {
        "n_windows", "range_k", "all_dates", "non_overlapping", "last_12_months",
        "time_split", "inside_universe", "outside_universe", "by_year", "by_sigma_quintile",
        "date_clustered", "realised_to_predicted_sigma", "correlation", "share_sigma_above_max",
    }
    # the universe holds AAA and BBB; CCC is outside it
    assert report["outside_universe"]["n"] > 0
    assert report["inside_universe"]["n"] > report["outside_universe"]["n"]
    assert set(report["share_sigma_above_max"]) == {"listed", "delisted"}
    assert len(report["by_sigma_quintile"]) == 5
    for row in (report["all_dates"], report["non_overlapping"]):
        assert 0.0 <= row["x1"] <= row["xsqrt5"] <= 1.0  # a wider band never covers less
    assert report["non_overlapping"]["n"] < report["all_dates"]["n"] / 4


def test_time_split_trains_before_2024_and_tests_from_february_2024(tmp_path):
    db, model = tmp_path / "app.db", tmp_path / "har_rv_model.json"
    _make_db(db)
    _make_model(model)

    split = ev.run(db, model)["time_split"]

    assert split["train_end"] == "2024-01-01"
    assert split["test_start"] == "2024-02-01"
    assert split["n_train"] > 0 and split["n_test"] > 0


def test_the_artifact_supplies_range_k(tmp_path):
    db, model = tmp_path / "app.db", tmp_path / "har_rv_model.json"
    _make_db(db)
    _make_model(model, range_k=1.234)
    before = _sha(model)

    report = ev.run(db, model)

    assert report["range_k"] == 1.234 and report["range_k_source"] == "model"
    assert _sha(model) == before


def test_read_only_connection_handles_paths_with_uri_special_characters(tmp_path):
    for name in ("a#b", "c%41d", "e?f"):
        directory = tmp_path / name
        directory.mkdir()
        db = directory / "app.db"
        _make_db(db, n_rows=70)

        conn = ev.open_readonly(db)
        try:
            assert conn.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0] > 0
        finally:
            conn.close()
