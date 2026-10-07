"""Tests for backend/scripts/train_har_rv.py (calibrate-volatility-range, task 4)."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.db.schema import CREATE_OHLCV_TABLE, CREATE_TICKER_UNIVERSE_TABLE
from app.ml import volatility as vol_mod
from app.ml.volatility import build_window_frame, fit_har_ols

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import train_har_rv as train  # noqa: E402

SQRT5 = math.sqrt(5)
TRAINED_AT = "2026-10-07T08:00:00+00:00"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_db(path: Path, symbols=("AAA", "BBB", "CCC", "DDD"), n_rows: int = 1500) -> None:
    rng = np.random.default_rng(5)
    dates = pd.bdate_range("2019-01-01", periods=n_rows).strftime("%Y-%m-%d")
    conn = sqlite3.connect(path)
    conn.execute(CREATE_OHLCV_TABLE)
    conn.execute(CREATE_TICKER_UNIVERSE_TABLE)
    for symbol in symbols:
        closes = 20 * np.exp(np.cumsum(rng.normal(0, 0.015, n_rows)))
        conn.executemany(
            "INSERT INTO ohlcv VALUES (?, ?, ?, ?, ?, ?, 1000)",
            [(symbol, d, c, c, c, c) for d, c in zip(dates, closes)],
        )
        conn.execute(
            "INSERT INTO ticker_universe (symbol, listing_status, fails_liquidity_filter, "
            "below_minimum_history, ingestion_state, updated_at) VALUES (?, 'listed', 0, 0, 'ok', 'x')",
            (symbol,),
        )
    conn.commit()
    conn.close()


def _frame(n_tickers: int = 4, n_rows: int = 1500) -> pd.DataFrame:
    """Windows for several tickers with the columns the training script works on."""
    rng = np.random.default_rng(9)
    dates = pd.Series(pd.bdate_range("2019-01-01", periods=n_rows).strftime("%Y-%m-%d"))
    parts = []
    for i in range(n_tickers):
        closes = pd.Series(20 * np.exp(np.cumsum(rng.normal(0, 0.015, n_rows))))
        parts.append(build_window_frame(dates, closes).assign(ticker=f"T{i}"))
    return train.prepare(pd.concat(parts, ignore_index=True))


def _passing_validation(**overrides) -> dict:
    validation = {
        "scheme": "expanding walk-forward by calendar year, 5-session purge",
        "folds": [{"test_year": 2024, "n": 100, "coverage": 0.70, "k": 1.2, "corr": 0.45, "baseline_corr": 0.43}],
        "pooled_coverage": 0.68,
        "pooled_coverage_ci": [0.60, 0.75],
        "coverage_by_sigma_quintile": [0.66, 0.67, 0.68, 0.69, 0.70],
        "oot_corr": 0.45,
        "baseline_log_rv20_corr": 0.43,
    }
    return {**validation, **overrides}


# ---------------------------------------------------------------------------
# walk-forward split and fit
# ---------------------------------------------------------------------------

def test_walk_forward_split_purges_windows_whose_outcome_reaches_the_test_year():
    frame = pd.DataFrame(
        {
            "date": ["2023-12-20", "2023-12-27", "2023-12-28", "2024-01-02", "2024-06-03"],
            "outcome_date": ["2023-12-27", "2024-01-03", "2024-01-04", "2024-01-09", "2024-06-10"],
        }
    )

    fit, test = train.split_fold(frame, 2024)

    assert list(fit["date"]) == ["2023-12-20"]  # t+5 on or after 2024-01-01 is dropped
    assert list(test["date"]) == ["2024-01-02", "2024-06-03"]


def test_fit_fold_range_k_is_the_empirical_quantile_of_the_scaled_move():
    frame = _frame()
    fit, _ = train.split_fold(frame, 2023)

    intercept, coef, range_k = train.fit_fold(fit, 0.68)

    expected_intercept, expected_coef = fit_har_ols(fit)
    sigma = np.exp(expected_intercept + fit[["rv5", "rv20", "rv60"]].to_numpy() @ expected_coef) * 100
    z = fit["abs_r5_pct"].to_numpy() / (SQRT5 * sigma)
    assert intercept == pytest.approx(expected_intercept)
    assert range_k == pytest.approx(np.quantile(z, 0.68))


def test_run_validation_reports_out_of_time_figures():
    frame = _frame()

    validation = train.run_validation(frame, coverage=0.68, min_train_rows=2000)

    json.dumps(validation, allow_nan=False)  # the artifact embeds it: plain Python numbers only
    assert [f["test_year"] for f in validation["folds"]] == sorted(f["test_year"] for f in validation["folds"])
    assert validation["folds"], "expected at least one test year"
    assert all({"test_year", "n", "coverage", "k"} <= set(f) for f in validation["folds"])
    low, high = validation["pooled_coverage_ci"]
    assert low <= validation["pooled_coverage"] <= high
    assert len(validation["coverage_by_sigma_quintile"]) == 5
    assert -1 <= validation["oot_corr"] <= 1 and -1 <= validation["baseline_log_rv20_corr"] <= 1
    # pooled coverage is over the test years only, not the in-sample fit
    pooled = sum(f["coverage"] * f["n"] for f in validation["folds"]) / sum(f["n"] for f in validation["folds"])
    assert validation["pooled_coverage"] == pytest.approx(pooled)


def _large_synthetic_frame(years=(2021, 2022, 2023, 2024), rows_per_year: int = 40_000) -> pd.DataFrame:
    """Folds above 32,768 rows: the size at which NumPy 2.2.6 on CPython 3.14 elides `scalar * array`.

    2022 is far more volatile in 5-session moves than the daily sigma implies, so each fold's range_k
    differs and an overwritten sigma (shifted by log(range_k * sqrt 5) per fold) changes the pooled
    correlation instead of cancelling out.
    """
    rng = np.random.default_rng(4)
    n = rows_per_year * len(years)
    year = np.repeat(years, rows_per_year)
    month = rng.integers(1, 13, n)
    rv20 = 0.005 + np.abs(rng.normal(0, 0.01, n))
    realised = rv20 * np.exp(rng.normal(0, 0.3, n))
    return train.prepare(pd.DataFrame({
        "ticker": "T0",
        "date": [f"{y}-{m:02d}-10" for y, m in zip(year, month)],
        "outcome_date": [f"{y}-{m:02d}-17" for y, m in zip(year, month)],
        "rv5": rv20 * np.exp(rng.normal(0, 0.2, n)), "rv20": rv20, "rv60": rv20 * np.exp(rng.normal(0, 0.1, n)),
        "realised_std": realised,
        "r5": rng.normal(0, 1, n) * realised * np.sqrt(5) * np.where(year == 2022, 4.0, 1.0),
    }))


def test_validation_correlation_is_the_mean_of_per_fold_correlations_on_large_folds():
    frame = _large_synthetic_frame()

    validation = train.run_validation(frame, coverage=0.68, min_train_rows=1000)

    folds = validation["folds"]
    expected = []
    for year in (2022, 2023, 2024):
        fit, test = train.split_fold(frame, year)
        intercept, coef, _ = train.fit_fold(fit, 0.68)
        predicted = np.log(train._sigma(test, intercept, coef) / 100.0)
        expected.append(np.corrcoef(predicted, vol_mod.log_realised(test).to_numpy())[0, 1])
    assert [f["n"] for f in folds] == [40_000, 40_000, 40_000]
    assert [f["corr"] for f in folds] == pytest.approx(expected)
    assert validation["oot_corr"] == pytest.approx(np.mean(expected))
    assert validation["baseline_log_rv20_corr"] == pytest.approx(np.mean([f["baseline_corr"] for f in folds]))


def test_scaled_band_never_overwrites_its_input_on_large_arrays():
    sigma = np.full(40_000, 2.0)  # above 32,768 elements, where numpy 2.2.6 on CPython 3.14 elides

    band = vol_mod.scaled_band(sigma, 1.2)

    assert (sigma == 2.0).all() and band[0] == pytest.approx(1.2 * SQRT5 * 2.0)


def test_run_validation_skips_years_without_enough_prior_windows():
    frame = _frame()

    validation = train.run_validation(frame, coverage=0.68, min_train_rows=10**9)

    assert validation["folds"] == []


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

def test_good_validation_passes_every_gate():
    assert train.failed_gates(_passing_validation(), n_rows=200_000, n_tickers=208) == []


def test_pooled_coverage_gate():
    failures = train.failed_gates(_passing_validation(pooled_coverage=0.60), 200_000, 208)
    assert any("pooled" in f for f in failures)


def test_single_year_coverage_gate():
    folds = [{"test_year": 2022, "n": 10, "coverage": 0.55, "k": 1.2}]
    failures = train.failed_gates(_passing_validation(folds=folds), 200_000, 208)
    assert any("2022" in f for f in failures)


def test_baseline_gate():
    failures = train.failed_gates(_passing_validation(oot_corr=0.40, baseline_log_rv20_corr=0.43), 200_000, 208)
    assert any("baseline" in f for f in failures)


@pytest.mark.parametrize(("rows", "tickers"), [(99_999, 208), (200_000, 99)])
def test_insufficient_data_gate(rows, tickers):
    assert train.failed_gates(_passing_validation(), rows, tickers)


def test_a_non_finite_correlation_fails_instead_of_passing_every_comparison():
    failures = train.failed_gates(_passing_validation(oot_corr=float("nan")), 200_000, 208)
    assert any("not finite" in f for f in failures)


def test_no_fold_fails():
    assert train.failed_gates(_passing_validation(folds=[]), 200_000, 208)


# ---------------------------------------------------------------------------
# artifact
# ---------------------------------------------------------------------------

def test_model_version_is_deterministic_for_identical_coefficients():
    a = train.model_version(TRAINED_AT, -4.94, np.array([9.28, 13.77, 14.18]), 1.2)
    b = train.model_version(TRAINED_AT, -4.94, np.array([9.28, 13.77, 14.18]), 1.2)
    c = train.model_version(TRAINED_AT, -4.94, np.array([9.28, 13.77, 14.19]), 1.2)

    assert a == b != c
    assert a.startswith("har-rv-2026-10-07-") and len(a.split("-")[-1]) == 8


def test_artifact_has_every_key_the_spec_lists_and_loads():
    frame = _frame()
    artifact = train.build_artifact(
        frame, _passing_validation(), sorted(frame["ticker"].unique()), TRAINED_AT, 0.68
    )

    assert set(artifact) >= {
        "schema_version", "model_version", "trained_at", "data_through", "features", "intercept",
        "coef", "target", "range_k", "range_coverage", "universe", "n_rows", "validation",
    }
    assert artifact["universe"]["n_tickers"] == 4 and artifact["universe"]["symbols"] == ["T0", "T1", "T2", "T3"]
    assert artifact["n_rows"] == len(frame)
    assert artifact["data_through"] == frame["outcome_date"].max()
    assert artifact["range_coverage"] == 0.68
    assert artifact["validation"]["pooled_coverage"] == 0.68
    json.dumps(artifact, allow_nan=False)  # strict JSON, no NaN


def test_write_is_atomic_when_the_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "har_rv_model.json"
    target.write_text('{"old": true}')
    before = _sha(target)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        train.write_artifact(target, {"new": True})

    assert _sha(target) == before
    assert [p.name for p in tmp_path.iterdir()] == ["har_rv_model.json"]  # temp file removed


def test_write_replaces_the_target(tmp_path):
    target = tmp_path / "har_rv_model.json"
    target.write_text('{"old": true}')

    train.write_artifact(target, {"new": True})

    assert json.loads(target.read_text()) == {"new": True}
    assert [p.name for p in tmp_path.iterdir()] == ["har_rv_model.json"]


# ---------------------------------------------------------------------------
# main(): refusal leaves the old artifact alone
# ---------------------------------------------------------------------------

@pytest.fixture
def existing_artifact(tmp_path):
    out = tmp_path / "har_rv_model.json"
    out.write_text('{"previous": "artifact"}')
    db = tmp_path / "app.db"
    _make_db(db)
    return db, out, _sha(out)


def test_insufficient_rows_exits_non_zero_and_keeps_the_old_artifact(existing_artifact):
    db, out, before = existing_artifact  # 4 tickers x ~1,400 windows is far below 100,000 rows

    with pytest.raises(SystemExit) as exc:
        train.main(["--db", str(db), "--out", str(out)])

    assert exc.value.code not in (0, None)
    assert _sha(out) == before


@pytest.mark.parametrize(
    "bad",
    [{"pooled_coverage": 0.60}, {"oot_corr": 0.30, "baseline_log_rv20_corr": 0.43}],
    ids=["coverage-gate", "baseline-gate"],
)
def test_failed_validation_exits_non_zero_and_keeps_the_old_artifact(existing_artifact, monkeypatch, bad):
    db, out, before = existing_artifact
    monkeypatch.setattr(train, "MIN_ROWS", 1)
    monkeypatch.setattr(train, "MIN_TICKERS", 1)
    monkeypatch.setattr(train, "run_validation", lambda *a, **k: _passing_validation(**bad))

    with pytest.raises(SystemExit) as exc:
        train.main(["--db", str(db), "--out", str(out)])

    assert exc.value.code not in (0, None)
    assert _sha(out) == before


def test_passing_run_writes_an_artifact_the_loader_accepts(existing_artifact, monkeypatch):
    db, out, _ = existing_artifact
    monkeypatch.setattr(train, "MIN_ROWS", 1)
    monkeypatch.setattr(train, "MIN_TICKERS", 1)
    monkeypatch.setattr(train, "run_validation", lambda *a, **k: _passing_validation())
    monkeypatch.setattr(vol_mod, "MODEL_PATH", out)

    train.main(["--db", str(db), "--out", str(out)])

    model = vol_mod.load_model()
    assert model is not None
    assert model.universe == frozenset({"AAA", "BBB", "CCC", "DDD"})
    assert model.range_coverage == 0.68 and model.range_k > 0
    assert model.model_version.startswith("har-rv-")
