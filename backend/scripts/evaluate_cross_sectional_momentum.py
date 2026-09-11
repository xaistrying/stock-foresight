"""
Cross-sectional momentum evaluation (`cross-sectional-momentum-evaluation`
change).

READ-ONLY over `backend/data/app.db`. Measures whether the one directional
effect that survived `docs/DISCUSSION_model_direction.md` Finding 4 —
cross-sectional (relative, daily-demeaned) momentum, +0.025 at 5 sessions
growing to +0.056 at 63, measured on 15 tickers where a top decile was 1.5
stocks — holds at the 208-symbol modelling universe `hose-universe-
ingestion` exists to unlock (a top decile of roughly 21).

Reuses `backend/app/ml/training.py`'s walk-forward protocol
(`compute_fold_boundaries`, its default fold count) unmodified (design.md
Decision 1), so results are comparable to `docs/MODEL_CARD.md`'s existing
figures. `purge_training_rows`/`_label_dates_by_ticker` are hard-coded to
the single production horizon (`TARGET_HORIZON = 5`); rather than adding a
horizon parameter to that shared, production-serving module for a caller
it does not otherwise have, this script carries a local, horizon-
parameterized generalization of the same logic (design.md Decision 1,
tasks.md task group 2). `training.py` itself is not modified.

Writes no row to any table, reads and writes no model artifact — this is
analysis tooling, not a served feature.

Run from the project root:
    python backend/scripts/evaluate_cross_sectional_momentum.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.db.connection import get_connection  # noqa: E402
from app.ml.training import N_FOLDS, compute_fold_boundaries  # noqa: E402
from app.services.ticker_universe import modelling_universe  # noqa: E402

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

# design.md Goals: measure at all four; tasks.md 4.4 requires all four
# reported together, no horizon picked after seeing which scored best.
HORIZONS = (5, 10, 21, 63)

# docs/DISCUSSION_model_direction.md Finding 7's figure, measured on the
# original 15-ticker universe. Reported alongside the recomputed value
# (tasks.md 7.4) — never substituted for it (design.md Decision 4).
PRIOR_15_TICKER_RHO_BAR = 0.411


# --------------------------------------------------------------------- #
# 1. Universe and data loading (tasks.md task group 1)
# --------------------------------------------------------------------- #

def load_universe(conn=None) -> list[str]:
    """The current modelling universe, read live at call time (tasks.md
    1.1/1.3): `ticker_universe` rows with `ingestion_state = 'ok'`,
    `fails_liquidity_filter = 0`, `below_minimum_history = 0`. No
    hard-coded ticker list — a symbol that starts or stops passing those
    filters changes what this returns on the next run, without a code
    change.
    """
    return modelling_universe(conn=conn)


def load_close_history(symbols: list[str], conn=None) -> pd.DataFrame:
    """`(ticker, date, close)` rows for `symbols`, ordered for per-ticker
    groupby/shift use (tasks.md 1.2)."""
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()
    try:
        if not symbols:
            return pd.DataFrame(columns=["ticker", "date", "close"])
        placeholders = ", ".join("?" for _ in symbols)
        return pd.read_sql_query(
            f"SELECT ticker, date, close FROM ohlcv WHERE ticker IN ({placeholders}) "
            "ORDER BY ticker ASC, date ASC",
            conn,
            params=tuple(symbols),
        )
    finally:
        if owns_connection:
            conn.close()


def report_coverage(close_df: pd.DataFrame, universe: list[str], max_horizon: int) -> dict:
    """How many universe symbols have enough stored sessions to produce at
    least one valid signal/forward-target pair at `max_horizon` (tasks.md
    1.2) — distinct from the ingestion-time `MINIMUM_HISTORY_SESSIONS`
    filter, which is calibrated to the production pipeline's warm-up needs,
    not this evaluation's 63-session horizon.

    `2 * max_horizon + 1` sessions is the minimum span for a single
    `close[t-h]`/`close[t+h]` pair to exist anywhere in a ticker's history.
    This is a reporting step, not an additional hard filter: a symbol short
    of this contributes no rows once `compute_signal_frame`'s shift()
    produces all-NaN values for it and those rows are dropped, so nothing
    downstream needs to special-case it separately.
    """
    minimum_sessions = 2 * max_horizon + 1
    counts = close_df.groupby("ticker").size()
    covered = [t for t in universe if counts.get(t, 0) >= minimum_sessions]
    short = [t for t in universe if counts.get(t, 0) < minimum_sessions]
    return {
        "universe_size": len(universe),
        "minimum_sessions_required": minimum_sessions,
        "covered": len(covered),
        "short_of_span": short,
    }


# --------------------------------------------------------------------- #
# 2. Multi-horizon purge (design.md Decision 1, tasks.md task group 2)
# --------------------------------------------------------------------- #

def label_dates_by_ticker(full_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """`training._label_dates_by_ticker`'s logic (backend/app/ml/
    training.py), generalized to take `horizon` as an argument instead of
    the fixed `TARGET_HORIZON` constant (tasks.md 2.1). Maps each
    `(ticker, date)` row to its true label date — the date of the row
    `horizon` positions ahead in that ticker's *full*, unfiltered stored
    sequence. `training.py` is not modified; see design.md Decision 1.
    """
    parts = []
    for ticker, ticker_df in full_df.groupby("ticker", sort=False):
        ordered = ticker_df.sort_values("date")
        parts.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": ordered["date"].values,
                    "label_date": ordered["date"].shift(-horizon).values,
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def purge_rows(full_df: pd.DataFrame, clean_df: pd.DataFrame, boundary: str, horizon: int) -> pd.DataFrame:
    """`training.purge_training_rows`'s logic (tasks.md 2.2), generalized to
    `horizon` via `label_dates_by_ticker` above: drop any candidate row
    from `clean_df` whose true label date — looked up via `full_df`'s
    unfiltered per-ticker sequence — lands at or after `boundary`.
    """
    label_dates = label_dates_by_ticker(full_df, horizon)
    merged = clean_df.merge(label_dates, on=["ticker", "date"], how="left")
    keep = (merged["label_date"].isna() | (merged["label_date"] < boundary)).to_numpy()
    return clean_df[keep]


# --------------------------------------------------------------------- #
# 3. Signal computation (tasks.md task group 3)
# --------------------------------------------------------------------- #

def compute_signal_frame(close_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """`ret_h = ln(close[t]/close[t-h])` (the signal) and the forward target
    `ln(close[t+h]/close[t])`, per symbol per date (tasks.md 3.1/3.2;
    design.md Decision 2 — the same definition
    docs/DISCUSSION_model_direction.md Finding 4's scratchpad measurement
    used). Rows missing either value (not `horizon` sessions of history on
    both sides) are dropped.
    """
    parts = []
    for ticker, ticker_df in close_df.groupby("ticker", sort=False):
        ordered = ticker_df.sort_values("date")
        close = ordered["close"]
        signal = np.log(close / close.shift(horizon))
        forward_target = np.log(close.shift(-horizon) / close)
        parts.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": ordered["date"].values,
                    "signal": signal.values,
                    "forward_target": forward_target.values,
                }
            )
        )
    frame = pd.concat(parts, ignore_index=True)
    return frame.dropna(subset=["signal", "forward_target"]).reset_index(drop=True)


def demean_cross_sectionally(frame: pd.DataFrame) -> pd.DataFrame:
    """Demean `signal` and `forward_target` against the mean of *other
    universe symbols sharing that date* (tasks.md 3.3; design.md Decision
    2) — not each symbol's own historical mean, which is exactly the
    distinction tasks.md 3.4 tests for.
    """
    frame = frame.copy()
    frame["signal_demeaned"] = frame["signal"] - frame.groupby("date")["signal"].transform("mean")
    frame["forward_target_demeaned"] = (
        frame["forward_target"] - frame.groupby("date")["forward_target"].transform("mean")
    )
    return frame


# --------------------------------------------------------------------- #
# 4. Walk-forward evaluation (tasks.md task group 4)
# --------------------------------------------------------------------- #

def _correlation(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 2 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _decile_spread(day: pd.DataFrame) -> float | None:
    """Top-decile minus bottom-decile average forward return, for the
    symbols ranked by signal on a single date (design.md Decision 3,
    tasks.md 4.3). `forward_target_demeaned` is used, but raw and demeaned
    give the identical spread here — both subtract the same per-date mean,
    which cancels in a top-minus-bottom difference. Deterministic rank
    split (`sort_values` + slicing), no `qcut`/randomness (tasks.md 6.2).
    """
    n = len(day)
    if n < 2:
        return None
    decile = max(1, n // 10)
    ordered = day.sort_values("signal_demeaned")
    bottom = ordered.iloc[:decile]["forward_target_demeaned"].mean()
    top = ordered.iloc[-decile:]["forward_target_demeaned"].mean()
    return float(top - bottom)


def evaluate_horizon(close_df: pd.DataFrame, horizon: int) -> dict | None:
    """Full per-horizon walk-forward evaluation (tasks.md task group 4):
    `compute_fold_boundaries` reused unmodified (design.md Decision 1) over
    this horizon's own signal dates, then per-fold and pooled correlation
    and decile spread over each fold's test period.

    The multi-horizon purge (task group 2) is run each fold and its
    resulting purged training-row count is reported for auditability and
    protocol parity with `training.py`'s own walk-forward loop — but this
    evaluation trains nothing, so it does not change what is reported: the
    statistic at risk of leakage in `training.py` is a *fitted model's*
    prediction, whereas a forward_target/signal pair already present in the
    stored data carries no equivalent look-ahead risk. See tasks.md 2.3's
    known-answer check for direct validation that the generalization here
    matches `training.py`'s own purge exactly at horizon 5.
    """
    raw = compute_signal_frame(close_df, horizon)
    frame = demean_cross_sectionally(raw)

    try:
        boundaries = compute_fold_boundaries(frame)
    except ValueError as exc:
        print(f"  horizon {horizon}: skipped — {exc}")
        return None

    test_windows = list(zip(boundaries, boundaries[1:] + [None]))

    folds = []
    test_frames = []
    for fold_index, (boundary, next_boundary) in enumerate(test_windows):
        purged_train = purge_rows(close_df, frame, boundary, horizon)
        purged_train = purged_train[purged_train["date"] < boundary]

        test = frame[frame["date"] >= boundary]
        if next_boundary is not None:
            test = test[test["date"] < next_boundary]
        if test.empty:
            continue
        test_frames.append(test)

        corr = _correlation(test["signal_demeaned"], test["forward_target_demeaned"])
        spreads = [s for s in (_decile_spread(day) for _, day in test.groupby("date")) if s is not None]
        folds.append(
            {
                "fold": fold_index,
                "test_start": boundary,
                "test_end": next_boundary,
                "n_rows": len(test),
                "n_dates": test["date"].nunique(),
                "n_train_rows_after_purge": len(purged_train),
                "correlation": corr,
                "decile_spread": float(np.mean(spreads)) if spreads else float("nan"),
            }
        )

    pooled = pd.concat(test_frames, ignore_index=True) if test_frames else frame.iloc[0:0]
    pooled_corr = _correlation(pooled["signal_demeaned"], pooled["forward_target_demeaned"])
    pooled_spreads = [
        s for s in (_decile_spread(day) for _, day in pooled.groupby("date")) if s is not None
    ]

    valid_corr_signs = {np.sign(f["correlation"]) for f in folds if not np.isnan(f["correlation"])}
    valid_spread_signs = {np.sign(f["decile_spread"]) for f in folds if not np.isnan(f["decile_spread"])}

    return {
        "horizon": horizon,
        "folds": folds,
        "pooled_correlation": pooled_corr,
        "pooled_decile_spread": float(np.mean(pooled_spreads)) if pooled_spreads else float("nan"),
        "correlation_sign_stable": len(valid_corr_signs) <= 1,
        "decile_spread_sign_stable": len(valid_spread_signs) <= 1,
    }


# --------------------------------------------------------------------- #
# 5. Effective breadth (tasks.md task group 5)
# --------------------------------------------------------------------- #

def compute_rho_bar(close_df: pd.DataFrame) -> dict:
    """Mean pairwise cross-sectional correlation of daily log returns across
    the modelling universe (tasks.md 5.1; design.md Decision 4) — the same
    method `baseline_model_diagnostics.finding_7_portfolio_risk` uses for
    the 15-ticker figure this recomputes, run instead over the current
    208-symbol universe.
    """
    wide = close_df.pivot(index="date", columns="ticker", values="close")
    returns = np.log(wide / wide.shift(1)).dropna(how="all")
    # Symbols with too little shared history would corrupt a pairwise
    # correlation computed over that ragged window (same guard as
    # baseline_model_diagnostics.py's Finding 7 measurement).
    returns = returns.dropna(axis=1, thresh=int(len(returns) * 0.5)).dropna()
    if returns.shape[1] < 2:
        return {"symbols_used": returns.shape[1], "rho_bar": float("nan"), "min_pair": float("nan"), "max_pair": float("nan")}
    correlation = returns.corr()
    pairs = correlation.where(~np.eye(len(correlation), dtype=bool)).stack()
    return {
        "symbols_used": returns.shape[1],
        "rho_bar": float(pairs.mean()),
        "min_pair": float(pairs.min()),
        "max_pair": float(pairs.max()),
    }


def effective_breadth(n: int, rho_bar: float) -> float:
    """`n / (1 + (n-1) * rho_bar)` (design.md Decision 4, tasks.md 5.2)."""
    if n < 1 or np.isnan(rho_bar):
        return float("nan")
    return n / (1 + (n - 1) * rho_bar)


# --------------------------------------------------------------------- #
# 6. Report (tasks.md task group 6)
# --------------------------------------------------------------------- #

def main() -> int:
    if not DB_PATH.exists():
        print(f"FAIL: no database at {DB_PATH}")
        return 1

    conn = get_connection()
    try:
        universe = load_universe(conn=conn)
        close_df = load_close_history(universe, conn=conn)
    finally:
        conn.close()

    print("=" * 72)
    print("CROSS-SECTIONAL MOMENTUM EVALUATION")
    print("=" * 72)

    if not universe or close_df.empty:
        print("\nFAIL: modelling universe is empty — nothing to evaluate")
        return 1

    coverage = report_coverage(close_df, universe, max(HORIZONS))
    print(f"\nModelling universe:        {coverage['universe_size']} symbols "
          "(ticker_universe: ingestion_state='ok', fails_liquidity_filter=0, "
          "below_minimum_history=0)")
    print(f"Minimum sessions required: {coverage['minimum_sessions_required']} "
          f"(2 x max horizon {max(HORIZONS)} + 1) for at least one valid "
          f"signal/target pair at the longest horizon")
    print(f"Covered (usable at h={max(HORIZONS)}):  {coverage['covered']}")
    if coverage["short_of_span"]:
        shown = ", ".join(coverage["short_of_span"][:20])
        more = " ..." if len(coverage["short_of_span"]) > 20 else ""
        print(f"Excluded, insufficient span ({len(coverage['short_of_span'])}): {shown}{more}")

    rho = compute_rho_bar(close_df)
    breadth = effective_breadth(rho["symbols_used"], rho["rho_bar"])
    print(f"\nMean pairwise correlation (rho-bar): {rho['rho_bar']:.4f} "
          f"over {rho['symbols_used']} symbols with shared daily-return history "
          f"(min {rho['min_pair']:.2f}, max {rho['max_pair']:.2f})")
    print(f"Effective breadth: {breadth:.1f} of {rho['symbols_used']} nominal symbols "
          f"(n / (1 + (n-1)*rho-bar))")
    print(f"Prior figure (15-ticker universe, docs/DISCUSSION_model_direction.md "
          f"Finding 7): rho-bar {PRIOR_15_TICKER_RHO_BAR}")

    print(f"\nWalk-forward protocol: compute_fold_boundaries (N_FOLDS={N_FOLDS}, "
          "backend/app/ml/training.py) reused unmodified — expanding-window, "
          f"pooled date cutoffs, {N_FOLDS - 1} evaluation folds.\n")

    header = f"{'horizon':>7} {'fold':>6} {'n_dates':>8} {'n_rows':>8} {'correlation':>12} {'decile_spread':>14}"
    print(header)
    print("-" * len(header))

    results = []
    for horizon in HORIZONS:
        result = evaluate_horizon(close_df, horizon)
        if result is None:
            continue
        results.append(result)
        for fold in result["folds"]:
            print(f"{horizon:>7} {fold['fold']:>6} {fold['n_dates']:>8} {fold['n_rows']:>8} "
                  f"{fold['correlation']:>12.4f} {fold['decile_spread']:>14.4f}")
        print(f"{horizon:>7} {'pooled':>6} {'':>8} {'':>8} "
              f"{result['pooled_correlation']:>12.4f} {result['pooled_decile_spread']:>14.4f}")
        print(f"{'':>7} correlation sign-stable across folds: {result['correlation_sign_stable']}   "
              f"decile-spread sign-stable across folds: {result['decile_spread_sign_stable']}\n")

    print("All four horizons reported together above — no horizon selected "
          "after the fact based on which scored best (tasks.md 4.4).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
