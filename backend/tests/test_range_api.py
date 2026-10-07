"""GET /tickers/{ticker}/range (calibrate-volatility-range, task 5)."""

from __future__ import annotations

import json
import math
import pickle
import sqlite3

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.db.schema import CREATE_OHLCV_TABLE
from app.main import app
from app.ml import volatility as vol_mod
from app.services import data_eligibility
from app.services import range as range_service

SQRT5 = math.sqrt(5)
RESPONSE_KEYS = {
    "ticker", "as_of", "status", "reasons", "sigma_daily_pct", "range_5s_pct",
    "range_k", "range_coverage", "range_hit_rate",
}
ARTIFACT = {
    "schema_version": 1,
    "model_version": "har-rv-2026-10-07-abcd1234",
    "trained_at": "2026-10-07T00:00:00+00:00",
    "data_through": "2026-09-15",
    "features": ["rv5", "rv20", "rv60"],
    "intercept": -4.94,
    "coef": {"rv5": 9.28, "rv20": 13.77, "rv60": 14.18},
    "target": "ln(std of next 5 daily log returns)",
    "range_k": 1.2,
    "range_coverage": 0.68,
    "universe": {"criteria": "test", "n_tickers": 1, "symbols": ["AAA", "WILD"]},
    "n_rows": 200000,
    "validation": {},
}


def _closes(n: int, noise: float = 0.012, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 20.0 * np.exp(np.cumsum(rng.normal(0, noise, n)))


class _SpyConnection:
    def __init__(self, conn):
        self._conn, self.calls = conn, []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self._conn.execute(sql, params)

    def close(self):
        self._conn.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A client over a temp database, an artifact on disk, and a scriptable eligibility service."""
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_OHLCV_TABLE)
    dates = pd.bdate_range("2024-01-01", periods=400).strftime("%Y-%m-%d")
    series = {
        "AAA": _closes(400),  # in the calibration universe
        "OUT": _closes(400, seed=2),  # eligible, outside it
        "SHORT": _closes(50, seed=3),  # fewer than 61 closes
        "WILD": np.concatenate([_closes(340), _closes(60, noise=0.2, seed=4)]),  # corrupt recent closes
    }
    for ticker, closes in series.items():
        conn.executemany(
            "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, 1)",
            [(ticker, d, c, c, c, c) for d, c in zip(dates, closes)],
        )
    conn.commit()
    conn.close()

    spy_holder: list[_SpyConnection] = []

    def connect():
        spy = _SpyConnection(sqlite3.connect(db_path))
        spy_holder.append(spy)
        return spy

    monkeypatch.setattr(vol_mod, "get_connection", connect)

    model_path = tmp_path / "har_rv_model.json"
    model_path.write_text(json.dumps(ARTIFACT))
    monkeypatch.setattr(vol_mod, "MODEL_PATH", model_path)

    eligibility = {"reasons": [], "calls": []}

    def fake_assess(ticker):
        eligibility["calls"].append(ticker)
        reasons = list(eligibility["reasons"])
        return {"eligible": not reasons, "reasons": reasons, "as_of": "2025-07-01", "age_sessions": 0}

    monkeypatch.setattr(range_service, "assess_eligibility", fake_assess)

    # No `with`: the lifespan (init_db on the real database, XGBoost load) is not needed here.
    return type("Env", (), {
        "client": TestClient(app), "model_path": model_path, "eligibility": eligibility,
        "dates": dates, "spy": spy_holder,
    })


def _get(env, ticker):
    return env.client.get(f"/tickers/{ticker}/range")


def test_ok_populates_every_field(env):
    body = _get(env, "AAA").json()

    assert set(body) == RESPONSE_KEYS
    assert body["status"] == "ok" and body["reasons"] == []
    assert body["ticker"] == "AAA" and body["as_of"] == env.dates[-1]
    assert body["range_k"] == 1.2 and body["range_coverage"] == 0.68
    assert body["range_5s_pct"] == pytest.approx(1.2 * SQRT5 * body["sigma_daily_pct"], abs=0.02)
    assert 0 < body["sigma_daily_pct"] <= 7.0
    assert set(body["range_hit_rate"]) == {"rate", "n"} and body["range_hit_rate"]["n"] == 50
    assert 0.0 <= body["range_hit_rate"]["rate"] <= 1.0


def test_ticker_with_no_rows_is_404_and_eligibility_is_not_consulted(env):
    response = _get(env, "NONE")

    assert response.status_code == 404
    assert response.json() == {"detail": "Ticker has not been loaded"}
    assert env.eligibility["calls"] == []


def test_ineligible_copies_the_services_reasons_minus_indicators_missing(env):
    env.eligibility["reasons"] = ["stale", "indicators_missing"]

    body = _get(env, "AAA").json()

    assert body["status"] == "ineligible" and body["reasons"] == ["stale"]
    for key in ("sigma_daily_pct", "range_5s_pct", "range_k", "range_coverage", "range_hit_rate"):
        assert body[key] is None


def test_missing_indicators_alone_do_not_block_the_range(env):
    env.eligibility["reasons"] = ["indicators_missing"]

    body = _get(env, "AAA").json()

    assert body["status"] == "ok" and body["reasons"] == []


@pytest.mark.parametrize("reason", ["near_gap", "hard_quality_flag", "delisted", "insufficient_history"])
def test_other_eligibility_reasons_still_block(env, reason):
    env.eligibility["reasons"] = [reason, "indicators_missing"]

    body = _get(env, "AAA").json()

    assert body["status"] == "ineligible" and body["reasons"] == [reason]


def test_missing_artifact_is_model_unavailable(env):
    env.model_path.unlink()

    response = _get(env, "AAA")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "model_unavailable" and body["reasons"] == []
    assert body["sigma_daily_pct"] is None and body["range_5s_pct"] is None


def test_short_history_despite_eligibility_is_insufficient_history(env, caplog):
    with caplog.at_level("ERROR"):
        body = _get(env, "SHORT").json()

    assert body["status"] == "ineligible" and body["reasons"] == ["insufficient_history"]
    assert body["range_5s_pct"] is None
    assert any("eligibility threshold" in r.message for r in caplog.records)


def test_out_of_bounds_sigma_is_reported_but_never_clipped(env):
    body = _get(env, "WILD").json()

    assert body["status"] == "range_out_of_bounds" and body["reasons"] == []
    assert body["sigma_daily_pct"] > 7.0
    assert body["range_5s_pct"] is None and body["range_hit_rate"] is None


def test_ticker_outside_the_calibration_universe_is_uncalibrated(env):
    body = _get(env, "OUT").json()

    assert body["status"] == "uncalibrated" and body["reasons"] == []
    assert body["range_coverage"] is None
    assert body["range_k"] == 1.2 and body["range_5s_pct"] > 0
    assert body["range_hit_rate"]["n"] == 50


def test_status_precedence_follows_the_spec_order(env):
    # eligibility beats the missing artifact
    env.eligibility["reasons"] = ["stale"]
    env.model_path.unlink()
    assert _get(env, "AAA").json()["status"] == "ineligible"
    # the missing artifact beats the history check
    env.eligibility["reasons"] = []
    assert _get(env, "SHORT").json()["status"] == "model_unavailable"
    # out-of-bounds sigma beats uncalibrated: a corrupt ticker outside the universe is not served
    env.model_path.write_text(json.dumps({**ARTIFACT, "universe": {**ARTIFACT["universe"], "symbols": []}}))
    assert _get(env, "WILD").json()["status"] == "range_out_of_bounds"


def test_eligibility_threshold_covers_the_history_the_range_needs():
    """`debate-data-guards` must never call a ticker eligible with fewer than 61 closes."""
    assert data_eligibility.MIN_SESSIONS >= vol_mod.MIN_CLOSES == 61


def test_repeated_calls_unpickle_nothing_open_the_model_once_and_read_closes_once(env, monkeypatch):
    def no_pickle(*_a, **_k):
        raise AssertionError("pickle used on the serving path")

    monkeypatch.setattr(pickle, "load", no_pickle)
    monkeypatch.setattr(pickle, "loads", no_pickle)
    opened: list[object] = []
    real_open = open
    monkeypatch.setattr(
        vol_mod, "open", lambda *a, **k: (opened.append(a[0]), real_open(*a, **k))[1], raising=False
    )

    for _ in range(2):
        assert _get(env, "AAA").json()["status"] == "ok"

    assert len(opened) == 1
    # eligibility is monkeypatched, so every query is the bounded closes read: one per request
    assert [len(spy.calls) for spy in env.spy] == [1, 1]
    sql, params = env.spy[0].calls[0]
    assert "LIMIT" in sql and params == ("AAA", vol_mod.HISTORY_ROWS)
