"""
Reproduce the cross-ticker risk measurement behind
`docs/DISCUSSION_model_direction.md` (Finding 7): return correlation across
tickers and the equal-weight portfolio volatility that independence would
understate. It reads only `ohlcv`, so it needs no model and supports the
still-open "portfolio risk" option.

Findings 1 and 2 (the direction model's flat output and booster importance)
read the retired model and `backtest_predictions`; they are no longer
reproducible here. Their numbers stay in `docs/DISCUSSION_model_direction.md`
and the script's git history (retire-direction-model).

WHAT THIS DELIBERATELY DOES NOT COVER
- Findings 3-5 (volatility targets, interval output) are *experiments
  proposing a model change*, not baseline measurements; the volatility range
  now lives in `backend/scripts/evaluate_vol_range.py`.
- Finding 8's price-limit scan is superseded: it is now the quality gate
  (`app/services/ohlcv_quality_gate.py`), permanently reproducible via
  `backend/scripts/verify_quality_gate.py`.

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
from app.ml.training import TRAINING_TICKERS  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

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
        help="comma-separated tickers (default: TRAINING_TICKERS)",
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
        finding_7_portfolio_risk(conn, tickers)
    finally:
        conn.close()

    print("Findings 1-5 are not reproduced here: see "
          "docs/DISCUSSION_model_direction.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
