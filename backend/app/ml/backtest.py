import numpy as np
import pandas as pd
import xgboost as xgb

from app.db.connection import get_connection
from app.db.schema import CREATE_BACKTEST_PREDICTIONS_TABLE
from app.ml.training import (
    assemble_feature_matrix,
    compute_fold_boundaries,
    purge_training_rows,
    train_xgb_model,
)


def run_walk_forward_backtest(full_df: pd.DataFrame, clean_df: pd.DataFrame) -> pd.DataFrame:
    """Run the pooled walk-forward backtest (tasks.md 5.1): for each fold
    boundary from `compute_fold_boundaries`, train on that fold's purged
    training set (design.md Decision 4) and predict on its held-out test
    period, collecting out-of-fold predictions across all folds.

    `full_df` is the unfiltered per-ticker sequence (needed for the purge's
    label-date lookup); `clean_df` is the near_gap=0/target-not-null set
    folds are drawn from. The first boundary's training data has no prior
    fold to validate against for early stopping, so that boundary's own
    test period doubles as the validation set — mirroring
    `train_final_model`'s approach of validating against the held-out
    period nearest the training cutoff.

    Returns a `(ticker, date, fold, predicted, actual)` frame pooling every
    fold's test-period predictions — the out-of-fold set later consumed by
    the hit-rate/error metrics (tasks.md 5.2/5.3) and backtest persistence
    (tasks.md 6.1). `fold` is the boundary's position (0-indexed) among the
    walk-forward test windows, letting error metrics be broken down per
    fold as well as pooled.
    """
    boundaries = compute_fold_boundaries(clean_df)
    test_windows = list(zip(boundaries, boundaries[1:] + [None]))

    results = []
    for fold, (boundary, next_boundary) in enumerate(test_windows):
        train_df = purge_training_rows(full_df, clean_df, boundary)
        train_df = train_df[train_df["date"] < boundary]

        test_df = clean_df[clean_df["date"] >= boundary]
        if next_boundary is not None:
            test_df = test_df[test_df["date"] < next_boundary]

        if len(train_df) == 0 or len(test_df) == 0:
            continue

        model = train_xgb_model(
            assemble_feature_matrix(train_df),
            train_df["target"],
            assemble_feature_matrix(test_df),
            test_df["target"],
        )

        predicted = model.predict(xgb.DMatrix(assemble_feature_matrix(test_df)))

        results.append(
            pd.DataFrame(
                {
                    "ticker": test_df["ticker"].to_numpy(),
                    "date": test_df["date"].to_numpy(),
                    "fold": fold,
                    "predicted": predicted,
                    "actual": test_df["target"].to_numpy(),
                }
            )
        )

    return pd.concat(results, ignore_index=True) if results else pd.DataFrame(
        columns=["ticker", "date", "fold", "predicted", "actual"]
    )


def is_hit(predicted: pd.Series, actual: pd.Series) -> pd.Series:
    """Compute the directional hit/miss outcome for backtested predictions
    (tasks.md 5.2 / design.md Decision 6): a hit is
    `sign(predicted) == sign(actual)`; `actual == 0` is always a miss,
    regardless of `predicted`'s sign, since sign is undefined at exactly
    zero.
    """
    return (actual != 0) & (np.sign(predicted) == np.sign(actual))


def compute_error_metrics(results: pd.DataFrame) -> pd.DataFrame:
    """Compute MAE and RMSE on the log-return target (tasks.md 5.3), per
    fold and pooled, from `run_walk_forward_backtest`'s out-of-fold
    `predicted`/`actual` columns — standard regression error metrics only,
    no simulated P&L/trading-return figure (design.md Non-Goals).

    Returns one row per fold plus a final `fold="pooled"` row computed
    across all out-of-fold predictions, with columns `fold`, `mae`, `rmse`.
    """
    def _metrics(group: pd.DataFrame) -> pd.Series:
        error = group["predicted"] - group["actual"]
        return pd.Series(
            {"mae": error.abs().mean(), "rmse": np.sqrt((error**2).mean())}
        )

    per_fold = results.groupby("fold").apply(_metrics, include_groups=False).reset_index()
    pooled = _metrics(results)
    pooled_row = pd.DataFrame([{"fold": "pooled", **pooled.to_dict()}])
    return pd.concat([per_fold, pooled_row], ignore_index=True)


def persist_backtest_predictions(results: pd.DataFrame) -> None:
    """Persist out-of-fold backtest predictions (tasks.md 6.1) to the
    `backtest_predictions` SQLite table: one row per `(ticker, date)`
    out-of-fold prediction from `run_walk_forward_backtest`, with its
    hit/miss outcome (`is_hit`) precomputed and stored alongside so
    `compute_rolling_hit_rate` (tasks.md 6.3) can read it directly without
    recomputing signs. `(ticker, date)` is the primary key, so re-running
    the backtest replaces prior results for the same ticker/date pairs
    rather than duplicating them (`INSERT OR REPLACE`) — the only rows
    that can shift between runs are ones from the same walk-forward
    windows recomputed over the same underlying data.

    Ordering by `(ticker, date)` here (rather than relying on the caller
    or a later query) is what lets `compute_rolling_hit_rate` retrieve a
    ticker's most recent ~60 predictions via a plain `ORDER BY date DESC
    LIMIT 60` (specs/model-backtest: "retrievable filtered to that ticker,
    ordered by date").
    """
    to_store = results.assign(hit=is_hit(results["predicted"], results["actual"]).astype(int))

    conn = get_connection()
    try:
        conn.execute(CREATE_BACKTEST_PREDICTIONS_TABLE)
        conn.executemany(
            "INSERT OR REPLACE INTO backtest_predictions "
            "(ticker, date, fold, predicted, actual, hit) VALUES (?, ?, ?, ?, ?, ?)",
            to_store[["ticker", "date", "fold", "predicted", "actual", "hit"]].itertuples(
                index=False, name=None
            ),
        )
        conn.commit()
    finally:
        conn.close()


ROLLING_HIT_RATE_WINDOW = 60


def compute_rolling_hit_rate(ticker: str, window: int = ROLLING_HIT_RATE_WINDOW) -> float | None:
    """Compute `ticker`'s hit-rate over its most recent `window` persisted
    backtested predictions (tasks.md 6.3), reading directly from
    `backtest_predictions` — the value Rule 4's confidence score will read
    from in a future milestone (not wired into any API/UI in this change).

    Selects the `window` most recent rows for `ticker` by `date DESC`, then
    returns the fraction with `hit = 1`. Returns `None` if the ticker has no
    persisted predictions yet, so callers can distinguish "no data" from a
    real `0.0` hit-rate rather than mistaking one for the other.
    """
    conn = get_connection()
    try:
        conn.execute(CREATE_BACKTEST_PREDICTIONS_TABLE)
        rows = conn.execute(
            "SELECT hit FROM backtest_predictions WHERE ticker = ? "
            "ORDER BY date DESC LIMIT ?",
            (ticker, window),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    hits = sum(row[0] for row in rows)
    return hits / len(rows)
