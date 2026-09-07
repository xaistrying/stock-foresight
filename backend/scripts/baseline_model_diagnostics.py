"""
Reproduce the pre-expansion baseline measurements behind
`docs/DISCUSSION_model_direction.md` (hose-universe-ingestion, task 9.4).

That document's own "Reproducing these numbers" section records that every
figure in it was produced ad hoc in a session scratchpad and **is not
preserved anywhere in the repo**. This script is that preservation: the
baseline is now re-measurable against the database as it changes, rather
than remembered from a doc that cannot be re-run.

WHAT THIS COVERS
- Finding 1: the model is flat, not weak — `sd(actual)`, `sd(predicted)`,
  `corr(predicted, actual)` over `backtest_predictions`, and the per-fold
  base rate / predicted-up rate / hit-rate table that explains a sub-50%
  hit rate as a sign artefact of a near-constant output.
- Finding 2: feature importance by gain from the persisted booster, which is
  where `obv`'s 96 splits (a calendar-time proxy) came from.
- Finding 7: cross-ticker return correlation and the equal-weight portfolio
  volatility understatement, which is what makes portfolio risk a
  computation rather than a prediction.

WHAT THIS DELIBERATELY DOES NOT COVER
- Findings 3-5 (volatility targets, interval output) are *experiments
  proposing a model change*, not baseline measurements. Reproducing them
  means implementing the pivot, which `hose-universe-ingestion` lists as an
  explicit non-goal. They stay in the discussion doc until a change adopts
  them.
- Finding 8's price-limit scan is superseded: it is now the quality gate
  (`app/services/ohlcv_quality_gate.py`), permanently reproducible via
  `backend/scripts/verify_quality_gate.py`, which also asserts the
  known-answer counts rather than just printing them.

READ-ONLY. Touches no table, fetches nothing, and is safe to run at any
time — including while an ingest is in flight.

Run from the project root:
    python backend/scripts/baseline_model_diagnostics.py [--tickers TCB,VIB]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.ml.training import MODEL_PATH, TRAINING_TICKERS  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

# The doc's Finding 1 excludes GAS, which entered `backtest_predictions`
# later through the per-ticker backtest button and so covers different folds
# than the pooled M3 run. Kept as the default so the printed numbers are
# comparable with the ones written down.
FINDING_1_EXCLUDED = ("GAS",)

# Finding 7's out-of-sample test used a trailing 120 sessions to predict the
# next 5-session portfolio volatility.
COVARIANCE_WINDOW = 120
HORIZON = 5

# Finding 7's published figures are over "the 15 loaded tickers" — the set
# loaded at the time the doc was written, which is no longer what `tickers`
# contains now that the batch ingest has run. Pinned here so the doc's
# numbers stay reproducible rather than drifting with the database:
# `--doc-baseline` measures exactly these.
DISCUSSION_DOC_TICKERS = (
    "ACB", "BID", "CTG", "FPT", "GAS", "HPG", "MSN", "MWG", "PNJ", "SAB",
    "TCB", "VHM", "VIB", "VND", "VNM",
)


def _corr(x: pd.Series, y: pd.Series) -> float:
    """Pearson correlation, matching the doc's `AVG(xy)-AVG(x)AVG(y)` over
    `sd` formulation."""
    if len(x) < 2:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def finding_1_dispersion(conn: sqlite3.Connection, tickers: list[str]) -> None:
    """Predictions dispersed far too narrowly, and why that flips hit-rate."""
    kept = [t for t in tickers if t not in FINDING_1_EXCLUDED]
    placeholders = ", ".join("?" for _ in kept)
    df = pd.read_sql_query(
        f"SELECT ticker, date, fold, predicted, actual, hit "
        f"FROM backtest_predictions WHERE ticker IN ({placeholders})",
        conn,
        params=tuple(kept),
    )
    print("== Finding 1: the model is flat, not weak ==")
    if df.empty:
        print("  no backtest_predictions rows for these tickers — run the "
              "backtest first")
        return

    print(f"  rows {len(df)} across {df['ticker'].nunique()} ticker(s), "
          f"excluding {', '.join(FINDING_1_EXCLUDED)}")
    print(f"  sd(actual)               {df['actual'].std():.4f}")
    print(f"  sd(predicted)            {df['predicted'].std():.4f}")
    print(f"  dispersion ratio         "
          f"{df['actual'].std() / df['predicted'].std():.1f}x too narrow")
    corr = _corr(df["predicted"], df["actual"])
    print(f"  corr(predicted, actual)  {corr:.4f}   (R^2 ~ {corr ** 2:.4f})")

    print("\n  per fold:")
    print(f"    {'fold':>4} {'base up':>9} {'pred up':>9} {'hit-rate':>9} "
          f"{'mean pred':>11} {'corr':>8}")
    for fold, group in df.groupby("fold"):
        print(
            f"    {fold:>4} {(group['actual'] > 0).mean():>8.1%} "
            f"{(group['predicted'] > 0).mean():>8.1%} "
            f"{group['hit'].mean():>8.1%} "
            f"{group['predicted'].mean():>11.4f} "
            f"{_corr(group['predicted'], group['actual']):>8.3f}"
        )
    print("\n  A nearly-flat output means the *sign* of every prediction is "
          "set by\n  where that constant sits, not by the input — which is "
          "what produces a\n  sub-50% hit rate without the model being "
          "wrong about anything.\n")


def finding_2_importance() -> None:
    """Which features the booster actually used, by gain."""
    print("== Finding 2: feature importance by gain ==")
    if not MODEL_PATH.exists():
        print(f"  no model at {MODEL_PATH} — train first\n")
        return
    import xgboost as xgb

    booster = xgb.Booster()
    booster.load_model(MODEL_PATH)
    gain = booster.get_score(importance_type="gain")
    splits = booster.get_score(importance_type="weight")
    if not gain:
        print("  booster reports no splits at all\n")
        return
    total = sum(gain.values())
    print(f"    {'feature':<16} {'gain':>10} {'share':>7} {'splits':>7}")
    for feature, value in sorted(gain.items(), key=lambda kv: -kv[1]):
        print(f"    {feature:<16} {value:>10.2f} {value / total:>6.1%} "
              f"{int(splits.get(feature, 0)):>7}")
    print("\n  `obv` carrying many splits is the finding here: it is a "
          "cumulative sum,\n  so it encodes calendar time, and a tree can "
          "use it to memorise *when*\n  rather than learn *what* "
          "(design Decision 11's segmentation makes it\n  discontinuous at a "
          "hard flag, which does not make it a better feature).\n")


def finding_7_portfolio_risk(conn: sqlite3.Connection, tickers: list[str]) -> None:
    """Correlation across tickers, and the diversification that isn't."""
    placeholders = ", ".join("?" for _ in tickers)
    prices = pd.read_sql_query(
        f"SELECT ticker, date, close FROM ohlcv WHERE ticker IN ({placeholders}) "
        f"ORDER BY date",
        conn,
        params=tuple(tickers),
    )
    print("== Finding 7: portfolio risk is computed, not predicted ==")
    if prices.empty:
        print("  no ohlcv rows for these tickers\n")
        return

    wide = prices.pivot(index="date", columns="ticker", values="close")
    returns = np.log(wide / wide.shift(1)).dropna(how="all")
    # Only tickers with a usable common history — a symbol delisted years ago
    # shares no sessions with a current one, and pairwise-complete correlation
    # across disjoint windows would be meaningless.
    returns = returns.dropna(axis=1, thresh=int(len(returns) * 0.5)).dropna()
    if returns.shape[1] < 2:
        print("  fewer than two tickers share enough history\n")
        return

    correlation = returns.corr()
    pairs = correlation.where(~np.eye(len(correlation), dtype=bool)).stack()
    print(f"  {returns.shape[1]} tickers over {len(returns)} shared sessions")
    print(f"  mean pairwise correlation  {pairs.mean():.3f} "
          f"(min {pairs.min():.2f}, max {pairs.max():.2f})")

    equal_weight = returns.mean(axis=1)
    actual = equal_weight.rolling(HORIZON).sum().std()
    independent = np.sqrt(
        sum(returns[col].rolling(HORIZON).sum().std() ** 2 for col in returns)
    ) / returns.shape[1]
    print(f"  {HORIZON}-session equal-weight volatility  {actual:.2%}")
    print(f"  if the same tickers were uncorrelated     {independent:.2%}")
    print(f"  understated by                            "
          f"{actual / independent - 1:.0%}")
    effective = len(correlation) / (1 + (len(correlation) - 1) * pairs.mean())
    print(f"  approximate independent bets              {effective:.1f} "
          f"of {returns.shape[1]}")

    # The out-of-sample caveat: does trailing covariance predict realized
    # portfolio volatility at all?
    realized, forecast = [], []
    summed = equal_weight.rolling(HORIZON).sum()
    for index in range(COVARIANCE_WINDOW, len(returns) - HORIZON):
        window = returns.iloc[index - COVARIANCE_WINDOW : index]
        weights = np.full(returns.shape[1], 1.0 / returns.shape[1])
        variance = float(weights @ window.cov().to_numpy() @ weights)
        forecast.append(np.sqrt(max(variance, 0.0) * HORIZON))
        realized.append(abs(summed.iloc[index + HORIZON]))
    if len(forecast) > 2:
        forecast_s, realized_s = pd.Series(forecast), pd.Series(realized)
        print(f"  trailing-{COVARIANCE_WINDOW} covariance vs realized: "
              f"corr {_corr(forecast_s, realized_s):.3f}, "
              f"mean bias {(forecast_s.mean() / realized_s.mean() - 1):+.0%}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tickers",
        help="comma-separated tickers (default: TRAINING_TICKERS, the set "
             "Findings 1-2 were measured over)",
    )
    parser.add_argument(
        "--doc-baseline", action="store_true",
        help="measure the 15 tickers the discussion doc's Finding 7 figures "
             "were taken over, rather than the 9 training tickers",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"FAIL: no database at {DB_PATH}")
        return 1

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.doc_baseline:
        tickers = list(DISCUSSION_DOC_TICKERS)
    else:
        tickers = list(TRAINING_TICKERS)

    print(f"Baseline diagnostics over {len(tickers)} ticker(s): "
          f"{', '.join(tickers)}")
    print(f"Database: {DB_PATH}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        finding_1_dispersion(conn, tickers)
        finding_2_importance()
        finding_7_portfolio_risk(conn, tickers)
    finally:
        conn.close()

    print("Findings 3-5 (volatility targets, interval output) are not "
          "reproduced here:\nthey propose a model change this repo has not "
          "made. See\ndocs/DISCUSSION_model_direction.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
