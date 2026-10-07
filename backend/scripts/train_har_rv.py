"""Train, validate out of time, and serialise the HAR-RV volatility model and its band multiplier.

Run once from the repo root (retrain after deploying calibrate-volatility-range):
    python backend/scripts/train_har_rv.py [--db PATH] [--out PATH]

Pools the modelling universe (`modelling_universe()`), fits ln(std of the next 5 daily log
returns) on rv5/rv20/rv60 by OLS, and fits `range_k`, the empirical 0.68-quantile of
z = |ln(close[t+5]/close[t])| / (√5 · sigma_daily), so that range_k · √5 · sigma contains the real
5-session move about 2 times in 3. Validation is an expanding walk-forward by calendar year: for
each test year the HAR and `range_k` are refit on windows whose OUTCOME date precedes it (the
5-session purge) and coverage is measured in that year. The artifact reports those out-of-time
figures. The script exits non-zero and leaves any existing artifact untouched if a gate fails
(design.md Decisions 3-5, 11). All gate thresholds are new and provisional, covered by no domain rule.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Make backend/app importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.vnstock_guard  # noqa: F401, E402 — must install before any vnstock import

from app.db.connection import DB_PATH, open_readonly  # noqa: E402
from app.ml.volatility import (  # noqa: E402
    FEATURE_NAMES,
    MODEL_PATH,
    SCHEMA_VERSION,
    build_window_frame,
    fit_har_ols,
    fit_range_k,
    log_realised,
    scaled_band,
    sigma_pct,
)
from app.services.ticker_universe import modelling_universe  # noqa: E402

SQRT5 = math.sqrt(5)
RANGE_COVERAGE = 0.68  # nominal coverage, "about 2 in 3" (Decision 2)
COVERAGE_TOLERANCE = 0.05  # pooled out-of-time coverage vs nominal
YEAR_TOLERANCE = 0.10  # any single test year vs nominal (single years swing about 7 points)
MIN_ROWS = 100_000
MIN_TICKERS = 100
MIN_TRAIN_ROWS = 40_000  # a fold needs this many purged prior windows (first test year 2020 on real data)
BOOTSTRAP_RESAMPLES = 1000
SCHEME = "expanding walk-forward by calendar year, outcome-date (5-session) purge"
UNIVERSE_CRITERIA = (
    "modelling_universe(): ingestion_state ok, not fails_liquidity_filter, not below_minimum_history, "
    "delisted symbols included"
)
TARGET = "ln(std of next 5 daily log returns)"


def load_frame(conn, symbols: list[str]) -> pd.DataFrame:
    """Windows (see build_window_frame) for every symbol, with a `ticker` column."""
    placeholders = ", ".join("?" for _ in symbols)
    closes = pd.read_sql_query(
        f"SELECT ticker, date, close FROM ohlcv WHERE close > 0 AND ticker IN ({placeholders}) "
        "ORDER BY ticker, date",
        conn,
        params=tuple(symbols),
    )
    parts = [
        build_window_frame(group["date"], group["close"]).assign(ticker=ticker)
        for ticker, group in closes.groupby("ticker", sort=False)
    ]
    return prepare(pd.concat(parts, ignore_index=True)) if parts else pd.DataFrame()


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.assign(abs_r5_pct=frame["r5"].abs() * 100.0)


def split_fold(frame: pd.DataFrame, test_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(fit windows, test windows). Fit keeps only windows whose t+5 precedes the test year."""
    fit = frame[frame["outcome_date"] < f"{test_year}-01-01"]
    test = frame[frame["date"].str[:4] == str(test_year)]
    return fit, test


def _sigma(frame: pd.DataFrame, intercept: float, coef: np.ndarray) -> np.ndarray:
    return sigma_pct(frame[list(FEATURE_NAMES)].to_numpy(), intercept, coef)


def fit_fold(fit: pd.DataFrame, coverage: float) -> tuple[float, np.ndarray, float]:
    """(intercept, coef, range_k) fitted on `fit` alone."""
    intercept, coef = fit_har_ols(fit)
    z = fit["abs_r5_pct"].to_numpy() / scaled_band(_sigma(fit, intercept, coef), 1.0)
    return intercept, coef, fit_range_k(z, coverage)


def _month_block_interval(oot: pd.DataFrame, rng: np.random.Generator) -> list[float]:
    """95% interval of pooled coverage, resampling calendar months (windows move together by date)."""
    by_month = oot.groupby(oot["date"].str[:7])["hit"].agg(["sum", "count"])
    hits, counts = by_month["sum"].to_numpy(), by_month["count"].to_numpy()
    picks = rng.integers(0, len(by_month), size=(BOOTSTRAP_RESAMPLES, len(by_month)))
    resampled = hits[picks].sum(axis=1) / counts[picks].sum(axis=1)
    return [float(np.percentile(resampled, 2.5)), float(np.percentile(resampled, 97.5))]


def run_validation(
    frame: pd.DataFrame, coverage: float = RANGE_COVERAGE, min_train_rows: int = MIN_TRAIN_ROWS
) -> dict:
    folds, pieces = [], []
    for year in sorted(int(y) for y in frame["date"].str[:4].unique()):
        fit, test = split_fold(frame, year)
        if len(fit) < min_train_rows or test.empty:
            continue
        intercept, coef, range_k = fit_fold(fit, coverage)
        sigma = _sigma(test, intercept, coef)
        hit = test["abs_r5_pct"].to_numpy() <= scaled_band(sigma, range_k)
        predicted = np.log(np.divide(sigma, 100.0))  # not `sigma / 100.0`: numpy elision can overwrite sigma
        actual, baseline = log_realised(test).to_numpy(), np.log(test["rv20"].to_numpy())
        folds.append({
            "test_year": year, "n": int(len(test)), "coverage": float(hit.mean()), "k": range_k,
            "corr": float(np.corrcoef(predicted, actual)[0, 1]),
            "baseline_corr": float(np.corrcoef(baseline, actual)[0, 1]),
        })
        pieces.append(
            pd.DataFrame(
                {
                    "date": test["date"].to_numpy(), "sigma": sigma, "hit": hit,
                }
            )
        )
    validation: dict = {"scheme": SCHEME, "folds": folds}
    if not folds:
        return validation | {
            "pooled_coverage": None, "pooled_coverage_ci": None, "coverage_by_sigma_quintile": None,
            "oot_corr": None, "baseline_log_rv20_corr": None,
        }
    oot = pd.concat(pieces, ignore_index=True)
    quintile = pd.qcut(oot["sigma"], 5, labels=False, duplicates="drop")
    return validation | {
        "pooled_coverage": float(oot["hit"].mean()),
        "pooled_coverage_ci": _month_block_interval(oot, np.random.default_rng(0)),
        "coverage_by_sigma_quintile": [float(v) for v in oot.groupby(quintile)["hit"].mean()],
        # Mean of the per-fold correlations: each fold has its own refit intercept, so a pooled
        # correlation would mostly measure fold-to-fold level shifts the fixed baseline lacks.
        "oot_corr": float(np.mean([f["corr"] for f in folds])),
        "baseline_log_rv20_corr": float(np.mean([f["baseline_corr"] for f in folds])),
    }


def failed_gates(
    validation: dict, n_rows: int, n_tickers: int, coverage: float = RANGE_COVERAGE
) -> list[str]:
    """Every gate that fails; an empty list means the artifact may be written."""
    failures = []
    if n_rows < MIN_ROWS:
        failures.append(f"data gate: {n_rows:,} pooled rows, need at least {MIN_ROWS:,}")
    if n_tickers < MIN_TICKERS:
        failures.append(f"data gate: {n_tickers} tickers, need at least {MIN_TICKERS}")
    if not validation["folds"]:
        return failures + ["no walk-forward fold had enough prior windows"]
    measured = (validation["pooled_coverage"], validation["oot_corr"], validation["baseline_log_rv20_corr"])
    if not all(np.isfinite(measured)):  # NaN compares False against every threshold below
        return failures + [f"validation gate: a pooled figure is not finite {measured}"]
    if abs(validation["pooled_coverage"] - coverage) > COVERAGE_TOLERANCE:
        failures.append(
            f"coverage gate: pooled out-of-time coverage {validation['pooled_coverage']:.3f} "
            f"is not within {COVERAGE_TOLERANCE} of {coverage}"
        )
    failures += [
        f"coverage gate: test year {fold['test_year']} coverage {fold['coverage']:.3f} "
        f"is not within {YEAR_TOLERANCE} of {coverage}"
        for fold in validation["folds"]
        if abs(fold["coverage"] - coverage) > YEAR_TOLERANCE
    ]
    if validation["oot_corr"] < validation["baseline_log_rv20_corr"]:
        failures.append(
            f"baseline gate: out-of-time correlation {validation['oot_corr']:.4f} is below the "
            f"log(rv20) baseline {validation['baseline_log_rv20_corr']:.4f}"
        )
    return failures


def model_version(trained_at: str, intercept: float, coef: np.ndarray, range_k: float) -> str:
    """har-rv-<trained date>-<8 hex of SHA-256 of the coefficients and range_k>."""
    payload = json.dumps(
        {"intercept": float(intercept), "coef": [float(c) for c in coef], "range_k": float(range_k)},
        sort_keys=True,
    )
    return f"har-rv-{trained_at[:10]}-{hashlib.sha256(payload.encode()).hexdigest()[:8]}"


def build_artifact(
    frame: pd.DataFrame, validation: dict, symbols: list[str], trained_at: str, coverage: float
) -> dict:
    """Final fit on every window (all have an outcome date up to the last stored session)."""
    intercept, coef, range_k = fit_fold(frame, coverage)
    return {
        "schema_version": SCHEMA_VERSION,
        "model_version": model_version(trained_at, intercept, coef, range_k),
        "trained_at": trained_at,
        "data_through": str(frame["outcome_date"].max()),
        "features": list(FEATURE_NAMES),
        "intercept": intercept,
        "coef": {name: float(c) for name, c in zip(FEATURE_NAMES, coef)},
        "target": TARGET,
        "range_k": range_k,
        "range_coverage": coverage,
        "universe": {"criteria": UNIVERSE_CRITERIA, "n_tickers": len(symbols), "symbols": sorted(symbols)},
        "n_rows": int(len(frame)),
        "validation": validation,
    }


def write_artifact(path: Path, artifact: dict) -> None:
    """Temp file in the same directory, fsync, os.replace: a reader never sees a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--out", type=Path, default=MODEL_PATH)
    args = parser.parse_args(argv)

    conn = open_readonly(args.db)
    try:
        symbols = modelling_universe(conn=conn)
        frame = load_frame(conn, symbols) if symbols else pd.DataFrame()
    finally:
        conn.close()
    if frame.empty:
        sys.exit("ERROR: no windows in the modelling universe. Aborting.")
    n_tickers = int(frame["ticker"].nunique())
    print(f"Modelling universe: {len(symbols)} symbols; {len(frame):,} windows from {n_tickers} tickers.")

    validation = run_validation(frame)
    print(json.dumps(validation, indent=2))
    failures = failed_gates(validation, len(frame), n_tickers)
    if failures:
        print("REFUSING to write the artifact:\n  " + "\n  ".join(failures), file=sys.stderr)
        sys.exit(1)

    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    artifact = build_artifact(frame, validation, symbols, trained_at, RANGE_COVERAGE)
    write_artifact(args.out, artifact)
    print(f"Wrote {args.out}: {artifact['model_version']}, range_k {artifact['range_k']:.3f}, "
          f"data through {artifact['data_through']}.")


if __name__ == "__main__":
    main()
