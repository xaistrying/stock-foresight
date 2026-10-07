"""Read-only evaluation of the HAR-RV volatility band's coverage.

Reproduces the 2026-10-06 post-pivot review's numbers (docs/DISCUSSION_post_pivot_review.md,
Finding 1) and checks the calibrated band (openspec change calibrate-volatility-range).

Coverage = share of windows with |ln(close[t+5]/close[t])| × 100 <= multiplier × sigma_daily_pct(t),
at ×1 (the band as first shipped), ×√5 and range_k × √5. Opens the database with mode=ro and writes
no table and no model file.

Run from the repo root:
    python backend/scripts/evaluate_vol_range.py [--db PATH] [--model PATH.json] [--json PATH]
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.connection import open_readonly  # noqa: E402
from app.ml.volatility import (  # noqa: E402
    FEATURE_NAMES,
    SIGMA_DAILY_MAX_PCT,
    _build_har_features,
    build_window_frame,
    fit_har_ols,
    fit_range_k,
    log_realised,
    parse_artifact,
    scaled_band,
    sigma_pct,
)
from app.services.ticker_universe import modelling_universe  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = BACKEND_DIR / "data" / "app.db"
DEFAULT_MODEL = BACKEND_DIR / "data" / "models" / "har_rv_model.json"

SQRT5 = math.sqrt(5)
RANGE_COVERAGE = 0.68
TIME_SPLIT_TRAIN_END = "2024-01-01"  # train on windows whose outcome date precedes this
TIME_SPLIT_TEST_START = "2024-02-01"
LATEST_ROWS = 65  # what the old /prediction path read per ticker

# The review's headline figures, printed beside the reproduced ones (design.md, Context).
REVIEW = {
    "all_dates": "32.3% / 61.0% on 385,909 windows",
    "non_overlapping": "32.2%",
    "last_12_months": "33.8%",
    "time_split": "34.8% / 64.7%",
    "outside_universe": "53.7% / 74.7%",
    "correlation": "0.431 vs baseline 0.424",
    "latest_sigma": "28 tickers above 25%",
}


@dataclass(frozen=True)
class Coefficients:
    intercept: float
    coef: np.ndarray
    range_k: float


def load_coefficients(path: Path) -> Coefficients:
    model = parse_artifact(json.loads(Path(path).read_text(encoding="utf-8")))
    return Coefficients(model.intercept, np.array(model.coef), model.range_k)


def coverage(windows: pd.DataFrame, multiplier: float) -> float:
    if windows.empty:
        return math.nan
    return float((windows["abs_r5_pct"] <= multiplier * windows["sigma"]).mean())


def coverage_row(windows: pd.DataFrame, range_k: float) -> dict:
    return {
        "n": int(len(windows)),
        "x1": coverage(windows, 1.0),
        "xsqrt5": coverage(windows, SQRT5),
        "range_k": coverage(windows, range_k * SQRT5),
    }


def load_windows(conn: sqlite3.Connection, model: Coefficients) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(windows for every loaded ticker, closes). `sigma` uses `model`; r5 is Rule 1's outcome."""
    closes = pd.read_sql_query(
        "SELECT ticker, date, close FROM ohlcv WHERE close > 0 ORDER BY ticker, date", conn
    )
    parts = []
    for ticker, group in closes.groupby("ticker", sort=False):
        frame = build_window_frame(group["date"], group["close"])
        parts.append(frame.assign(ticker=ticker))
    windows = pd.concat(parts, ignore_index=True)
    windows["sigma"] = sigma_pct(windows[list(FEATURE_NAMES)].to_numpy(), model.intercept, model.coef)
    windows["abs_r5_pct"] = windows["r5"].abs() * 100.0
    windows["year"] = windows["date"].str[:4]
    return windows, closes


def _corr(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    return float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else math.nan


def time_split(universe_windows: pd.DataFrame, shipped: Coefficients) -> dict:
    """Refit on windows whose outcome precedes 2024, test on windows from 2024-02."""
    train = universe_windows[universe_windows["outcome_date"] < TIME_SPLIT_TRAIN_END]
    test = universe_windows[universe_windows["date"] >= TIME_SPLIT_TEST_START]
    out = {
        "train_end": TIME_SPLIT_TRAIN_END, "test_start": TIME_SPLIT_TEST_START,
        "n_train": int(len(train)), "n_test": int(len(test)),
    }
    if len(train) < 100 or len(test) < 100:
        return out
    intercept, coef = fit_har_ols(train)
    train_sigma = sigma_pct(train[list(FEATURE_NAMES)].to_numpy(), intercept, coef)
    k_train = fit_range_k(train["abs_r5_pct"].to_numpy() / scaled_band(train_sigma, 1.0), RANGE_COVERAGE)
    test = test.assign(sigma=sigma_pct(test[list(FEATURE_NAMES)].to_numpy(), intercept, coef))
    realised = log_realised(test)
    out |= {
        "fitted_k": k_train,
        **coverage_row(test, k_train),
        "correlation": {
            "refit": _corr(np.log(test["sigma"] / 100.0), realised),
            "baseline_log_rv20": _corr(np.log(test["rv20"]), realised),
        },
    }
    return out


def by_quintile(windows: pd.DataFrame, range_k: float) -> list[dict]:
    bucket = pd.qcut(windows["sigma"], 5, labels=False, duplicates="drop")
    return [
        {"quintile": int(q) + 1, "sigma_lo": float(g["sigma"].min()), "sigma_hi": float(g["sigma"].max()),
         **coverage_row(g, range_k)}
        for q, g in windows.groupby(bucket)
    ]


def date_clustered(windows: pd.DataFrame, range_k: float) -> dict:
    """Mean and sd across dates of the per-date coverage: windows on one date move together."""
    out = {}
    for name, multiplier in (("x1", 1.0), ("xsqrt5", SQRT5), ("range_k", range_k * SQRT5)):
        hit = (windows["abs_r5_pct"] <= multiplier * windows["sigma"]).groupby(windows["date"]).mean()
        out[name] = {"mean": float(hit.mean()), "sd": float(hit.std()), "n_dates": int(len(hit))}
    return out


def latest_sigma_counts(closes: pd.DataFrame, model: Coefficients) -> dict:
    """Latest sigma per loaded ticker from its last 65 closes, as the old /prediction path read it."""
    latest = []
    for _, group in closes.groupby("ticker", sort=False):
        features = _build_har_features(group["close"].tail(LATEST_ROWS)).dropna().tail(1)
        if not features.empty:
            latest.append(float(sigma_pct(features.to_numpy(), model.intercept, model.coef)[0]))
    values = np.array(latest)
    return {"n_tickers": len(values), "above_25": int((values > 25).sum()),
            "above_15": int((values > 15).sum()), "max": float(values.max()) if len(values) else math.nan}


def run(db_path: Path, model_path: Path) -> dict:
    model = load_coefficients(model_path)
    conn = open_readonly(db_path)
    try:
        windows, closes = load_windows(conn, model)
        universe = set(modelling_universe(conn=conn))
        status = dict(conn.execute("SELECT symbol, listing_status FROM ticker_universe").fetchall())
    finally:
        conn.close()

    inside = windows[windows["ticker"].isin(universe)]
    outside = windows[~windows["ticker"].isin(universe)]
    range_k = model.range_k

    realised = log_realised(inside)
    last_year = inside[inside["date"] > (pd.Timestamp(inside["date"].max()) - pd.DateOffset(years=1)).strftime("%Y-%m-%d")]
    split = time_split(inside, model)
    shipped_test = inside[inside["date"] >= TIME_SPLIT_TEST_START]
    if split.get("correlation"):
        split["correlation"]["shipped"] = _corr(
            np.log(shipped_test["sigma"] / 100.0), log_realised(shipped_test)
        )
    listing = windows["ticker"].map(status).fillna("unknown")
    over_max = (windows["sigma"] > SIGMA_DAILY_MAX_PCT).groupby(listing).mean()

    return {
        "n_windows": int(len(inside)),
        "range_k": range_k,
        "range_k_source": "model",
        "all_dates": coverage_row(inside, range_k),
        "non_overlapping": coverage_row(inside[inside["pos"] % 5 == 0], range_k),
        "last_12_months": coverage_row(last_year, range_k),
        "time_split": split,
        "inside_universe": coverage_row(inside, range_k),
        "outside_universe": coverage_row(outside, range_k),
        "by_year": {y: coverage_row(g, range_k) for y, g in inside.groupby("year")},
        "by_sigma_quintile": by_quintile(inside, range_k),
        "date_clustered": date_clustered(inside, range_k),
        "realised_to_predicted_sigma": float(inside["realised_std"].mean() * 100.0 / inside["sigma"].mean()),
        "correlation": {
            "model": _corr(np.log(inside["sigma"] / 100.0), realised),
            "baseline_log_rv20": _corr(np.log(inside["rv20"]), realised),
        },
        "share_sigma_above_max": {str(k): float(v) for k, v in over_max.items()},
        "latest_sigma": latest_sigma_counts(closes, model),
    }


def _pct(value: float) -> str:
    return "n/a" if value is None or math.isnan(value) else f"{value * 100:5.1f}%"


def _row(name: str, row: dict, review: str = "") -> str:
    line = (f"{name:<22} n={row['n']:>9,}  x1 {_pct(row['x1'])}  x√5 {_pct(row['xsqrt5'])}"
            f"  k·√5 {_pct(row['range_k'])}")
    return f"{line}   (review: {review})" if review else line


def format_report(report: dict) -> str:
    split = report["time_split"]
    lines = [f"range_k = {report['range_k']:.3f} ({report['range_k_source']})", ""]
    for key in ("all_dates", "non_overlapping", "last_12_months", "inside_universe", "outside_universe"):
        lines.append(_row(key, report[key], REVIEW.get(key, "")))
    if "x1" in split:
        lines.append(_row("time_split (test)", {"n": split["n_test"], **split}, REVIEW["time_split"]))
        lines.append(f"{'':<22} refit k {split['fitted_k']:.3f}; corr {split['correlation']}")
    else:
        lines.append(f"time_split: too few windows (train {split['n_train']}, test {split['n_test']})")
    lines += ["", "By year:"] + [_row(f"  {y}", r) for y, r in report["by_year"].items()]
    lines += ["", "By sigma quintile:"] + [
        _row(f"  Q{r['quintile']} σ {r['sigma_lo']:.2f}-{r['sigma_hi']:.2f}", r) for r in report["by_sigma_quintile"]
    ]
    dc = report["date_clustered"]
    lines += ["", "Date-clustered coverage (mean, sd across dates): "
              + "; ".join(f"{k} {_pct(v['mean'])} / {v['sd']:.3f}" for k, v in dc.items()),
              f"Realised / predicted mean sigma: {report['realised_to_predicted_sigma']:.3f}",
              f"Out-of-sample-style correlation (in sample here): {report['correlation']}  (review: {REVIEW['correlation']})",
              f"Share of windows with sigma > {SIGMA_DAILY_MAX_PCT}%: {report['share_sigma_above_max']}",
              f"Latest sigma: {report['latest_sigma']}  (review: {REVIEW['latest_sigma']})"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--json", type=Path, dest="json_path")
    args = parser.parse_args(argv)

    report = run(args.db, args.model)
    print(format_report(report))
    if args.json_path:
        args.json_path.write_text(json.dumps(report, indent=2, default=float))


if __name__ == "__main__":
    main()
