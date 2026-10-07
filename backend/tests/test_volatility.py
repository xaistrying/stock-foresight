"""Unit tests for backend/app/ml/volatility.py"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.db.schema import CREATE_OHLCV_TABLE
from app.ml import volatility as vol_mod
from app.ml.volatility import (
    HIT_RATE_MAX_WINDOWS,
    HIT_RATE_MIN_WINDOWS,
    HISTORY_ROWS,
    SIGMA_DAILY_MAX_PCT,
    HarModel,
    band_from_sigma,
    load_model,
    range_hit_rate,
    read_recent_closes,
    sigma_daily_pct_from_closes,
    sigma_out_of_bounds,
)

SQRT5 = math.sqrt(5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_df(n: int, close_start: float = 10.0, noise: float = 0.01) -> pd.DataFrame:
    """Create a synthetic OHLCV close-price DataFrame with n rows."""
    rng = np.random.default_rng(42)
    closes = close_start * np.cumprod(1 + rng.normal(0, noise, n))
    return pd.DataFrame({"date": [f"2024-{i:04d}" for i in range(n)], "close": closes})


def _closes(n: int, noise: float = 0.01, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 20.0 * np.exp(np.cumsum(rng.normal(0, noise, n)))


def _artifact(**overrides) -> dict:
    artifact = {
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
        "universe": {"criteria": "modelling_universe()", "n_tickers": 2, "symbols": ["AAA", "BBB"]},
        "n_rows": 200000,
        "validation": {"pooled_coverage": 0.675},
    }
    return {**artifact, **overrides}


def _write(path: Path, artifact: dict) -> Path:
    path.write_text(json.dumps(artifact))
    return path


def _model(intercept: float, coef=(0.0, 0.0, 0.0), range_k: float = 1.0) -> HarModel:
    return HarModel(
        model_version="test", trained_at="2026-10-07T00:00:00+00:00", data_through="2026-09-15",
        intercept=intercept, coef=tuple(coef), range_k=range_k, range_coverage=0.68,
        universe=frozenset({"AAA"}), n_rows=1, validation={},
    )


def _constant_sigma_model(sigma_pct: float, range_k: float = 1.0) -> HarModel:
    return _model(math.log(sigma_pct / 100.0), range_k=range_k)


def _reference_hits(closes: np.ndarray, model: HarModel) -> list[bool]:
    """Independent pandas implementation of the spec's hit-rate definition."""
    s = pd.Series(closes[-HISTORY_ROWS:])
    log_returns = np.log(s / s.shift(1))
    rv = pd.DataFrame({name: log_returns.rolling(w).std() for name, w in (("rv5", 5), ("rv20", 20), ("rv60", 60))})
    hits, t = [], len(s) - 6
    for _ in range(HIT_RATE_MAX_WINDOWS):
        if t < 60:
            break
        sigma = float(np.exp(model.intercept + rv.iloc[t].to_numpy() @ np.array(model.coef)) * 100)
        if np.isfinite(sigma) and sigma <= SIGMA_DAILY_MAX_PCT:
            move = abs(math.log(s[t + 5] / s[t])) * 100
            hits.append(move <= model.range_k * SQRT5 * sigma)
        t -= 5
    return hits


# ---------------------------------------------------------------------------
# _build_har_features
# ---------------------------------------------------------------------------

def test_build_har_features_shape():
    from app.ml.volatility import _build_har_features

    closes = pd.Series(range(1, 71), dtype="float64")
    features = _build_har_features(closes)
    assert set(features.columns) == {"rv5", "rv20", "rv60"}
    assert len(features) == 70


def test_build_har_features_nans_at_start():
    """The first 59 rows should have NaN rv60 (warm-up period)."""
    from app.ml.volatility import _build_har_features

    df = _make_ohlcv_df(100)
    features = _build_har_features(df["close"])
    assert features["rv60"].iloc[:59].isna().all()
    assert not features["rv60"].iloc[60:].isna().any()


# ---------------------------------------------------------------------------
# load_model
# ---------------------------------------------------------------------------

def test_load_model_returns_immutable_har_model(tmp_path, monkeypatch):
    path = _write(tmp_path / "har_rv_model.json", _artifact())
    monkeypatch.setattr(vol_mod, "MODEL_PATH", path)

    model = load_model()

    assert isinstance(model, HarModel)
    assert model.intercept == -4.94
    assert model.coef == (9.28, 13.77, 14.18)
    assert model.range_k == 1.2 and model.range_coverage == 0.68
    assert model.model_version == "har-rv-2026-10-07-abcd1234"
    assert model.universe == frozenset({"AAA", "BBB"})
    with pytest.raises(dataclasses.FrozenInstanceError):
        model.range_k = 2.0  # type: ignore[misc]


def test_load_model_returns_none_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(vol_mod, "MODEL_PATH", tmp_path / "nonexistent.json")
    assert load_model() is None


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        json.dumps(_artifact(intercept=float("nan"))),
        json.dumps(_artifact(coef={"rv5": 1.0, "rv20": float("inf"), "rv60": 1.0})),
        json.dumps(_artifact(schema_version=2)),
        json.dumps({k: v for k, v in _artifact().items() if k != "range_k"}),
        json.dumps(_artifact(range_k=0)),
    ],
    ids=["malformed", "nan-intercept", "inf-coef", "schema-version", "missing-key", "zero-k"],
)
def test_load_model_returns_none_for_unusable_file(tmp_path, monkeypatch, content):
    path = tmp_path / "har_rv_model.json"
    path.write_text(content)
    monkeypatch.setattr(vol_mod, "MODEL_PATH", path)

    assert load_model() is None


def test_load_model_opens_the_file_once_across_calls(tmp_path, monkeypatch):
    path = _write(tmp_path / "har_rv_model.json", _artifact())
    monkeypatch.setattr(vol_mod, "MODEL_PATH", path)
    opened: list[object] = []
    real_open = open
    monkeypatch.setattr(
        vol_mod, "open", lambda *a, **k: (opened.append(a[0]), real_open(*a, **k))[1], raising=False
    )

    first = load_model()
    for _ in range(99):
        assert load_model() is first

    assert len(opened) == 1


def test_load_model_rereads_after_the_file_is_replaced(tmp_path, monkeypatch):
    path = _write(tmp_path / "har_rv_model.json", _artifact(range_k=1.2))
    monkeypatch.setattr(vol_mod, "MODEL_PATH", path)
    assert load_model().range_k == 1.2

    replacement = _write(tmp_path / "next.json", _artifact(range_k=1.5, model_version="har-rv-new"))
    old_ns = path.stat().st_mtime_ns
    os.utime(replacement, ns=(old_ns + 10**9, old_ns + 10**9))
    os.replace(replacement, path)

    reloaded = load_model()
    assert reloaded.range_k == 1.5 and reloaded.model_version == "har-rv-new"


# ---------------------------------------------------------------------------
# sigma, band, bounds
# ---------------------------------------------------------------------------

def test_sigma_daily_pct_matches_the_har_formula():
    closes = _closes(100)
    model = _model(-4.94, coef=(9.28, 13.77, 14.18))
    log_returns = np.diff(np.log(closes))
    rv = [log_returns[-n:].std(ddof=1) for n in (5, 20, 60)]
    expected = math.exp(-4.94 + 9.28 * rv[0] + 13.77 * rv[1] + 14.18 * rv[2]) * 100

    assert sigma_daily_pct_from_closes(closes, model) == pytest.approx(expected)


def test_sigma_daily_pct_is_none_without_61_closes():
    model = _model(-4.94, coef=(9.28, 13.77, 14.18))
    assert sigma_daily_pct_from_closes(_closes(60), model) is None
    assert sigma_daily_pct_from_closes(_closes(61), model) is not None


def test_sigma_daily_pct_is_a_percentage_not_a_log_value():
    """Rule 2: output is a percentage; a log-volatility would be negative (around -4)."""
    sigma = sigma_daily_pct_from_closes(_closes(100, noise=0.02), _model(-4.94, coef=(9.28, 13.77, 14.18)))
    assert sigma is not None and sigma > 0.5


def test_band_is_range_k_times_root_five_times_sigma():
    model = _model(0.0, range_k=1.20)
    assert band_from_sigma(1.50, model) == pytest.approx(1.20 * SQRT5 * 1.50)  # about 4.02


@pytest.mark.parametrize(
    ("sigma", "out"),
    [(7.0, False), (7.0001, True), (41.7, True), (math.nan, True), (math.inf, True), (0.0, False)],
)
def test_sigma_bounds(sigma, out):
    assert SIGMA_DAILY_MAX_PCT == 7.0
    assert sigma_out_of_bounds(sigma) is out


# ---------------------------------------------------------------------------
# read_recent_closes
# ---------------------------------------------------------------------------

class _SpyConnection:
    def __init__(self, conn: sqlite3.Connection):
        self._conn, self.calls = conn, []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return self._conn.execute(sql, params)

    def close(self):
        self._conn.close()


@pytest.fixture
def ohlcv_conn(tmp_path, monkeypatch):
    """A 2,500-row ticker with one zero close, behind a spy on the connection."""
    conn = sqlite3.connect(tmp_path / "app.db")
    conn.execute(CREATE_OHLCV_TABLE)
    dates = pd.bdate_range("2015-01-05", periods=2500).strftime("%Y-%m-%d")
    closes = _closes(2500)
    closes[2000] = 0.0
    conn.executemany(
        "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, 1)",
        [("AAA", d, c, c, c, c) for d, c in zip(dates, closes)],
    )
    conn.commit()
    spy = _SpyConnection(conn)
    monkeypatch.setattr(vol_mod, "get_connection", lambda: spy)
    return spy, dates, closes


def test_read_recent_closes_is_bounded_ascending_and_parameterised(ohlcv_conn):
    spy, dates, closes = ohlcv_conn

    got_dates, got_closes = read_recent_closes("AAA", limit=311)

    assert len(got_closes) == 311 and len(got_dates) == 311
    assert list(got_dates) == sorted(got_dates)
    assert got_dates[-1] == dates[-1]
    np.testing.assert_allclose(got_closes, closes[-311:])
    (sql, params), = spy.calls
    assert params == ("AAA", 311)
    assert "AAA" not in sql and "?" in sql
    assert "close > 0" in sql and "ORDER BY date DESC" in sql and "LIMIT" in sql


def test_read_recent_closes_skips_non_positive_closes(ohlcv_conn):
    _, dates, _ = ohlcv_conn

    got_dates, got_closes = read_recent_closes("AAA", limit=1000)

    assert (got_closes > 0).all()
    assert dates[2000] not in got_dates


# ---------------------------------------------------------------------------
# range_hit_rate
# ---------------------------------------------------------------------------

def _closes_with_known_hits(n_hits: int, n_windows: int = 50) -> np.ndarray:
    """Every scored window has a 5-session move of 1% (inside a 2.236% band) or 5% (outside)."""
    n = 61 + 5 * (n_windows - 1) + 5
    rng = np.random.default_rng(1)
    returns = np.zeros(n)
    returns[1:61] = rng.normal(0, 0.01, 60)
    first_t = n - 6 - 5 * (n_windows - 1)  # oldest scored window, t = 60
    for i in range(n_windows):
        t = first_t + 5 * i
        size = 0.01 if i < n_hits else 0.05
        returns[t + 1 : t + 6] = size / 5
    return 20.0 * np.exp(np.cumsum(returns))


def test_hit_rate_for_a_known_fixture():
    closes = _closes_with_known_hits(35)

    result = range_hit_rate(closes, _constant_sigma_model(1.0))

    assert result == {"rate": 0.7, "n": 50}


def test_hit_rate_matches_an_independent_implementation():
    closes = _closes(500, noise=0.012, seed=11)
    model = _model(-4.94, coef=(9.28, 13.77, 14.18), range_k=1.2)

    expected = _reference_hits(closes, model)
    result = range_hit_rate(closes, model)

    assert result["n"] == len(expected) == HIT_RATE_MAX_WINDOWS
    assert result["rate"] == pytest.approx(sum(expected) / len(expected))


def test_windows_are_non_overlapping_at_most_fifty_and_read_311_closes():
    closes = _closes(2000)
    model = _model(-4.94, coef=(9.28, 13.77, 14.18))

    starts, hits = vol_mod._window_hits(closes, model)

    assert len(starts) <= HIT_RATE_MAX_WINDOWS == 50
    assert np.all(np.diff(starts) == 5)
    assert starts[-1] == HISTORY_ROWS - 6  # newest window is the latest t that has a t+5 row
    assert len(hits) == len(starts)


def test_a_close_after_t_plus_five_does_not_change_window_t():
    closes = _closes(311, seed=5)
    model = _model(-4.94, coef=(9.28, 13.77, 14.18))
    starts, hits = vol_mod._window_hits(closes, model)

    changed = closes.copy()
    changed[-4:] *= 1.5  # the newest window's outcome (t+5 = 310) and closes after t+2
    starts2, hits2 = vol_mod._window_hits(changed, model)

    assert list(starts2) == list(starts)
    # every window whose t + 5 precedes the change keeps its result
    unchanged = starts + 5 < 307
    assert list(np.asarray(hits2)[unchanged]) == list(np.asarray(hits)[unchanged])


def test_short_history_reports_its_n():
    closes = _closes_with_known_hits(30, n_windows=30)

    result = range_hit_rate(closes, _constant_sigma_model(1.0))

    assert result == {"rate": 1.0, "n": 30}


def test_too_few_windows_gives_a_null_rate_with_n():
    closes = _closes_with_known_hits(15, n_windows=15)
    assert HIT_RATE_MIN_WINDOWS == 20

    assert range_hit_rate(closes, _constant_sigma_model(1.0)) == {"rate": None, "n": 15}


def test_windows_with_out_of_bounds_sigma_are_excluded_from_n():
    rng = np.random.default_rng(2)
    volatile = rng.normal(0, 0.04, 150)
    calm = rng.normal(0, 0.005, 161)
    closes = 20.0 * np.exp(np.cumsum(np.concatenate([volatile, calm])))
    model = _model(-5.0, coef=(0.0, 0.0, 100.0))  # sigma = 100 * exp(-5 + 100 * rv60)

    expected = _reference_hits(closes, model)
    result = range_hit_rate(closes, model)

    assert 0 < result["n"] < HIT_RATE_MAX_WINDOWS
    assert result["n"] == len(expected)


def test_hit_rate_runs_well_under_the_latency_bound():
    closes = _closes(HISTORY_ROWS)
    model = _model(-4.94, coef=(9.28, 13.77, 14.18))
    range_hit_rate(closes, model)  # warm numpy

    started = time.perf_counter()
    for _ in range(10):
        range_hit_rate(closes, model)

    assert (time.perf_counter() - started) / 10 < 0.05
